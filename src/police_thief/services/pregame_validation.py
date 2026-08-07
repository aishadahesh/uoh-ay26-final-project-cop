"""Fail-closed validation of public, shared match inputs before play.

This module deliberately never reads an opponent's private strategy, prompts,
credentials, email configuration, or model settings.  It validates only the
closed shared game definition, a redacted TOML projection, and required public
repository artifacts at the declared immutable commit.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VALIDATOR_VERSION = "1.0.0"

_SCHEMA: dict[str, dict[str, type | tuple[type, ...]]] = {
    "board_and_agents": {
        "grid_size": int, "num_agents": int, "thief_start": list,
        "cop_start": list, "axis_origin_corner": str, "axis_start_index": int,
    },
    "movement_and_barriers": {
        "move_set": list, "max_barriers": int, "max_moves": int,
        "survival_threshold": int,
    },
    "scoring": {
        "capture_cop": int, "capture_thief": int, "survival_cop": int,
        "survival_thief": int, "tie_score": int, "technical_loss": int,
    },
    "pheromones": {
        "pheromone_center_intensity": (int, float),
        "pheromone_min_center_intensity": (int, float),
        "pheromone_decay": (int, float), "pheromone_grid_size": int,
    },
    "world": {"map_area": str, "hint_max_words": int},
    "network_and_league": {
        "response_timeout_sec": (int, float),
        "watchdog_timeout_sec": (int, float), "num_games": int,
        "diversity_reward": int, "min_games_to_pass": int,
        "max_games_per_team": int, "token_budget_per_series": int,
    },
    "rate_limiter_gatekeeper": {
        "requests_per_minute": int, "concurrent_requests": int,
        "retry_backoff_sec": (int, float), "max_retries": int,
        "queue_depth": int,
    },
}

_TOP_LEVEL = {"schema_version", "agreed_between", *_SCHEMA}

# Values fixed by the official project specification. Timeout values, the New
# York setting, and the series size are signed shared terms that may be changed
# by agreement; they are type/range checked and peer-compared rather than pinned.
_PROTECTED: dict[str, Any] = {
    "schema_version": "1.00",
    "agreed_between": ["cop", "thief"],
    "board_and_agents.grid_size": 7,
    "board_and_agents.num_agents": 2,
    "board_and_agents.thief_start": [3, 3],
    "board_and_agents.cop_start": [0, 0],
    "board_and_agents.axis_origin_corner": "top-left",
    "board_and_agents.axis_start_index": 0,
    "movement_and_barriers.move_set": ["N", "S", "E", "W", "STAY"],
    "movement_and_barriers.max_barriers": 14,
    "movement_and_barriers.max_moves": 35,
    "movement_and_barriers.survival_threshold": 35,
    "scoring.capture_cop": 20, "scoring.capture_thief": 5,
    "scoring.survival_cop": 5, "scoring.survival_thief": 10,
    "scoring.tie_score": 2, "scoring.technical_loss": 0,
    "pheromones.pheromone_center_intensity": 0.9,
    "pheromones.pheromone_min_center_intensity": 0.5,
    "pheromones.pheromone_decay": 0.1,
    "pheromones.pheromone_grid_size": 5,
    "world.hint_max_words": 15,
    "network_and_league.diversity_reward": 10,
    "network_and_league.min_games_to_pass": 2,
    "network_and_league.max_games_per_team": 10,
    "network_and_league.token_budget_per_series": 200000,
    "rate_limiter_gatekeeper.requests_per_minute": 30,
    "rate_limiter_gatekeeper.concurrent_requests": 2,
    "rate_limiter_gatekeeper.retry_backoff_sec": 5,
    "rate_limiter_gatekeeper.max_retries": 3,
    "rate_limiter_gatekeeper.queue_depth": 100,
}

_RULE_PROFILE = {
    "capture": "same-cell-or-thief-boxed-in",
    "information_model": "local-truth-commit-reveal",
    "movement": ["N", "S", "E", "W", "STAY"],
    "turn_order": "thief-then-police",
}

_TOML_TOP = {"version", "game", "network", "strategy", "trash_talk", "llm", "email"}
_TOML_GAME = {"group_name", "group_id", "sub_game_number", "members", "repos"}
_TOML_NETWORK = {"my_port", "opponent_url", "turn_timeout_seconds"}
_PRIVATE_SECTIONS = {"strategy", "trash_talk", "llm", "email"}
_GITHUB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/#]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class ValidationIssue:
    scope: str
    file: str
    field: str
    code: str
    expected: Any
    received: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _at(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _issue(scope: str, file: str, field: str, code: str, expected: Any, received: Any) -> ValidationIssue:
    return ValidationIssue(scope, file, field, code, expected, received)


def _strict_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    if isinstance(value, bool) and expected is not bool:
        return False
    return isinstance(value, expected)


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
    if "agreed_between" in data and not _strict_type(data["agreed_between"], list):
        issues.append(_issue(scope, file, "agreed_between", "wrong_type", "array", type(data["agreed_between"]).__name__))
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


def validate_peer_conformance(
    peer: Any, local: dict[str, Any], *, local_role: str,
    sub_game_number: int, peer_identity: dict[str, Any], inspect_repository: bool = True,
) -> tuple[list[ValidationIssue], list[dict[str, Any]]]:
    issues: list[ValidationIssue] = []
    checks: list[dict[str, Any]] = []
    if not isinstance(peer, dict):
        return [_issue("opponent", "agreement.conformance", "$", "missing_or_wrong_type", "object", type(peer).__name__)], checks
    required = {
        "validator_version", "role", "sub_game_number", "game_config",
        "game_config_sha256", "protected_config_sha256",
        "official_rule_profile_sha256", "toml_public", "git_commit_hash",
    }
    for key in sorted(required - set(peer)):
        issues.append(_issue("opponent", "agreement.conformance", key, "missing_field", "present", "missing"))
    for key in sorted(set(peer) - required):
        issues.append(_issue("opponent", "agreement.conformance", key, "unexpected_field", "not present", peer[key]))
    peer_game = peer.get("game_config")
    issues.extend(validate_shared_game(peer_game, scope="opponent"))
    if isinstance(peer_game, dict):
        for field, expected, received in _diff(local.get("game_config"), peer_game):
            issues.append(_issue("opponent", "config/game.json", field, "shared_config_mismatch", expected, received))
        expected_hash = _sha256(peer_game)
        if peer.get("game_config_sha256") != expected_hash:
            issues.append(_issue("opponent", "agreement.conformance", "game_config_sha256", "checksum_mismatch", expected_hash, peer.get("game_config_sha256")))
        protected_hash = _sha256({key: _at(peer_game, key) for key in sorted(_PROTECTED)})
        if peer.get("protected_config_sha256") != protected_hash:
            issues.append(_issue("opponent", "agreement.conformance", "protected_config_sha256", "checksum_mismatch", protected_hash, peer.get("protected_config_sha256")))
    expected_peer_role = "thief" if local_role == "cop" else "cop"
    for field, expected in (("role", expected_peer_role), ("sub_game_number", sub_game_number), ("official_rule_profile_sha256", _sha256(_RULE_PROFILE))):
        if peer.get(field) != expected:
            issues.append(_issue("opponent", "agreement.conformance", field, "value_mismatch", expected, peer.get(field)))
    expected_commit = peer.get("git_commit_hash")
    if not isinstance(expected_commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", expected_commit):
        issues.append(_issue("opponent", "agreement.conformance", "git_commit_hash", "invalid_value", "40-character Git commit SHA", expected_commit))
    identity_commit = peer_identity.get("git_commit_hash")
    if identity_commit != expected_commit:
        issues.append(_issue("opponent", "agreement.identity", "git_commit_hash", "manifest_identity_mismatch", expected_commit, identity_commit))
    public = peer.get("toml_public")
    if not isinstance(public, dict):
        issues.append(_issue("opponent", "config/game.toml", "$", "missing_or_wrong_type", "redacted public projection", type(public).__name__))
    else:
        allowed_public = {"version", "game", "network", "private_sections_present"}
        for key in sorted(set(public) - allowed_public):
            issues.append(_issue("opponent", "config/game.toml", key, "unexpected_field", "not present", public[key]))
        game_public = public.get("game", {})
        if isinstance(game_public, dict):
            for key in sorted(set(game_public) - _TOML_GAME):
                issues.append(_issue("opponent", "config/game.toml", f"game.{key}", "unexpected_field", "not present", game_public[key]))
        network_public = public.get("network", {})
        if isinstance(network_public, dict):
            for key in sorted(set(network_public) - {"turn_timeout_seconds"}):
                issues.append(_issue("opponent", "config/game.toml", f"network.{key}", "private_field_exposed", "not transmitted", network_public[key]))
        identity_expected = {
            "group_id": peer_identity.get("group_id"),
            "group_name": peer_identity.get("group_name"),
            "members": peer_identity.get("members"), "repos": peer_identity.get("repos"),
        }
        for field, expected in identity_expected.items():
            received = game_public.get(field) if isinstance(game_public, dict) else None
            if received != expected:
                issues.append(_issue("opponent", "config/game.toml", f"game.{field}", "identity_mismatch", expected, received))
        timeout = _at(public, "network.turn_timeout_seconds")
        expected_timeout = _at(local.get("game_config", {}), "network_and_league.response_timeout_sec")
        if timeout != expected_timeout:
            issues.append(_issue("opponent", "config/game.toml", "network.turn_timeout_seconds", "shared_config_mismatch", expected_timeout, timeout))
    if inspect_repository and not any(issue.field == "git_commit_hash" for issue in issues):
        role = peer.get("role")
        repos = peer_identity.get("repos", {})
        repo_url = repos.get(role) if isinstance(repos, dict) else None
        repo_issues, checks = inspect_public_repository(repo_url, expected_commit, peer_game)
        issues.extend(repo_issues)
    return issues, checks


def validate_local_identity(manifest: dict[str, Any], identity: dict[str, Any]) -> list[ValidationIssue]:
    """Bind the locally validated TOML projection to the announced identity."""
    public = manifest.get("toml_public", {})
    game = public.get("game", {}) if isinstance(public, dict) else {}
    issues: list[ValidationIssue] = []
    for field in ("group_id", "group_name", "members", "repos"):
        expected, received = game.get(field), identity.get(field)
        if received != expected:
            issues.append(_issue("local", "config/game.toml", f"game.{field}", "announced_identity_mismatch", expected, received))
    expected_commit = manifest.get("git_commit_hash")
    if identity.get("git_commit_hash") != expected_commit:
        issues.append(_issue("local", "agreement.identity", "git_commit_hash", "manifest_identity_mismatch", expected_commit, identity.get("git_commit_hash")))
    return issues


def inspect_public_repository(repo_url: Any, commit_hash: str, expected_game: Any) -> tuple[list[ValidationIssue], list[dict[str, Any]]]:
    """Inspect only public rule artifacts; never fetch private strategy files."""
    issues: list[ValidationIssue] = []
    checks: list[dict[str, Any]] = []
    match = _GITHUB_RE.match(repo_url) if isinstance(repo_url, str) else None
    if not match:
        return [_issue("opponent", "repository", "url", "invalid_value", "public GitHub repository URL", repo_url)], checks
    owner, repo = match.groups()
    base = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_hash}"

    def fetch(path: str, *, body: bool) -> bytes | None:
        request = urllib.request.Request(f"{base}/{path}", method="GET" if body else "HEAD", headers={"User-Agent": "police-thief-pregame-validator/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                checks.append({"file": path, "status": "verified", "http_status": response.status})
                return response.read() if body else b""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            checks.append({"file": path, "status": "failed", "error": str(exc)})
            return None

    raw = fetch("config/game.json", body=True)
    if raw is None:
        issues.append(_issue("opponent", "repository/config/game.json", "$", "missing_or_unreachable", "file at declared commit", "unavailable"))
    else:
        try:
            repository_game = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            issues.append(_issue("opponent", "repository/config/game.json", "$", "invalid_json", "valid JSON", str(exc)))
        else:
            issues.extend(validate_shared_game(repository_game, scope="opponent_repository"))
            # By-agreement values (for example response timeouts) may differ
            # between a repository default and the signed match instance.  The
            # immutable repository must still carry the exact protected rules.
            for field in sorted(_PROTECTED):
                expected = _at(expected_game, field) if isinstance(expected_game, dict) else None
                received = _at(repository_game, field)
                if expected != received:
                    issues.append(_issue("opponent", "repository/config/game.json", field, "protected_repository_mismatch", expected, received))
    # Existence only: the TOML body may contain legitimate private settings.
    if fetch("config/game.toml", body=False) is None:
        issues.append(_issue("opponent", "repository/config/game.toml", "$", "missing_or_unreachable", "file at declared commit", "unavailable"))
    required_groups = (("README.md",), ("docs/PRD.md", "PRD.md"), ("docs/PLAN.md", "PLAN.md"), ("docs/TODO.md", "TODO.md"))
    for candidates in required_groups:
        if not any(fetch(path, body=False) is not None for path in candidates):
            issues.append(_issue("opponent", "repository", "required_file", "missing_required_file", " or ".join(candidates), "missing"))
    return issues, checks


def save_validation_result(
    output_dir: Path, *, game_id: str, sub_game_number: int, status: str,
    local_manifest: dict[str, Any] | None, peer_manifest: Any = None,
    issues: list[ValidationIssue] = (), repository_checks: list[dict[str, Any]] = (),
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"validation_{game_id}_g{sub_game_number:02d}.json"
    report = {
        "schema_version": "1.00", "validator_version": VALIDATOR_VERSION,
        "validated_at": datetime.now(UTC).isoformat(), "game_id": game_id,
        "sub_game_number": sub_game_number, "status": status,
        "policy": {
            "protected_config_sha256": _sha256(_PROTECTED),
            "official_rule_profile_sha256": _sha256(_RULE_PROFILE),
            "privacy_boundary": "shared configuration and public metadata only; private strategy not inspected",
        },
        "local": _report_manifest(local_manifest),
        "opponent": _report_manifest(peer_manifest),
        "repository_checks": list(repository_checks),
        "issues": [item.to_dict() for item in issues],
    }
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _report_manifest(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value.get(key) for key in (
            "validator_version", "role", "sub_game_number", "game_config_sha256",
            "protected_config_sha256", "official_rule_profile_sha256", "git_commit_hash",
        )
    }


def format_failure(issues: list[ValidationIssue], report_path: Path) -> str:
    first = issues[0]
    return (
        f"pre-game validation failed before any moves: {first.file} field "
        f"{first.field!r} expected {first.expected!r}, received {first.received!r} "
        f"({first.code}); full report: {report_path}"
    )
