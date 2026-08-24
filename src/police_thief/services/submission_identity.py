"""Series consensus digest, game_uid derivation, and the public participant
record -- the identity fields both peers must agree on."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from police_thief.services.submission_schema import (
    SCHEMA_VERSION,
    SubmissionValidationError,
    _write,
    canonical_bytes,
    canonical_hash,
)
from police_thief.shared.game_config import FIXED_TIE_SCORE


def series_consensus_payload(
    game_id: str, game_uid: str, series_result: dict[str, Any],
) -> dict[str, Any]:
    """Return the stable, cross-peer series adjudication preimage.

    Local timestamps, token counters, filenames and email metadata are
    intentionally excluded: peers can agree on the game without generating
    those local observations byte-for-byte.
    """
    rows: list[dict[str, Any]] = []
    for row in sorted(
        series_result["sub_games"], key=lambda item: int(item["sub_game_number"]),
    ):
        roles = {
            key: ("police" if value == "cop" else value)
            for key, value in row["roles"].items()
        }
        score = dict(sorted(row["score"].items()))
        winner = None if len(set(score.values())) == 1 else max(score, key=score.get)
        rows.append({
            "sub_game_number": int(row["sub_game_number"]),
            "result": row["outcome"],
            "roles": dict(sorted(roles.items())),
            "score": score,
            "winner_group": winner,
        })
    if not rows:
        raise ValueError("series consensus requires at least one sub-game")
    return {
        "game_id": game_id,
        "game_uid": game_uid,
        "sub_games": rows,
    }


def series_consensus_hash(
    game_id: str, game_uid: str, series_result: dict[str, Any],
) -> str:
    return canonical_hash(series_consensus_payload(game_id, game_uid, series_result))


def derive_game_uid(terms: dict[str, Any], group_ids: list[str]) -> str:
    pair = sorted(group_ids)
    seed = canonical_bytes(terms) + b"|" + "|".join(pair).encode("utf-8")
    return str(uuid.UUID(bytes=hashlib.sha256(seed).digest()[:16]))


def public_participant(identity: dict[str, Any]) -> dict[str, Any]:
    """Copy only fields the PDF explicitly requires in the declaration."""
    spec = identity.get("spec") or identity.get("step0_hardware") or {}
    participant = {
        "group_id": str(identity.get("group_id", "")),
        "group_name": str(identity.get("group_name", "")),
        "members": list(identity.get("members", [])),
        "repos": dict(identity.get("repos", {})),
        "mcp_servers": dict(identity.get("mcp_servers", {})),
        "llm_model": str(identity.get("llm_model", "unknown")),
        "hardware_spec": dict(spec),
        "github_commit": str(identity.get("git_commit_hash", "")),
        "code_version": str((identity.get("protocol") or {}).get("version", "3.0.0")),
    }
    # A SHA-256 integrity signature over exactly the public declaration.
    participant["signature"] = f"sha256:{canonical_hash(participant)}"
    return participant


def save_submission_validation_report(
    directory: Path,
    game_id: str,
    errors: list[SubmissionValidationError],
    message: str,
) -> Path:
    """Persist a public, secret-free explanation when the bundle cannot be sent."""
    return _write(directory / f"submission_validation_{game_id}.json", {
        "schema_version": SCHEMA_VERSION,
        "game_id": game_id,
        "valid": False,
        "created_at": datetime.now().astimezone().isoformat(),
        "message": message,
        "errors": [error.to_dict() for error in errors],
    })


def series_final_result(
    result_rows: list[dict[str, Any]], participants: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate the per-sub-game rows into the series `final_result` block."""
    totals = {key: sum(item["score"].get(key, 0) for item in result_rows) for key in participants}
    wins = {
        key: sum(item["winner_group"] == key for item in result_rows) for key in participants
    }
    ties = sum(item["tie"] for item in result_rows)
    series_tie = len(set(totals.values())) == 1
    if series_tie:
        # Tie Rule (Sec. 9.2.8-9.2.9 / Appendix F Table 17 row 5): a tied
        # cumulative series credits each side the fixed tie score on top of
        # its raw subtotal, so e.g. 75-75 is reported as 77-77.
        totals = {key: value + FIXED_TIE_SCORE for key, value in totals.items()}
    winner = None if series_tie else max(totals, key=totals.get)
    token_totals = {
        key: sum(int(item["tokens"].get(key, 0)) for item in result_rows)
        for key in participants
    }
    final = {
        "total_score": totals,
        "sub_games_won": wins,
        "ties": ties,
        "winner_group": winner,
        "series_tie": series_tie,
        "tokens_total_series": token_totals,
    }
    return final
