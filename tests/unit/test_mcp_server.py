"""In-memory contract tests for the four reference-compatible MCP tools."""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from police_thief.services.mcp_server import PeerInboxes, build_peer_server


@pytest.mark.asyncio
async def test_server_advertises_exact_reference_tool_names():
    mcp = build_peer_server("cop", PeerInboxes())
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert {tool.name for tool in tools} == {
        "negotiate", "receive_turn", "submit_audit", "receive_control",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "argument", "inbox_name", "response_kind"),
    [
        ("negotiate", "message", "agreements", "negotiate"),
        ("receive_turn", "message", "turns", "turn"),
        ("submit_audit", "payload", "audits", "audit"),
        ("receive_control", "message", "controls", "control"),
    ],
)
async def test_each_tool_acknowledges_and_queues_payload(
    tool, argument, inbox_name, response_kind,
):
    inboxes = PeerInboxes()
    mcp = build_peer_server("thief", inboxes)
    payload = {"kind": tool}
    async with Client(mcp) as client:
        result = await client.call_tool(tool, {argument: payload})
    assert result.data == {"accepted": True, "kind": response_kind, "errors": []}
    assert getattr(inboxes, inbox_name).get_nowait() == payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "argument", "inbox_name", "response_kind"),
    [
        ("negotiate", "message", "agreements", "negotiate"),
        ("receive_turn", "message", "turns", "turn"),
        ("submit_audit", "payload", "audits", "audit"),
    ],
)
async def test_retried_delivery_is_acknowledged_without_queueing_a_duplicate(
    tool, argument, inbox_name, response_kind,
):
    inboxes = PeerInboxes()
    mcp = build_peer_server("thief", inboxes)
    payload = {"sender": "police", "step": 7, "commit": "a" * 64}
    async with Client(mcp) as client:
        first = await client.call_tool(tool, {argument: payload})
        retry = await client.call_tool(tool, {argument: payload})

    expected = {"accepted": True, "kind": response_kind, "errors": []}
    assert first.data == expected
    assert retry.data == expected
    inbox = getattr(inboxes, inbox_name)
    assert inbox.get_nowait() == payload
    assert inbox.empty()


@pytest.mark.asyncio
async def test_distinct_turn_commit_is_not_mistaken_for_a_retry():
    inboxes = PeerInboxes()
    mcp = build_peer_server("thief", inboxes)
    first = {"sender": "police", "step": 7, "commit": "a" * 64}
    second = {"sender": "police", "step": 7, "commit": "b" * 64}
    async with Client(mcp) as client:
        await client.call_tool("receive_turn", {"message": first})
        result = await client.call_tool("receive_turn", {"message": second})

    assert result.data == {"accepted": True, "kind": "turn", "errors": []}
    assert inboxes.turns.get_nowait() == first
    assert inboxes.turns.get_nowait() == second


@pytest.mark.asyncio
async def test_tool_schema_rejects_wrong_argument_name():
    mcp = build_peer_server("cop", PeerInboxes())
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("negotiate", {"payload": {}})


def test_build_peer_server_names_server_after_role():
    assert build_peer_server("cop", PeerInboxes()).name == "police-thief-cop"
