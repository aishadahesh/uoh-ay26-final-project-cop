"""FastMCP server wrapper: this peer's local truth, exposed to the opponent.

Chapter 2 (docs/tasks.md Sec. 3) requires every agent to be simultaneously an
MCP server (exposing tools the opponent calls) and an MCP client (calling the
opponent's own tools) — fully symmetric, no "strong side"/"weak side".

The tool exposed here, receive_move, deliberately carries only a placeholder
envelope (signed_move, signature) at this stage. Real move content arrives in
Chapter 3 (board state replaces the free-form string) and real cryptographic
signing arrives in Chapter 5/6 (commit-reveal replaces the placeholder
signature). What this module owns is transport plumbing and basic structural
input validation — never move legality, never cryptographic trust.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastmcp import FastMCP

TOOL_SCHEMA_VERSION = "1.00"


@dataclass(frozen=True)
class MoveEnvelope:
    """Placeholder wire format for one exchanged move.

    `signed_move` becomes a real serialized board move in Chapter 3;
    `signature` becomes a real SHA-256 commitment in Chapter 5/6. Both exist
    now purely to establish and test the transport contract early.
    """

    signed_move: str
    signature: str

    def is_structurally_valid(self) -> bool:
        """Reject obviously malformed payloads (empty/whitespace-only fields).

        This is defensive input validation only — not cryptographic
        verification. See docs/tasks.md Chapter 5 for the real trust
        mechanism that later replaces this check.
        """
        return bool(self.signed_move.strip()) and bool(self.signature.strip())


ReceiveHandler = Callable[[MoveEnvelope], dict]


def build_peer_server(peer_name: str, receive_handler: ReceiveHandler | None = None) -> FastMCP:
    """Construct this peer's FastMCP server instance.

    Each peer (cop or thief) calls this with its own `peer_name` (e.g.
    "police_peer" / "thief_peer") to get a server exposing the receive_move
    tool for its opponent to call. FastMCP derives a pydantic schema from the
    function signature below, so a call with missing or unexpected fields is
    rejected by the framework itself with a clean ToolError — never a crash.
    """
    mcp = FastMCP(peer_name)

    @mcp.tool(version=TOOL_SCHEMA_VERSION)
    def receive_move(signed_move: str, signature: str) -> dict:
        """Receive one move envelope from the opponent over the network."""
        envelope = MoveEnvelope(signed_move=signed_move, signature=signature)
        accepted = envelope.is_structurally_valid()
        if accepted and receive_handler is not None:
            return receive_handler(envelope)
        return {"accepted": accepted, "move": envelope.signed_move if accepted else None}

    return mcp


def run_peer_server(mcp: FastMCP, host: str, port: int) -> None:
    """Bind and run this peer's server; blocks until interrupted.

    Binding to host="0.0.0.0" (rather than "127.0.0.1") is required so a
    tunneling tool (ngrok/Localtonet, Chapter 2 Sec. 3 / Stage 5) can later
    forward public traffic to this process. Graceful shutdown on Ctrl-C/
    SIGTERM is handled by the underlying uvicorn server when run in the main
    thread — no additional signal handling is needed here.
    """
    mcp.run(transport="http", host=host, port=port)
