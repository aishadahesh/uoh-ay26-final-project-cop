"""Unit tests for the commit-reveal cryptographic protocol (Chapter 5)."""

import dataclasses
import hashlib
import json

import pytest

from police_thief.domain.board import Position
from police_thief.domain.capture import CaptureClaim
from police_thief.services.commit_reveal import (
    AuditResult,
    LogEntry,
    audit_log,
    canonical_json,
    commit,
    generate_nonce,
    verify,
)
from police_thief.shared.constants import AgentRole


def test_canonical_json_is_independent_of_key_insertion_order():
    a = canonical_json({"z": 1, "a": 2})
    b = canonical_json({"a": 2, "z": 1})
    assert a == b


def test_canonical_json_uses_fixed_compact_separators():
    assert canonical_json({"a": 1}) == b'{"a":1}'


def test_generate_nonce_is_64_hex_characters():
    nonce = generate_nonce()
    assert len(nonce) == 64
    assert all(ch in "0123456789abcdef" for ch in nonce)


def test_generate_nonce_is_unique_across_calls():
    assert generate_nonce() != generate_nonce()


def test_commit_produces_a_64_character_hex_digest():
    c = commit(state={"turn": 1}, move="N", intent=True)
    assert len(c.h_commit) == 64
    assert all(ch in "0123456789abcdef" for ch in c.h_commit)


def test_commit_is_deterministic_given_the_same_nonce():
    c1 = commit(state={"turn": 1}, move="N", intent=True, nonce="fixed")
    c2 = commit(state={"turn": 1}, move="N", intent=True, nonce="fixed")
    assert c1.h_commit == c2.h_commit


def test_commit_never_reuses_a_nonce_when_none_is_supplied():
    c1 = commit(state={"turn": 1}, move="N", intent=True)
    c2 = commit(state={"turn": 1}, move="N", intent=True)
    assert c1.nonce != c2.nonce
    assert c1.h_commit != c2.h_commit


def test_verify_true_for_an_untampered_reveal():
    c = commit(state={"turn": 1}, move="N", intent=True)
    assert verify({"turn": 1}, "N", True, c.nonce, c.h_commit)


@pytest.mark.parametrize(
    ("state", "move", "intent"),
    [
        ({"turn": 2}, "N", True),  # tampered state
        ({"turn": 1}, "S", True),  # tampered move
        ({"turn": 1}, "N", False),  # tampered intent
    ],
)
def test_verify_false_when_any_single_field_is_tampered(state, move, intent):
    c = commit(state={"turn": 1}, move="N", intent=True)
    assert not verify(state, move, intent, c.nonce, c.h_commit)


def test_verify_false_with_a_replayed_wrong_nonce():
    c = commit(state={"turn": 1}, move="N", intent=True)
    other_nonce = generate_nonce()
    assert not verify({"turn": 1}, "N", True, other_nonce, c.h_commit)


def test_verify_false_when_the_commit_hash_itself_is_altered():
    c = commit(state={"turn": 1}, move="N", intent=True)
    flipped = ("0" if c.h_commit[0] != "0" else "1") + c.h_commit[1:]
    assert not verify({"turn": 1}, "N", True, c.nonce, flipped)


def test_audit_log_passes_on_a_fully_untampered_log():
    entries = [
        LogEntry(state={"turn": i}, move="N", intent=True, **vars(commit({"turn": i}, "N", True)))
        for i in range(5)
    ]
    assert audit_log(entries) == AuditResult(verified=True)


def test_network_payload_without_optional_state_or_intent_still_verifies():
    payload = {
        "step": 2,
        "role": "police",
        "position": [2, 3],
        "move": "E",
    }
    nonce = "peer-nonce"
    serialized = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    digest = hashlib.sha256(f"{serialized}|{nonce}".encode()).hexdigest()
    entry = LogEntry(
        state=None, move="E", intent=None, nonce=nonce,
        h_commit=digest, payload=payload,
    )
    assert audit_log([entry]) == AuditResult(verified=True)


