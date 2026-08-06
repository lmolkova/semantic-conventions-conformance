# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The conformance session — a plain library, free of pytest.

It owns the server and weaver lifecycles so a pytest fixture and the
CLI are thin wrappers over the same entry point, and it never raises for
something a scenario got wrong: that lands in ``ScenarioReport.failures`` and
the caller decides what it means. A broken harness still raises.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from string import Template
from types import TracebackType
from typing import TYPE_CHECKING, Callable, Generator, Mapping, Protocol

from ._checks import check
from ._coverage import coverage
from ._env import (
    METRIC_EXPORT_INTERVAL_MILLIS,
    build_env,
    timeout_seconds,
)
from ._server import Server
from ._spec import (
    PackageSpec,
    ScenarioSpec,
    ServerSpec,
    SpecError,
    WeaverSpec,
    load_spec,
)

if TYPE_CHECKING:
    from opentelemetry.test.weaver_live_check import LiveCheckReport

# A cold scenario subprocess can spend a while importing a large framework
# before it emits anything, and a slow run costs nothing. Each is overridable
# through the environment; see ``timeout_seconds``.
_WEAVER_INACTIVITY_TIMEOUT = (
    "OTEL_CONFORMANCE_WEAVER_INACTIVITY_TIMEOUT",
    300.0,
)
_WEAVER_STOP_TIMEOUT = ("OTEL_CONFORMANCE_WEAVER_STOP_TIMEOUT", 120.0)
_SCENARIO_TIMEOUT = ("OTEL_CONFORMANCE_SCENARIO_TIMEOUT", 600.0)

# Both artifacts a run produces. The raw reports are one per scenario and
# usually throwaway; the data file is one reduction over the run and usually
# committed. Each is configured on its own.
# The report directory is relative to the scenario directory; the data file to
# the working directory, since it is one file for however many packages ran.
DEFAULT_REPORT_DIR = Path("output") / "weaver-reports"
DEFAULT_DATA_FILE = Path("output") / "data.json"


class SessionFactory(Protocol):
    """What ``conformance_session`` is, as a type.

    A repo wraps it to bake in its own registry and server — see
    ``genai_conformance`` — and passes the wrapper wherever a session is
    opened, including to the CLI.
    """

    def __call__(
        self,
        directory: Path | str,
        *,
        report_dir: Path | str | None = ...,
        data_file: Path | str | None = ...,
        variables: Mapping[str, str] | None = ...,
        weaver: WeaverSpec | None = ...,
        server: ServerSpec | None = ...,
        env: Mapping[str, str] | None = ...,
        build_data: Callable[[Path, PackageSpec], object] = ...,
    ) -> AbstractContextManager[ConformanceSession]: ...


@dataclass(frozen=True)
class ScenarioReport:
    """What one scenario produced, and every way it fell short."""

    name: str
    failures: list[str]
    report: LiveCheckReport | None = None
    stdout: str = ""
    stderr: str = ""


