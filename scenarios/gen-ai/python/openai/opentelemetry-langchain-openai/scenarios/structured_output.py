# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conformance scenario: an OpenAI JSON schema answer, through langchain."""

from langchain_openai import ChatOpenAI

SCHEMA = {
    "title": "forecast",
    "type": "object",
    "properties": {
        "location": {"type": "string"},
        "temperature": {"type": "integer"},
        "conditions": {"enum": ["sunny", "cloudy", "rainy"]},
    },
    "required": ["location", "temperature", "conditions"],
}

model = ChatOpenAI(model="gpt-4o-mini", max_tokens=100, temperature=0.5)

model.with_structured_output(SCHEMA).invoke(
    [
        ("system", "You are a helpful assistant."),
        ("human", "What is the weather in Seattle?"),
    ]
)
