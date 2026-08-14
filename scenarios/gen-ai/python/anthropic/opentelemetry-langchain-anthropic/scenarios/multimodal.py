# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conformance scenario: Anthropic image input, through langchain.

langchain carries the image as a content block on a human message.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

# A 1x1 transparent PNG. The bytes are never decoded by anything under test.
IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

model = ChatAnthropic(
    model="claude-sonnet-4-20250514", max_tokens=100, temperature=0.5
)

model.invoke(
    [
        ("system", "You are a helpful assistant."),
        HumanMessage(
            content=[
                {"type": "text", "text": "What is in this image?"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": IMAGE,
                    },
                },
            ]
        ),
    ]
)
