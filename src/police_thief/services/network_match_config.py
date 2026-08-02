"""Loading and validating config/network_match.json -- the match-session
config shared by the CLI `peer` command and the `play` GUI's two-computer
setup screen (gui/network_setup.py). Kept separate from the GUI module so
main.py can reuse it without importing tkinter-dependent code.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_REPORT_EMAIL = "rmisegal+uoh26finalgame@gmail.com"


def load_network_defaults(path: Path, project_root: Path) -> dict:
    """Flatten config/network_match.json into a single field dict."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        peer = raw["peer"]
        match = raw["match"]
        team1 = raw["team_1"]
        team2 = raw["team_2"]
        email = raw["email"]
        team1_members = list(team1["members"])
        team2_members = list(team2["members"])
        if len(team1_members) != 2 or len(team2_members) != 2:
            raise ValueError("each team must contain exactly two members")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid network defaults file {path}: {exc}") from exc
    output = Path(str(match.get("output_directory", "results/network")))
    if not output.is_absolute():
        output = project_root / output
    return {
        "role": str(peer.get("role", "cop")),
        "port": str(peer.get("local_port", 8801)),
        "opponent": str(peer.get("opponent_url", "https://opponent.example/mcp")),
        "public": str(peer.get("public_url", "https://your-tunnel.example/mcp")),
        "game": str(match.get("game_id", "G001")),
        "subgame": str(match.get("sub_game_number", 1)),
        "output": str(output),
        "secret": str(match.get("shared_match_secret", "")),
        "team1_name": str(team1.get("name", "")),
        "team1_member1": str(team1_members[0]),
        "team1_member2": str(team1_members[1]),
        "own_cop": str(team1.get("repos", {}).get("cop", "")),
        "own_thief": str(team1.get("repos", {}).get("thief", "")),
        "team2_name": str(team2.get("name", "")),
        "team2_member1": str(team2_members[0]),
        "team2_member2": str(team2_members[1]),
        "opponent_cop": str(team2.get("repos", {}).get("cop", "")),
        "opponent_thief": str(team2.get("repos", {}).get("thief", "")),
        "email": bool(email.get("automatic", False)),
        "email_recipient": str(email.get("recipient", DEFAULT_REPORT_EMAIL)),
    }


def validate_mcp_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path.endswith("/mcp"):
        raise ValueError("URL must be http(s) and end with /mcp")
    return url


def validate_peer_defaults(defaults: dict, opponent_url: str) -> None:
    """Fail before opening a port when live-match metadata is incomplete."""
    urls = {
        "opponent URL": validate_mcp_url(opponent_url),
        "public URL": validate_mcp_url(defaults["public"]),
    }
    for label, url in urls.items():
        if (urlparse(url).hostname or "").endswith(".example"):
            raise ValueError(f"{label} is still a placeholder: {url}")

    required_text = {
        "game ID": defaults["game"],
        "shared match secret": defaults["secret"],
        "Team 1 name": defaults["team1_name"],
        "Team 1 member 1": defaults["team1_member1"],
        "Team 1 member 2": defaults["team1_member2"],
        "Team 2 name": defaults["team2_name"],
        "Team 2 member 1": defaults["team2_member1"],
        "Team 2 member 2": defaults["team2_member2"],
    }
    required_repos = {
        "Team 1 cop repository": defaults["own_cop"],
        "Team 1 thief repository": defaults["own_thief"],
        "Team 2 cop repository": defaults["opponent_cop"],
        "Team 2 thief repository": defaults["opponent_thief"],
    }
    missing = [label for label, value in required_text.items() if not str(value).strip()]
    for label, value in required_repos.items():
        parsed = urlparse(str(value).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            missing.append(label)
    if missing:
        raise ValueError("live peer configuration is incomplete: " + ", ".join(missing))
