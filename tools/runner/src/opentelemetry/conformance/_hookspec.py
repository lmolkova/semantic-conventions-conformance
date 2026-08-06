# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The one thing the pytest plugin can't know by itself."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from ._session import SessionFactory


@pytest.hookspec(firstresult=True)
def pytest_conformance_session_factory() -> SessionFactory | None:
    """Return the session factory to open scenario directories with.

    Collection is generic; which registry, server and reduction a run uses is
    not. A conventions-aware package implements this to supply its own
    factory — ``genai_conformance`` does — and installing that package is all
    the configuration there is. Unimplemented, runs use the plain
    ``conformance_session``.
    """
