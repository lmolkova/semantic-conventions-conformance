# genai-conformance

What makes a run a *GenAI* run. The [runner](../runner) knows how to execute
scenarios and check them; everything specific to these semantic conventions is
here.

| | |
| --- | --- |
| [`versions.env`](versions.env) | the pinned registry and weaver versions, managed by Renovate |
| [`policies/`](policies) | advice policies weaver live-check runs on top of the registry's own checks |
| [`weaver.toml`](weaver.toml) | live-check finding filters |
| `src/genai_conformance/` | ties those to the runner and the [mock LLM server](../mock-servers/genai), and reduces a run to `data.json` |

```sh
pip install -e tools/runner -e tools/mock-servers/genai -e tools/genai-runner
genai-conformance scenarios/gen-ai/python/openai/opentelemetry --report-only
```

`genai-conformance` is `otel-conformance` with the registry, policies and
server filled in — every flag still works, and still wins. Or, as a library,
`genai_session` is `conformance_session` with the same defaults applied:

```python
with genai_session(directory) as session:
    report = session.run("inference")
```

Install it editable from a checkout: it finds `versions.env`, `policies/` and
`weaver.toml` by walking up from its own source, and nothing here is on PyPI.

## What a run reduces to

The runner's own reduction keys `data.json` on the spans a scenario *declares*,
which is all it can do without knowing the conventions. `genai_session`
replaces it: every span is classified into a registry span type, and the file
records which of that type's attributes were present.

```json
{"spans": {"gen_ai.inference.client": ["gen_ai.input.messages", "gen_ai.operation.name", "…"]}}
```

Two implementations of one library, and an implementation against the
reference, diff directly.

What a span type declares comes from the registry, resolved by
[`tools/collect-coverage-model.sh`](../collect-coverage-model.sh) into a
`coverage-model.json` next to the provisioned registry. Starting a session
runs it when the pin hasn't got one yet, so the weaver run happens up front
rather than after the scenarios have; run it by hand to refresh one:

```sh
tools/collect-coverage-model.sh
```

It is `weaver registry generate --v2` over the
[coverage-model template](../weaver-templates/coverage-model), whose filter is
the whole reduction. Weaver reports provider refinements alongside the span
type they refine, so an implementation that emits `openai.*` exactly as
`openai.inference.client` specifies records them on its inference spans, and
every metric and event the registry declares is recordable.

Recognising a span is the one thing the registry can't answer — every span type
carries the whole `gen_ai.operation.name` enum — so which operation names mean
which span type is stated in `_coverage.py`.

The file records only what the registry knows: an attribute it doesn't declare
doesn't appear, and neither do metrics or events unless the run produced them.
Pass `build_data=opentelemetry.conformance.coverage` for the runner's generic
reduction instead.

## The registry

`versions.env` pins a `semantic-conventions-genai` commit. On first use the
package downloads that tarball into `$SEMCONV_CACHE` (default
`~/.cache/otel-conformance/semconv`). Its `model/manifest.yaml` names the
upstream `semantic-conventions` registry as a git URL, so weaver fetches and
resolves that itself.

One thing is still patched: the draft-07 `$ref` in
`gen-ai-tool-definitions.json` is rewritten to a plain object, because weaver's
rego engine won't fetch it at eval time.

A repo checking its own working tree overrides just the registry:

```sh
genai-conformance path/to/scenarios --registry ./model
```
