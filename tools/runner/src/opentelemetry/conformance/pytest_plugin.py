# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Collect ``conformance.yaml`` as a test file, one test per scenario.

A scenario directory already says everything a test needs — how to run each
program and what it must produce — so pytest collects the YAML directly rather
than each repo writing a module to point at it. ``pytest tests/`` reports
``conformance.yaml::inference``.

The session is opened once per directory and closed when the run ends, which
is what lets a complete run write its data file. Which session — which
registry, server and reduction — comes from the
:func:`pytest_conformance_session_factory` hook.
"""

from __future__ import annotations

import shutil
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from ._session import conformance_session
from ._spec import SPEC_FILE, SpecError, scenarios

if TYPE_CHECKING:
    from ._session import ConformanceSession, SessionFactory

_SESSIONS = pytest.StashKey[dict[Path, "ConformanceSession"]]()
_STACK = pytest.StashKey[ExitStack]()


def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    from . import _hookspec  # noqa: PLC0415

    pluginmanager.add_hookspecs(_hookspec)


def pytest_configure(config: pytest.Config) -> None:
    config.stash[_SESSIONS] = {}
    config.stash[_STACK] = ExitStack()


def pytest_unconfigure(config: pytest.Config) -> None:
    # Closing writes each session's data file, so it has to happen even when
    # the run failed — a reduction is an observation, not a reward.
    stack = config.stash.get(_STACK, None)
    if stack is not None:
        stack.close()


def pytest_collect_file(
    file_path: Path, parent: pytest.Collector
) -> pytest.Collector | None:
    if file_path.name != SPEC_FILE:
        return None
    return ConformanceFile.from_parent(  # pyright: ignore[reportUnknownMemberType]
        parent, path=file_path
    )


class ConformanceFile(pytest.File):
    """One scenario directory: its declared scenarios become the tests."""

    def collect(self) -> Any:
        try:
            declared = scenarios(self.path.parent)
        except SpecError as error:
            raise pytest.Collector.CollectError(str(error)) from error
        for name in declared:
            yield ConformanceItem.from_parent(  # pyright: ignore[reportUnknownMemberType]
                self, name=name
            )


class ConformanceItem(pytest.Item):
    """One scenario, run under its own live-check."""

    def runtest(self) -> None:
        session = _session_for(self.config, self.path.parent)
        report = session.run(self.name)
        if report.failures:
            raise ConformanceFailure("\n".join(report.failures))

    def repr_failure(self, excinfo: Any, style: Any = None) -> str:
        if isinstance(excinfo.value, ConformanceFailure):
            return str(excinfo.value)
        # The base returns a rich representation; the caller only wants
        # something to print.
        return str(super().repr_failure(excinfo, style))

    def reportinfo(self) -> tuple[Path, int, str]:
        return self.path, 0, self.name


class ConformanceFailure(Exception):
    """What a scenario got wrong, already formatted by the runner."""


def _session_for(config: pytest.Config, directory: Path) -> ConformanceSession:
    """The session for ``directory``, opened once and shared by its scenarios.

    Shared so a declared server and the ``setup`` command run once rather than
    per scenario; weaver is still started and ended around each one.
    """
    sessions = config.stash[_SESSIONS]
    if directory in sessions:
        return sessions[directory]

    if shutil.which("weaver") is None:
        pytest.skip(
            "weaver binary not on PATH — install it from "
            "https://github.com/open-telemetry/weaver/releases"
        )

    factory: SessionFactory = (
        config.hook.pytest_conformance_session_factory() or conformance_session
    )
    # A session that won't open — an unreachable registry, a broken pin, a
    # server that never came up — is a failure, not a skip: skipping would
    # report a green run that checked nothing.
    session = config.stash[_STACK].enter_context(factory(directory))
    sessions[directory] = session
    return session
