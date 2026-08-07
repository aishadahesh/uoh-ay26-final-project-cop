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


@pytest.mark.parametrize("ack", [{"ok": True}, {"accepted": True, "kind": "negotiate"}])
def test_exchange_agreement_accepts_local_and_reference_acknowledgements(monkeypatch, ack):
    inboxes = PeerInboxes()
    transport = McpPeerTransport("https://peer.example/mcp", inboxes)
    agreement = {"identity": {}, "nonce": "n", "signature": "s", "terms": {}}
    inboxes.agreements.put(agreement)

    async def call_once(_tool, _argument_name, _payload):
        return ack

    monkeypatch.setattr(transport, "_call_async", call_once)
    assert transport.exchange_agreement(agreement, timeout=0.1) == agreement


def test_exchange_agreement_accepts_inline_reference_agreement(monkeypatch):
    transport = McpPeerTransport("https://peer.example/mcp", PeerInboxes())
    agreement = {"identity": {}, "nonce": "n", "signature": "s", "terms": {}}

    async def call_once(_tool, _argument_name, _payload):
        return {"accepted": True, "kind": "negotiate", "agreement": agreement}

    monkeypatch.setattr(transport, "_call_async", call_once)
    assert transport.exchange_agreement(agreement, timeout=0.1) == agreement
