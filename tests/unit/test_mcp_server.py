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
    ("tool", "argument", "inbox_name"),
    [
        ("negotiate", "message", "agreements"),
        ("receive_turn", "message", "turns"),
        ("submit_audit", "payload", "audits"),
        ("receive_control", "message", "controls"),
    ],
)
async def test_each_tool_acknowledges_and_queues_payload(tool, argument, inbox_name):
    inboxes = PeerInboxes()
    mcp = build_peer_server("thief", inboxes)
    payload = {"kind": tool}
    async with Client(mcp) as client:
        result = await client.call_tool(tool, {argument: payload})
    assert result.data == {"ok": True}
    assert getattr(inboxes, inbox_name).get_nowait() == payload


@pytest.mark.asyncio
async def test_tool_schema_rejects_wrong_argument_name():
    mcp = build_peer_server("cop", PeerInboxes())
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("negotiate", {"payload": {}})


def test_build_peer_server_names_server_after_role():
    assert build_peer_server("cop", PeerInboxes()).name == "police-thief-cop"
