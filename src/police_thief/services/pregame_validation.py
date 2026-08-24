"""Fail-closed validation of public, shared match inputs before play.

This module deliberately never reads an opponent's private strategy, prompts,
credentials, email configuration, or model settings.  It validates only the
closed shared game definition, a redacted TOML projection, and required public
repository artifacts at the declared immutable commit.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from police_thief.services.pregame_conformance import build_local_conformance
from police_thief.services.pregame_game_json import validate_shared_game
from police_thief.services.pregame_peer_check import validate_peer_conformance
from police_thief.services.pregame_schema import (
    _RULE_PROFILE,
    VALIDATOR_VERSION,
    ValidationIssue,
    _issue,
    _sha256,
)

__all__ = [
    "VALIDATOR_VERSION",
    "ValidationIssue",
    "build_local_conformance",
    "format_failure",
    "inspect_public_repository",
    "save_validation_result",
    "validate_local_identity",
    "validate_peer_conformance",
    "validate_shared_game",
]
from police_thief.services.pregame_repository import inspect_public_repository
from police_thief.services.pregame_schema import _PROTECTED


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
