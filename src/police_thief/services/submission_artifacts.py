"""Build and validate the four mandatory JSON submission artifact types.

The shapes and filenames follow project PDF section 9.3.3 (physical pages
94-95) and Appendix table 20.  Only public match/audit data is included.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from police_thief.shared.game_config import FIXED_TIE_SCORE

SCHEMA_VERSION = "1.1"
ALLOWED_ROLES = {"police", "thief"}
ALLOWED_RESULTS = {"capture", "survival", "technical_loss"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_RE = re.compile(r"^[0-9a-f]{40}$")
GITHUB_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/?$")
SIGNED_TERM_FIELDS = {
    "board_size", "smell_grid_size", "decay_per_step", "emit_intensity",
    "min_center_intensity",
    "max_steps", "barriers_max", "setting", "hint_max_words",
    "axis_origin_corner", "axis_start_index", "thief_start", "cop_start",
    "num_games",
}


@dataclass(frozen=True)
class SubmissionValidationError:
    filename: str
    field: str
    expected: Any
    received: Any
    code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"{self.filename}: field {self.field!r}: expected {self.expected!r}, "
            f"received {self.received!r} ({self.code})"
        )


class SubmissionBundleError(ValueError):
    """Raised when a bundle is incomplete or unsafe to email."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


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


def derive_game_uid(
    terms: dict[str, Any],
    group_ids: list[str],
    *,
    game_id: str | None = None,
) -> str:
    pair = sorted(group_ids)
    identity = "|".join(pair)
    if game_id:
        label = str(game_id)
        identity = label if "-vs-" in label else f"{pair[0]}-vs-{pair[1]}-{label}"
    seed = canonical_bytes(terms) + b"|" + identity.encode("utf-8")
    return str(uuid.UUID(bytes=hashlib.sha256(seed).digest()[:16]))


def submission_filenames(game_id: str, num_sub_games: int) -> list[str]:
    return [
        f"declaration_{game_id}.json",
        *(f"config_{game_id}_g{number:02d}.json" for number in range(1, num_sub_games + 1)),
        *(f"log_{game_id}_g{number:02d}.json" for number in range(1, num_sub_games + 1)),
        f"result_{game_id}.json",
    ]


def _links(game_id: str, participants: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "declaration": f"declaration_{game_id}.json",
        "config": f"config_{game_id}_g<NN>.json",
        "log": f"log_{game_id}_g<NN>.json",
        "result": f"result_{game_id}.json",
        "github": {group_id: value["repos"] for group_id, value in participants.items()},
    }


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


