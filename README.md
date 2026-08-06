# OpenTelemetry Semantic Conventions Conformance

Does an instrumentation actually emit what the semantic conventions say it
should? This repo answers that the same way for every library, every
implementation and every language: run a small program that exercises the
library, collect what it emits through
[Weaver live-check](https://github.com/open-telemetry/weaver), and check it
against expectations declared in YAML.

| | |
| --- | --- |
| [`tools/runner/`](tools/runner) | the runner. Generic — it carries no semantic conventions of its own |
| [`tools/genai-runner/`](tools/genai-runner) | what makes a run a *GenAI* run: the registry pin, the advice policies, and the package that wires them to the runner |
| [`tools/mock-servers/genai/`](tools/mock-servers/genai) | a mock LLM server, so scenarios are deterministic without cassettes |
| [`scenarios/`](scenarios) | the scenarios, by language, library and instrumentation |

```sh
pip install -e tools/runner -e tools/mock-servers/genai -e tools/genai-runner
genai-conformance scenarios/gen-ai/python/openai/opentelemetry --report-only
```

Start with the [runner's README](tools/runner/README.md) for what a scenario and its
`conformance.yaml` look like, and [`scenarios/gen-ai/`](scenarios/gen-ai/README.md) for running
against the GenAI conventions.

> **Early.** The scenarios under `scenarios/` are demos showing the
> layout, not maintained conformance results, and nothing here is published to
> PyPI yet.

## Maintainers

- [Christophe Kamphaus](https://github.com/kamphaus), Independent
- [Jay DeLuca](https://github.com/jaydeluca), Grafana Labs
- [Josh Suereth](https://github.com/jsuereth), Google
- [Liudmila Molkova](https://github.com/lmolkova), Google
- [Trask Stalnaker](https://github.com/trask), Microsoft

For more information about the maintainer role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#maintainer).

## Approvers

- None

For more information about the approver role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#approver).
