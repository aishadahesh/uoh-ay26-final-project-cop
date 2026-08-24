"""Replay vocabulary: role aliases, move labels, the frame and entity types,
and position parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


class UnsupportedLogError(ValueError):
    """Raised when JSON cannot be interpreted as a chronological game log."""


@dataclass(frozen=True)
class Entity:
    kind: str
    position: tuple[int, int]
    label: str = ""


@dataclass
class ReplayFrame:
    index: int
    turn: int
    actor: str
    move: str
    before: tuple[int, int]
    after: tuple[int, int]
    positions: dict[str, tuple[int, int]]
    hint: str = ""
    events: list[str] = field(default_factory=list)
    scores: dict[str, Any] = field(default_factory=dict)
    collected: dict[str, Any] = field(default_factory=dict)
    obstacles: set[tuple[int, int]] = field(default_factory=set)
    goals: list[Entity] = field(default_factory=list)
    items: list[Entity] = field(default_factory=list)
    verified: bool | None = None
    commitment: str = ""
    is_final: bool = False

    @property
    def important(self) -> bool:
        text = " ".join(self.events).lower()
        return self.is_final or any(word in text for word in IMPORTANT_WORDS)


def parse_position(value: Any) -> tuple[int, int] | None:
    """Extract a row/column pair from common JSON position encodings."""
    if isinstance(value, dict):
        if "row" in value and ("col" in value or "column" in value):
            try:
                return int(value["row"]), int(value.get("col", value.get("column")))
            except (TypeError, ValueError):
                return None
        for key in ("position", "pos", "location", "cell", "coordinates"):
            found = parse_position(value.get(key))
            if found is not None:
                return found
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        own_cell = re.search(
            r"self\s*=\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
            value,
            re.IGNORECASE,
        )
        if own_cell:
            return int(own_cell.group(1)), int(own_cell.group(2))
        numbers = re.findall(r"-?\d+", value)
        if len(numbers) >= 2:
            return int(numbers[0]), int(numbers[1])
    return None


def _role(record: dict[str, Any], fallback: str | None = None) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    raw = payload.get("role", record.get("role", record.get("actor", record.get("agent", ""))))
    role = ROLE_ALIASES.get(str(raw).strip().lower())
    if role is None and not str(raw).strip() and fallback is not None:
        return fallback
    if role is None:
        raise UnsupportedLogError(f"step has an unsupported or missing role: {raw!r}")
    return role


ROLE_ALIASES = {"police": "cop", "cop": "cop", "thief": "thief", "robber": "thief"}


MOVE_LABELS = {"N": "North", "S": "South", "E": "East", "W": "West", "STAY": "Stay"}


IMPORTANT_WORDS = (
    "capture",
    "caught",
    "collect",
    "gem",
    "goal",
    "fallback",
    "invalid",
    "blocked",
    "win",
    "finish",
)


SUPPORTED_WRAPPERS = ("entries", "log", "steps", "turns", "records", "replay")
