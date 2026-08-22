"""Optional JSONL wire trace for cross-team protocol debugging."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def _trace_path() -> Path | None:
    raw = os.environ.get("PT_WIRE_TRACE", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.suffix.lower() != ".jsonl":
        path = path.with_name(f"{path.name}.{os.getpid()}.jsonl")
    return path


def _extract(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    terms = payload.get("terms") if isinstance(payload.get("terms"), dict) else {}
    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    return {
        "game_id": payload.get("game_id") or terms.get("match_id"),
        "subgame": payload.get("sub_game_number") or terms.get("game_index"),
        "step": payload.get("step"),
        "sender": payload.get("sender") or identity.get("role"),
        "commit": payload.get("commit"),
    }


def trace_wire(
    *,
    direction: str,
    tool: str,
    peer: str | None = None,
    payload: dict | None = None,
    result: str | None = None,
    error: str | None = None,
    **extra,
) -> None:
    path = _trace_path()
    if path is None:
        return
    event = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "dir": direction,
        "tool": tool,
        "peer": peer,
        "result": result,
        "error": error,
        **_extract(payload),
        **{key: value for key, value in extra.items() if value is not None},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
