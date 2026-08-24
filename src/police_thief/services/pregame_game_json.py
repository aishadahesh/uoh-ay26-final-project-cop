"""Validation of the shared config/game.json against the agreed schema."""

from __future__ import annotations

from typing import Any

from police_thief.services.pregame_schema import (
    _PROTECTED,
    _SCHEMA,
    _TOP_LEVEL,
    ValidationIssue,
    _at,
    _issue,
    _strict_type,
)


def validate_shared_game(data: Any, *, scope: str = "local") -> list[ValidationIssue]:
    """Strict schema and canonical-policy validation for shared game.json."""
    file = "config/game.json"
    if not isinstance(data, dict):
        return [_issue(scope, file, "$", "wrong_type", "object", type(data).__name__)]
    issues: list[ValidationIssue] = []
    for key in sorted(_TOP_LEVEL - set(data)):
        issues.append(_issue(scope, file, key, "missing_field", "present", "missing"))
    for key in sorted(set(data) - _TOP_LEVEL):
        issues.append(_issue(scope, file, key, "unexpected_field", "not present", data[key]))
    if "schema_version" in data and not _strict_type(data["schema_version"], str):
        issues.append(_issue(scope, file, "schema_version", "wrong_type", "string", type(data["schema_version"]).__name__))
    agreed_between = data.get("agreed_between")
    if not _strict_type(agreed_between, list):
        if "agreed_between" in data:
            issues.append(_issue(scope, file, "agreed_between", "wrong_type", "array", type(agreed_between).__name__))
    elif (
        len(agreed_between) != 2
        or any(not isinstance(group, str) or not group.strip() for group in agreed_between)
        or len(set(agreed_between)) != 2
    ):
        issues.append(
            _issue(
                scope,
                file,
                "agreed_between",
                "invalid_participants",
                "exactly two unique non-empty group IDs",
                agreed_between,
            )
        )
    for section, fields in _SCHEMA.items():
        value = data.get(section)
        if not isinstance(value, dict):
            if section in data:
                issues.append(_issue(scope, file, section, "wrong_type", "object", type(value).__name__))
            continue
        for key in sorted(set(fields) - set(value)):
            issues.append(_issue(scope, file, f"{section}.{key}", "missing_field", "present", "missing"))
        for key in sorted(set(value) - set(fields)):
            issues.append(_issue(scope, file, f"{section}.{key}", "unexpected_field", "not present", value[key]))
        for key, expected_type in fields.items():
            if key in value and not _strict_type(value[key], expected_type):
                names = expected_type.__name__ if isinstance(expected_type, type) else "number"
                issues.append(_issue(scope, file, f"{section}.{key}", "wrong_type", names, type(value[key]).__name__))
    for path, expected in _PROTECTED.items():
        received = _at(data, path)
        if received != expected:
            issues.append(_issue(scope, file, path, "protected_value_mismatch", expected, received))
    for path in ("network_and_league.response_timeout_sec", "network_and_league.watchdog_timeout_sec"):
        value = _at(data, path)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 0:
            issues.append(_issue(scope, file, path, "invalid_value", "positive number", value))
    num_games = _at(data, "network_and_league.num_games")
    max_games = _at(data, "network_and_league.max_games_per_team")
    if (
        isinstance(num_games, int)
        and not isinstance(num_games, bool)
        and (
            num_games < 1
            or (
            isinstance(max_games, int) and not isinstance(max_games, bool)
            and num_games > max_games
            )
        )
    ):
        issues.append(_issue(
            scope, file, "network_and_league.num_games", "invalid_value",
            f"integer from 1 through max_games_per_team ({max_games})", num_games,
        ))
    return issues
