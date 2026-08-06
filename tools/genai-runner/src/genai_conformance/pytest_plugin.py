# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Make pytest open GenAI sessions.

The runner's plugin collects a ``conformance.yaml`` and runs its scenarios;
this says which session to open them with. Installing this package *is* the
configuration — there is nothing to declare in a conftest or an ini file.
"""

from __future__ import annotations

import pytest

from ._session import genai_session


# optionalhook: the hookspec belongs to the runner's plugin, and a hook
# implementation for a spec nobody declared is a hard error in pluggy. Without
# this, disabling that plugin (`-p no:conformance`) would crash pytest instead
# of simply collecting nothing.
@pytest.hookimpl(optionalhook=True)
def pytest_conformance_session_factory() -> object:
    return genai_session
