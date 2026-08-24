"""Building this side's public conformance manifest and diffing it against
the peer's."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from police_thief.services.pregame_game_json import validate_shared_game
from police_thief.services.pregame_schema import (
    _PROTECTED,
    _RULE_PROFILE,
    VALIDATOR_VERSION,
    ValidationIssue,
    _at,
    _issue,
    _sha256,
)
from police_thief.services.pregame_toml import _validate_toml


def build_local_conformance(
    game_path: Path, toml_path: Path, *, role: str, sub_game_number: int,
    git_commit_hash: str,
) -> tuple[dict[str, Any], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    try:
        game = json.loads(game_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        game = {}
        issues.append(_issue("local", "config/game.json", "$", "unreadable_or_invalid_json", "valid JSON object", str(exc)))
    issues.extend(validate_shared_game(game, scope="local"))
    try:
        with toml_path.open("rb") as stream:
            toml = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        toml = {}
        issues.append(_issue("local", "config/game.toml", "$", "unreadable_or_invalid_toml", "valid TOML", str(exc)))
    toml_public, toml_issues = _validate_toml(toml, game, scope="local")
    issues.extend(toml_issues)
    manifest = {
        "validator_version": VALIDATOR_VERSION,
        "role": role,
        "sub_game_number": sub_game_number,
        "game_config": game,
        "game_config_sha256": _sha256(game),
        "protected_config_sha256": _sha256({key: _at(game, key) for key in sorted(_PROTECTED)}),
        "official_rule_profile_sha256": _sha256(_RULE_PROFILE),
        "toml_public": toml_public,
        "git_commit_hash": git_commit_hash,
    }
    return manifest, issues


def _diff(expected: Any, received: Any, path: str = "$" ) -> list[tuple[str, Any, Any]]:
    if isinstance(expected, dict) and isinstance(received, dict):
        differences: list[tuple[str, Any, Any]] = []
        for key in sorted(set(expected) | set(received)):
            child = f"{path}.{key}" if path != "$" else key
            if key not in expected:
                differences.append((child, "not present", received[key]))
            elif key not in received:
                differences.append((child, expected[key], "missing"))
            else:
                differences.extend(_diff(expected[key], received[key], child))
        return differences
    return [] if expected == received else [(path, expected, received)]