def test_audit_log_catches_the_first_tampered_entry_and_reports_its_index():
    good = commit({"turn": 0}, "N", True)
    entries = [
        LogEntry(state={"turn": 0}, move="N", intent=True, nonce=good.nonce, h_commit=good.h_commit),
        LogEntry(state={"turn": 1}, move="TAMPERED", intent=True, nonce=good.nonce, h_commit=good.h_commit),
    ]
    result = audit_log(entries)
    assert result.verified is False
    assert result.tampered_index == 1


def test_audit_log_of_empty_list_is_trivially_verified():
    assert audit_log([]) == AuditResult(verified=True)


def test_audit_log_result_is_deterministic_across_repeated_runs():
    """docs/tasks.md Sec. 5.4.2: the outcome must not depend on who runs it."""
    entries = [
        LogEntry(state={"turn": i}, move="N", intent=True, **vars(commit({"turn": i}, "N", True)))
        for i in range(5)
    ]
    first = audit_log(entries)
    second = audit_log(entries)
    assert first == second == AuditResult(verified=True)


def test_commitment_object_never_carries_the_raw_state_move_or_intent():
    """docs/tasks.md Sec. 5.2.2: only H_commit (plus the still-secret nonce)
    is ever sent -- the Commitment type structurally cannot leak the rest.
    """
    c = commit(state={"secret": "board layout"}, move="N", intent=True)
    fields = {f.name for f in dataclasses.fields(c)}
    assert fields == {"h_commit", "nonce"}


def test_capture_claim_can_be_sealed_and_verified_via_the_generic_commit_primitive():
    """docs/tasks.md Sec. 5.4 / T0378-379: no bespoke "sign_capture_claim"
    function is needed -- commit()/verify() are already generic enough to
    seal any claim shape, exactly like check_capture() is generic enough
    to cover both move-based and barrier-based captures (Chapter 3).
    """
    claim = CaptureClaim(claimant=AgentRole.COP, position=Position(2, 2))
    sealed = commit(state={"turn": 9}, move=dataclasses.asdict(claim), intent=True)

    # Honest claim verifies.
    assert verify({"turn": 9}, dataclasses.asdict(claim), True, sealed.nonce, sealed.h_commit)

    # A false claim (different position) is exposed by verification failure.
    false_claim = dataclasses.asdict(CaptureClaim(claimant=AgentRole.COP, position=Position(5, 5)))
    assert not verify({"turn": 9}, false_claim, True, sealed.nonce, sealed.h_commit)


def test_barrier_declaration_can_be_sealed_and_tamper_detected():
    """docs/tasks.md Sec. 3.3.6 / T0380-381: a barrier's declared location
    cannot be silently altered after being committed without breaking
    verification -- using the same generic primitive as any other move.
    """
    barrier_move = {"action": "place_barrier", "target": [2, 3]}
    sealed = commit(state={"turn": 4}, move=barrier_move, intent=True)
    assert verify({"turn": 4}, barrier_move, True, sealed.nonce, sealed.h_commit)

    altered_location = {"action": "place_barrier", "target": [0, 0]}
    assert not verify({"turn": 4}, altered_location, True, sealed.nonce, sealed.h_commit)


def test_multi_turn_log_audit_catches_a_post_hoc_tampering_attempt():
    """T0376's spirit without a live match engine yet: build a short
    realistic commit/reveal sequence across several turns, then tamper one
    entry after the fact and confirm the mutual audit catches it. Wiring
    this into an actual run_local_match log is Chapter 8's Log Manager/
    Orchestrator responsibility.
    """
    entries = []
    for turn in range(4):
        state = {"turn": turn, "cop": [0, turn], "thief": [6, 6 - turn]}
        move = "E"
        c = commit(state, move, intent=True)
        entries.append(LogEntry(state=state, move=move, intent=True, nonce=c.nonce, h_commit=c.h_commit))

    assert audit_log(entries).verified is True

    tampered_entries = list(entries)
    tampered_entries[2] = dataclasses.replace(tampered_entries[2], move="W")
    result = audit_log(tampered_entries)
    assert result.verified is False
    assert result.tampered_index == 2
