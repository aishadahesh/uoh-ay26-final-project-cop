"""Unit tests for the Replay Viewer core logic (Chapter 7)."""

import dataclasses
import json

import pytest

from police_thief.domain.replay import (
    TAMPERED,
    VERIFIED_OK,
    ReplayLogError,
    ReplaySession,
    load_log,
    save_log,
)
from police_thief.services.commit_reveal import LogEntry, commit
from police_thief.services.network_protocol import seal_payload


def _make_entries(n: int) -> list[LogEntry]:
    entries = []
    for i in range(n):
        c = commit(state={"turn": i}, move="N", intent=True)
        entries.append(LogEntry(state={"turn": i}, move="N", intent=True, nonce=c.nonce, h_commit=c.h_commit))
    return entries


def test_save_and_load_log_round_trips_exactly(tmp_path):
    entries = _make_entries(4)
    path = tmp_path / "log.json"
    save_log(entries, path)
    loaded = load_log(path)
    assert loaded == entries


def test_load_log_raises_on_missing_file(tmp_path):
    with pytest.raises(ReplayLogError, match="missing match log file"):
        load_log(tmp_path / "does_not_exist.json")


def test_load_log_raises_on_malformed_json(tmp_path):
    path = tmp_path / "log.json"
    path.write_text('[{"state": {}, "move": "N"}]', encoding="utf-8")  # missing required fields
    with pytest.raises(ReplayLogError, match="malformed match log"):
        load_log(path)


def test_replay_session_on_clean_log_is_fully_verified():
    session = ReplaySession(_make_entries(5))
    assert session.is_fully_verified is True
    assert session.first_tampered_index is None
    assert session.total_steps == 5


def test_replay_session_summary_counts_on_a_clean_log():
    session = ReplaySession(_make_entries(5))
    assert session.verified_count == 5
    assert session.tampered_count == 0


def test_replay_session_summary_counts_on_a_tampered_log():
    entries = _make_entries(5)
    tampered = list(entries)
    tampered[2] = dataclasses.replace(tampered[2], move="X")
    session = ReplaySession(tampered)
    assert session.verified_count == 2
    assert session.tampered_count == 3


def test_replay_session_every_step_is_verified_ok_on_a_clean_log():
    session = ReplaySession(_make_entries(5))
    for i in range(5):
        assert session.step_view(i).status == VERIFIED_OK


def test_replay_session_detects_tampering_and_reports_the_exact_index():
    entries = _make_entries(5)
    tampered = list(entries)
    tampered[2] = dataclasses.replace(tampered[2], move="TAMPERED_MOVE")
    session = ReplaySession(tampered)
    assert session.is_fully_verified is False
    assert session.first_tampered_index == 2


def test_replay_session_voids_every_step_from_the_first_tamper_onward():
    """Sec. 7.5.1: 'the entire match is voided on the first tamper detected'
    -- not just the one altered entry.
    """
    entries = _make_entries(5)
    tampered = list(entries)
    tampered[2] = dataclasses.replace(tampered[2], move="TAMPERED_MOVE")
    session = ReplaySession(tampered)
    assert session.step_view(0).status == VERIFIED_OK
    assert session.step_view(1).status == VERIFIED_OK
    assert session.step_view(2).status == TAMPERED
    assert session.step_view(3).status == TAMPERED
    assert session.step_view(4).status == TAMPERED


def test_replay_session_step_view_rejects_out_of_range_index():
    session = ReplaySession(_make_entries(3))
    with pytest.raises(IndexError):
        session.step_view(3)
    with pytest.raises(IndexError):
        session.step_view(-1)


def test_replay_session_next_stops_at_the_last_step():
    session = ReplaySession(_make_entries(3))
    session.jump_to(2)
    assert session.next().index == 2  # already at the last step, stays put


def test_replay_session_previous_stops_at_the_first_step():
    session = ReplaySession(_make_entries(3))
    assert session.previous().index == 0  # already at the first step, stays put


def test_replay_session_scrubbing_moves_forward_and_backward():
    session = ReplaySession(_make_entries(4))
    assert session.current_step.index == 0
    assert session.next().index == 1
    assert session.next().index == 2
    assert session.previous().index == 1


def test_replay_session_jump_to_moves_directly_to_a_step():
    session = ReplaySession(_make_entries(4))
    assert session.jump_to(3).index == 3
    assert session.current_step.index == 3


def test_replay_session_jump_to_rejects_out_of_range_and_does_not_move():
    session = ReplaySession(_make_entries(3))
    with pytest.raises(IndexError):
        session.jump_to(99)
    assert session.current_step.index == 0  # unchanged after the rejected jump


def test_end_to_end_tampering_via_a_real_file_round_trip(tmp_path):
    """The full Chapter 7 promise: save a clean log, tamper the file on
    disk, reload it, and confirm the Replay Viewer's own logic (not a
    mocked shortcut) catches it.
    """
    entries = _make_entries(4)
    path = tmp_path / "log.json"
    save_log(entries, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw[1]["move"] = "TAMPERED"
    path.write_text(json.dumps(raw), encoding="utf-8")

    reloaded = load_log(path)
    session = ReplaySession(reloaded)
    assert session.is_fully_verified is False
    assert session.first_tampered_index == 1


def test_replay_verifies_reference_style_full_payload_commitment():
    payload = {
        "step": 1, "state": "grid=7x7;self=[1, 2]", "move": "move:north",
        "intent": "truth", "hint": "near the river",
    }
    record = seal_payload(payload)
    entry = LogEntry(
        state=payload["state"], move=payload["move"], intent=payload["intent"],
        nonce=record["nonce"], h_commit=record["commit"], payload=payload,
    )

    assert ReplaySession([entry]).is_fully_verified
    assert not ReplaySession([dataclasses.replace(entry, move="tampered")]).is_fully_verified
