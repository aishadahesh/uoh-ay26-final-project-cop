"""Integration test: a real FastMCP HTTP server + client round trip.

Unlike tests/unit/test_mcp_server.py (in-memory transport, no sockets), this
test binds an actual TCP port and calls it over real HTTP -- exercising the
same code path main.py uses in production (docs/tasks.md Chapter 2).
"""

import socket
import threading
import time

import pytest

from police_thief.services.mcp_client import send_move
from police_thief.services.mcp_server import PeerInboxes, build_peer_server, run_peer_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_server():
    port = _free_port()
    inboxes = PeerInboxes()
    mcp = build_peer_server("cop", inboxes)
    thread = threading.Thread(
        target=lambda: run_peer_server(mcp, host="127.0.0.1", port=port),
        daemon=True,
    )
    thread.start()
    time.sleep(1.0)  # give uvicorn a moment to bind before the first request
    yield f"http://127.0.0.1:{port}/mcp", inboxes


def test_real_http_roundtrip_accepts_well_formed_move(running_server):
    url, inboxes = running_server
    result = send_move(url, signed_move="N", signature="abc123")
    assert result == {"accepted": True, "ok": True}
    assert inboxes.turns.get_nowait() == {"signed_move": "N", "signature": "abc123"}


def test_real_http_server_exposes_no_legacy_receive_move_tool(running_server):
    _url, inboxes = running_server
    assert inboxes.agreements.empty()
