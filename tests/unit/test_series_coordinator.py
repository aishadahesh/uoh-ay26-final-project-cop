from __future__ import annotations

import json
from types import SimpleNamespace

from police_thief.services import series_coordinator
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchSettings, finalize_completed_series
from police_thief.shared.constants import AgentRole


def test_role_schedule_starts_with_police_and_alternates() -> None:
    assert [
        series_coordinator.role_for_series_game(AgentRole.COP, number)
        for number in range(1, 7)
    ] == [
        AgentRole.COP, AgentRole.THIEF, AgentRole.COP,
        AgentRole.THIEF, AgentRole.COP, AgentRole.THIEF,
    ]


def test_run_series_launches_fixed_role_repositories_and_finalizes_last_child(
    tmp_path, monkeypatch,
) -> None:
    current = tmp_path / "cop"
    sibling = tmp_path / "thief"
    (current / "config").mkdir(parents=True)
    (sibling / "config").mkdir(parents=True)
    output = tmp_path / "results"
    monkeypatch.setattr(
        series_coordinator, "load_match_parameters",
        lambda _path: SimpleNamespace(network_league=SimpleNamespace(num_games=6)),
    )
    calls = []

    def fake_run(command, *, cwd, env, check):
        calls.append((command, cwd, env, check))
        number = int(command[command.index("--sub-game-number") + 1])
        (output / f"log_G003_g{number:02d}.json").parent.mkdir(parents=True, exist_ok=True)
        (output / f"log_G003_g{number:02d}.json").write_text("[]", encoding="utf-8")
        (output / f"result_G003_g{number:02d}.json").write_text(json.dumps({
            "game_id": "G003", "sub_game_number": number, "outcome": "survival",
            "mutual_sign_off": True,
        }), encoding="utf-8")
        if number == 6:
            (output / "result_G003.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(series_coordinator.subprocess, "run", fake_run)
    path = series_coordinator.run_series(
        current_role=AgentRole.COP,
        first_role=AgentRole.COP,
        current_repo=current,
        sibling_repo=sibling,
        config_root=current / "config",
        output_dir=output,
        game_id="G003",
        first_sub_game=1,
    )
    assert path == output / "result_G003.json"
    assert [cwd for _, cwd, _, _ in calls] == [
        current, sibling, current, sibling, current, sibling,
    ]
    assert "--finalize-series" not in calls[4][0]
    assert "--finalize-series" in calls[5][0]
    assert all(call[2]["PYTHONPATH"].split(";")[0] == str(call[1] / "src") for call in calls)


def test_run_series_resumes_after_verified_existing_artifact(tmp_path, monkeypatch) -> None:
    current = tmp_path / "cop"
    sibling = tmp_path / "thief"
    (current / "config").mkdir(parents=True)
    (sibling / "config").mkdir(parents=True)
    output = tmp_path / "results"
    output.mkdir()
    (output / "log_G003_g01.json").write_text("[]", encoding="utf-8")
    (output / "result_G003_g01.json").write_text(json.dumps({
        "game_id": "G003", "sub_game_number": 1, "outcome": "survival",
        "mutual_sign_off": True,
    }), encoding="utf-8")
    monkeypatch.setattr(
        series_coordinator, "load_match_parameters",
        lambda _path: SimpleNamespace(network_league=SimpleNamespace(num_games=2)),
    )
    calls = []

    def fake_run(command, *, cwd, env, check):
        calls.append(command)
        (output / "log_G003_g02.json").write_text("[]", encoding="utf-8")
        (output / "result_G003_g02.json").write_text(json.dumps({
            "game_id": "G003", "sub_game_number": 2, "outcome": "survival",
            "mutual_sign_off": True,
        }), encoding="utf-8")
        (output / "result_G003.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(series_coordinator.subprocess, "run", fake_run)
    series_coordinator.run_series(
        current_role=AgentRole.COP, first_role=AgentRole.COP,
        current_repo=current, sibling_repo=sibling, config_root=current / "config",
        output_dir=output, game_id="G003", first_sub_game=1,
    )
    assert len(calls) == 1
    assert calls[0][calls[0].index("--sub-game-number") + 1] == "2"


def test_run_series_does_not_treat_stale_subgame_result_as_final(tmp_path, monkeypatch) -> None:
    current = tmp_path / "cop"
    sibling = tmp_path / "thief"
    (current / "config").mkdir(parents=True)
    (sibling / "config").mkdir(parents=True)
    output = tmp_path / "results"
    output.mkdir()
    (output / "log_G003_g01.json").write_text("[]", encoding="utf-8")
    (output / "result_G003_g01.json").write_text(json.dumps({
        "game_id": "G003", "sub_game_number": 1, "outcome": "survival",
        "mutual_sign_off": True,
    }), encoding="utf-8")
    (output / "result_G003.json").write_text(json.dumps({
        "game_id": "G003", "sub_game_number": 1, "outcome": "survival",
        "mutual_sign_off": True,
    }), encoding="utf-8")
    monkeypatch.setattr(
        series_coordinator, "load_match_parameters",
        lambda _path: SimpleNamespace(network_league=SimpleNamespace(num_games=1)),
    )
    calls = []

    def fake_run(command, *, cwd, env, check):
        calls.append(command)
        (output / "result_G003.json").write_text(json.dumps({
            "game_id": "G003", "report_type": "final_game_result",
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(series_coordinator.subprocess, "run", fake_run)
    path = series_coordinator.run_series(
        current_role=AgentRole.COP, first_role=AgentRole.COP,
        current_repo=current, sibling_repo=sibling, config_root=current / "config",
        output_dir=output, game_id="G003", first_sub_game=1,
    )
    assert path == output / "result_G003.json"
    assert len(calls) == 1
    assert "--finalize-series" in calls[0]


def test_finalize_completed_series_builds_six_game_result(tmp_path, monkeypatch) -> None:
    participants = {
        "alpha": {"group_name": "alpha", "github_commit": "a" * 40, "mcp_servers": {}},
        "beta": {"group_name": "beta", "github_commit": "b" * 40, "mcp_servers": {}},
    }
    games = {}
    for number in range(1, 7):
        games[str(number)] = {"started_at": f"2026-01-01T00:0{number}:00+00:00", "ended_at": f"2026-01-01T00:0{number}:30+00:00"}
        (tmp_path / f"result_G003_g{number:02d}.json").write_text(json.dumps({
            "game_id": "G003", "sub_game_number": number, "outcome": "survival",
            "cop_score": 5, "thief_score": 10, "mutual_sign_off": True,
            "participants": participants, "token_usage_by_group": {"alpha": 0, "beta": 0},
            "log_sha256": str(number) * 64,
        }), encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"game_id": "G003", "series_started_at": "2026-01-01T00:00:00+00:00", "games": games}), encoding="utf-8")
    params = SimpleNamespace(
        network_league=SimpleNamespace(num_games=6, response_timeout_sec=1, token_budget_per_series=200000),
        scoring=SimpleNamespace(tie_score=2),
    )
    monkeypatch.setattr("police_thief.services.network_match.load_match_parameters", lambda _path: params)
    monkeypatch.setattr(
        "police_thief.services.network_match.derive_game_uid",
        lambda _terms, _groups, **_kwargs: "uid",
    )
    monkeypatch.setattr("police_thief.services.network_match.finalize_submission_bundle", lambda *args, **kwargs: [tmp_path / "result_G003.json"])
    monkeypatch.setattr("police_thief.services.network_match.save_series_result", lambda result, directory, game_id: (directory / f"result_{game_id}.json").write_text(json.dumps(result), encoding="utf-8"))

    class Transport:
        def exchange_audit(self, payload, timeout):
            return {"sender": "thief", "records": [], "result_claim": "series_consensus", "consensus_sha": payload["consensus_sha"], "token_usage": None}

    settings = NetworkMatchSettings(
        role=AgentRole.COP, local_port=8801, opponent_url="https://peer.test/mcp",
        public_url="https://us.test/mcp", game_id="G003", sub_game_number=6,
        shared_config=tmp_path / "game.json", output_dir=tmp_path, team_name="alpha",
    )
    monkeypatch.setattr("police_thief.services.network_match.McpPeerTransport", lambda *args, **kwargs: Transport())
    monkeypatch.setattr("police_thief.services.network_match.NetworkMatchRunner._terms", lambda self, value: {})
    path = finalize_completed_series(settings, PeerInboxes(), state, AgentRole.COP)
    assert path == tmp_path / "result_G003.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    assert len(result["sub_games"]) == 6
    assert result["consensus_confirmed"] is True


def test_finalize_completed_series_accepts_peer_natural_role_consensus_sender(
    tmp_path, monkeypatch,
) -> None:
    participants = {
        "alpha": {"group_name": "alpha", "github_commit": "a" * 40, "mcp_servers": {}},
        "beta": {"group_name": "beta", "github_commit": "b" * 40, "mcp_servers": {}},
    }
    games = {}
    for number in range(1, 7):
        games[str(number)] = {
            "started_at": f"2026-01-01T00:0{number}:00+00:00",
            "ended_at": f"2026-01-01T00:0{number}:30+00:00",
        }
        (tmp_path / f"result_G003_g{number:02d}.json").write_text(json.dumps({
            "game_id": "G003", "sub_game_number": number, "outcome": "survival",
            "cop_score": 5, "thief_score": 10, "mutual_sign_off": True,
            "participants": participants, "token_usage_by_group": {"alpha": 0, "beta": 0},
            "log_sha256": str(number) * 64,
        }), encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "game_id": "G003", "series_started_at": "2026-01-01T00:00:00+00:00",
        "games": games,
    }), encoding="utf-8")
    params = SimpleNamespace(
        network_league=SimpleNamespace(num_games=6, response_timeout_sec=1, token_budget_per_series=200000),
        scoring=SimpleNamespace(tie_score=2),
    )
    monkeypatch.setattr("police_thief.services.network_match.load_match_parameters", lambda _path: params)
    monkeypatch.setattr(
        "police_thief.services.network_match.derive_game_uid",
        lambda _terms, _groups, **_kwargs: "uid",
    )
    monkeypatch.setattr("police_thief.services.network_match.finalize_submission_bundle", lambda *args, **kwargs: [tmp_path / "result_G003.json"])
    monkeypatch.setattr("police_thief.services.network_match.save_series_result", lambda result, directory, game_id: (directory / f"result_{game_id}.json").write_text(json.dumps(result), encoding="utf-8"))

    class Transport:
        def exchange_audit(self, payload, timeout):
            return {
                "sender": "thief", "records": [],
                "result_claim": "series_consensus",
                "consensus_sha": payload["consensus_sha"],
                "token_usage": None,
            }

    settings = NetworkMatchSettings(
        role=AgentRole.THIEF, local_port=8802, opponent_url="https://peer.test/mcp",
        public_url="https://us.test/mcp", game_id="G003", sub_game_number=6,
        shared_config=tmp_path / "game.json", output_dir=tmp_path, team_name="alpha",
    )
    monkeypatch.setattr("police_thief.services.network_match.McpPeerTransport", lambda *args, **kwargs: Transport())
    monkeypatch.setattr("police_thief.services.network_match.NetworkMatchRunner._terms", lambda self, value: {})
    path = finalize_completed_series(settings, PeerInboxes(), state, AgentRole.COP)
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["consensus_confirmed"] is True
