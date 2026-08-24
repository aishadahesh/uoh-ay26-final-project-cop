"""Validation of the private per-role game.toml."""

from __future__ import annotations

from typing import Any

from police_thief.services.pregame_schema import (
    _GITHUB_RE,
    _PRIVATE_SECTIONS,
    _TOML_GAME,
    _TOML_NETWORK,
    _TOML_TOP,
    ValidationIssue,
    _at,
    _issue,
    _strict_type,
)


def _validate_toml(data: Any, game: dict[str, Any], *, scope: str) -> tuple[dict[str, Any], list[ValidationIssue]]:
    file = "config/game.toml"
    issues: list[ValidationIssue] = []
    if not isinstance(data, dict):
        return {}, [_issue(scope, file, "$", "wrong_type", "table", type(data).__name__)]
    for key in sorted({"version", "game", "network"} - set(data)):
        issues.append(_issue(scope, file, key, "missing_field", "present", "missing"))
    for key in sorted(set(data) - _TOML_TOP):
        issues.append(_issue(scope, file, key, "unexpected_field", "not present", data[key]))
    game_table = data.get("game", {})
    network = data.get("network", {})
    if not isinstance(game_table, dict):
        issues.append(_issue(scope, file, "game", "wrong_type", "table", type(game_table).__name__))
        game_table = {}
    if not isinstance(network, dict):
        issues.append(_issue(scope, file, "network", "wrong_type", "table", type(network).__name__))
        network = {}
    for table_name, table, allowed in (("game", game_table, _TOML_GAME), ("network", network, _TOML_NETWORK)):
        for key in sorted(allowed - set(table)):
            issues.append(_issue(scope, file, f"{table_name}.{key}", "missing_field", "present", "missing"))
        for key in sorted(set(table) - allowed):
            issues.append(_issue(scope, file, f"{table_name}.{key}", "unexpected_or_protected_field", "not present", table[key]))
    expected_types = {
        "version": str, "game.group_name": str, "game.group_id": str,
        "game.sub_game_number": int, "game.members": list, "game.repos": dict,
        "network.my_port": int, "network.opponent_url": str,
        "network.turn_timeout_seconds": (int, float),
    }
    for path, expected_type in expected_types.items():
        value = _at(data, path)
        if value is not None and not _strict_type(value, expected_type):
            issues.append(_issue(scope, file, path, "wrong_type", "required schema type", type(value).__name__))
    repos = game_table.get("repos")
    if isinstance(repos, dict):
        for key in sorted({"cop", "thief"} - set(repos)):
            issues.append(_issue(scope, file, f"game.repos.{key}", "missing_field", "repository URL", "missing"))
        for key in sorted(set(repos) - {"cop", "thief"}):
            issues.append(_issue(scope, file, f"game.repos.{key}", "unexpected_field", "not present", repos[key]))
        for key in ("cop", "thief"):
            if key in repos and (not isinstance(repos[key], str) or not _GITHUB_RE.match(repos[key])):
                issues.append(_issue(scope, file, f"game.repos.{key}", "invalid_value", "public GitHub repository URL", repos[key]))
    members = game_table.get("members")
    if isinstance(members, list) and (not members or any(not isinstance(item, str) or not item.strip() for item in members)):
        issues.append(_issue(scope, file, "game.members", "invalid_value", "non-empty array of names", members))
    timeout = network.get("turn_timeout_seconds")
    expected_timeout = _at(game, "network_and_league.response_timeout_sec")
    if timeout is not None and timeout != expected_timeout:
        issues.append(_issue(scope, file, "network.turn_timeout_seconds", "shared_config_mismatch", expected_timeout, timeout))
    public = {
        "version": data.get("version"),
        "game": {key: game_table.get(key) for key in sorted(_TOML_GAME)},
        "network": {"turn_timeout_seconds": network.get("turn_timeout_seconds")},
        "private_sections_present": sorted(_PRIVATE_SECTIONS & set(data)),
    }
    return public, issues
