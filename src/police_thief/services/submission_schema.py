"""Submission JSON vocabulary: the allowed values, the regexes, the error
types, canonical hashing, and the small read/write primitives.

Split out of submission_artifacts.py, which re-exports what callers use."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _write(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep canonical_bytes() compact for signatures and hashes, but make the
    # persisted submission artifacts readable for human review.
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _links(game_id: str, participants: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "declaration": f"declaration_{game_id}.json",
        "config": f"config_{game_id}_g<NN>.json",
        "log": f"log_{game_id}_g<NN>.json",
        "result": f"result_{game_id}.json",
        "github": {group_id: value["repos"] for group_id, value in participants.items()},
    }


def submission_filenames(game_id: str, num_sub_games: int) -> list[str]:
    return [
        f"declaration_{game_id}.json",
        *(f"config_{game_id}_g{number:02d}.json" for number in range(1, num_sub_games + 1)),
        *(f"log_{game_id}_g{number:02d}.json" for number in range(1, num_sub_games + 1)),
        f"result_{game_id}.json",
    ]
