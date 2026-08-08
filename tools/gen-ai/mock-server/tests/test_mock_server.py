# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Every blueprint answers, and answers the same way twice.

Scenarios depend on the responses being deterministic — that is what replaces
cassette replay — so each case asserts the shape a scenario reads, not just a
200.
"""

import json

import pytest

from genai_mock_server import app

# Inference-style endpoints: same request in, same bytes out.
ENDPOINTS = [
    (
        "openai-chat",
        "post",
        "/v1/chat/completions",
        {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    ),
    (
        "openai-embeddings",
        "post",
        "/v1/embeddings",
        {"model": "text-embedding-3-small", "input": "hi"},
    ),
    (
        "openai-responses",
        "post",
        "/v1/responses",
        {"model": "gpt-4o-mini", "input": "hi"},
    ),
    (
        "anthropic",
        "post",
        "/v1/messages",
        {
            "model": "claude-sonnet-4-20250514",
            "messages": [{"role": "user", "content": "hi"}],
        },
    ),
    (
        "google-genai",
        "post",
        "/v1beta/models/gemini-2.5-flash:generateContent",
        {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
    ),
    (
        "bedrock",
        "post",
        "/model/amazon.titan-text-express-v1/converse",
        {"messages": [{"role": "user", "content": [{"text": "hi"}]}]},
    ),
    (
        "cohere",
        "post",
        "/v2/chat",
        {"model": "command-r", "messages": [{"role": "user", "content": "hi"}]},
    ),
]

# Resource-creating endpoints mint a fresh id per call, so only the shape is
# stable. Kept separate rather than loosening the assertion above.
CREATE_ENDPOINTS = [
    ("anthropic-agents", "post", "/v1/agents", {"model": "claude-sonnet-4-20250514"}),
    ("bedrock-agent", "put", "/agents/", {"agentName": "mock-agent"}),
    ("bedrock-agentcore", "post", "/memories/create", {"name": "mock-memory"}),
    ("openai-assistants", "post", "/v1/assistants", {"model": "gpt-4o-mini"}),
    ("mistral-agents", "post", "/mistral/v1/agents", {"model": "mistral-medium-latest"}),
]


@pytest.fixture(name="client")
def _client():
    return app.test_client()


def test_health(client):
    assert client.get("/health").json == {"status": "ok"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [case[1:] for case in ENDPOINTS],
    ids=[case[0] for case in ENDPOINTS],
)
def test_endpoint_answers_deterministically(client, method, path, body):
    first = getattr(client, method)(path, json=body)
    assert first.status_code == 200, first.data

    second = getattr(client, method)(path, json=body)
    assert second.status_code == 200
    assert first.get_data() == second.get_data()


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [case[1:] for case in CREATE_ENDPOINTS],
    ids=[case[0] for case in CREATE_ENDPOINTS],
)
def test_create_endpoint_answers_with_a_stable_shape(client, method, path, body):
    first = getattr(client, method)(path, json=body)
    assert first.status_code < 300, first.data

    second = getattr(client, method)(path, json=body)
    assert second.status_code == first.status_code
    assert first.json.keys() == second.json.keys()


def test_chat_echoes_the_requested_model(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]},
    )
    body = response.json
    assert body["model"] == "gpt-5"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["usage"]["total_tokens"] > 0


def test_chat_returns_a_tool_call_when_tools_are_offered(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "weather in Seattle?"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"location": {"type": "string"}},
                        },
                    },
                }
            ],
        },
    )
    tool_calls = response.json["choices"][0]["message"]["tool_calls"]
    assert [call["function"]["name"] for call in tool_calls] == ["get_weather"]
    assert "location" in json.loads(tool_calls[0]["function"]["arguments"])


def test_chat_streams_when_asked(client):
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    chunks = response.get_data(as_text=True)
    assert chunks.startswith("data: ")
    assert chunks.rstrip().endswith("data: [DONE]")


# Azure routes the same operation under a deployment path; instrumentations
# read the URL, so the alias has to serve the identical body.
def test_azure_deployment_path_matches_the_plain_one(client):
    body = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
    plain = client.post("/v1/chat/completions", json=body)
    deployment = client.post(
        "/openai/deployments/gpt-4o-mini/chat/completions", json=body
    )
    assert deployment.get_data() == plain.get_data()


# ─── Behaviours a scenario elsewhere depends on ─────────────────────────────


def test_responses_report_a_terminal_status(client):
    """Instrumentation reads `status` to know the response finished."""
    response = client.post(
        "/v1/responses", json={"model": "gpt-4o-mini", "input": "hi"}
    )

    assert response.json["status"] == "completed"


# qwen-agent and other Hermes/Nous-protocol clients advertise tools inside a
# <tools> block in the system prompt and expect the call back as <tool_call>
# JSON in the assistant content — not through the `tools` request field.
HERMES_SYSTEM = """You may call tools.

<tools>
{"type": "function", "function": {"name": "get_weather", "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}}}
</tools>

Return calls as <tool_call>{"name": ..., "arguments": ...}</tool_call>.
"""


def _hermes_request(*extra_messages):
    return {
        "model": "qwen-max",
        "messages": [
            {"role": "system", "content": HERMES_SYSTEM},
            {"role": "user", "content": "weather in Seattle?"},
            *extra_messages,
        ],
    }


def test_text_protocol_tools_get_a_tool_call_in_the_content(client):
    response = client.post("/v1/chat/completions", json=_hermes_request())

    content = response.json["choices"][0]["message"]["content"]
    assert content.startswith("<tool_call>")
    call = json.loads(content.removeprefix("<tool_call>").removesuffix("</tool_call>"))
    assert call["name"] == "get_weather"
    assert "location" in call["arguments"]


def test_text_protocol_does_not_loop_once_the_tool_has_answered(client):
    """A second call after the result must not ask for the tool again."""
    answered = _hermes_request(
        {"role": "assistant", "content": '<tool_call>\n{"name": "get_weather"}\n</tool_call>'},
        {"role": "user", "content": "<tool_response>\n70 degrees\n</tool_response>"},
    )

    response = client.post("/v1/chat/completions", json=answered)

    content = response.json["choices"][0]["message"]["content"]
    assert "<tool_call>" not in content
