# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Classifying spans, and reducing a run against the resolved coverage model.

The model is what weaver resolved out of the pinned registry: provider
refinements folded into the span type they refine — ``openai.inference.client``
adds ``openai.*`` to ``gen_ai.inference.client`` — and every metric and event
the registry declares.

Needs the pinned registry and the model
``tools/collect-coverage-model.sh`` resolves out of it.
"""

from __future__ import annotations

import pytest

from genai_conformance._coverage import (
    _classify,
    _coverage_model,
    _data,
    _reference_source,
)


@pytest.fixture(name="model", scope="module")
def _model():
    try:
        _reference_source()
        return _coverage_model()
    except (OSError, RuntimeError) as error:
        pytest.skip(f"coverage model not available: {error}")


@pytest.fixture(name="result_for")
def _result_for(model):
    """A parsed run that emitted the given signals, carrying every attribute."""
    from semconv_genai.parse_results import (  # noqa: PLC0415
        DetectedSignals,
        ObservedTelemetry,
        ScenarioResult,
        SpanClassification,
    )

    def build(span_types=(), events=(), metrics=()):
        carried = {
            span_type: set(model["spans"][span_type]["attributes"])
            for span_type in span_types
        }
        return ScenarioResult(
            library="test",
            statistics=None,
            observed=ObservedTelemetry(),
            spans=SpanClassification(
                detected_types=set(span_types),
                per_type_attrs=carried,
                per_type_any_attrs=dict(carried),
            ),
            detected=DetectedSignals(
                events={name: 1 for name in events},
                metrics={name: 1 for name in metrics},
                event_attrs={
                    name: set(model["events"][name]["attributes"])
                    for name in events
                },
                event_any_attrs={
                    name: set(model["events"][name]["attributes"])
                    for name in events
                },
                metric_attrs={
                    name: set(model["metrics"][name]["attributes"])
                    for name in metrics
                },
                metric_any_attrs={
                    name: set(model["metrics"][name]["attributes"])
                    for name in metrics
                },
            ),
        )

    return build


def test_the_operation_name_names_the_span_type(model) -> None:
    assert _classify(
        "chat gpt-4", "client", {"gen_ai.operation.name": "chat"}
    ) == {"gen_ai.inference.client"}


def test_a_span_without_an_operation_name_is_identified_by_its_attributes(
    model,
) -> None:
    assert _classify(
        "tool", "internal", {"gen_ai.tool.name": "get_weather"}
    ) == {"gen_ai.execute_tool.internal"}


def test_the_operation_name_wins_over_identifying_attributes(model) -> None:
    """An inference span holding gen_ai.agent.id is not an agent invocation."""
    classified = _classify(
        "chat gpt-4",
        "client",
        {"gen_ai.operation.name": "chat", "gen_ai.agent.id": "a1"},
    )

    assert classified == {"gen_ai.inference.client"}


def test_span_kind_tells_the_two_invoke_agent_types_apart(model) -> None:
    attributes = {"gen_ai.operation.name": "invoke_agent"}

    assert _classify("", "client", attributes) == {
        "gen_ai.invoke_agent.client"
    }
    assert _classify("", "internal", attributes) == {
        "gen_ai.invoke_agent.internal"
    }


def test_a_span_of_no_known_type_is_classified_as_nothing(model) -> None:
    assert (
        _classify("GET /", "client", {"http.request.method": "GET"}) == set()
    )


def test_provider_attributes_reach_the_span_type_they_refine(
    result_for,
) -> None:
    data = _data(result_for(span_types=["gen_ai.inference.client"]))
    inference = data["spans"]["gen_ai.inference.client"]

    assert "openai.response.service_tier" in inference
    assert "openai.request.service_tier" in inference


def test_the_base_conventions_come_through_too(result_for) -> None:
    """Folding adds provider attributes; it must not drop gen_ai ones."""
    data = _data(result_for(span_types=["gen_ai.inference.client"]))

    assert {"gen_ai.operation.name", "gen_ai.request.model"} <= set(
        data["spans"]["gen_ai.inference.client"]
    )


def test_an_attribute_a_refinement_restates_is_not_listed_twice(
    result_for,
) -> None:
    """openai makes gen_ai.request.model required; it moves, not duplicates."""
    data = _data(result_for(span_types=["gen_ai.inference.client"]))
    inference = data["spans"]["gen_ai.inference.client"]

    assert len(inference) == len(set(inference))


def test_a_required_attribute_missing_from_one_span_is_absent(
    model, result_for
) -> None:
    """Required means every span of the type carried it, not just one."""
    result = result_for(span_types=["gen_ai.inference.client"])
    required = next(
        name
        for name, level in model["spans"]["gen_ai.inference.client"][
            "attributes"
        ].items()
        if level == "required"
    )
    result.spans.per_type_attrs["gen_ai.inference.client"].discard(required)

    data = _data(result)

    assert required not in data["spans"]["gen_ai.inference.client"]


def test_every_declared_metric_is_recordable(model, result_for) -> None:
    """Upstream hand-lists two of twelve; a coverage artifact wants them all."""
    declared = [
        name for name in model["metrics"] if name.startswith("gen_ai.")
    ]

    recorded = _data(result_for(metrics=declared))["metrics"]

    assert set(recorded) == set(declared)
    assert "gen_ai.operation.name" in recorded["gen_ai.client.token.usage"]


def test_every_declared_event_is_recordable(model, result_for) -> None:
    declared = [name for name in model["events"] if name.startswith("gen_ai.")]

    recorded = _data(result_for(events=declared))["events"]

    assert set(recorded) == set(declared)
    assert "gen_ai.client.operation.exception" in recorded


def test_a_signal_the_run_did_not_emit_reads_back_as_empty(result_for) -> None:
    """Every key is always there: "emitted none" has to be readable as that."""
    data = _data(result_for(span_types=["gen_ai.inference.client"]))

    assert list(data["spans"]) == ["gen_ai.inference.client"]
    assert data["events"] == {}
    assert data["metrics"] == {}


def test_the_file_is_written_in_a_stable_order(result_for) -> None:
    """These files are committed and diffed byte for byte."""
    data = _data(
        result_for(
            span_types=[
                "gen_ai.inference.client",
                "gen_ai.embeddings.client",
                "gen_ai.create_agent.client",
            ],
            events=["gen_ai.evaluation.result"],
            metrics=[
                "gen_ai.invoke_agent.tool_calls",
                "gen_ai.client.token.usage",
            ],
        )
    )

    assert list(data) == ["spans", "events", "metrics"]
    for section in data.values():
        assert list(section) == sorted(section)
    for attributes in data["spans"].values():
        assert attributes == sorted(attributes)
