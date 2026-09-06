# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Instrumentation scope expectations are recorded as weaver findings."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from http_conformance import DOMAIN
from opentelemetry.conformance import WeaverNotInstalledError, check_weaver
from opentelemetry.conformance._scope_policy import render
from opentelemetry.conformance._spec import (
    AttributeMatcher,
    InstrumentationScopeExpectation,
    SpanExpectation,
    SpanMatch,
)


def test_scope_findings_are_in_weaver_report(tmp_path: Path) -> None:
    try:
        check_weaver()
        registry = DOMAIN.registry
    except (WeaverNotInstalledError, OSError, RuntimeError) as error:
        pytest.skip(f"scope policy test unavailable: {error}")

    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "instrumentation_scope_validation.rego").write_text(
        render(
            InstrumentationScopeExpectation(
                schema_url=AttributeMatcher(present=True)
            ),
            None,
        ),
        encoding="utf-8",
    )
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "instrumentation_scope": {
                        "name": "has-schema",
                        "version": "1.0.0",
                        "schema_url": "https://example.test/schema/1.0.0",
                        "attributes": [],
                    }
                },
                {
                    "instrumentation_scope": {
                        "name": "missing-schema",
                        "version": "1.0.0",
                        "schema_url": "",
                        "attributes": [],
                    }
                },
                {
                    "span": {
                        "name": "missing-scope",
                        "kind": "client",
                        "attributes": [],
                    }
                },
            ]
        ),
        encoding="utf-8",
    )
    report_dir = tmp_path / "report"

    result = subprocess.run(
        [
            "weaver",
            "registry",
            "live-check",
            "--quiet",
            "--registry",
            str(registry),
            "--input-source",
            str(input_path),
            "--advice-policies",
            str(policies),
            "--format",
            "json",
            "--fail-on",
            "none",
            "--no-stream",
            "--output",
            str(report_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    report: dict[str, Any] = json.loads(
        (report_dir / "live_check.json").read_text(encoding="utf-8")
    )
    scopes = {
        scope["name"]: scope["live_check_result"]["all_advice"]
        for sample in report["samples"]
        if (scope := sample.get("instrumentation_scope")) is not None
    }
    assert scopes["has-schema"] == []
    assert [finding["id"] for finding in scopes["missing-schema"]] == [
        "instrumentation_scope_schema_url_missing"
    ]
    assert scopes["missing-schema"][0]["message"] == (
        "Instrumentation scope 'missing-schema' does not have schema_url."
    )
    unscoped_span = next(
        sample["span"]
        for sample in report["samples"]
        if sample.get("span", {}).get("name") == "missing-scope"
    )
    assert unscoped_span["live_check_result"]["all_advice"] == [
        {
            "context": {
                "actual": None,
                "expected": {"present": True},
            },
            "id": "instrumentation_scope_schema_url_missing",
            "level": "violation",
            "message": (
                "Instrumentation scope '<missing>' does not have schema_url."
            ),
            "signal_name": "missing-scope",
            "signal_type": "span",
            "type": "PolicyFinding",
        }
    ]


def test_signal_scope_expectation_uses_owning_scope(tmp_path: Path) -> None:
    try:
        check_weaver()
        registry = DOMAIN.registry
    except (WeaverNotInstalledError, OSError, RuntimeError) as error:
        pytest.skip(f"scope policy test unavailable: {error}")
    trace = pytest.importorskip("opentelemetry.trace")
    trace_exporter = pytest.importorskip(
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter"
    )
    sdk_trace = pytest.importorskip("opentelemetry.sdk.trace")
    sdk_trace_export = pytest.importorskip("opentelemetry.sdk.trace.export")
    weaver_live_check = pytest.importorskip(
        "opentelemetry.test.weaver_live_check"
    )

    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "instrumentation_scope_validation.rego").write_text(
        render(
            None,
            (
                SpanExpectation(
                    match=SpanMatch(
                        attributes={"operation": "chat"}, kind="CLIENT"
                    ),
                    instrumentation_scope=InstrumentationScopeExpectation(
                        name=AttributeMatcher(equals="expected-scope")
                    ),
                ),
            ),
        ),
        encoding="utf-8",
    )
    weaver = weaver_live_check.WeaverLiveCheck(
        registry=str(registry), policies_dir=str(policies)
    ).start()
    try:
        provider = sdk_trace.TracerProvider()
        provider.add_span_processor(
            sdk_trace_export.SimpleSpanProcessor(
                trace_exporter.OTLPSpanExporter(
                    endpoint=weaver.otlp_endpoint, insecure=True
                )
            )
        )
        tracer = provider.get_tracer(
            "actual-scope",
            "1.2.3",
            schema_url="https://example.test/schema/1.0.0",
        )
        with tracer.start_as_current_span(
            "scoped-span", kind=trace.SpanKind.CLIENT
        ) as span:
            span.set_attribute("operation", "chat")
        provider.shutdown()
        report = weaver.end()
    finally:
        weaver.close()

    scoped_span = next(
        sample["span"]
        for sample in report["samples"]
        if sample.get("span", {}).get("name") == "scoped-span"
    )
    finding = next(
        finding
        for finding in scoped_span["live_check_result"]["all_advice"]
        if finding["id"] == "instrumentation_scope_name_mismatch"
    )
    assert finding["context"] == {
        "actual": "actual-scope",
        "expected": {"equals": "expected-scope"},
    }
    assert finding["signal_type"] == "span"
    assert finding["signal_name"] == "scoped-span"
