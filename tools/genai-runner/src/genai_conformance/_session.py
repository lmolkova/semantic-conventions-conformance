# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The GenAI half of a conformance run.

``opentelemetry.conformance`` knows how to run scenarios, check them and hand
the reports back; everything specific to these semantic conventions lives
here: the pinned ``semantic-conventions-genai`` registry, the advice policies
that check it, and the mock LLM server the scenarios talk to.
"""

from __future__ import annotations

import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from opentelemetry.conformance import (
    ConformanceSession,
    PackageSpec,
    ServerSpec,
    WeaverSpec,
    conformance_session,
)

from ._coverage import genai_coverage, provision_coverage_model
from ._registry import (
    advice_data_glob,
    check_weaver_version,
    policies_dir,
    semconv_registry,
    weaver_config_file,
)

MOCK_SERVER_MODULE = "genai_mock_server"


def weaver_defaults() -> WeaverSpec:
    """The provisioned GenAI registry, as defaults for a package's ``weaver``."""
    return WeaverSpec(
        registry=str(semconv_registry()),
        policies=str(policies_dir()),
        advice_data=advice_data_glob(),
        config=str(weaver_config_file()),
    )


def server_defaults() -> ServerSpec:
    """The mock LLM server, as the default for a package's ``server``."""
    return ServerSpec(
        run=(
            sys.executable,
            "-m",
            MOCK_SERVER_MODULE,
            "--port",
            "${PORT}",
        )
    )


@contextmanager
def genai_session(
    directory: Path | str,
    *,
    report_dir: Path | str | None = None,
    data_file: Path | str | None = None,
    variables: Mapping[str, str] | None = None,
    weaver: WeaverSpec | None = None,
    server: ServerSpec | None = None,
    env: Mapping[str, str] | None = None,
    build_data: Callable[[Path, PackageSpec], object] = genai_coverage,
) -> Generator[ConformanceSession, None, None]:
    """A conformance session wired to the GenAI registry and mock server.

    Signature-compatible with ``conformance_session`` — it is a
    ``SessionFactory``, so the CLI can drive it — and supplies the GenAI
    wiring under whatever the caller passes, including the reduction: a run
    reduces to what each semconv span type carried, not to what the scenario
    happened to declare. Pass ``build_data=opentelemetry.conformance.coverage``
    for the runner's generic one. Coverage data lands next to the scenarios,
    where it is committed and diffed.

    Starting a session resolves the registry into the coverage model that
    reduction reads, once, if the pin doesn't have one yet — so the weaver run
    it takes happens here rather than after the scenarios have run.
    """
    check_weaver_version()
    if build_data is genai_coverage:
        provision_coverage_model()

    with conformance_session(
        directory,
        report_dir=report_dir,
        data_file=data_file
        if data_file is not None
        else Path(directory) / "data.json",
        variables=variables,
        weaver=(weaver or WeaverSpec()).over(weaver_defaults()),
        server=(server or ServerSpec()).over(server_defaults()),
        env=env,
        build_data=build_data,
    ) as session:
        yield session
