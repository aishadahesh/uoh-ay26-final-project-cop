"""Unit tests for the Chapter-2 FastMCP client wrapper's error handling."""

import pytest

from police_thief.services.mcp_client import McpPeerTransport, PeerClientError, send_move_async
from police_thief.services.mcp_server import PeerInboxes


async def test_send_move_raises_peer_client_error_when_opponent_unreachable():
    """No server is listening on this port -- connection should fail fast."""
    with pytest.raises(PeerClientError, match="failed to reach opponent"):
        await send_move_async(
            "http://127.0.0.1:1/mcp", signed_move="N", signature="abc123", timeout=2.0
        )


@pytest.mark.parametrize(
    "ack",
    [
        {"ok": True},
        {"accepted": True, "kind": "negotiate"},
        {"ok": True, "accepted": True, "kind": "negotiate"},
    ],
)
def test_exchange_agreement_accepts_local_and_reference_acknowledgements(monkeypatch, ack):
    inboxes = PeerInboxes()
    transport = McpPeerTransport("https://peer.example/mcp", inboxes)
    agreement = {"identity": {}, "nonce": "n", "signature": "s", "terms": {}}
    inboxes.agreements.put(agreement)

    async def call_once(_tool, _argument_name, _payload):
        return ack

    monkeypatch.setattr(transport, "_call_async", call_once)
    assert transport.exchange_agreement(agreement, timeout=0.1) == agreement


def test_exchange_agreement_surfaces_explicit_rejection_without_retrying(monkeypatch):
    transport = McpPeerTransport("https://peer.example/mcp", PeerInboxes())
    agreement = {"identity": {}, "nonce": "n", "signature": "s", "terms": {}}
    calls = 0

    async def reject_once(_tool, _argument_name, _payload):
        nonlocal calls
        calls += 1
        return {
            "ok": False,
            "accepted": False,
            "kind": "negotiate",
            "errors": ["bad term"],
        }

    monkeypatch.setattr(transport, "_call_async", reject_once)
    with pytest.raises(PeerClientError, match="bad term"):
        transport.exchange_agreement(agreement, timeout=1)
    assert calls == 1


def test_exchange_agreement_retries_temporary_boundary_rejection(monkeypatch):
    inboxes = PeerInboxes()
    transport = McpPeerTransport(
        "https://peer.example/mcp", inboxes, boundary_retry_interval=0,
    )
    agreement = {"identity": {}, "nonce": "n", "signature": "s", "terms": {}}
    inboxes.agreements.put(agreement)
    responses = iter([
        {
            "ok": False,
            "accepted": False,
            "kind": "negotiate",
            "errors": ["a mini-game is in progress; re-send this handshake at the boundary"],
        },
        {"ok": True, "accepted": True, "kind": "negotiate", "errors": []},
    ])
    calls = 0

    async def retry_at_boundary(_tool, _argument_name, _payload):
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(transport, "_call_async", retry_at_boundary)
    assert transport.exchange_agreement(agreement, timeout=1) == agreement
    assert calls == 2


def test_exchange_agreement_accepts_inline_reference_agreement(monkeypatch):
    transport = McpPeerTransport("https://peer.example/mcp", PeerInboxes())
    agreement = {"identity": {}, "nonce": "n", "signature": "s", "terms": {}}

    async def call_once(_tool, _argument_name, _payload):
        return {"accepted": True, "kind": "negotiate", "agreement": agreement}

    monkeypatch.setattr(transport, "_call_async", call_once)
    assert transport.exchange_agreement(agreement, timeout=0.1) == agreement
