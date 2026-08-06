# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Collecting ``conformance.yaml`` as a test file.

A scenario directory already declares everything a test needs, so no repo
should have to write a module that points at it. These run pytest inside
pytest, with a stub factory standing in for a real session — starting weaver
is the session's job, not the plugin's.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]

SPEC = """
library: demo
scenarios:
  inference:
    run: python inference.py
  tool_calling:
    run: python tool_calling.py
"""

# A factory that never starts weaver: it logs each session it opens, and fails
# whichever scenarios the test names.
CONFTEST = """
from contextlib import contextmanager
from pathlib import Path

FAILING = {failing!r}


class FakeSession:
    def run(self, name):
        from opentelemetry.conformance import ScenarioReport

        return ScenarioReport(
            name=name,
            failures=[name + ": nope"] if name in FAILING else [],
        )


@contextmanager
def factory(directory, **kwargs):
    with Path("opened.log").open("a") as log:
        log.write(str(directory) + chr(10))
    yield FakeSession()


def pytest_conformance_session_factory():
    return factory
"""


@pytest.fixture(name="scenarios")
def _scenarios(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
    """A scenario directory, with weaver pretended present."""
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/bin/weaver" if name == "weaver" else None,
    )

    def build(failing: frozenset[str] = frozenset()) -> None:
        pytester.makeconftest(CONFTEST.format(failing=set(failing)))
        pytester.makefile(".yaml", **{"conformance/conformance": SPEC})

    return build


def test_each_declared_scenario_becomes_a_test(pytester, scenarios) -> None:
    scenarios()

    result = pytester.runpytest("-v")

    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(
        ["*conformance.yaml::inference*", "*conformance.yaml::tool_calling*"]
    )


def test_a_scenarios_failures_are_the_test_failure(
    pytester, scenarios
) -> None:
    scenarios(failing=frozenset({"inference"}))

    result = pytester.runpytest()

    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*inference: nope*"])


def test_one_session_is_shared_by_a_directory(pytester, scenarios) -> None:
    """So a declared server and `setup` run once, not per scenario."""
    scenarios()

    result = pytester.runpytest()

    result.assert_outcomes(passed=2)
    opened = (pytester.path / "opened.log").read_text().splitlines()
    assert len(opened) == 1, opened


def test_a_broken_spec_is_a_collection_error(pytester, scenarios) -> None:
    scenarios()
    pytester.makefile(
        ".yaml", **{"conformance/conformance": "library: demo\n"}
    )

    result = pytester.runpytest()

    result.stdout.fnmatch_lines(["*declares no scenarios*"])


def test_without_weaver_the_scenarios_skip(
    pytester, scenarios, monkeypatch
) -> None:
    """A machine without the binary shouldn't fail an unrelated test run."""
    scenarios()
    monkeypatch.setattr("shutil.which", lambda _name: None)

    result = pytester.runpytest()

    result.assert_outcomes(skipped=2)
