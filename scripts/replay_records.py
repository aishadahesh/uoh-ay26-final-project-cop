"""Reading and verifying raw log records across the supported schemas."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# This script is run by path, not imported as a package, so its own
# directory has to be importable before the sibling modules below.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_model import SUPPORTED_WRAPPERS, UnsupportedLogError  # noqa: E402


def _records_from_root(root: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(root, list):
        records, metadata = root, {}
    elif isinstance(root, dict):
        records = None
        for key in SUPPORTED_WRAPPERS:
            if isinstance(root.get(key), list):
                records = root[key]
                break
        if records is None and isinstance(root.get("match"), dict):
            for key in SUPPORTED_WRAPPERS:
                if isinstance(root["match"].get(key), list):
                    records = root["match"][key]
                    break
        if records is None:
            raise UnsupportedLogError(
                "unsupported object schema: expected a JSON array or one of "
                + ", ".join(SUPPORTED_WRAPPERS)
            )
        metadata = root
    else:
        raise UnsupportedLogError("top-level JSON value must be an array or object")
    if not records:
        raise UnsupportedLogError("the log contains no recorded steps")
    if not all(isinstance(record, dict) for record in records):
        raise UnsupportedLogError("every recorded step must be a JSON object")
    return records, metadata


def _verify_record(record: dict[str, Any]) -> bool | None:
    nonce = record.get("nonce")
    expected = record.get("h_commit", record.get("commit"))
    if not isinstance(nonce, str) or not isinstance(expected, str):
        return None
    payload = record.get("payload")
    if isinstance(payload, dict):
        mirrors = all(
            record[key] == payload.get(key) for key in ("state", "move", "intent") if key in record
        )
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        actual = hashlib.sha256(f"{canonical}|{nonce}".encode()).hexdigest()
        return mirrors and actual == expected
    canonical = json.dumps(
        {
            "state": record.get("state"),
            "move": record.get("move"),
            "intent": record.get("intent"),
            "nonce": nonce,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest() == expected


def _find_mapping(source: Any, keys: Iterable[str]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    for key in keys:
        value = source.get(key)
        if isinstance(value, dict):
            return value
    return {}
