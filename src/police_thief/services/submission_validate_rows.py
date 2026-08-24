"""Per-record and per-result-row checks used by the directory validator."""

from __future__ import annotations

import hashlib
from typing import Any

from police_thief.services.submission_schema import (
    ALLOWED_RESULTS,
    ALLOWED_ROLES,
    GIT_RE,
    SubmissionValidationError,
    _error,
    _iso,
    _required,
    canonical_bytes,
)


def _validate_records(filename: str, records: list[Any], errors: list[SubmissionValidationError]) -> None:
    for index, record in enumerate(records):
        field = f"records[{index}]"
        if not isinstance(record, dict) or set(record) != {"payload", "nonce", "commit"}:
            errors.append(_error(filename, field, "object with payload, nonce, commit", record, "invalid_schema"))
            continue
        payload, nonce, commit = record["payload"], record["nonce"], record["commit"]
        expected = hashlib.sha256(canonical_bytes(payload) + b"|" + str(nonce).encode()).hexdigest()
        if commit != expected:
            errors.append(_error(filename, f"{field}.commit", expected, commit, "commit_mismatch"))
        if not isinstance(payload, dict):
            continue
        role = payload.get("role")
        if role is not None and role not in ALLOWED_ROLES:
            errors.append(_error(filename, f"{field}.payload.role", sorted(ALLOWED_ROLES), role, "invalid_value"))


def _validate_result_rows(filename: str, rows: list[dict[str, Any]], group_ids: list[str], errors: list[SubmissionValidationError]) -> None:
    required = {"sub_game_number", "roles", "started_at", "ended_at", "result", "winner_group", "tie", "steps", "github_commit", "tokens", "score", "log_files", "audit"}
    for index, row in enumerate(rows):
        field = f"sub_games[{index}]"
        if not isinstance(row, dict):
            errors.append(_error(filename, field, "object", type(row).__name__, "wrong_type"))
            continue
        _required(row, filename, required, errors)
        if row.get("result") not in ALLOWED_RESULTS:
            errors.append(_error(filename, f"{field}.result", sorted(ALLOWED_RESULTS), row.get("result"), "invalid_value"))
        if set((row.get("roles") or {}).values()) != ALLOWED_ROLES:
            errors.append(_error(filename, f"{field}.roles", "one police and one thief", row.get("roles"), "invalid_value"))
        if set(row.get("score") or {}) != set(group_ids):
            errors.append(_error(filename, f"{field}.score", f"numeric map for {group_ids}", row.get("score"), "invalid_value"))
        if set(row.get("tokens") or {}) != set(group_ids):
            errors.append(_error(filename, f"{field}.tokens", f"integer map for {group_ids}", row.get("tokens"), "invalid_value"))
        commits = row.get("github_commit") or {}
        if set(commits) != set(group_ids) or any(
            not GIT_RE.fullmatch(str(commits.get(group_id, "")))
            for group_id in group_ids
        ):
            errors.append(_error(filename, f"{field}.github_commit", f"40-hex map for {group_ids}", commits, "invalid_value"))
        for timestamp in ("started_at", "ended_at"):
            if not _iso(row.get(timestamp)):
                errors.append(_error(filename, f"{field}.{timestamp}", "ISO-8601 timestamp", row.get(timestamp), "invalid_value"))


def _walk(value: Any, prefix: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            field = f"{prefix}.{key}"
            yield field, item
            yield from _walk(item, field)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{prefix}[{index}]")


def _first_terms(documents: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    for _, doc in documents:
        if isinstance(doc.get("terms"), dict):
            return doc["terms"]
    return None
