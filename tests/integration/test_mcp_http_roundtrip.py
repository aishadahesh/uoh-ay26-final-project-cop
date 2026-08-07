"""Integration test: a real FastMCP HTTP server + client round trip.

Unlike tests/unit/test_mcp_server.py (in-memory transport, no sockets), this
test binds an actual TCP port and calls it over real HTTP -- exercising the
same code path main.py uses in production (docs/tasks.md Chapter 2).
"""

import asyncio
import socket
import threading
import time

import pytest
from fastmcp import Client

from police_thief.services.mcp_client import send_move
from police_thief.services.mcp_server import PeerInboxes, build_peer_server, run_peer_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, *, open_: bool, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            is_open = probe.connect_ex(("127.0.0.1", port)) == 0
        if is_open is open_:
            return
        time.sleep(0.05)
    pytest.fail(f"port {port} did not become {'open' if open_ else 'closed'}")


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
    assert result == {"ok": True, "accepted": True, "kind": "turn", "errors": []}
    assert inboxes.turns.get_nowait() == {"signed_move": "N", "signature": "abc123"}


def test_real_http_retry_is_acknowledged_without_duplicate_delivery(running_server):
    url, inboxes = running_server
    payload = {"sender": "police", "step": 7, "commit": "a" * 64}

    async def exercise() -> None:
        async with Client(url) as client:
            first = await client.call_tool("receive_turn", {"message": payload})
            retry = await client.call_tool("receive_turn", {"message": payload})
        expected = {"ok": True, "accepted": True, "kind": "turn", "errors": []}
        assert first.data == expected
        assert retry.data == expected

    asyncio.run(exercise())
    assert inboxes.turns.get_nowait() == payload
    assert inboxes.turns.empty()


def test_real_http_server_exposes_no_legacy_receive_move_tool(running_server):
    _url, inboxes = running_server
    assert inboxes.agreements.empty()


def test_real_http_server_routes_all_four_reference_tools(running_server):
    url, inboxes = running_server
    payloads = {
        "negotiate": ("message", {"terms": {}}, "negotiate"),
        "receive_turn": ("message", {"step": 1}, "turn"),
        "submit_audit": ("payload", {"records": []}, "audit"),
        "receive_control": ("message", {"kind": "status"}, "control"),
    }

    async def exercise() -> None:
        async with Client(url) as client:
            tools = {tool.name for tool in await client.list_tools()}
            assert tools == set(payloads)
            for tool, (argument, payload, response_kind) in payloads.items():
                result = await client.call_tool(tool, {argument: payload})
                assert result.data == {
                    "ok": True, "accepted": True, "kind": response_kind, "errors": [],
                }

    asyncio.run(exercise())
    assert inboxes.agreements.get_nowait() == {"terms": {}}
    # The legacy test already queued one turn only in its own fresh fixture.
    assert inboxes.turns.get_nowait() == {"step": 1}
    assert inboxes.audits.get_nowait() == {"records": []}
    assert inboxes.controls.get_nowait() == {"kind": "status"}


def test_gui_server_can_stop_and_restart_on_the_same_port():
    port = _free_port()

    for _ in range(2):
        stop_event = threading.Event()
        mcp = build_peer_server("cop", PeerInboxes())
        thread = threading.Thread(
            target=run_peer_server,
            args=(mcp, "127.0.0.1", port, stop_event),
            daemon=True,
        )
        thread.start()
        _wait_for_port(port, open_=True)
        stop_event.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        _wait_for_port(port, open_=False)
