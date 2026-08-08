# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Reading weaver reports, and reducing them against a coverage model.

Both halves of the registry-shaped reduction: what ``_report`` sees in a run,
and what ``_semconv`` writes down about it. The model here is a small
hand-written one — resolving a real registry is weaver's job and is covered by
each domain's own tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opentelemetry.conformance._report import Observed, Signal, read
from opentelemetry.conformance._semconv import _reduce, semconv_coverage

MODEL = {
    "spans": {
        "http.server": {
            "kind": "server",
            "attributes": {
                "http.request.method": "required",
                "http.route": "conditionally_required",
                "url.scheme": "recommended",
                "client.port": "opt_in",
            },
        }
    },
    "metrics": {
        "http.server.request.duration": {
            "attributes": {
                "http.request.method": "required",
                "error.type": "conditionally_required",
            }
        }
    },
    "events": {"some.event": {"attributes": {"a": "recommended"}}},
}


def by_kind(_name: str, kind: str, _attributes: object) -> set[str]:
    """Classify every span by its kind, which is all these fixtures need."""
    return {f"http.{kind}"}


def attribute(name: str, value: object = "x", *, advice: str | None = None):
    record: dict[str, object] = {"name": name, "value": value}
    if advice is not None:
        record["live_check_result"] = {"all_advice": [{"id": advice}]}
    return record


def write_report(directory: Path, name: str, **report: object) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps(report))


def span_sample(kind: str = "server", *attributes: object) -> dict:
    return {"span": {"name": "GET /", "kind": kind, "attributes": list(attributes)}}


# ── reading reports ────────────────────────────────────────────────


def test_a_span_is_recorded_under_every_type_it_classifies_as(tmp_path) -> None:
    write_report(
        tmp_path, "one", samples=[span_sample("server", attribute("url.scheme"))]
    )

    observed = read(tmp_path, by_kind)

    assert set(observed.spans) == {"http.server"}
    assert observed.spans["http.server"].on_any == {"url.scheme"}


def test_an_attribute_only_one_sample_carried_is_not_on_every(tmp_path) -> None:
    write_report(
        tmp_path,
        "one",
        samples=[
            span_sample("server", attribute("http.request.method")),
            span_sample(
                "server",
                attribute("http.request.method"),
                attribute("http.route"),
            ),
        ],
    )

    signal = read(tmp_path, by_kind).spans["http.server"]

    assert signal.on_every == {"http.request.method"}
    assert signal.on_any == {"http.request.method", "http.route"}
    assert signal.count == 2


def test_an_attribute_weaver_rejected_did_not_really_arrive(tmp_path) -> None:
    """A type_mismatch means the name is there holding something disallowed."""
    write_report(
        tmp_path,
        "one",
        samples=[
            span_sample(
                "server",
                attribute("http.route", advice="type_mismatch"),
                attribute("url.scheme", advice="not_stable"),
            )
        ],
    )

    signal = read(tmp_path, by_kind).spans["http.server"]

    assert signal.on_any == {"url.scheme"}


def test_a_metric_carries_the_attributes_of_all_its_data_points(
    tmp_path,
) -> None:
    write_report(
        tmp_path,
        "one",
        samples=[
            {
                "metric": {
                    "name": "http.server.request.duration",
                    "data_points": [
                        {"attributes": [attribute("http.request.method")]},
                        {"attributes": [attribute("error.type")]},
                    ],
                }
            }
        ],
    )

    signal = read(tmp_path, by_kind).metrics["http.server.request.duration"]

    assert signal.on_any == {"http.request.method", "error.type"}


def test_a_signal_weaver_only_counted_is_still_recorded(tmp_path) -> None:
    """Weaver keeps no sample of every signal it sees; it still happened."""
    write_report(
        tmp_path,
        "one",
        samples=[],
        statistics={
            "seen_registry_metrics": {
                "http.server.request.duration": 3,
                "http.client.request.duration": 0,
            }
        },
    )

    observed = read(tmp_path, by_kind)

    assert set(observed.metrics) == {"http.server.request.duration"}
    assert observed.metrics["http.server.request.duration"].on_every is None


def test_counts_are_merged_across_a_run_s_reports(tmp_path) -> None:
    """One report per scenario: the run saw a signal if any scenario did."""
    write_report(
        tmp_path,
        "a",
        samples=[],
        statistics={"seen_registry_events": {"some.event": 0}},
    )
    write_report(
        tmp_path,
        "b",
        samples=[],
        statistics={"seen_registry_events": {"some.event": 2}},
    )

    assert read(tmp_path, by_kind).events["some.event"].count == 2


# ── reducing against the model ─────────────────────────────────────


def signal(*names: str, every: bool = True) -> Signal:
    return Signal(
        count=1, on_every=set(names) if every else set(), on_any=set(names)
    )


def test_a_required_attribute_counts_only_when_every_sample_had_it() -> None:
    data = _reduce(
        Observed(
            spans={
                "http.server": signal("http.request.method", every=False)
            }
        ),
        MODEL,
    )

    assert data["spans"] == {}


def test_a_recommended_attribute_counts_when_any_sample_had_it() -> None:
    data = _reduce(
        Observed(spans={"http.server": signal("url.scheme", every=False)}),
        MODEL,
    )

    assert data["spans"]["http.server"] == ["url.scheme"]


def test_an_attribute_the_registry_does_not_declare_is_not_coverage() -> None:
    data = _reduce(
        Observed(spans={"http.server": signal("something.custom")}), MODEL
    )

    assert data["spans"] == {}


def test_a_signal_the_registry_does_not_declare_is_dropped() -> None:
    data = _reduce(Observed(metrics={"custom.metric": signal("a")}), MODEL)

    assert data["metrics"] == {}


def test_a_metric_the_run_emitted_bare_is_still_recorded() -> None:
    """Emitting it is a fact; a span type recognised by nothing is not."""
    data = _reduce(
        Observed(
            metrics={"http.server.request.duration": Signal(count=1)},
            spans={"http.server": Signal(count=1)},
        ),
        MODEL,
    )

    assert data["metrics"] == {"http.server.request.duration": []}
    assert data["spans"] == {}


def test_every_section_is_present_even_when_empty() -> None:
    """A reader can tell "emitted none" from a file that says so."""
    assert _reduce(Observed(), MODEL) == {
        "spans": {},
        "events": {},
        "metrics": {},
    }


def test_the_file_is_written_in_a_stable_order() -> None:
    """These files are committed and diffed byte for byte."""
    data = _reduce(
        Observed(
            spans={
                "http.server": signal(
                    "url.scheme", "http.request.method", "client.port"
                )
            },
            metrics={"http.server.request.duration": signal("error.type")},
        ),
        MODEL,
    )

    assert list(data) == ["spans", "events", "metrics"]
    for section in data.values():
        assert list(section) == sorted(section)
    assert data["spans"]["http.server"] == sorted(
        data["spans"]["http.server"]
    )


def test_a_run_that_produced_no_reports_is_an_error(tmp_path) -> None:
    build = semconv_coverage(by_kind, lambda: MODEL)

    with pytest.raises(RuntimeError, match="produced nothing to record"):
        build(tmp_path / "missing", None)  # pyright: ignore[reportArgumentType]
