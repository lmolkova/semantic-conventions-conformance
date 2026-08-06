# opentelemetry-conformance

Runs scenario programs, collects what they emit through
[Weaver live-check](https://github.com/open-telemetry/weaver), and checks it
against expectations you declare in YAML. It carries no semantic conventions
of its own — you tell it which registry and policies to validate against.

Not on PyPI yet: it needs `opentelemetry.test.weaver_live_check`, which hasn't
been released. Install it from a checkout — `pip install -e tools/runner[python]` —
with the OpenTelemetry stack pinned from git.

For the GenAI conventions, [`genai-runner`](../genai-runner) wraps
this with the registry, policies and mock LLM server already wired up.

## A conformance directory

A scenario is a plain program — exercise the library, end — sitting next to a
`conformance.yaml` that says how to run each one and what it must produce. No
providers, no test framework, and usually nothing about telemetry at all: it
runs in its own process under whatever agent the `run` command names.

```python
# inference.py
from openai import OpenAI

OpenAI().chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say this is a test"}],
)
```

That the scenario says nothing about instrumentation is what lets the same
program be run against several implementations of it.

**Write one scenario per thing you want to know about** — one operation, one
code path. A single scenario that exercises everything can only tell you that
*something* is wrong; ten small ones tell you which one, and each stays
readable as a description of what the library does.

## Running the scenarios

Every scenario names the command that runs it. The runner tells it where to
export through the environment — OTLP endpoint, protocol, metric interval — so
anything that reads standard OpenTelemetry configuration works. For Python that
is `opentelemetry-instrument`, the zero-code agent:

```yaml
scenarios:
  inference:
    run: opentelemetry-instrument python inference.py
  checkout:
    run: node --require @opentelemetry/auto-instrumentations-node/register checkout.js
```

Zero-code loads every instrumentation it finds installed, so a scenario's
environment should hold only the one under test — otherwise spans nobody
declared show up and fail the run. That is a feature: it's also how one library
gets compared across implementations, by changing only what's installed.

Which means the run command should build that environment rather than assume
it. In Python, `uv run --project .` syncs a `.venv` beside the scenario's
`pyproject.toml` and runs inside it:

```yaml
run: uv run --project . opentelemetry-instrument python inference.py
```

Installing into whatever environment happened to be active instead — the
runner's own, say — puts every implementation in one environment, which is
exactly the case above.

If you'd rather set the SDK up in the program itself, this package also ships
`otel-conformance-python <script>`, which installs the global providers and
nothing else — no instrumentation is loaded, so the scenario must turn on its
own.

A package can also declare one `setup` command, run once before any scenario:

```yaml
setup: ./build-fixtures.sh
```

`setup` gets no OTLP endpoint, so whatever it emits stays invisible to the
checks. Use it for building something the scenarios need, or prep API calls —
creating an assistant, seeding a store — that shouldn't count toward any
scenario's expectations. A non-zero exit stops the session. Dependencies
belong in the run command's own environment, per above, not here.

## Driving a run

From the command line:

```sh
otel-conformance scenarios/ --registry …/model --policies …/policies
otel-conformance scenarios/ --scenario inference   # just this one
```

or as a library, when you want the results rather than an exit code:

```python
with conformance_session(directory) as session:
    report = session.run("inference")
    print(report.failures)
```

Anything the scenario got wrong — a mismatch, an undeclared violation, a
crash, a command that won't start or overruns — lands in `report.failures`
rather than raising, and the weaver report is written out before anything is
checked. (Problems with the harness itself still raise: an unknown scenario
name, a registry that won't load, a missing `weaver` binary.) Deciding what a
failure means is the caller's job, which is what makes two things easy:

- **Collecting data without failing.** Run every scenario, log the failures,
  exit 0 — `--report-only` on the command line. Useful for measuring attribute
  coverage across a whole repo, or for checking implementations you don't own.
- **Bringing up a new scenario.** Declare it with no expectations, run it,
  read the dumped report, and write the expectations from what you see.

A run writes two things, configured independently: one raw weaver report per
scenario under `--report-dir`, and one reduction over the whole run to
`--data-file` (`output/data.json` by default, usually committed).

A scenario's report is replaced each time that scenario runs, and left alone
otherwise — so running one scenario doesn't discard what the others last
reported. The default path sits inside the scenario directory, so sibling
implementations, which run the same scenario names, don't collide — and so a
run lands in the same place however it was invoked:

```
<scenario directory>/output/weaver-reports/<scenario>.json
```

The reduction is the
coverage this package computes — for each span a scenario declares, the
attributes it actually carried, plus the metrics and events seen:

```json
{
  "spans": {"{\"gen_ai.operation.name\":\"chat\"}": ["gen_ai.input.messages", "…"]},
  "metrics": ["gen_ai.client.operation.duration"],
  "events": []
}
```

Diff it to notice an attribute quietly disappearing. `--data-command` replaces
it when you want a different shape.

## Expectations

Expectations are optional — declare them when you want the run to be strict
about what a scenario produces, which is what turns it from a smoke test into
a check:

```yaml
library: openai

env:
  OPENAI_BASE_URL: ${MOCK_SERVER_URL}/v1
  OPENAI_API_KEY: test_openai_api_key

scenarios:
  inference:
    run: opentelemetry-instrument python inference.py
    spans:
      - match:
          attributes:
            gen_ai.operation.name: chat
        expect:
          count: 1
    metrics:
      - gen_ai.client.operation.duration
    events: []

  tool_calling:
    run: opentelemetry-instrument python tool_calling.py
    spans:
      - match:
          attributes:
            gen_ai.operation.name: chat
        expect:
          count: 2
      - match:
          attributes:
            gen_ai.operation.name: execute_tool
        expect:
          count: 2
          attributes:
            gen_ai.tool.name: { distinct: 2 }
```

Each entry has two halves, declared separately so an attribute used to *find*
a span never reads like one being *checked* on it. `match` selects — by
attribute value or span `kind`. `expect` then asserts over what it selected:
`count` is exact, and a span no entry selects fails as undeclared. Each entry
under `expect.attributes` takes one of three forms:

| form | holds when |
| --- | --- |
| `gen_ai.request.stream: true` | every selected span carries the attribute, set to that value |
| `{present: true}` | every selected span carries it, whatever the value (`false`: none does) |
| `{distinct: 2}` | across the selected spans the attribute took exactly 2 different values |

So `gen_ai.tool.name: { distinct: 2 }` above says the two `execute_tool`
spans called two *different* tools, without pinning down which.

`spans`, `metrics` and `events` follow the same rule. A key you leave out is
**not checked** — a scenario with no expectations only has to run cleanly. A
key you write is checked exactly: nothing missing, nothing extra, including
when empty — `events: []` means "emits no events".

`env` configures the scenario process. The real process environment wins over
it, so exporting a real key and base URL points a scenario at a real provider
instead of a mock. What the runner injects — the OTLP endpoint, the server URL
— wins over both, since those name what this run actually started.

### Known violations

Violations weaver reports are failures unless you declare them, with a reason:

```yaml
  tool_calling:
    expected_violations:
      - id: genai_expected_attribute_missing
        context:
          operation: execute_tool
          missing_attribute: gen_ai.tool.call.id
        reason: >-
          The SDK does not expose the tool call id — https://github.com/…/86
```

A declared violation weaver *stops* reporting fails too, so suppressions don't
outlive the gap that caused them.

`context` is matched in full — the same advice `id` with a different context is
a different finding. Leave it out to accept **every** finding with that `id`,
which is what you want when they're one gap seen many times:

```yaml
    expected_violations:
      - id: missing_attribute
        reason: This implementation's own attribute namespace.
```

That trades away some of the signal: a declaration covering a whole class stops
telling you when the class *shrinks*, only when it empties. Reach for it when
the members are interchangeable, and write them out when each is its own gap.
(`context: {}` is not the same thing — it declares a finding that carried no
context at all.)

Declare them at the top level instead, and every scenario gets them — the right
place for a gap that belongs to the instrumentation rather than to one program:

```yaml
library: openai

expected_violations:
  - id: genai_span_kind_unexpected
    context: {operation: chat, kind: internal}
    reason: Inference is a remote call, so semconv expects kind=client.

scenarios:
  inference: …
```

A scenario's own list is merged on top. The two levels differ in one way
besides scope: a package-level entry only ever *suppresses*, so a scenario that
doesn't reach that gap isn't failed for it, while a scenario's own is still
required to still be reported. Declaring the same `id` at both levels is an
error — two reasons for one finding, and no way to tell which one is stale.

## Wrapping it for your repo

Your repo's conventions — the canonical registry and policies, the server the
scenarios talk to, what a run should produce — belong in one place, so each
package's YAML stays small. Everything can be passed on the command line:

```sh
otel-conformance scenarios/ \
    --registry …/model --policies …/policies \
    --env MOCK_LLM_URL='${MOCK_SERVER_URL}' \
    --server 'env PYTHONPATH=…/src python -m my_mocks.server --port ${PORT}' \
    --data-command ./reduce-coverage
```

`--server` is told its port through `${PORT}` and its base URL reaches the
scenarios as `${MOCK_SERVER_URL}`.

`--data-command` replaces the built-in coverage reduction with a shell command
run after a complete (unfiltered) run: `"$1"` is the report directory, `"$2"`
the library name, and the JSON it prints becomes the data file. A non-zero exit
or output that isn't JSON fails the run.

```sh
--data-command 'jq -s --arg lib "$2" "{(\$lib): [.[].samples[].span.name]}" "$1"/*.json'
```

A package overrides any of it by declaring `weaver:` or `server:` itself,
field by field — `server: {health: /ready}` keeps your server and only changes
where it is probed. Paths declared inside a package file are relative to that
file, paths on the command line to your shell.

## Limitations

- **Only really exercised against the GenAI semantic conventions**, and against
  Python scenarios. Both are conventions of use rather than of design: a
  scenario gets everything it needs — OTLP endpoint and protocol, metric export
  interval, server URL — as environment variables and names its own `run`
  command, so another language only needs its own adapter.
- **Weaver live-check is the only backend**, so what it can't observe can't be
  checked. Expectations select spans only, by attribute value or kind — not by
  name, status or parent — and add count and attribute assertions on top of
  weaver's own conformance checks. Metrics and events are matched by name.
  Content isn't checked: whether a tool call round-tripped through the messages
  belongs in unit tests.
- **Servers are started, not managed.** A declared `server` must listen on
  `${PORT}` and answer a health endpoint. Anything with a different lifecycle —
  a container pool, a shared staging backend — you run yourself and pass the URL
  in with `--env`.
- **Scenarios run one at a time**, each under its own live-check.
