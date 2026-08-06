# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""What a run observed, reduced to one file.

The default reduction, and the reason a repo needs no code of its own to get
a coverage artifact: for every span expectation a scenario declares, the
attributes its spans actually carried, plus the metrics and events the run
produced. A caller wanting a different shape passes its own reduction.

A run *always* reduces to what it saw, however badly it went. Coverage is an
observation, and an implementation that violates the conventions everywhere is
exactly the one worth having a record of. So a span no expectation selected —
including every span, when a scenario declares none — is still counted, keyed
by its kind.
"""

from __future__ import annotations

import json
from pathlib import Path

from ._checks import observed_spans, seen_events, seen_metrics, selects
from ._spec import PackageSpec, SpanMatch


def coverage(report_dir: Path, spec: PackageSpec) -> dict[str, object]:
    """Reduce a run's weaver reports into observed coverage."""
    attributes: dict[str, set[str]] = {}
    metrics: set[str] = set()
    events: set[str] = set()

    for name, scenario in spec.scenarios.items():
        report_file = report_dir / f"{name}.json"
        if not report_file.is_file():
            continue
        report = json.loads(report_file.read_text())
        statistics = report.get("statistics", {})
        metrics |= seen_metrics(statistics)
        events |= seen_events(statistics)

        spans = observed_spans(report)
        selected: set[int] = set()
        for expectation in scenario.spans or ():
            matched = attributes.setdefault(expectation.match.key(), set())
            for index, span in enumerate(spans):
                if selects(expectation, span):
                    matched.update(span.attributes)
                    selected.add(index)

        for index, span in enumerate(spans):
            if index in selected:
                continue
            key = SpanMatch(attributes={}, kind=span.kind).key()
            attributes.setdefault(key, set()).update(span.attributes)

    return {
        "spans": {
            key: sorted(values) for key, values in sorted(attributes.items())
        },
        "metrics": sorted(metrics),
        "events": sorted(events),
    }
