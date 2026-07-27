"""Editable JSON defaults for the cross-computer launcher."""

import json

import pytest

from police_thief.gui.network_setup import load_network_defaults, validate_mcp_url


def _defaults():
    return {
        "peer": {
            "role": "thief", "local_port": 9902,
            "opponent_url": "https://cop.example/mcp",
            "public_url": "https://thief.example/mcp",
        },
        "match": {
            "game_id": "G900", "sub_game_number": 2,
            "shared_match_secret": "shared", "output_directory": "results/custom",
        },
        "team_1": {
            "name": "Alpha", "members": ["A1", "A2"],
            "repos": {"cop": "alpha-cop", "thief": "alpha-thief"},
        },
        "team_2": {
            "name": "Beta", "members": ["B1", "B2"],
            "repos": {"cop": "beta-cop", "thief": "beta-thief"},
        },
        "email": {"automatic": True, "recipient": "reports@example.com"},
    }


def test_network_defaults_populate_all_gui_fields(tmp_path):
    path = tmp_path / "network_match.json"
    path.write_text(json.dumps(_defaults()), encoding="utf-8")

    loaded = load_network_defaults(path, tmp_path)

    assert loaded["role"] == "thief"
    assert loaded["port"] == "9902"
    assert loaded["team1_member2"] == "A2"
    assert loaded["team2_name"] == "Beta"
    assert loaded["email_recipient"] == "reports@example.com"
    assert loaded["output"] == str(tmp_path / "results" / "custom")


def test_network_defaults_require_two_members_per_team(tmp_path):
    raw = _defaults()
    raw["team_2"]["members"] = ["only-one"]
    path = tmp_path / "network_match.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly two members"):
        load_network_defaults(path, tmp_path)


def test_mcp_url_must_include_transport_route():
    assert validate_mcp_url("https://peer.example/mcp/") == "https://peer.example/mcp"
    with pytest.raises(ValueError, match="end with /mcp"):
        validate_mcp_url("https://peer.example")
