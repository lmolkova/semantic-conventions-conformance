# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""DEMO conformance scenario: mistralai chat completion.

Shared by every implementation under ``mistralai/`` — today only ``native``,
where the SDK ships its own OpenTelemetry tracing hook and installs it itself.
The program is just the library being used; whatever an implementation makes of
that is what gets checked.
"""

import os

from mistralai.client import Mistral

client = Mistral(
    api_key="test_mistral_api_key",
    server_url=os.environ["MISTRAL_BASE_URL"],
)

client.chat.complete(
    model="mistral-large-latest",
    messages=[{"role": "user", "content": "Say this is a test"}],
)
