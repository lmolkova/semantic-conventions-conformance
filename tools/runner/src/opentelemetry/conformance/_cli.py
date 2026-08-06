# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""``otel-conformance <dir> [options]``.

Everything a session takes is available here, so a repo can wire conformance
up without writing Python: the registry to validate against, defaults for the
environment, a server to run, and a command to reduce the reports afterwards.
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable

from ._session import (
    DEFAULT_DATA_FILE,
    DEFAULT_REPORT_DIR,
    SessionFactory,
    conformance_session,
)
from ._spec import PackageSpec, ServerSpec, WeaverSpec


class _DataCommandError(RuntimeError):
    """``--data-command`` failed or printed something that isn't JSON."""


def _key_value(argument: str) -> tuple[str, str]:
    key, separator, value = argument.partition("=")
    if not separator or not key:
        raise argparse.ArgumentTypeError(
            f"expected KEY=VALUE, got {argument!r}"
        )
    return key, value


def _absolute(value: str | None) -> str | None:
    """A path given on the command line is relative to the caller's cwd.

    Only paths declared inside a package file are relative to that file.
    """
    return None if value is None else str(Path(value).absolute())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="otel-conformance",
        description="Run a package's conformance scenarios.",
    )
    parser.add_argument(
        "directory", type=Path, help="the package's conformance directory"
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        metavar="NAME",
        help="run only this scenario (repeatable); the data file is not "
        "written, since a reduction over the reports only holds for a whole "
        "run",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        metavar="DIR",
        help=(
            "one raw weaver report per scenario (default "
            f"<DIRECTORY>/{DEFAULT_REPORT_DIR})"
        ),
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        metavar="PATH",
        help="where the reduction over a complete run is written — the "
        "built-in coverage, or --data-command's output "
        f"(default {DEFAULT_DATA_FILE})",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="print the findings but exit 0",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="log warnings only; by default the run says what it is doing "
        "(fetching a registry, an environment variable it took from the "
        "process environment)",
    )

    weaver = parser.add_argument_group(
        "registry", "defaults for what the package doesn't declare"
    )
    weaver.add_argument("--registry", metavar="PATH")
    weaver.add_argument("--policies", metavar="PATH")
    weaver.add_argument("--advice-data", metavar="GLOB")
    weaver.add_argument("--weaver-config", metavar="PATH")

    environment = parser.add_argument_group("environment")
    environment.add_argument(
        "--env",
        action="append",
        default=[],
        type=_key_value,
        metavar="KEY=VALUE",
        help="default environment variable for the scenarios (repeatable)",
    )
    environment.add_argument(
        "--var",
        action="append",
        default=[],
        type=_key_value,
        metavar="KEY=VALUE",
        help="value for a ${KEY} reference in the package file (repeatable)",
    )

    server = parser.add_argument_group(
        "server", "a server to run for the session"
    )
    server.add_argument(
        "--server",
        metavar="COMMAND",
        help="command to run; it is told its port through ${PORT} and "
        "inherits this environment",
    )
    server.add_argument("--server-health", metavar="PATH")
    server.add_argument("--server-url-var", metavar="NAME")

    parser.add_argument(
        "--data-command",
        metavar="COMMAND",
        help="reduce a complete run into the data file with this shell "
        'command instead of the built-in coverage: "$1" is the report '
        'directory, "$2" the library name, and its stdout is the data',
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    session: SessionFactory = conformance_session,
) -> int:
    args = _parser().parse_args(argv)

    # The library logs what a run would otherwise do invisibly: which registry
    # it is fetching, which declared environment values the process
    # environment took over.
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    def run_data_command(report_dir: Path, spec: PackageSpec) -> object:
        # Through a shell, so the command can glob the directory it is
        # handed. It reads its inputs as "$1" (the report directory) and "$2"
        # (the library), wherever it needs them.
        completed = subprocess.run(  # noqa: S603
            [
                "sh",
                "-c",
                args.data_command,
                "sh",
                str(report_dir),
                spec.library,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise _DataCommandError(
                f"--data-command exited with {completed.returncode}\n"
                f"--- stdout ---\n{completed.stdout}\n"
                f"--- stderr ---\n{completed.stderr}"
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise _DataCommandError(
                f"--data-command did not print JSON: {error}\n"
                f"--- stdout ---\n{completed.stdout}"
            ) from error

    # The reduction runs when the session closes, so a broken --data-command
    # surfaces here, after every scenario has already been reported. It is one
    # more thing the run got wrong, not a crash.
    try:
        failed = _run(args, session, run_data_command)
    except _DataCommandError as error:
        failed = True
        print(f"FAIL {error}")
    return 1 if failed and not args.report_only else 0


def _run(
    args: argparse.Namespace,
    session: SessionFactory,
    run_data_command: Callable[[Path, PackageSpec], object],
) -> bool:
    """Run the requested scenarios; True if any of them fell short."""
    failed = False
    with session(
        args.directory,
        report_dir=args.report_dir,
        data_file=args.data_file,
        weaver=WeaverSpec(
            registry=_absolute(args.registry),
            policies=_absolute(args.policies),
            advice_data=_absolute(args.advice_data),
            config=_absolute(args.weaver_config),
        ),
        server=ServerSpec(
            run=tuple(shlex.split(args.server)) if args.server else None,
            health=args.server_health,
            url_var=args.server_url_var,
        ),
        env=dict(args.env),
        variables=dict(args.var),
        # Only when asked: a session factory wrapping this one may know a
        # better reduction than the generic default, and passing that default
        # here would silently override it.
        **(
            {"build_data": run_data_command} if args.data_command else {}
        ),
    ) as opened:
        for name in args.scenarios or opened.spec.scenarios:
            report = opened.run(name)
            if report.failures:
                failed = True
                print(f"FAIL {name}")
                for failure in report.failures:
                    print(f"  - {failure}")
            else:
                print(f"ok   {name}")
    return failed


def cli() -> None:
    """Console-script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    cli()
