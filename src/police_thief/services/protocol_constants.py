"""The wire vocabulary: role and phase names, control kinds, and the
mandatory handshake/identity field sets."""

from __future__ import annotations

PROTOCOL_NAME = "police-thief-mcp"

PROTOCOL_VERSION = "3.0.0"

WIRE_ROLES = {"cop": "police", "thief": "thief"}

CONTROL_KINDS = frozenset({"enable", "status", "restart", "quit"})

ALLOWED_WIN_CLAIMS = frozenset({"boxed_in", "survival"})


class NetworkProtocolError(ValueError):
    """Raised when a peer message is malformed, incompatible, or tampered."""
