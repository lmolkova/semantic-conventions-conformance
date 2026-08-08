# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The coverage model: what a registry declares, per signal.

Weaver resolves a registry — including provider refinements, so
``openai.inference.client`` folds into the ``gen_ai.inference.client`` span
type it refines — into one JSON file::

    {"spans":   {"http.server": {"kind": "server", "attributes": {name: level}}},
     "events":  {name: {"attributes": {name: level}}},
     "metrics": {name: {"attributes": {name: level}}}}

That is what a reduction reads to say which of a signal's declared attributes
a run actually carried.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCRIPT = Path(__file__).parent / "collect-coverage-model.sh"


def resolve(registry: Path, output: Path) -> Path:
    """Resolve ``registry`` into a coverage model at ``output``, once.

    Callers put the output next to the fetched registry, so moving a pin asks
    for a fresh model rather than silently reusing the old registry's.
    """
    if output.is_file():
        return output

    logger.info("Resolving the coverage model into %s", output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(  # noqa: S603
        [str(_SCRIPT), str(registry), str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not output.is_file():
        raise RuntimeError(
            f"Could not resolve the coverage model for {registry}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return output


def load(path: Path) -> dict[str, dict[str, Any]]:
    """Read a resolved coverage model."""
    if not path.is_file():
        raise RuntimeError(
            f"{path} not found — resolve the registry into a coverage model "
            "before reducing a run."
        )
    return json.loads(path.read_text(encoding="utf-8"))
