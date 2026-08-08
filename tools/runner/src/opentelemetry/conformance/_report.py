# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""A run's weaver reports, read as "what each signal carried".

One :class:`Observed` over every report in a directory. Per span type, per
metric and per event it records two attribute sets: those present on *every*
sample of that signal, and those present on *any*. That distinction is what
lets a reduction say "this implementation always sets the required ones"
rather than "it set them once".

A span becomes a span *type* through a ``classify`` callable — the registry
declares what a type carries but not how to recognise one, so that knowledge
belongs to the conventions, not here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, cast

# A span's name, kind and attributes → the registry span types it belongs to.
ClassifySpan = Callable[[str, str, Mapping[str, object]], "set[str]"]

_Json = Mapping[str, object]


@dataclass
class Signal:
    """What one signal carried across every sample of it in a run."""

    count: int = 0
    # ``None`` until the first sample, which keeps "counted but never sampled"
    # distinct from "sampled carrying nothing".
    on_every: set[str] | None = None
    on_any: set[str] = field(default_factory=set[str])

    def add(self, attributes: set[str]) -> None:
        self.count += 1
        if self.on_every is None:
            self.on_every = set(attributes)
        else:
            self.on_every &= attributes
        self.on_any |= attributes


@dataclass
class Observed:
    """Every signal a run produced, keyed by span type, metric or event name."""

    spans: dict[str, Signal] = field(default_factory=dict[str, Signal])
    metrics: dict[str, Signal] = field(default_factory=dict[str, Signal])
    events: dict[str, Signal] = field(default_factory=dict[str, Signal])


def read(report_dir: Path, classify: ClassifySpan) -> Observed:
    """Read every weaver report under ``report_dir`` into one :class:`Observed`."""
    observed = Observed()
    counted: dict[str, dict[str, int]] = {}

    for path in sorted(report_dir.glob("**/*.json")):
        report = cast("object", json.loads(path.read_text(encoding="utf-8")))
        if not isinstance(report, dict):
            continue
        document = cast(_Json, report)
        _merge_counts(counted, _mapping(document.get("statistics")))
        for sample in _list(document.get("samples")):
            _read_sample(observed, sample, classify)

    # Weaver counts signals it kept no sample of. Record those too, with no
    # attributes — there is nothing to read them off.
    for key, signals in (
        ("seen_registry_metrics", observed.metrics),
        ("seen_registry_events", observed.events),
    ):
        for name, count in counted.get(key, {}).items():
            signal = signals.setdefault(name, Signal())
            signal.count = max(signal.count, count)

    return observed


_COUNT_KEYS = ("seen_registry_metrics", "seen_registry_events")


def _merge_counts(into: dict[str, dict[str, int]], statistics: _Json) -> None:
    """Merge one report's non-zero counts, keeping the larger of each.

    A directory holds one report per scenario and a signal may appear in
    several, so the run saw a signal if any scenario did.
    """
    for key in _COUNT_KEYS:
        merged = into.setdefault(key, {})
        for name, count in _mapping(statistics.get(key)).items():
            if isinstance(count, int) and count > 0:
                merged[name] = max(merged.get(name, 0), count)


def _read_sample(
    observed: Observed, sample: object, classify: ClassifySpan
) -> None:
    if not isinstance(sample, dict):
        return
    entry = cast(_Json, sample)

    span = _mapping(entry.get("span"))
    if span:
        attributes = _attributes(span)
        names = set(attributes)
        for span_type in classify(
            str(span.get("name", "")), str(span.get("kind", "")), attributes
        ):
            observed.spans.setdefault(span_type, Signal()).add(names)

    metric = _mapping(entry.get("metric"))
    if metric.get("name"):
        observed.metrics.setdefault(str(metric["name"]), Signal()).add(
            _data_point_attributes(metric)
        )

    log = _mapping(entry.get("log"))
    if log.get("event_name"):
        observed.events.setdefault(str(log["event_name"]), Signal()).add(
            set(_attributes(log))
        )


def _data_point_attributes(metric: _Json) -> set[str]:
    """Every attribute name across a metric's data points.

    A metric's attributes are per data point, and a run's points differ by
    exactly the dimensions being recorded, so the union is what it carried.
    """
    return {
        name
        for point in _list(metric.get("data_points"))
        for name in _attributes(_mapping(point))
    }


def _attributes(owner: _Json) -> dict[str, object]:
    """The owner's attributes by name, dropping any weaver rejected."""
    attributes: dict[str, object] = {}
    for record in _list(owner.get("attributes")):
        attribute = _mapping(record)
        name = attribute.get("name")
        if isinstance(name, str) and name and _counts_as_present(attribute):
            attributes[name] = attribute.get("value")
    return attributes


def _counts_as_present(attribute: _Json) -> bool:
    """An attribute whose value weaver rejected didn't really arrive.

    A ``type_mismatch`` means the name is there but holding something the
    registry doesn't allow — recording it as coverage would claim conformance
    the run didn't have.
    """
    result = _mapping(attribute.get("live_check_result"))
    return not any(
        _mapping(advice).get("id") == "type_mismatch"
        for advice in _list(result.get("all_advice"))
    )


def _mapping(value: object) -> _Json:
    """A JSON object, or an empty one — reports are read defensively."""
    return cast(_Json, value) if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []
