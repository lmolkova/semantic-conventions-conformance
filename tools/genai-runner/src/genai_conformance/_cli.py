# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""``genai-conformance`` — the runner's CLI, wired to the GenAI defaults.

Every flag ``otel-conformance`` takes still works and still wins over the
defaults, so a scenario directory can point at its own registry — which is
what ``semantic-conventions-genai`` does to check its working tree.
"""

from __future__ import annotations

import sys

from opentelemetry.conformance import main as run_cli

from ._session import genai_session


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv, session=genai_session)


def cli() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli()
