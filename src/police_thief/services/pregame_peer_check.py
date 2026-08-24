"""Checking the peer's declared conformance manifest against our own."""

from __future__ import annotations

import re
from typing import Any

from police_thief.services.pregame_conformance import _diff
from police_thief.services.pregame_game_json import validate_shared_game
from police_thief.services.pregame_repository import inspect_public_repository
from police_thief.services.pregame_schema import (
    _PROTECTED,
    _RULE_PROFILE,
    _TOML_GAME,
    ValidationIssue,
    _at,
    _issue,
    _sha256,
)


def validate_peer_conformance(
    peer: Any, local: dict[str, Any], *, local_role: str,
    sub_game_number: int, peer_identity: dict[str, Any], inspect_repository: bool = True,
) -> tuple[list[ValidationIssue], list[dict[str, Any]]]:
    issues: list[ValidationIssue] = []
    checks: list[dict[str, Any]] = []
    if peer is None:
        # The lecturer/reference envelope contains exactly identity, nonce,
        # signature, and terms. Preserve the custom manifest when another
        # copy of this project offers it, but do not require that extension.
        expected_peer_role = "thief" if local_role == "cop" else "cop"
        expected_commit = peer_identity.get("git_commit_hash")
        if not isinstance(expected_commit, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}", expected_commit,
        ):
            issues.append(_issue(
                "opponent", "agreement.identity", "git_commit_hash",
                "invalid_value", "40-character Git commit SHA", expected_commit,
            ))
        servers = peer_identity.get("mcp_servers")
        if isinstance(servers, dict) and expected_peer_role not in servers:
            issues.append(_issue(
                "opponent", "agreement.identity", "mcp_servers",
                "missing_role", expected_peer_role, sorted(servers),
            ))
        if inspect_repository and not issues:
            repos = peer_identity.get("repos", {})
            repo_url = repos.get(expected_peer_role) if isinstance(repos, dict) else None
            repo_issues, checks = inspect_public_repository(
                repo_url, expected_commit, local.get("game_config"),
            )
            issues.extend(repo_issues)
        checks.insert(0, {
            "status": "reference-envelope",
            "detail": "custom conformance extension not supplied",
        })
        return issues, checks
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
