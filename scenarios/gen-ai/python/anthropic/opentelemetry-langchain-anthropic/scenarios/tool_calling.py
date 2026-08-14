# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conformance scenario: Anthropic tool calling, through langchain.

Two round trips driven by hand, matching anthropic/scenarios/tool_calling.py.
langchain binds the tools; it does not run them here.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool


@tool
def get_current_weather(location: str) -> str:
    """Get the current weather in a given location."""
    return f"70 degrees and sunny in {location}"


model = ChatAnthropic(
    model="claude-sonnet-4-20250514", max_tokens=100, temperature=0.5
)
with_tools = model.bind_tools([get_current_weather])

messages = [
    ("system", "You are a helpful assistant."),
    ("human", "What's the weather in Seattle today?"),
]

answer = with_tools.invoke(messages)
messages.append(answer)
for call in answer.tool_calls:
    messages.append(
        ToolMessage(
            content=f"70 degrees and sunny in {call['args']['location']}",
            tool_call_id=call["id"],
        )
    )

with_tools.invoke(messages)
