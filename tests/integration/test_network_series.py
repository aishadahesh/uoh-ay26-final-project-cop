"""Two peers playing a full agreed series with role alternation.

Split out of the original `test_network_match.py`."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import (
    NetworkMatchSeriesRunner,
    NetworkMatchSettings,
)
from police_thief.shared.constants import AgentRole
from tests.integration.network_match_helpers import (
    MemoryTransport,
    _team_config,
)


@pytest.mark.skip(reason="obsolete: submitted repositories may not alternate live roles in-process")
@pytest.mark.parametrize("num_games", [1, 6])
def test_two_peers_play_agreed_series_with_role_alternation(
    tmp_path, monkeypatch, num_games,
):
    project_root = Path(__file__).parents[2]
    monkeypatch.setattr(
        "police_thief.services.pregame_peer_check.inspect_public_repository",
        lambda *_args: ([], [{"status": "verified-test-double"}]),
    )
    monkeypatch.setattr(
        "police_thief.services.network_match.get_git_commit_hash", lambda _path: "a" * 40,
    )
    alpha_repos = {
        "cop": "https://github.com/example/a-cop",
        "thief": "https://github.com/example/a-thief",
    }
    beta_repos = {
        "cop": "https://github.com/example/b-cop",
        "thief": "https://github.com/example/b-thief",
    }
    alpha_config = _team_config(
        tmp_path, project_root / "config" / "game.json", "alpha", "alpha",
        ("Ada", "Grace"), alpha_repos, num_games,
    )
    beta_config = _team_config(
        tmp_path, project_root / "config" / "game.json", "beta", "beta",
        ("Linus", "Margaret"), beta_repos, num_games,
    )
    common = {
        "local_port": 8801,
        "game_id": "NETWORK-TEST", "sub_game_number": 1,
        "shared_key": b"integration-secret",
    }
    cop_inboxes, thief_inboxes = PeerInboxes(), PeerInboxes()
    cop = NetworkMatchSeriesRunner(
        NetworkMatchSettings(
            role=AgentRole.COP, opponent_url="https://thief.example/mcp",
            public_url="https://cop.example/mcp", output_dir=tmp_path / "cop",
            team_name="alpha", members=("Ada", "Grace"),
            opponent_team_name="beta", opponent_members=("Linus", "Margaret"),
            own_cop_repo=alpha_repos["cop"], own_thief_repo=alpha_repos["thief"],
            opponent_cop_repo=beta_repos["cop"], opponent_thief_repo=beta_repos["thief"],
            shared_config=alpha_config, **common,
        ),
        cop_inboxes, transport=MemoryTransport(cop_inboxes, thief_inboxes),
    )
    thief = NetworkMatchSeriesRunner(
        NetworkMatchSettings(
            role=AgentRole.THIEF, opponent_url="https://cop.example/mcp",
            public_url="https://thief.example/mcp", output_dir=tmp_path / "thief",
            team_name="beta", members=("Linus", "Margaret"),
            opponent_team_name="alpha", opponent_members=("Ada", "Grace"),
            own_cop_repo=beta_repos["cop"], own_thief_repo=beta_repos["thief"],
            opponent_cop_repo=alpha_repos["cop"], opponent_thief_repo=alpha_repos["thief"],
            shared_config=beta_config, **common,
        ),
        thief_inboxes, transport=MemoryTransport(thief_inboxes, cop_inboxes),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(lambda runner: runner.run(Event()), (cop, thief)))

    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert all(result["mutual_agreement"]["confirmed"] for result in results)
    assert len({result["mutual_agreement"]["sha256"] for result in results}) == 1
    assert all(result["num_sub_games"] == num_games for result in results)
    assert results[0]["game_uid"] == results[1]["game_uid"]
    assert results[0]["final_result"]["total_score"] == results[1]["final_result"]["total_score"]
    assert [game["roles"]["alpha"] for game in results[0]["sub_games"]] == [
        "police" if index % 2 == 0 else "thief" for index in range(num_games)
    ]
    assert [game["roles"]["beta"] for game in results[0]["sub_games"]] == [
        "thief" if index % 2 == 0 else "police" for index in range(num_games)
    ]
    for number in range(1, num_games + 1):
        assert (tmp_path / "cop" / f"log_NETWORK-TEST_g{number:02d}.json").is_file()
        assert (tmp_path / "thief" / f"config_NETWORK-TEST_g{number:02d}.json").is_file()
    assert (tmp_path / "cop" / "declaration_NETWORK-TEST.json").is_file()
    assert (tmp_path / "cop" / "result_NETWORK-TEST.json").is_file()

    trajectories = set()
    for number in range(1, num_games + 1):
        log_document = json.loads(
            (tmp_path / "cop" / f"log_NETWORK-TEST_g{number:02d}.json").read_text(
                encoding="utf-8"
            )
        )
        records = log_document["records"]
        moves = [
            record["payload"]
            for record in records
            if record.get("payload", {}).get("move")
        ]
        for move in moves:
            if "barrier_placed" not in move:
                continue
            assert move["role"] == "police"
            assert move["move"] == "STAY"
            assert move["state"] == {
                "row": move["position"][0],
                "col": move["position"][1],
            }
        trajectories.add(
            tuple((move["role"], move["move"], tuple(move["position"])) for move in moves)
        )
    assert len(trajectories) >= min(2, num_games), (
        "multi-game series must not replay one identical trajectory"
    )
