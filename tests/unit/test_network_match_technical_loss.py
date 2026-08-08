"""Unit tests for NetworkMatchRunner._write_technical_loss_result.

Covers the graceful-failure path added after a real opponent's tunnel
dropped mid-match and crashed the whole process with an unhandled
PeerClientError traceback -- this is what NetworkMatchRunner.run() now
falls back to instead (Sec. 9.2's technical-loss score, 0/0).
"""

import json
from pathlib import Path

from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.services.network_protocol import seal_payload
from police_thief.shared.constants import AgentRole
from police_thief.shared.game_config import load_match_parameters


def _runner(tmp_path: Path) -> NetworkMatchRunner:
    settings = NetworkMatchSettings(
        role=AgentRole.COP, local_port=8801, opponent_url="https://peer.example/mcp",
        public_url="https://local.example/mcp", game_id="TL-TEST", sub_game_number=1,
        shared_config=Path("config/game.json"), output_dir=tmp_path,
        team_name="our-team", members=("Ada", "Grace"),
    )
    return NetworkMatchRunner(settings, PeerInboxes(), transport=object())


def _own_records() -> list[dict]:
    return [
        seal_payload({"step": 0, "type": "system_spec"}),
        seal_payload({
            "step": 1, "state": {"row": 0, "col": 0}, "move": "N", "intent": True,
        }),
    ]


def _records_with_terminal_capture_ack() -> list[dict]:
    return [
        *_own_records(),
        seal_payload({
            "step": 2,
            "role": "thief",
            "state": {"row": 3, "col": 3},
            "position": [3, 3],
            "terminal_ack": "capture",
            "claim_response": {"claim": [3, 3], "caught": True},
        }),
    ]


def _peer_identity() -> dict:
    return {
        "group_name": "rival-team", "group_id": "rival-team", "members": ["Linus", "Margaret"],
        "repos": {"cop": "https://example.test/b-cop", "thief": "https://example.test/b-thief"},
    }


def test_technical_loss_result_scores_zero_zero(tmp_path):
    runner = _runner(tmp_path)
    params = load_match_parameters(Path("config/game.json"))
    path = runner._write_technical_loss_result(
        params, _own_records(), _peer_identity(), lambda _message: None,
    )
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["outcome"] == "technical_loss"
    assert result["cop_score"] == 0
    assert result["thief_score"] == 0


def test_technical_loss_result_is_not_mutually_signed_off(tmp_path):
    """Unlike every normal result, the opponent never confirmed anything
    past whatever it acknowledged before going dark -- this must not be
    reported as if it were a normal, cross-verified outcome."""
    runner = _runner(tmp_path)
    params = load_match_parameters(Path("config/game.json"))
    path = runner._write_technical_loss_result(
        params, _own_records(), _peer_identity(), lambda _message: None,
    )
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["mutual_sign_off"] is False


def test_technical_loss_result_excludes_the_step_zero_system_spec_record(tmp_path):
    """Only real move steps (step > 0) belong in the replay log -- the
    step-0 system-spec record is metadata, not a move (matches
    NetworkMatchRunner._combined_log's own filter)."""
    runner = _runner(tmp_path)
    params = load_match_parameters(Path("config/game.json"))
    runner._write_technical_loss_result(
        params, _own_records(), _peer_identity(), lambda _message: None,
    )
    log_path = tmp_path / "log_TL-TEST_g01.json"
    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["move"] == "N"


def test_technical_loss_result_excludes_terminal_records_without_a_move(tmp_path):
    """A capture acknowledgement is signed evidence, not an executed move."""
    runner = _runner(tmp_path)
    params = load_match_parameters(Path("config/game.json"))

    path = runner._write_technical_loss_result(
        params,
        _records_with_terminal_capture_ack(),
        _peer_identity(),
        lambda _message: None,
    )

    result = json.loads(path.read_text(encoding="utf-8"))
    entries = json.loads((tmp_path / "log_TL-TEST_g01.json").read_text(encoding="utf-8"))
    assert result["outcome"] == "technical_loss"
    assert [entry["move"] for entry in entries] == ["N"]
