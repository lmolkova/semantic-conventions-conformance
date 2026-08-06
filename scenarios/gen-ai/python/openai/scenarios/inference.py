# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conformance scenario: openai chat completion (inference).

Shared by every implementation under ``openai/`` — each one's
``conformance.yaml`` runs this same file. Comparing implementations only means
something if the program is identical, so it lives here once rather than being
copied per implementation.

Nothing here turns instrumentation on, and nothing here may: the scenario runs
under ``opentelemetry-instrument``, which installs the providers and loads
whatever instrumentation the environment holds. Naming one would defeat the
sharing, and would check a hand-written ``instrument()`` call instead of the
zero-code path users actually take.
"""

from openai import OpenAI

OpenAI().chat.completions.create(
    messages=[{"role": "user", "content": "Say this is a test"}],
    model="gpt-4o-mini",
    stream=False,
)
