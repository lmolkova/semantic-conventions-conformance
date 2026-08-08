# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conformance runs against the GenAI semantic conventions.

The whole domain: the ``semantic-conventions-genai`` registry at a pinned SHA,
the advice policies that check it, and how to recognise a GenAI span.
Everything a directory declaring ``runner: genai-conformance`` then gets is
the runner's :class:`~.Domain`.

The mock LLM server is not part of it: a directory declares the one it talks
to under ``server:``.
"""

from pathlib import Path

from opentelemetry.conformance import Domain, require_pin

from ._coverage import classifier

_HERE = Path(__file__).parent


def _advice_data(checkout: Path) -> str:
    """A ``--advice-data`` glob of the GenAI content JSON schemas.

    gen-ai-tool-definitions.json references the external draft-07 meta-schema,
    which weaver's rego engine refuses to fetch at eval time; rewrite that one
    $ref to a local object in place (idempotent).
    """
    source = checkout / "model" / "gen-ai"
    schema = source / "gen-ai-tool-definitions.json"
    text = schema.read_text(encoding="utf-8")
    patched = text.replace(
        '"$ref": "http://json-schema.org/draft-07/schema#"',
        '"type": "object"',
    )
    if patched != text:
        schema.write_text(patched, encoding="utf-8")
    return str(source / "*.json")


DOMAIN = Domain(
    name="genai-conformance",
    repo="open-telemetry/semantic-conventions-genai",
    ref=require_pin(_HERE / "versions.env", "SEMCONV_GENAI_REF"),
    classifier=classifier,
    policies=_HERE / "policies",
    advice_data=_advice_data,
)

# Named in pyproject.toml: the runner entry point and the console script.
genai_session = DOMAIN.session
cli = DOMAIN.cli

__all__ = ["DOMAIN", "cli", "genai_session"]
