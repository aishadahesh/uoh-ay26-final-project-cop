"""Report filenames on disk, JSON read/write, and log hashing.

Split out of match_reports.py, which re-exports these names."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from police_thief.services.commit_reveal import LogEntry, canonical_json


class MatchReportError(ValueError):
    """Raised when a report file is missing, malformed, or schema-invalid."""


def declaration_filename(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def config_filename(game_id: str, sub_game_number: int) -> str:
    return f"config_{game_id}_g{sub_game_number:02d}.json"


def log_filename(game_id: str, sub_game_number: int) -> str:
    return f"log_{game_id}_g{sub_game_number:02d}.json"


def result_filename(game_id: str, sub_game_number: int | None = None) -> str:
    suffix = "" if sub_game_number is None else f"_g{sub_game_number:02d}"
    return f"result_{game_id}{suffix}.json"


def _write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise MatchReportError(f"missing report file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MatchReportError(f"malformed JSON report at {path}: {exc}") from exc


def sha256_of_log(entries: list[LogEntry]) -> str:
    """SHA-256 over the canonically-serialized log (Sec. 9.3.17's "SHA-256 of the match log")."""
    payload = canonical_json([asdict(entry) for entry in entries])
    return hashlib.sha256(payload).hexdigest()
