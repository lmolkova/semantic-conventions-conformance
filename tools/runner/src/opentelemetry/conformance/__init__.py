# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Semantic-convention conformance runner.

A scenario is a standalone program that enables instrumentation and exercises
the library — no providers, no test helpers, no cassettes. Everything else
lives in sibling non-code files inside the scenario directory:

- ``<name>.py`` — the scenario program
- ``conformance.yaml`` — the environment each scenario runs with, how to run
  it, and what it must produce
- ``data.json`` — generated attribute coverage, committed

The runner carries no semantic conventions of its own: the caller says which
registry and policies to check against, and which server the scenarios talk
to. The core is a plain library that owns the server and weaver lifecycles::

    with conformance_session(conformance_dir) as session:
        report = session.run("inference")

``run`` returns rather than raises whatever the scenario got wrong — a count
mismatch, a crash — in ``report.failures``, and what it emitted that departs
from the conventions in ``report.violations``; only a broken harness (an
unknown scenario name, a registry that won't load) raises. pytest asserts on
both, the CLI turns them into an exit code (``--report-only`` warns about the
violations), and calling the library directly gives a full report and no
failure signal, which is the recording workflow.
"""

from ._cli import main
from ._coverage import coverage
from ._session import (
    ConformanceSession,
    ScenarioReport,
    SessionFactory,
    conformance_session,
)
from ._spec import (
    AttributeMatcher,
    ExpectedViolation,
    PackageSpec,
    ScenarioSpec,
    ServerSpec,
    SpanExpectation,
    SpanMatch,
    SpecError,
    WeaverSpec,
    load_spec,
    scenarios,
)

__all__ = [
    "AttributeMatcher",
    "ConformanceSession",
    "coverage",
    "ExpectedViolation",
    "PackageSpec",
    "ScenarioReport",
    "ScenarioSpec",
    "ServerSpec",
    "SessionFactory",
    "SpanExpectation",
    "SpanMatch",
    "SpecError",
    "WeaverSpec",
    "conformance_session",
    "load_spec",
    "main",
    "scenarios",
]
