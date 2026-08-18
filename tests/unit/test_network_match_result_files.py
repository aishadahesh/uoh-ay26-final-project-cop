from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from police_thief.domain.scoring import MatchOutcome, ScoringTable
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.shared.constants import AgentRole


def test_network_subgame_result_is_suffixed_even_for_one_game_series(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "police_thief.services.network_match.get_git_commit_hash",
        lambda _cwd: "a" * 40,
    )
    settings = NetworkMatchSettings(
        role=AgentRole.COP,
        local_port=8801,
        opponent_url="https://peer.example/mcp",
        public_url="https://us.example/mcp",
        game_id="GONE",
        sub_game_number=1,
        shared_config=Path("config/game.json"),
        output_dir=tmp_path,
        team_name="uoh-ay26",
        opponent_team_name="SMNGRP05",
    )
    runner = NetworkMatchRunner(settings, PeerInboxes(), transport=None)
    params = SimpleNamespace(
        network_league=SimpleNamespace(num_games=1),
        scoring=ScoringTable(),
    )

    path = runner._write_result(
        params,
        [],
        MatchOutcome.SURVIVAL,
        {
            "group_id": "SMNGRP05",
            "group_name": "SMNGRP05",
            "members": [],
            "repos": {},
            "github_commit": "b" * 40,
        },
        {"total": 0},
        lambda _message: None,
    )

    assert path == tmp_path / "result_GONE_g01.json"
    assert path.exists()
    assert not (tmp_path / "result_GONE.json").exists()
