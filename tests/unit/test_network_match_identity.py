"""Peer identity matching tests."""

from pathlib import Path

import pytest

from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.services.network_protocol import NetworkProtocolError, verify_record
from police_thief.shared.constants import AgentRole


def _runner() -> NetworkMatchRunner:
    settings = NetworkMatchSettings(
        role=AgentRole.COP,
        local_port=8801,
        opponent_url="https://opponent.example/mcp",
        public_url="https://local.example/mcp",
        game_id="IDENTITY",
        sub_game_number=1,
        shared_config=Path("config/game.json"),
        output_dir=Path("results/network"),
        opponent_team_name="najamjad",
    )
    return NetworkMatchRunner(settings, PeerInboxes())


def test_peer_group_name_matching_is_case_insensitive():
    _runner()._validate_peer_identity({"group_name": "NajAmjad"})


def test_peer_group_name_still_rejects_a_different_name():
    with pytest.raises(NetworkProtocolError, match="opponent identity mismatch for group_name"):
        _runner()._validate_peer_identity({"group_name": "different-team"})


def test_sealed_step_zero_contains_the_serving_git_commit(monkeypatch):
    commit = "a" * 40
    monkeypatch.setattr(
        "police_thief.services.network_match.get_git_commit_hash",
        lambda _cwd: commit,
    )

    record = _runner()._sealed_system_spec()

    assert record["payload"]["git_commit_hash"] == commit
    assert record["payload"]["github_commit"] == commit
    assert verify_record(record)
