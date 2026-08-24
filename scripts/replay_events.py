"""Deriving entity positions and human-readable events from a record."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# This script is run by path, not imported as a package, so its own
# directory has to be importable before the sibling modules below.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_model import Entity, parse_position  # noqa: E402


def _entity_positions(source: Any, keys: Iterable[str], kind: str) -> list[Entity]:
    if not isinstance(source, dict):
        return []
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        entities: list[Entity] = []
        for index, item in enumerate(values, 1):
            position = parse_position(item)
            if position is not None:
                label = (
                    str(item.get("name", item.get("id", index)))
                    if isinstance(item, dict)
                    else str(index)
                )
                entities.append(Entity(kind, position, label))
        if entities:
            return entities
    return []


def _events(record: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    events: list[str] = []
    for source in (payload, record):
        for key in ("event", "events", "status", "reason", "rationale", "error"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                events.append(value.strip())
            elif isinstance(value, list):
                events.extend(str(item) for item in value if item)
        if source.get("fallback") or source.get("used_fallback"):
            events.append("Fallback strategy activated")
        if source.get("invalid") or source.get("invalid_move"):
            events.append("Invalid action rejected")
        if source.get("captured") or source.get("capture"):
            events.append("Capture confirmed")
        if source.get("capture_claim") is not None:
            events.append(f"Capture claim at {source['capture_claim']}")
        response = source.get("claim_response")
        if isinstance(response, dict):
            events.append(
                "Capture confirmed by Thief"
                if response.get("caught") is True
                else "Capture claim rejected truthfully"
            )
        if source.get("barrier_placed") is not None:
            events.append(f"Barrier placed at {source['barrier_placed']}")
        win_claim = source.get("win_claim")
        if isinstance(win_claim, dict):
            claim_type = str(win_claim.get("type", "")).replace("_", " ").strip()
            if claim_type:
                events.append(f"Terminal claim: {claim_type}")
        collected = source.get("collected", source.get("collected_items"))
        if collected:
            events.append(f"Collected {collected}")
    return list(dict.fromkeys(events))
