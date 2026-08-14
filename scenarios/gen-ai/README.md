# GenAI scenarios

Scenario programs checked against the
[GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai).

How to run a directory, and what its `conformance.yaml` may declare, is in the
[runner's README](../../tools/runner/README.md). What makes a run a *GenAI*
run (the registry pin, the advice policies, the reduction `data.json` is keyed
on) is in [`tools/gen-ai/runner`](../../tools/gen-ai/runner/README.md), and
the responses come from the
[mock LLM server](../../tools/gen-ai/mock-server/README.md). This file is only
about the scenarios themselves.

```sh
otel-conformance scenarios/gen-ai/python/openai/opentelemetry-openai --report-only
```

## The scenario tree

```
scenarios/gen-ai/<language>/<library>/
    scenarios/              the programs, one copy, shared
    <instrumentation>/      conformance.yaml, pyproject.toml, uv.lock, data.json
```

`<library>` is the library being exercised. `<instrumentation>` names the
instrumentation that produced the telemetry, so `opentelemetry-openai` is the
OpenTelemetry instrumentation for the openai client and
`opentelemetry-langchain-openai` is the OpenTelemetry langchain
instrumentation reaching OpenAI through `langchain-openai`. Both names are
labels for reading the tree. The runner never reads a path for meaning, so
what a run is about is whatever its `conformance.yaml` declares.

**Implementations that call the same client package share their programs**,
from `<library>/scenarios/`:

```yaml
run: uv run --frozen --project . opentelemetry-instrument python ../scenarios/inference.py
```

An implementation that reaches the provider through a different package
cannot run those files, so it keeps its own `scenarios/` beside its
`conformance.yaml`. `opentelemetry-langchain-openai` calls `ChatOpenAI`, not
`OpenAI`, so it has one; the programs still make the same exchange, which is
what keeps the two `data.json` files comparable.

```
openai/
    scenarios/                          the openai SDK programs
    opentelemetry-openai/               conformance.yaml, data.json
    opentelemetry-langchain-openai/
        scenarios/                      the ChatOpenAI programs
        conformance.yaml, data.json
```

`--project .` runs a program in the implementation directory's own
environment, which uv syncs from the `pyproject.toml` there. Each
implementation gets its own, so zero-code never finds a neighbour's
instrumentation installed. That is the constraint on adding an implementation:
its environment must hold only its own instrumentation, or someone else's
spans land in the results. So a scenario program never names an
instrumentation, and never imports OpenTelemetry.

## The scenario contract

Each class below defines one exchange. Every library makes that same exchange,
in its own SDK's names, so their `data.json` files compare directly.

Every inference-shaped request carries:

- one system instruction and one user turn;
- `max_tokens`, `temperature`, `top_p`, `top_k`, `stop_sequences`, `seed`,
  `frequency_penalty` and `presence_penalty`, wherever the API has that
  parameter. Anthropic has no seed and OpenAI no top-k, so those requests omit
  them.

| Class | Applies to | The exchange | What it is for |
| --- | --- | --- | --- |
| `inference` | client | one non-streaming call | request, response and usage attributes, and both metrics |
| `streaming` | client | the same call, streamed, consumed to the end | what an instrumentation can only report once the last chunk lands |
| `structured_output` | client | one call naming a JSON schema | `gen_ai.output.type` |
| `multimodal` | client | one call per non-text content kind the API takes | the *shape* of recorded content, per-modality token counts |
| `embeddings` | client | one batched call with an explicit encoding format and dimension count | the embeddings span type |
| `tool_calling` | client | two round trips: tool definitions and the requested call, then the tool result travelling back as input | tool definitions and calls on both sides of the exchange |
| `automatic_tool_calling` | both | the same exchange, with the SDK or framework running the tool and sending the result back | tool execution as a span, not a message |
| `invoke_agent` | agentic | one agent run, no tools | the agent span on its own |
| `workflow` | agentic | one chain, no agent | the workflow span on its own |

*client* means an LLM client SDK such as `openai` or `anthropic`. *agentic*
means a framework that drives a run, such as `langchain` or `openai-agents`.
Keep the two groups in separate directories: a directory covers one group.
`automatic_tool_calling` is the one class both groups have, so it is the one
that compares across them.

A library gets a scenario for every class its API supports. Anthropic has no
embeddings API, so `anthropic/` has no embeddings scenario. The OpenAI Python
SDK does not run tools, so `openai/` has no automatic tool calling scenario. A
class the API supports but the instrumentation does not still gets a scenario,
and the gap lands in `data.json`.

## What is covered

| Library | Instrumentation | Classes |
| --- | --- | --- |
| `openai` | `opentelemetry-instrumentation-genai-openai` | every client class |
| `openai` | `opentelemetry-instrumentation-genai-langchain` | every client class, through `langchain-openai` |
| `anthropic` | `opentelemetry-instrumentation-genai-anthropic` | client classes except structured output and embeddings |
| `anthropic` | `opentelemetry-instrumentation-genai-langchain` | the same, through `langchain-anthropic` |
| `google-genai` | `opentelemetry-instrumentation-google-genai` | every client class |
| `botocore` | `opentelemetry-instrumentation-botocore` | Bedrock Converse: inference, streaming, tool calling |
| `langchain` | `opentelemetry-instrumentation-genai-langchain` | agentic classes |
| `openai-agents` | `opentelemetry-instrumentation-genai-openai-agents` | agentic classes |

The conventions also cover retrieval, memory and planning. No instrumentation
here emits them, so there is no class for them yet.

Each class is one file, and each file gets its own weaver report.

## Content capture

Every directory sets `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to
`SPAN_AND_EVENT`, so one run covers content on spans and the
`gen_ai.client.inference.operation.details` event.
`opentelemetry-botocore` reads that variable as a boolean rather than as a
mode, so its directory sets `true`; there is no other way to turn content on
there.

Set it per directory, never per scenario. `data.json` is a union across the
directory's scenarios, so a directory mixing capture modes records the union
of both.

## Measuring, not testing

Scenarios here declare no expectations: no span counts, no required metrics,
no `expected_violations`. Those are tests, and a test belongs with the
instrumentation it covers, which is `opentelemetry-python-genai` for these
implementations. What this repo owns is the measurement.

Runs are `--report-only`, so a semconv finding is recorded, not a build
break. A scenario that crashed still fails, because then there is no
measurement to report.
