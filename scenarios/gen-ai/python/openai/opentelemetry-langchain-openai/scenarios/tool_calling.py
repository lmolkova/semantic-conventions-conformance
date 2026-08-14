# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conformance scenario: OpenAI tool calling, through langchain.

Two round trips driven by hand, matching openai/scenarios/tool_calling.py:
the tool definitions and the requested call, then the tool result travelling
back as input. langchain binds the tools; it does not run them here.
"""

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


@tool
def get_current_weather(location: str) -> str:
    """Get the current weather in a given location."""
    return f"70 degrees and sunny in {location}"


model = ChatOpenAI(model="gpt-4o-mini", max_tokens=100, temperature=0.5)
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
