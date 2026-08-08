# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The server a session starts for its scenarios."""

from __future__ import annotations

import socket
import sys
import urllib.request

import pytest

from opentelemetry.conformance._server import Server

# Answers /health, and writes far more than a pipe buffer holds — a server
# whose output nobody drains must not wedge.
CHATTY_SERVER = """
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

for index in range(20000):
    print(f"line {index} " + "x" * 80)
sys.stdout.flush()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        print("request " + "y" * 200, flush=True)
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
"""

NEVER_READY = "import time; time.sleep(60)"

EXITS = "import sys; print('boom'); sys.exit(3)"


def command(program: str) -> tuple[str, ...]:
    return (sys.executable, "-c", program, "${PORT}")


def test_starts_and_publishes_its_url() -> None:
    with Server(command(CHATTY_SERVER)) as server:
        with urllib.request.urlopen(f"{server.url}/health") as response:
            assert response.status == 200


def test_a_chatty_server_does_not_wedge() -> None:
    """Regression: stdout on an undrained pipe blocks once the buffer fills."""
    with Server(command(CHATTY_SERVER)) as server:
        for _ in range(50):
            with urllib.request.urlopen(f"{server.url}/health") as response:
                assert response.status == 200


def test_a_server_that_exits_reports_its_output() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with Server(command(EXITS)):
            pass


def test_a_server_that_never_answers_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_CONFORMANCE_SERVER_STARTUP_TIMEOUT", "2")

    with pytest.raises(RuntimeError, match="did not become ready"):
        with Server(command(NEVER_READY)):
            pass


def test_the_port_stays_reserved_until_the_server_starts() -> None:
    """Otherwise a parallel run can take it in the gap before start()."""
    server = Server(command(CHATTY_SERVER))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as other:
            with pytest.raises(OSError):
                other.bind(("127.0.0.1", server._port))  # noqa: SLF001
    finally:
        server.close()


def test_a_failed_start_leaves_no_process_behind() -> None:
    server = Server(command(EXITS))

    with pytest.raises(RuntimeError):
        server.start()

    assert server._process is None  # noqa: SLF001


def test_health_path_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_CONFORMANCE_SERVER_STARTUP_TIMEOUT", "5")

    with pytest.raises(RuntimeError, match="did not become ready"):
        with Server(command(CHATTY_SERVER), health_path="/nope"):
            pass
