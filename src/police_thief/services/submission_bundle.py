"""Assembling the complete submission bundle for a finished series."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from police_thief.services.submission_identity import (
    derive_game_uid,
    series_consensus_hash,
    series_final_result,
)
from police_thief.services.submission_schema import (
    SCHEMA_VERSION,
    SubmissionBundleError,
    _links,
    _write,
    canonical_hash,
)
from police_thief.services.submission_validate import validate_submission_directory


def finalize_submission_bundle(
    directory: Path,
    *,
    game_id: str,
    terms: dict[str, Any],
    participants: dict[str, dict[str, Any]],
    series_result: dict[str, Any],
    game_started_at: str,
    token_budget: int,
) -> list[Path]:
    """Replace internal artifacts with the canonical email-ready envelopes."""
    if len(participants) != 2:
        raise SubmissionBundleError(
            f"submission requires exactly two distinct groups; received {sorted(participants)}"
        )
    num_games = int(series_result["num_games"])
    game_uid = derive_game_uid(terms, list(participants))
    links = _links(game_id, participants)
    base = {
        "schema_version": SCHEMA_VERSION,
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links,
    }
    ordered = [participants[key] for key in sorted(participants)]
    declaration = {
        **base,
        "report_type": "declaration",
        "declaration_type": "pre_game_declaration",
        "timezone": "Asia/Jerusalem",
        "game_started_at": game_started_at,
        "num_sub_games": num_games,
        "max_tokens_per_game": token_budget,
        "groups": {"group_1": ordered[0], "group_2": ordered[1]},
    }
    paths = [_write(directory / links["declaration"], declaration)]
    config_hash = canonical_hash(terms)
    result_rows: list[dict[str, Any]] = []
    for row in series_result["sub_games"]:
        number = int(row["sub_game_number"])
        config_name = f"config_{game_id}_g{number:02d}.json"
        config_doc = {
            **base,
            "sub_game_number": number,
            "terms": terms,
            "config_sha256": config_hash,
        }
        paths.append(_write(directory / config_name, config_doc))

        raw_log_path = directory / f"log_{game_id}_g{number:02d}.json"
        try:
            raw = json.loads(raw_log_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SubmissionBundleError(f"cannot build submission log from {raw_log_path}: {exc}") from exc
        records_source = raw.get("records", []) if isinstance(raw, dict) else raw
        records = [
            {
                "payload": item["payload"],
                "nonce": item["nonce"],
                "commit": item.get("commit", item.get("h_commit")),
            }
            for item in records_source
        ]
        roles = {
            key: ("police" if value == "cop" else value)
            for key, value in row["roles"].items()
        }
        score = dict(row.get("score") or {})
        tokens = dict(row.get("tokens") or dict.fromkeys(participants, 0))
        winner = None if len(set(score.values())) == 1 else max(score, key=score.get)
        summary = {
            "sub_game_number": number,
            "roles": roles,
            "result": row["outcome"],
            "winner_group": winner,
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "steps": max((int(item["payload"].get("step", 0)) for item in records), default=0),
            "audit": {"passed": bool(row.get("mutual_sign_off", True)), "failed_steps": []},
        }
        log_doc = {
            **base,
            "sub_game_number": number,
            "summary": summary,
            "records": records,
        }
        log_name = f"log_{game_id}_g{number:02d}.json"
        paths.append(_write(directory / log_name, log_doc))
        result_rows.append({
            "sub_game_number": number,
            "roles": roles,
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "result": row["outcome"],
            "winner_group": winner,
            "tie": winner is None and any(score.values()),
            "steps": summary["steps"],
            "github_commit": {
                key: (row.get("github_commit") or {}).get(
                    key, participants[key]["github_commit"],
                )
                for key in participants
            },
            "tokens": tokens,
            "score": score,
            "log_files": dict.fromkeys(participants, log_name),
            "audit": {"log_verified": bool(row.get("mutual_sign_off", True)), "tampered": False},
        })

    final = series_final_result(result_rows, participants)
    consensus_sha = series_consensus_hash(game_id, game_uid, series_result)
    result_doc = {
        **base,
        "report_type": "final_game_result",
        "timezone": "Asia/Jerusalem",
        "groups": sorted(participants),
        "num_sub_games": num_games,
        "sub_games": result_rows,
        "final_result": final,
        "mutual_agreement": {
            "sha256": consensus_sha,
            "confirmed": bool(series_result.get("consensus_confirmed", False)),
        },
    }
    paths.append(_write(directory / links["result"], result_doc))
    errors, required_paths = validate_submission_directory(directory, game_id)
    if errors:
        raise SubmissionBundleError("submission validation failed:\n" + "\n".join(str(e) for e in errors))
    return required_paths
