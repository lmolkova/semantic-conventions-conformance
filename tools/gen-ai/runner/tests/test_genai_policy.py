# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""GenAI advice policy behavior."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from genai_conformance import DOMAIN, _advice_data
from opentelemetry.conformance import WeaverNotInstalledError, check_weaver

_POLICIES = Path(__file__).parents[1] / "src/genai_conformance/policies"
_RESPONSE_DERIVED = {
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.embeddings.dimension.count",
}


def _embeddings_span(
    model: str, *, error: bool = False, provider: bool = True
) -> dict[str, Any]:
    attributes: dict[str, object] = {
        "gen_ai.operation.name": "embeddings",
        "gen_ai.request.model": model,
        "server.address": "localhost",
        "server.port": 8080,
    }
    if provider:
        attributes["gen_ai.provider.name"] = "openai"
    span: dict[str, Any] = {
        "name": f"embeddings {model}",
        "kind": "client",
        "attributes": [
            {"name": key, "value": value} for key, value in attributes.items()
        ],
    }
    if error:
        span["attributes"].append({"name": "error.type", "value": "400"})
        span["status"] = {"code": "error", "message": "bad request"}
    return {"span": span}


@pytest.fixture(scope="module")
def missing_attributes(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, set[str]]:
    """Span name -> attributes reported by ``genai_expected_attribute_missing``."""
    try:
        check_weaver()
        registry = DOMAIN.registry
        advice_data = _advice_data(registry)
    except (WeaverNotInstalledError, OSError, RuntimeError) as error:
        pytest.skip(f"GenAI policy test unavailable: {error}")

    root = tmp_path_factory.mktemp("genai-policy")
    input_path = root / "input.json"
    report_dir = root / "report"
    input_path.write_text(
        json.dumps(
            [
                _embeddings_span("ok-model"),
                _embeddings_span("error-model", error=True),
                _embeddings_span("error-no-provider", error=True, provider=False),
            ]
        ),
        encoding="utf-8",
    )

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
            str(_POLICIES),
            "--advice-data",
            advice_data,
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
    return {
        span["name"]: {
            advice["context"]["missing_attribute"]
            for advice in span["live_check_result"]["all_advice"]
            if advice["id"] == "genai_expected_attribute_missing"
        }
        for sample in report["samples"]
        if (span := sample.get("span")) is not None
    }


def test_successful_span_is_expected_to_carry_response_attributes(
    missing_attributes: dict[str, set[str]],
) -> None:
    assert _RESPONSE_DERIVED <= missing_attributes["embeddings ok-model"]


def test_failed_span_is_not_expected_to_carry_response_attributes(
    missing_attributes: dict[str, set[str]],
) -> None:
    assert not _RESPONSE_DERIVED & missing_attributes["embeddings error-model"]


def test_failed_span_is_still_expected_to_carry_request_attributes(
    missing_attributes: dict[str, set[str]],
) -> None:
    assert "gen_ai.provider.name" in missing_attributes[
        "embeddings error-no-provider"
    ]
