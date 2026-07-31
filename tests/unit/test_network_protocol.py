"""Cryptographic and schema tests for protocol version 3."""

import pytest

from police_thief.services.network_protocol import (
    NetworkProtocolError,
    TurnMessage,
    audit_records,
    create_agreement,
    seal_payload,
    verify_agreement,
    verify_record,
)


def test_signed_negotiation_round_trip():
    terms = {"board_size": 7, "max_steps": 35}
    message = create_agreement(terms, {"group_name": "Alpha"})
    assert verify_agreement(message, terms) == {"group_name": "Alpha"}


def test_negotiation_rejects_different_terms():
    message = create_agreement({"board_size": 7}, {})
    with pytest.raises(NetworkProtocolError, match="do not match"):
        verify_agreement(message, {"board_size": 8})


def test_turn_contains_commit_but_no_private_truth():
    record = seal_payload({"step": 1, "state": "private", "move": "N", "intent": True})
    turn = TurnMessage(
        step=1, sender="thief", hint="near the river", smell_grid={},
        commit=record["commit"], timestamp="2026-07-31T00:00:00Z",
    ).to_dict()
    assert set(turn).isdisjoint({"state", "move", "intent", "nonce"})
    assert verify_record(record)


def test_audit_detects_tampering_and_missing_steps():
    record = seal_payload({"step": 2, "state": {}, "move": "E", "intent": True})
    expected = {2: record["commit"]}
    assert audit_records([record], expected) == (True, [])
    record["payload"]["move"] = "W"
    assert audit_records([record], expected) == (False, [2])
    assert audit_records([], expected) == (False, [2])