def _write(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep canonical_bytes() compact for signatures and hashes, but make the
    # persisted submission artifacts readable for human review.
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


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
    game_uid = derive_game_uid(terms, list(participants), game_id=game_id)
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


def _error(filename: str, field: str, expected: Any, received: Any, code: str) -> SubmissionValidationError:
    return SubmissionValidationError(filename, field, expected, received, code)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _read(path: Path, errors: list[SubmissionValidationError]) -> Any:
    if not path.is_file():
        errors.append(_error(path.name, "$", "existing JSON file", "missing", "missing_file"))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(_error(path.name, "$", "valid UTF-8 JSON", str(exc), "invalid_json"))
        return None


def _required(doc: dict[str, Any], filename: str, fields: set[str], errors: list[SubmissionValidationError]) -> None:
    for field in sorted(fields - set(doc)):
        errors.append(_error(filename, field, "mandatory field", "missing", "missing_field"))


def _iso(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def validate_submission_directory(
    directory: Path, game_id: str,
) -> tuple[list[SubmissionValidationError], list[Path]]:
    """Validate syntax, schema, hashes, names, values, joins, and privacy."""
    errors: list[SubmissionValidationError] = []
    declaration_path = directory / f"declaration_{game_id}.json"
    declaration = _read(declaration_path, errors)
    if not isinstance(declaration, dict):
        return errors, []
    _required(declaration, declaration_path.name, {
        "schema_version", "report_type", "declaration_type", "game_id", "game_uid",
        "links", "timezone", "game_started_at", "num_sub_games",
        "max_tokens_per_game", "groups",
    }, errors)
    num_games = declaration.get("num_sub_games")
    if not _is_int(num_games) or num_games < 1:
        errors.append(_error(declaration_path.name, "num_sub_games", "positive integer", num_games, "wrong_type_or_value"))
        return errors, []
    paths = [directory / name for name in submission_filenames(game_id, num_games)]
    documents: list[tuple[str, dict[str, Any]]] = []
    for path in paths:
        doc = declaration if path == declaration_path else _read(path, errors)
        if isinstance(doc, dict):
            documents.append((path.name, doc))
    try:
        uid = str(uuid.UUID(str(declaration.get("game_uid"))))
    except (ValueError, TypeError, AttributeError):
        uid = ""
        errors.append(_error(declaration_path.name, "game_uid", "UUID string", declaration.get("game_uid"), "invalid_value"))
    for filename, doc in documents:
        for field, expected in (("schema_version", SCHEMA_VERSION), ("game_id", game_id), ("game_uid", uid)):
            if doc.get(field) != expected:
                errors.append(_error(filename, field, expected, doc.get(field), "cross_file_mismatch"))
    groups = declaration.get("groups")
    participants = list(groups.values()) if isinstance(groups, dict) else []
    if len(participants) != 2:
        errors.append(_error(declaration_path.name, "groups", "exactly two group objects", groups, "invalid_value"))
    group_ids: list[str] = []
    for index, group in enumerate(participants, 1):
        field = f"groups.group_{index}"
        if not isinstance(group, dict):
            errors.append(_error(declaration_path.name, field, "object", type(group).__name__, "wrong_type"))
            continue
        mandatory = {"group_id", "group_name", "members", "repos", "mcp_servers", "llm_model", "hardware_spec", "github_commit", "code_version", "signature"}
        _required(group, declaration_path.name, mandatory, errors)
        group_ids.append(group.get("group_id"))
        if not isinstance(group.get("members"), list) or not group.get("members"):
            errors.append(_error(declaration_path.name, f"{field}.members", "non-empty array of names", group.get("members"), "invalid_value"))
        repos = group.get("repos")
        if not isinstance(repos, dict) or set(repos) != {"cop", "thief"}:
            errors.append(_error(declaration_path.name, f"{field}.repos", "object with cop and thief", repos, "invalid_value"))
        elif any(not GITHUB_RE.match(str(url)) for url in repos.values()):
            errors.append(_error(declaration_path.name, f"{field}.repos", "GitHub repository URLs", repos, "invalid_value"))
        if not GIT_RE.match(str(group.get("github_commit", ""))):
            errors.append(_error(declaration_path.name, f"{field}.github_commit", "40 lowercase hex characters", group.get("github_commit"), "invalid_value"))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(group.get("signature", ""))):
            errors.append(_error(declaration_path.name, f"{field}.signature", "sha256:<64 lowercase hex>", group.get("signature"), "invalid_value"))
    if not _iso(declaration.get("game_started_at")):
        errors.append(_error(declaration_path.name, "game_started_at", "ISO-8601 timestamp", declaration.get("game_started_at"), "invalid_value"))

    expected_uid = (
        derive_game_uid(_first_terms(documents), group_ids, game_id=game_id)
        if len(group_ids) == 2 and _first_terms(documents)
        else None
    )
    if expected_uid and uid != expected_uid:
        errors.append(_error(declaration_path.name, "game_uid", expected_uid, uid, "derivation_mismatch"))

    for number in range(1, num_games + 1):
        config_name = f"config_{game_id}_g{number:02d}.json"
        log_name = f"log_{game_id}_g{number:02d}.json"
        config = next((doc for name, doc in documents if name == config_name), None)
        log = next((doc for name, doc in documents if name == log_name), None)
        if config:
            _required(config, config_name, {"schema_version", "game_id", "game_uid", "links", "sub_game_number", "terms", "config_sha256"}, errors)
            if config.get("sub_game_number") != number:
                errors.append(_error(config_name, "sub_game_number", number, config.get("sub_game_number"), "filename_field_mismatch"))
            if not isinstance(config.get("terms"), dict) or set(config.get("terms", {})) != SIGNED_TERM_FIELDS:
                errors.append(_error(config_name, "terms", "14-key signed terms object", config.get("terms"), "invalid_value"))
            elif config.get("config_sha256") != canonical_hash(config["terms"]):
                errors.append(_error(config_name, "config_sha256", canonical_hash(config["terms"]), config.get("config_sha256"), "checksum_mismatch"))
        if log:
            _required(log, log_name, {"schema_version", "game_id", "game_uid", "links", "sub_game_number", "summary", "records"}, errors)
            if log.get("sub_game_number") != number:
                errors.append(_error(log_name, "sub_game_number", number, log.get("sub_game_number"), "filename_field_mismatch"))
            records = log.get("records")
            if not isinstance(records, list):
                errors.append(_error(log_name, "records", "array", type(records).__name__, "wrong_type"))
            else:
                _validate_records(log_name, records, errors)

    result_name = f"result_{game_id}.json"
    result = next((doc for name, doc in documents if name == result_name), None)
    if result:
        _required(result, result_name, {"schema_version", "report_type", "game_id", "game_uid", "links", "timezone", "groups", "num_sub_games", "sub_games", "final_result", "mutual_agreement"}, errors)
        if result.get("report_type") != "final_game_result":
            errors.append(_error(result_name, "report_type", "final_game_result", result.get("report_type"), "invalid_value"))
        rows = result.get("sub_games")
        if not isinstance(rows, list) or len(rows) != num_games:
            errors.append(_error(result_name, "sub_games", f"array of {num_games} rows", rows, "invalid_value"))
        else:
            _validate_result_rows(result_name, rows, group_ids, errors)
            totals = {key: sum(row["score"].get(key, 0) for row in rows) for key in group_ids}
            if len(set(totals.values())) == 1:
                # Tie Rule: a tied cumulative series must carry the fixed
                # tie-score credit for each side (Table 17 row 5).
                totals = {key: value + FIXED_TIE_SCORE for key, value in totals.items()}
            received = (result.get("final_result") or {}).get("total_score")
            if received != totals:
                errors.append(_error(result_name, "final_result.total_score", totals, received, "derived_value_mismatch"))
        agreement = result.get("mutual_agreement")
        if not isinstance(agreement, dict) or agreement.get("confirmed") is not True or not SHA256_RE.match(str(agreement.get("sha256", ""))):
            errors.append(_error(result_name, "mutual_agreement", "confirmed=true and SHA-256 digest", agreement, "invalid_value"))

    forbidden = {"credentials", "credentials_path", "token_path", "refresh_token", "client_secret", "api_key", "private_prompt", "rationale", "opponent_url"}
    for filename, doc in documents:
        for field, value in _walk(doc):
            if field.split(".")[-1].casefold() in forbidden:
                errors.append(_error(filename, field, "private field omitted", value, "private_information_exposed"))
    return errors, paths


def _first_terms(documents: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
    for _, doc in documents:
        if isinstance(doc.get("terms"), dict):
            return doc["terms"]
    return None


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
