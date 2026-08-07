# GenAI scenarios

Scenario programs checked against the
[GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai).
What makes a run a *GenAI* run — the registry pin, the advice policies, the
mock LLM server — lives in [`tools/genai-runner`](../../tools/genai-runner); the
[runner](../../tools/runner) carries none of it.

## Running

```sh
pip install -e tools/runner -e tools/mock-servers/genai -e tools/genai-runner
genai-conformance scenarios/gen-ai/python/openai/opentelemetry --report-only
genai-conformance scenarios/gen-ai/python/openai/opentelemetry --report-only --scenario inference
```

`genai-conformance` is `otel-conformance` with the registry, policies and mock
server filled in — every flag still works, and still wins. A repo checking its
own working tree points the registry at it:

```sh
genai-conformance path/to/scenarios --registry ./model
```

You also need the `weaver` binary on `PATH`, at the version
[`versions.env`](../../tools/genai-runner/versions.env) pins.

## The scenario tree

```
scenarios/gen-ai/<language>/<library>/
    scenarios/              the programs — one copy, shared
    <instrumentation>/      conformance.yaml, pyproject.toml, data.json
```

`<library>` is the client library being exercised; `<instrumentation>` is whose
instrumentation produced the telemetry — `opentelemetry`, `openinference`,
`reference` (the hand-written implementation the semconv repo maintains), or
`native` when the library instruments itself.

Those directory names are short labels for reading the tree. What a run is
actually about is declared in each `conformance.yaml`, where `library:` and
`instrumentation:` name the real packages:

```yaml
instrumented_library: openai
instrumentation_library: opentelemetry-instrumentation-genai-openai
```

Nothing derives one from the other: the runner never reads a path for meaning,
so a directory can be renamed or a scenario moved without changing what the
results say produced them.

**The programs live once, under the library.** Every implementation runs the
same file:

```yaml
run: uv run --project . opentelemetry-instrument python ../scenarios/inference.py
```

`--project .` runs it in the implementation directory's own environment, which
uv syncs from the `pyproject.toml` there. Each implementation gets its own, so
zero-code never finds a neighbour's instrumentation installed.

That is what makes the results comparable — otherwise a difference in
`data.json` could just as easily be a difference in the program. A scenario
therefore never names an instrumentation: it uses the library and nothing else,
and zero-code instruments whatever the implementation's directory installs.
Which is also the constraint — an implementation's environment must hold only
its own instrumentation, or someone else's spans land in the results.

`reference` is the exception, and runs its own program: there the
instrumentation *is* hand-written around the library calls, so there is nothing
to share.

Each implementation directory holds its `conformance.yaml` (how to run the
programs), a `pyproject.toml` declaring its dependencies, and a committed
`data.json` recording what the run actually emitted.

## Measuring, not testing

The runner can assert span counts, required metrics and the rest. **Nothing
here does.** Those are tests, and a test belongs with the instrumentation it
covers — `opentelemetry-python-genai` for the `opentelemetry` implementation,
`semantic-conventions-genai` for `reference`. What this repo owns is the
measurement: run the programs, record what came out, report where it diverges
from the conventions. Runs are `--report-only` for the same reason — a
semconv finding is a result to read, not a build to break. A scenario that
crashed or missed something it declared still fails: that is the harness
saying it has no measurement to report.

`expected_violations` is the exception, and stays. A divergence someone has
looked at and written a reason for is a different fact from one nobody has seen
yet, and only the file can carry that distinction. It changes nothing about
`data.json`, which records what a run emitted either way.

> The trees under `python/` today are **demos** — they show the layout and are
> not maintained conformance results.
