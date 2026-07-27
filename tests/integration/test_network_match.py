"""Two independent match runners exchanging only MCP envelopes."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from police_thief.services.mcp_server import MoveEnvelope
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.shared.constants import AgentRole


def test_two_computers_reconstruct_and_sign_off_same_match(tmp_path, monkeypatch):
    project_root = Path(__file__).parents[2]
    common = {
        "local_port": 8801,
        "public_url": "https://local.example/mcp",
        "game_id": "NETWORK-TEST",
        "sub_game_number": 1,
        "shared_config": project_root / "config" / "game.json",
        "team_name": "test-team",
        "members": ("Ada", "Grace"),
        "opponent_team_name": "rival-team",
        "opponent_members": ("Linus", "Margaret"),
        "own_cop_repo": "https://example.test/a-cop",
        "own_thief_repo": "https://example.test/a-thief",
        "opponent_cop_repo": "https://example.test/b-cop",
        "opponent_thief_repo": "https://example.test/b-thief",
        "shared_key": b"integration-secret",
    }
    cop = NetworkMatchRunner(NetworkMatchSettings(
        role=AgentRole.COP, opponent_url="https://thief.example/mcp",
        output_dir=tmp_path / "cop", **common,
    ))
    thief = NetworkMatchRunner(NetworkMatchSettings(
        role=AgentRole.THIEF, opponent_url="https://cop.example/mcp",
        output_dir=tmp_path / "thief", **common,
    ))
    routes = {
        "https://cop.example/mcp": cop,
        "https://thief.example/mcp": thief,
    }

    def route(url, payload, signature, _timeout):
        return routes[url].receive(MoveEnvelope(payload, signature))

    monkeypatch.setattr("police_thief.services.network_match.send_move", route)
    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(lambda runner: runner.run(Event()), (cop, thief)))

    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert all(result["mutual_sign_off"] for result in results)
    assert results[0]["team_a"] == {
        "team_name": "test-team", "members": ["Ada", "Grace"],
    }
    assert results[0]["team_b"] == {
        "team_name": "rival-team", "members": ["Linus", "Margaret"],
    }
    assert results[0]["log_sha256"] == results[1]["log_sha256"]
    assert (tmp_path / "cop" / "declaration_NETWORK-TEST.json").is_file()
    assert (tmp_path / "thief" / "config_NETWORK-TEST_g01.json").is_file()
