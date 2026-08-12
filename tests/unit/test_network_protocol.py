"""Cryptographic and schema tests for protocol version 3."""

import pytest

from police_thief.services.network_protocol import (
    AuditPayload,
    NetworkProtocolError,
    TurnMessage,
    audit_records,
    create_agreement,
    seal_payload,
    validate_claim_response,
    verify_agreement,
    verify_audit_records,
    verify_record,
)


def test_structurally_invalid_step0_is_unverified_but_not_tampering() -> None:
    verdict = verify_audit_records(
        [{"payload": {"hardware": "declared"}, "nonce": "n", "commit": "c"}],
        {},
        require_step0=True,
    )
    assert verdict.verified is False
    assert verdict.failed_steps == (-1, 0)
    assert verdict.cryptographic_failure is False


def test_changed_live_commit_is_cryptographic_failure() -> None:
    record = seal_payload({"step": 1, "role": "police", "move": "E"})
    verdict = verify_audit_records([record], {1: "0" * 64})
    assert verdict.verified is False
    assert verdict.failed_steps == (1,)
    assert verdict.cryptographic_failure is True


def test_audit_payload_omits_unset_consensus_sha() -> None:
    payload = AuditPayload("police", [], "survival").to_dict()
    assert "consensus_sha" not in payload


def test_audit_payload_accepts_valid_consensus_sha() -> None:
    digest = "a" * 64
    payload = AuditPayload("police", [], "series_consensus", consensus_sha=digest)
    assert AuditPayload.from_dict(payload.to_dict()).consensus_sha == digest


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "g" * 64, 123])
def test_audit_payload_rejects_invalid_consensus_sha(digest) -> None:
    with pytest.raises(NetworkProtocolError, match="consensus_sha"):
        AuditPayload.from_dict({
            "sender": "police", "records": [],
            "result_claim": "series_consensus", "consensus_sha": digest,
        })


def test_audit_payload_still_rejects_unagreed_unknown_fields() -> None:
    with pytest.raises(NetworkProtocolError, match="malformed audit payload"):
        AuditPayload.from_dict({
            "sender": "police", "records": [], "result_claim": "survival",
            "future_unagreed_field": True,
        })


def test_signed_negotiation_round_trip():
    terms = {"board_size": 7, "max_steps": 35}
    message = create_agreement(terms, {"group_name": "Alpha"})
    assert verify_agreement(message, terms) == {"group_name": "Alpha"}


def test_signed_negotiation_carries_public_conformance_manifest():
    terms = {"board_size": 7}
    manifest = {"game_config_sha256": "a" * 64}
    message = create_agreement(terms, {"group_name": "Alpha"}, manifest)
    assert message["conformance"] == manifest
    assert verify_agreement(message, terms) == {"group_name": "Alpha"}


def test_negotiation_rejects_non_object_terms():
    message = {"terms": [], "nonce": "x", "signature": "y", "identity": {}}
    with pytest.raises(NetworkProtocolError, match="terms must be an object"):
        verify_agreement(message, {})


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
    step0 = seal_payload({"step": 0, "type": "system_spec", "model": "test"})
    record = seal_payload({"step": 2, "state": {}, "move": "E", "intent": True})
    expected = {2: record["commit"]}
    assert audit_records([step0, record], expected, require_step0=True) == (True, [])
    record["payload"]["move"] = "W"
    assert audit_records([step0, record], expected, require_step0=True) == (False, [2])
    assert audit_records([], expected, require_step0=True) == (False, [2, 0])


def test_audit_accepts_reference_step_zero_but_rejects_duplicates():
    step0 = seal_payload({"step": 0, "type": "system_spec", "spec": {}})
    assert audit_records([step0], {}, require_step0=True) == (True, [])
    assert audit_records([step0, step0], {}, require_step0=True) == (False, [0])


def test_claim_response_must_reference_the_last_public_claim() -> None:
    response = {"claim": [5, 6], "caught": True}
    validate_claim_response(response, [[5, 5], [5, 6]])

    with pytest.raises(NetworkProtocolError, match="expected one of"):
        validate_claim_response(response, [[5, 5]])


def test_audit_accepts_peer_specific_move_schema_but_rejects_tampering() -> None:
    peer_record = seal_payload({
        "step": 1, "role": "thief", "state": {}, "move": "MOVE:S", "intent": True,
    })
    assert audit_records([peer_record], {1: peer_record["commit"]}) == (True, [])

    peer_record["payload"]["move"] = "MOVE:N"
    assert audit_records([peer_record], {1: peer_record["commit"]}) == (False, [1])


def test_turn_rejects_unknown_win_claim_type() -> None:
    record = seal_payload({"step": 1, "move": "N"})
    message = TurnMessage(
        step=1, sender="thief", hint="", smell_grid=[[0.0]],
        commit=record["commit"], timestamp="now", win_claim={"type": "invented"},
    )
    with pytest.raises(NetworkProtocolError, match="win_claim.type"):
        TurnMessage.from_dict(message.to_dict())
