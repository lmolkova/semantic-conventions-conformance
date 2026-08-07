# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The GenAI reduction of a run: what each span type carried.

The runner's own reduction keys on the spans a scenario *declares*, which is
all it can do without knowing the conventions. This one knows them: every span
is classified into a registry span type, and the data file records, per type,
which of that type's attributes were present.

What a span type declares is the coverage model
``tools/collect-coverage-model.sh`` resolves out of the registry with weaver,
including the provider refinements — ``openai.inference.client`` refines
``gen_ai.inference.client`` — and every metric and event the registry
declares. Reading a weaver report is the semconv repo's own, imported from the
checkout ``versions.env`` pins.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._registry import gen_ai_root, provision_genai_root, semconv_registry

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from opentelemetry.conformance import PackageSpec

# Which spans are of which type. The registry declares a span type's
# attributes but not how to recognise one — every span type carries the whole
# ``gen_ai.operation.name`` enum — so the operation names belong to a type,
# and the attributes that identify a span that omits the operation name, are
# stated here.
_OPERATION_NAMES = {
    "gen_ai.create_agent.client": {"create_agent"},
    "gen_ai.embeddings.client": {"embeddings"},
    "gen_ai.execute_tool.internal": {"execute_tool"},
    "gen_ai.fetch_response.client": {"fetch_response"},
    "gen_ai.inference.client": {"chat", "generate_content", "text_completion"},
    "gen_ai.invoke_agent.client": {"invoke_agent"},
    "gen_ai.invoke_agent.internal": {"invoke_agent"},
    "gen_ai.invoke_workflow.internal": {"invoke_workflow"},
    "gen_ai.memory.client": {
        "create_memory",
        "create_memory_store",
        "delete_memory",
        "delete_memory_store",
        "search_memory",
        "update_memory",
        "upsert_memory",
    },
    "gen_ai.plan.internal": {"plan"},
    "gen_ai.retrieval.client": {"retrieval"},
}

_IDENTIFYING_ATTRIBUTES = {
    "gen_ai.embeddings.client": {
        "gen_ai.embeddings.dimension.count",
        "gen_ai.request.encoding_formats",
    },
    "gen_ai.execute_tool.internal": {
        "gen_ai.tool.call.id",
        "gen_ai.tool.name",
    },
    "gen_ai.invoke_agent.client": {"gen_ai.agent.id", "gen_ai.agent.name"},
    "gen_ai.invoke_agent.internal": {"gen_ai.agent.id", "gen_ai.agent.name"},
    "gen_ai.invoke_workflow.internal": {"gen_ai.workflow.name"},
    "gen_ai.retrieval.client": {"gen_ai.data_source.id"},
    # create_agent and plan share gen_ai.agent.{id,name} with invoke_agent, so
    # nothing identifies them but the operation name.
}


def _reference_source() -> Path:
    """The pinned checkout's ``reference/src``, importable."""
    source = provision_genai_root() / "reference" / "src"
    if not (source / "semconv_genai").is_dir():
        raise RuntimeError(
            f"{source / 'semconv_genai'} not found — check the "
            "SEMCONV_GENAI_REF pin in versions.env."
        )
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    return source


def coverage_model_file() -> Path:
    """Where ``tools/collect-coverage-model.sh`` writes the resolved model.

    Next to the provisioned registry, so moving the ``versions.env`` pin asks
    for a fresh one rather than silently reusing the old registry's.
    """
    return provision_genai_root() / "coverage-model.json"


