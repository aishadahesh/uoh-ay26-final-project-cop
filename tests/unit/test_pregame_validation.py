"""Strict pre-game validation without private-strategy inspection."""

import copy
import json
from pathlib import Path

from police_thief.services.pregame_validation import (
    build_local_conformance,
    save_validation_result,
    validate_peer_conformance,
    validate_shared_game,
)

ROOT = Path(__file__).parents[2]
COMMIT = "a" * 40


def _game():
    return json.loads((ROOT / "config" / "game.json").read_text(encoding="utf-8"))


def _manifest(tmp_path, role="cop"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    game_path, toml_path = tmp_path / "game.json", tmp_path / "game.toml"
    game_path.write_text(json.dumps(_game()), encoding="utf-8")
    toml_path.write_text(
        'version = "1.00"\n[game]\ngroup_name = "alpha"\n'
        'group_id = "alpha001"\nsub_game_number = 1\n'
        'members = ["Ada", "Grace"]\n'
        'repos = { cop = "https://github.com/example/cop", thief = "https://github.com/example/thief" }\n'
        '[network]\nmy_port = 8801\nopponent_url = "https://peer.example/mcp"\n'
        'turn_timeout_seconds = 120\n[strategy]\nprivate_prompt = "never transmit"\n',
        encoding="utf-8",
    )
    return build_local_conformance(
        game_path, toml_path, role=role, sub_game_number=1,
        git_commit_hash=COMMIT,
    )


def test_official_shared_config_passes_strict_schema():
    assert validate_shared_game(_game()) == []


def test_protected_type_and_unknown_field_are_rejected():
    data = _game()
    data["board_and_agents"]["grid_size"] = "7"
    data["movement_and_barriers"]["diagonal_moves"] = True
    issues = validate_shared_game(data, scope="opponent")
    assert any(i.field == "board_and_agents.grid_size" and i.code == "wrong_type" for i in issues)
    assert any(i.field == "board_and_agents.grid_size" and i.code == "protected_value_mismatch" for i in issues)
    assert any(i.field == "movement_and_barriers.diagonal_moves" and i.code == "unexpected_field" for i in issues)


def test_private_toml_is_redacted_and_hidden_protected_key_fails(tmp_path):
    manifest, issues = _manifest(tmp_path)
    assert issues == []
    assert "private_prompt" not in json.dumps(manifest)
    assert manifest["toml_public"]["private_sections_present"] == ["strategy"]
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        toml_path.read_text(encoding="utf-8").replace(
            "sub_game_number = 1\n", "sub_game_number = 1\ngrid_size = 99\n"
        ), encoding="utf-8",
    )
    _, issues = build_local_conformance(
        tmp_path / "game.json", toml_path, role="cop",
        sub_game_number=1, git_commit_hash=COMMIT,
    )
    assert any(i.field == "game.grid_size" and i.code == "unexpected_or_protected_field" for i in issues)


def test_peer_shared_mismatch_stops_validation(tmp_path):
    local, issues = _manifest(tmp_path / "local")
    assert issues == []
    peer = copy.deepcopy(local)
    peer["role"] = "thief"
    peer["game_config"]["scoring"]["capture_cop"] = 999
    identity = {
        "group_name": "alpha", "members": ["Ada", "Grace"],
        "repos": {"cop": "https://github.com/example/cop", "thief": "https://github.com/example/thief"},
        "git_commit_hash": COMMIT,
    }
    peer_issues, _ = validate_peer_conformance(
        peer, local, local_role="cop", sub_game_number=1,
        peer_identity=identity, inspect_repository=False,
    )
    assert any(i.field == "scoring.capture_cop" for i in peer_issues)
    assert any(i.code == "checksum_mismatch" for i in peer_issues)


def test_agreed_single_game_is_valid():
    data = _game()
    data["network_and_league"]["num_games"] = 1
    assert validate_shared_game(data) == []


def test_failed_report_contains_expected_and_received(tmp_path):
    data = _game()
    data["network_and_league"]["num_games"] = 0
    issues = validate_shared_game(data)
    path = save_validation_result(
        tmp_path, game_id="G001", sub_game_number=1, status="failed",
        local_manifest=None, issues=issues,
    )
    report = json.loads(path.read_text(encoding="utf-8"))
    failure = next(i for i in report["issues"] if i["field"] == "network_and_league.num_games")
    assert report["status"] == "failed"
    assert failure["expected"] == "integer from 1 through max_games_per_team (10)"
    assert failure["received"] == 0
