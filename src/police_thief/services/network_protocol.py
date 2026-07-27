"""Signed wire messages for a cross-computer MCP match."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass

from police_thief.domain.board import Move, Position
from police_thief.services.commit_reveal import LogEntry, commit, verify
from police_thief.shared.constants import AgentRole


class NetworkProtocolError(ValueError):
    """Raised when a peer message is malformed, stale, or unverifiable."""


@dataclass(frozen=True)
class NetworkMove:
    game_id: str
    turn_index: int
    role: AgentRole
    state: Position
    move: Move
    intent: bool
    nonce: str
    h_commit: str

    def to_wire(self) -> tuple[str, str]:
        payload = asdict(self)
        payload["kind"] = "move"
        payload["role"] = self.role.value
        payload["move"] = self.move.value
        return json.dumps(payload, separators=(",", ":"), sort_keys=True), self.h_commit

    def to_log_entry(self) -> LogEntry:
        return LogEntry(
            state={"row": self.state.row, "col": self.state.col},
            move=self.move,
            intent=self.intent,
            nonce=self.nonce,
            h_commit=self.h_commit,
        )


def create_network_move(
    game_id: str, turn_index: int, role: AgentRole, state: Position, move: Move
) -> NetworkMove:
    state_dict = {"row": state.row, "col": state.col}
    sealed = commit(state_dict, move, True)
    return NetworkMove(game_id, turn_index, role, state, move, True, sealed.nonce, sealed.h_commit)


def parse_network_move(payload: str, signature: str) -> NetworkMove:
    try:
        raw = json.loads(payload)
        state = Position(int(raw["state"]["row"]), int(raw["state"]["col"]))
        message = NetworkMove(
            game_id=str(raw["game_id"]),
            turn_index=int(raw["turn_index"]),
            role=AgentRole(raw["role"]),
            state=state,
            move=Move(raw["move"]),
            intent=bool(raw["intent"]),
            nonce=str(raw["nonce"]),
            h_commit=str(raw["h_commit"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise NetworkProtocolError(f"malformed network move: {exc}") from exc
    if message.h_commit != signature:
        raise NetworkProtocolError("envelope signature does not match h_commit")
    state_dict = {"row": state.row, "col": state.col}
    if not verify(state_dict, message.move, message.intent, message.nonce, message.h_commit):
        raise NetworkProtocolError("commit-reveal verification failed")
    return message


def create_result_proof(result: dict, shared_key: bytes) -> tuple[str, str]:
    """Create an authenticated final-result message for mutual sign-off."""
    payload = json.dumps(
        {"kind": "result", "result": result}, separators=(",", ":"), sort_keys=True,
    )
    signature = hmac.new(shared_key, payload.encode(), hashlib.sha256).hexdigest()
    return payload, signature


def parse_result_proof(payload: str, signature: str, shared_key: bytes) -> dict:
    expected = hmac.new(shared_key, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise NetworkProtocolError("result proof signature is invalid")
    try:
        raw = json.loads(payload)
        if raw["kind"] != "result" or not isinstance(raw["result"], dict):
            raise ValueError("not a result proof")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise NetworkProtocolError(f"malformed result proof: {exc}") from exc
    return raw["result"]
