# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conformance runs against the GenAI semantic conventions.

``genai_session`` is ``opentelemetry.conformance.conformance_session`` with
the registry, advice policies and mock LLM server already wired in, so a
scenario directory only declares what it runs and what it must produce::

    with genai_session(directory) as session:
        report = session.run("inference")

The same wiring drives the CLI, ``genai-conformance <dir> [--scenario N]``.
"""

from ._cli import main
from ._coverage import genai_coverage
from ._registry import (
    advice_data_glob,
    check_weaver_version,
    policies_dir,
    semconv_registry,
    weaver_config_file,
)
from ._session import genai_session, server_defaults, weaver_defaults

__all__ = [
    "advice_data_glob",
    "check_weaver_version",
    "genai_coverage",
    "genai_session",
    "main",
    "policies_dir",
    "semconv_registry",
    "server_defaults",
    "weaver_config_file",
    "weaver_defaults",
]