class ConformanceSession:
    """Runs a package's scenarios against a mock server and weaver."""

    def __init__(
        self,
        spec: PackageSpec,
        report_dir: Path,
        *,
        variables: Mapping[str, str],
        weaver: WeaverSpec,
        env: Mapping[str, str],
        data_file: Path,
        build_data: Callable[[Path, PackageSpec], object],
    ) -> None:
        if weaver.registry is None:
            raise SpecError(
                f"{spec.directory}: no weaver registry — declare one under "
                "weaver: in conformance.yaml, or pass a default"
            )
        self._spec = spec
        self._report_dir = report_dir
        self._variables = dict(variables)
        self._weaver = weaver
        self._registry = weaver.registry
        self._default_env = dict(env)
        self._data_file = data_file
        self._build_data = build_data
        self._ran: set[str] = set()

    @property
    def spec(self) -> PackageSpec:
        return self._spec

    def run(self, name: str) -> ScenarioReport:
        """Run one scenario under a fresh weaver live-check."""
        scenario = self._spec.scenarios.get(name)
        if scenario is None:
            raise KeyError(
                f"{name!r} is not declared in {self._spec.directory}; "
                f"declared: {sorted(self._spec.scenarios)}"
            )
        self._ran.add(name)

        from opentelemetry.test.weaver_live_check import (  # noqa: PLC0415
            WeaverLiveCheck,
        )

        weaver_spec = self._weaver
        extra_args: list[str] = []
        if weaver_spec.config:
            extra_args += ["--config", self._resolve_path(weaver_spec.config)]
        if weaver_spec.advice_data:
            extra_args += [
                "--advice-data",
                self._resolve_path(weaver_spec.advice_data),
            ]

        with WeaverLiveCheck(
            inactivity_timeout=int(timeout_seconds(*_WEAVER_INACTIVITY_TIMEOUT)),
            registry=self._resolve_path(self._registry),
            policies_dir=self._resolve_path(weaver_spec.policies)
            if weaver_spec.policies
            else None,
            extra_args=extra_args,
        ) as weaver:
            completed = self._execute(scenario, weaver.otlp_endpoint)
            report = weaver.end(
                timeout=int(timeout_seconds(*_WEAVER_STOP_TIMEOUT))
            )

        # The report is an observation, not a judgement: dump it before the
        # checks so a failing run still leaves something to read.
        self._dump(name, report)

        failures: list[str] = []
        if completed.returncode != 0:
            failures.append(
                f"{name}: scenario exited with {completed.returncode}\n"
                f"--- stdout ---\n{completed.stdout}\n"
                f"--- stderr ---\n{completed.stderr}"
            )
        failures += check(scenario, report)
        return ScenarioReport(
            name=name,
            failures=failures,
            report=report,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def _resolve(self, value: str) -> str:
        return Template(value).safe_substitute(self._variables)

    def _resolve_path(self, value: str) -> str:
        """Resolve a declared path, relative ones against the package.

        A path in a config file reads as relative to that file, not to
        wherever the runner happens to be invoked from.
        """
        resolved = self._resolve(value)
        if Path(resolved).is_absolute():
            return resolved
        return str(self._spec.directory / resolved)

    def _execute(
        self, scenario: ScenarioSpec, otlp_endpoint: str
    ) -> subprocess.CompletedProcess[str]:
        return _run_command(
            scenario.run,
            cwd=scenario.directory,
            env=self._env(
                scenario.env,
                {
                    "OTEL_EXPORTER_OTLP_ENDPOINT": otlp_endpoint,
                    "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
                    "OTEL_METRIC_EXPORT_INTERVAL": str(
                        METRIC_EXPORT_INTERVAL_MILLIS
                    ),
                },
            ),
        )

    def _env(
        self, declared: Mapping[str, str], extra: Mapping[str, str]
    ) -> dict[str, str]:
        return build_env(
            self._default_env,
            self._spec.env,
            declared,
            injected={**self._variables, **extra},
        )

    def setup(self) -> subprocess.CompletedProcess[str] | None:
        """Run the package's ``setup`` command, if it declares one.

        No OTLP endpoint is in its environment, so whatever it emits stays
        invisible to the checks.
        """
        if self._spec.setup is None:
            return None
        completed = _run_command(
            self._spec.setup,
            cwd=self._spec.directory,
            env=self._env({}, {}),
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"setup command {self._spec.setup} failed with "
                f"{completed.returncode}\n"
                f"--- stdout ---\n{completed.stdout}\n"
                f"--- stderr ---\n{completed.stderr}"
            )
        return completed

    def _dump(self, name: str, report: LiveCheckReport) -> None:
        self._report_dir.mkdir(parents=True, exist_ok=True)
        (self._report_dir / f"{name}.json").write_text(
            # The report's own dict; weaver_live_check exposes no public
            # accessor for it yet.
            json.dumps(  # noqa: SLF001
                report._report,  # pyright: ignore[reportPrivateUsage]
                indent=2,
                sort_keys=True,
            )
        )

    def close(self) -> None:
        """Write the data file, if the run was complete and can produce one.

        A reduction over the reports (coverage data, a summary) only holds
        across a whole run, so a filtered one is skipped rather than left to
        write something partial.

        Scenarios that failed still count as complete. A violation is the
        result this repo is after, not an error — the data file records what
        a run emitted either way. Only a run that *raised* is incomplete, and
        :meth:`__exit__` skips this then.
        """
        if self._ran != set(self._spec.scenarios):
            return
        data = self._build_data(self._report_dir, self._spec)
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        self._data_file.write_text(json.dumps(data, indent=2) + "\n")

    def __enter__(self) -> ConformanceSession:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # A run that raised stopped partway through — the harness broke, the
        # caller bailed out — so its reports cover only part of the run and
        # reducing them would overwrite a committed data file with a
        # half-run. Scenario failures don't come through here; they are
        # returned in the report, and still produce data.
        if exc_type is None:
            self.close()


def _run_command(
    command: tuple[str, ...], *, cwd: Path, env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run a declared command, reporting its own failures as a failed run.

    A command that can't be started or that overruns is the same class of
    problem as one that exits non-zero — something the declaring package got
    wrong — so it comes back as a result rather than an exception.
    """
    limit = timeout_seconds(*_SCENARIO_TIMEOUT)
    try:
        return subprocess.run(  # noqa: S603
            command,
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=limit,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return _failed(
            command,
            f"did not finish within {limit}s",
            stdout=_text(expired.stdout),
            stderr=_text(expired.stderr),
        )
    except OSError as error:
        return _failed(command, str(error))


def _failed(
    command: tuple[str, ...],
    reason: str,
    *,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=list(command),
        returncode=1,
        stdout=stdout,
        stderr=f"{shlex.join(command)}: {reason}\n{stderr}",
    )


def _text(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return output


def _default_report_dir(directory: Path) -> Path:
    """Where a scenario directory's reports go, by default.

    Inside the scenario directory, so sibling implementations of the same
    library — which run the same scenario names — don't write over each other,
    and so a run lands in the same place however it was invoked. Anchoring
    this to the working directory instead would move the reports when pytest
    picks a different one than the shell did.
    """
    return directory / DEFAULT_REPORT_DIR


@contextmanager
def conformance_session(
    directory: Path | str,
    *,
    report_dir: Path | str | None = None,
    data_file: Path | str | None = None,
    variables: Mapping[str, str] | None = None,
    weaver: WeaverSpec | None = None,
    server: ServerSpec | None = None,
    env: Mapping[str, str] | None = None,
    build_data: Callable[[Path, PackageSpec], object] = coverage,
) -> Generator[ConformanceSession, None, None]:
    """Open a session over the conformance directory at ``directory``.

    ``variables`` are substituted into the ``${...}`` references in the
    package's ``weaver`` and ``env`` blocks — that is how a registry
    provisioned at run time, or a server started by this session, reaches a
    committed YAML file.

    ``weaver``, ``server`` and ``env`` are defaults for what the package
    doesn't declare itself, so the wiring common to every package lives with
    the runner rather than being repeated in each YAML file. Declare relative
    paths in ``weaver`` only from a package file — a default is resolved
    against each package directory in turn.

    A declared ``server`` runs for the session and publishes its base URL to
    the scenarios under its ``url_var``.

    A run produces two things, configured independently. ``report_dir`` holds
    one raw weaver report per scenario, ``<scenario>.json``, replaced each time
    that scenario runs and otherwise left alone — so running one scenario
    doesn't discard what the others last reported. It defaults to
    ``output/weaver-reports/`` inside ``directory``, so sibling scenario
    directories don't land on top of each other wherever the run started.
    ``build_data``, given that directory and the spec after a complete run,
    returns the data to write to ``data_file`` — one reduction over the run,
    ``output/data.json`` by default. It defaults to the coverage this package
    computes: the attributes each declared span carried, and the metrics and
    events the run produced.
    """
    spec = load_spec(Path(directory))
    reports = (
        Path(report_dir)
        if report_dir is not None
        else _default_report_dir(Path(directory))
    )
    reports.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        resolved = dict(variables or {})
        declared_server = spec.server.over(server or ServerSpec())
        if declared_server.run is not None:
            running = stack.enter_context(
                Server(
                    declared_server.run,
                    health_path=declared_server.health_path,
                )
            )
            resolved[declared_server.url_variable] = running.url

        # Constructing the session is what rejects a run with no registry, so
        # it is checked once and before any scenario has run.
        session = ConformanceSession(
            spec,
            reports,
            variables=resolved,
            weaver=spec.weaver.over(weaver or WeaverSpec()),
            env=env or {},
            data_file=Path(data_file)
            if data_file is not None
            else DEFAULT_DATA_FILE,
            build_data=build_data,
        )
        session.setup()
        stack.enter_context(session)
        yield session
