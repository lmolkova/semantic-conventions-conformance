"""AWS Bedrock-compatible endpoints."""

import json

from flask import Blueprint, Response, make_response

from ._common import encode_aws_event_stream_message

bp = Blueprint("bedrock", __name__)


CONVERSE_RESPONSE = {
    "output": {
        "message": {
            "role": "assistant",
            "content": [{"text": "This is a response from the mock server."}],
        }
    },
    "stopReason": "end_turn",
    "usage": {
        "inputTokens": 25,
        "outputTokens": 12,
        "totalTokens": 37,
    },
    "metrics": {"latencyMs": 100},
}


def _stream_converse():
    """Yield Bedrock ConverseStream event-stream chunks in binary format."""
    events = []
    events.append(("messageStart", {"role": "assistant"}))
    for word in ["This ", "is ", "a ", "mock ", "streamed ", "response."]:
        events.append(("contentBlockDelta", {"delta": {"text": word}, "contentBlockIndex": 0}))
    events.append(("contentBlockStop", {"contentBlockIndex": 0}))
    events.append(("messageStop", {"stopReason": "end_turn"}))
    events.append(
        (
            "metadata",
            {
                "usage": {"inputTokens": 25, "outputTokens": 6, "totalTokens": 31},
                "metrics": {"latencyMs": 100},
            },
        )
    )
    for event_type, body in events:
        payload = json.dumps(body).encode("utf-8")
        yield encode_aws_event_stream_message(event_type, payload)


@bp.route("/model/<path:model_id>/converse", methods=["POST"])
def bedrock_converse(model_id):
    resp = make_response(CONVERSE_RESPONSE)
    resp.headers["x-amzn-requestid"] = "converse-mock-001"
    return resp


@bp.route("/model/<path:model_id>/converse-stream", methods=["POST"])
def bedrock_converse_stream(model_id):
    resp = make_response(Response(_stream_converse(), mimetype="application/vnd.amazon.eventstream"))
    resp.headers["x-amzn-requestid"] = "converse-stream-mock-001"
    return resp


@bp.route("/model/<path:model_id>/invoke", methods=["POST"])
def bedrock_invoke(model_id):
    """Handle Bedrock InvokeModel — used for Titan Embeddings."""
    result = {
        "embedding": [0.001] * 256,
        "inputTextTokenCount": 8,
    }
    resp = make_response(Response(json.dumps(result), mimetype="application/json"))
    resp.headers["x-amzn-requestid"] = "invoke-mock-001"
    return resp