def provision_coverage_model() -> Path:
    """Resolve the coverage model if the pinned registry hasn't got one yet.

    Called when a session starts, so the weaver run that resolves the registry
    happens once, up front, and not while reducing a run.
    """
    model = coverage_model_file()
    if model.is_file():
        return model

    script = gen_ai_root().parent / "collect-coverage-model.sh"
    logger.info("Resolving the coverage model into %s", model)
    completed = subprocess.run(  # noqa: S603
        [str(script)],
        env={
            **os.environ,
            "SEMCONV_REGISTRY": str(semconv_registry()),
            "COVERAGE_MODEL": str(model),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not model.is_file():
        raise RuntimeError(
            f"{script} failed to resolve the coverage model: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return model


@lru_cache(maxsize=1)
def _coverage_model() -> dict[str, dict[str, Any]]:
    """Per span type, event and metric, what the registry declares."""
    path = coverage_model_file()
    if not path.is_file():
        raise RuntimeError(
            f"{path} not found — run tools/collect-coverage-model.sh to "
            "resolve the pinned registry before reducing a run."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _classify(
    span_name: str, span_kind: str, attributes: dict[str, Any]
) -> set[str]:
    """The span types a span belongs to.

    ``gen_ai.operation.name`` names the type when it is set. A span that omits
    it is recognised by the attributes only its type carries — but a span that
    names its operation is that operation, whatever else it carries, so an
    inference span holding ``gen_ai.agent.id`` is not an agent invocation.

    ``span_name`` is unused; it is accepted to match the report parser's
    ``ClassifySpan`` signature.
    """
    del span_name
    operation = str(attributes.get("gen_ai.operation.name", "")).lower()
    present = {name for name, value in attributes.items() if value is not None}

    named = {
        span_type
        for span_type, operations in _OPERATION_NAMES.items()
        if operation in operations
    }
    matched = named or {
        span_type
        for span_type, identifying in _IDENTIFYING_ATTRIBUTES.items()
        if identifying & present
    }

    # A type is declared client or internal — which is what tells an agent
    # invoked over the wire from one running in-process.
    spans = _coverage_model()["spans"]
    of_this_kind = {
        span_type
        for span_type in matched
        if spans.get(span_type, {}).get("kind") == span_kind.lower()
    }
    return of_this_kind or matched


def _present(
    declared: dict[str, str],
    on_every: set[str] | None,
    on_any: set[str] | None,
) -> list[str]:
    """Which declared attributes the run carried.

    A required attribute counts only when every sample of the signal had it;
    the rest count when any did. That is what makes a data file say "this
    implementation always sets the required ones".

    A signal weaver only counted, without a sample to read attributes off,
    carries nothing here: crediting it with what some other signal in the run
    happened to set would overstate the coverage this file records.
    """
    every = on_every or set()
    any_ = on_any or set()
    return sorted(
        name
        for name, level in declared.items()
        if name in (every if level == "required" else any_)
    )


def _signals(
    declared: dict[str, dict[str, Any]],
    counts: dict[str, int],
    on_every: dict[str, set[str]],
    on_any: dict[str, set[str]],
) -> dict[str, list[str]]:
    """The attributes carried by each event or metric the run emitted."""
    return {
        name: _present(
            declared[name]["attributes"],
            on_every.get(name),
            on_any.get(name),
        )
        for name, count in sorted(counts.items())
        if count > 0 and name in declared
    }


def _parse_results() -> Any:
    """The semconv repo's own report parser, from the provisioned checkout.

    It ships with the registry rather than on PyPI, so it is reachable only
    once the pin has been fetched — hence the import behind a call, and the
    untyped module it hands back.
    """
    _reference_source()
    import semconv_genai.parse_results as parse_results  # noqa: PLC0415  # pyright: ignore[reportMissingImports]

    return parse_results


def _data(result: Any) -> dict[str, object]:
    """A parsed run, reduced to the committed ``data.json`` shape.

    Every key and every list is alphabetical: these files are committed and
    diffed, so a run that emits the same telemetry must write the same bytes.
    """
    merge_signal_counts = _parse_results().merge_signal_counts
    model = _coverage_model()

    spans = {}
    for span_type in sorted(result.spans.detected_types):
        present = _present(
            model["spans"][span_type]["attributes"],
            result.spans.per_type_attrs.get(span_type),
            result.spans.per_type_any_attrs.get(span_type),
        )
        if present:
            spans[span_type] = present

    events = _signals(
        model["events"],
        merge_signal_counts(result.observed.events, result.detected.events),
        result.detected.event_attrs,
        result.detected.event_any_attrs,
    )
    metrics = _signals(
        model["metrics"],
        merge_signal_counts(result.observed.metrics, result.detected.metrics),
        result.detected.metric_attrs,
        result.detected.metric_any_attrs,
    )

    # Always all three, empty or not: a reader can tell "this run emitted no
    # metrics" from a file that says so, but not from a file that left the key
    # out — and a signal an implementation stops emitting shows up as an empty
    # object in the diff rather than a disappearing key.
    return {"spans": spans, "events": events, "metrics": metrics}


def genai_coverage(report_dir: Path, spec: PackageSpec) -> object:
    """Reduce a run's weaver reports the way the GenAI conventions read them."""
    parse_result_dir = _parse_results().parse_result_dir
    result = parse_result_dir(report_dir, spec.instrumented_library, _classify)
    if result is None:
        raise RuntimeError(
            f"no weaver reports to reduce under {report_dir} — the run "
            "produced nothing to record"
        )
    return _data(result)
