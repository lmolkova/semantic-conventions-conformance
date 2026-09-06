# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Render scenario instrumentation-scope expectations as a Rego policy."""

from __future__ import annotations

import json
from pathlib import Path

from ._spec import AttributeMatcher, InstrumentationScopeExpectation

_TEMPLATE = (
    Path(__file__).parent
    / "policies"
    / "instrumentation_scope_validation.rego.template"
)
_MARKER = "__INSTRUMENTATION_SCOPE_EXPECTATION__"


def render(expectation: InstrumentationScopeExpectation) -> str:
    """Return a policy containing exactly the fields this scenario checks."""
    fields: dict[str, dict[str, object]] = {}
    if expectation.name is not None:
        fields["name"] = {"equals": expectation.name}
    for name, matcher in (
        ("version", expectation.version),
        ("schema_url", expectation.schema_url),
    ):
        if matcher is not None:
            fields[name] = _matcher(matcher)

    return _TEMPLATE.read_text(encoding="utf-8").replace(
        _MARKER, json.dumps(fields, sort_keys=True)
    )


def _matcher(matcher: AttributeMatcher) -> dict[str, object]:
    if matcher.present is not None:
        return {"present": matcher.present}
    return {"equals": matcher.equals}
