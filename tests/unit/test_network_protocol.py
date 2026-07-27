"""Authenticated MCP payload tests for cross-computer matches."""

import pytest

from police_thief.domain.board import Move, Position
from police_thief.services.network_protocol import (
    NetworkProtocolError,
    create_network_move,
    create_result_proof,
    parse_network_move,
    parse_result_proof,
)
from police_thief.shared.constants import AgentRole


def test_network_move_round_trip_is_commit_verified():
    original = create_network_move("G007", 4, AgentRole.COP, Position(1, 2), Move.EAST)
    payload, signature = original.to_wire()
    assert parse_network_move(payload, signature) == original


def test_network_move_rejects_modified_signature():
    payload, _signature = create_network_move(
        "G007", 4, AgentRole.COP, Position(1, 2), Move.EAST,
    ).to_wire()
    with pytest.raises(NetworkProtocolError, match="signature"):
        parse_network_move(payload, "0" * 64)


def test_result_proof_round_trip_uses_shared_match_secret():
    result = {"game_id": "G007", "log_sha256": "abc", "mutual_sign_off": False}
    payload, signature = create_result_proof(result, b"shared-secret")
    assert parse_result_proof(payload, signature, b"shared-secret") == result


def test_result_proof_rejects_another_computers_secret():
    payload, signature = create_result_proof({"game_id": "G007"}, b"correct")
    with pytest.raises(NetworkProtocolError, match="signature"):
        parse_result_proof(payload, signature, b"wrong")
