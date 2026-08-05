#!/usr/bin/env python3
"""Convert Police-Thief JSON logs into polished animated GIF or MP4 replays."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - depends on the caller environment
    raise SystemExit("Pillow is required. Install project dependencies with `uv sync`.") from exc

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
        numbers = re.findall(r"-?\d+", value)
        if len(numbers) >= 2:
            return int(numbers[0]), int(numbers[1])
    return None


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


def _role(record: dict[str, Any]) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    raw = payload.get("role", record.get("role", record.get("actor", record.get("agent", ""))))
    role = ROLE_ALIASES.get(str(raw).strip().lower())
    if role is None:
        raise UnsupportedLogError(f"step has an unsupported or missing role: {raw!r}")
    return role


def _verify_record(record: dict[str, Any]) -> bool | None:
    nonce = record.get("nonce")
    expected = record.get("h_commit", record.get("commit"))
    if not isinstance(nonce, str) or not isinstance(expected, str):
        return None
    payload = record.get("payload")
    if isinstance(payload, dict):
        mirrors = all(record.get(key) == payload.get(key) for key in ("state", "move", "intent"))
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
        collected = source.get("collected", source.get("collected_items"))
        if collected:
            events.append(f"Collected {collected}")
    return list(dict.fromkeys(events))


def load_replay(path: Path) -> tuple[list[ReplayFrame], int, str]:
    """Parse a supported JSON log and return normalized replay frames."""
    try:
        root = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise UnsupportedLogError(f"input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise UnsupportedLogError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    records, metadata = _records_from_root(root)
    positions: dict[str, tuple[int, int]] = {}
    frames: list[ReplayFrame] = []
    seen_coordinates: list[tuple[int, int]] = []
    filename_match = re.search(r"(?:log|result)_([^_]+)(?:_g\d+)?$", path.stem, re.I)
    inferred_game_id = filename_match.group(1) if filename_match else path.stem
    game_id = str(metadata.get("game_id", metadata.get("id", inferred_game_id)))
    static_sources = [metadata, metadata.get("board", {}) if isinstance(metadata, dict) else {}]

    for index, record in enumerate(records):
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        actor = _role(record)
        before = parse_position(payload.get("state")) or parse_position(record.get("state"))
        after = (
            parse_position(payload.get("position"))
            or parse_position(record.get("position"))
            or parse_position(payload.get("after"))
        )
        if before is None and actor in positions:
            before = positions[actor]
        if before is None or after is None:
            raise UnsupportedLogError(
                f"step {index + 1} does not provide usable pre/post positions"
            )
        positions.setdefault(actor, before)
        positions[actor] = after
        seen_coordinates.extend((before, after))
        turn_value = payload.get("step", record.get("step", record.get("turn", index + 1)))
        try:
            turn = int(turn_value)
        except (TypeError, ValueError):
            turn = index + 1
        move = str(payload.get("move", record.get("move", "?"))).upper()
        obstacles: set[tuple[int, int]] = set()
        goals: list[Entity] = []
        items: list[Entity] = []
        for source in (*static_sources, payload, record):
            obstacles.update(
                entity.position
                for entity in _entity_positions(
                    source, ("obstacles", "barriers", "blocked", "walls"), "obstacle"
                )
            )
            goals.extend(_entity_positions(source, ("goals", "goal", "targets", "exits"), "goal"))
            items.extend(
                _entity_positions(source, ("gems", "items", "collectibles", "coins"), "item")
            )
        seen_coordinates.extend(obstacles)
        seen_coordinates.extend(entity.position for entity in (*goals, *items))
        scores = _find_mapping(payload, ("scores", "score")) or _find_mapping(
            record, ("scores", "score")
        )
        if not scores:
            scores = {
                key: value
                for key, value in {
                    "cop": payload.get("cop_score", record.get("cop_score")),
                    "thief": payload.get("thief_score", record.get("thief_score")),
                }.items()
                if value is not None
            }
        collected = _find_mapping(
            payload, ("collected", "collected_items", "inventory")
        ) or _find_mapping(record, ("collected", "collected_items", "inventory"))
        commitment = str(record.get("h_commit", record.get("commit", "")))
        frames.append(
            ReplayFrame(
                index=index,
                turn=turn,
                actor=actor,
                move=move,
                before=before,
                after=after,
                positions=dict(positions),
                hint=str(payload.get("hint", record.get("hint", ""))),
                events=_events(record, payload),
                scores=scores,
                collected=collected,
                obstacles=obstacles,
                goals=list(dict.fromkeys(goals)),
                items=list(dict.fromkeys(items)),
                verified=_verify_record(record),
                commitment=commitment,
            )
        )

    final = frames[-1]
    if final.positions.get("cop") == final.positions.get("thief") and "cop" in final.positions:
        final.events.append("CAPTURE — cop and thief occupy the same cell")
    else:
        final.events.append("Replay complete — final recorded state")
    final.is_final = True

    explicit_size = None
    candidates = [metadata, metadata.get("board", {}) if isinstance(metadata, dict) else {}]
    for source in candidates:
        if not isinstance(source, dict):
            continue
        for key in ("grid_size", "board_size", "size"):
            value = source.get(key)
            if isinstance(value, int) and value > 0:
                explicit_size = value
                break
    inferred = max((max(position) for position in seen_coordinates), default=6) + 1
    board_size = explicit_size or max(2, inferred)
    return frames, board_size, game_id


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = [
        "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _fit_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int, max_lines: int = 2
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(lines)) < len(text):
        last = lines[-1]
        while last and draw.textbbox((0, 0), last + "…", font=font)[2] > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def render_frame(
    frame: ReplayFrame,
    board_size: int,
    game_id: str,
    resolution: tuple[int, int],
    total_frames: int | None = None,
) -> Image.Image:
    """Render one normalized frame using a GitHub-friendly dark visual style."""
    width, height = resolution
    image = Image.new("RGB", resolution, "#08111f")
    draw = ImageDraw.Draw(image)
    accent = "#5eead4" if frame.actor == "thief" else "#60a5fa"
    actor_name = "THIEF" if frame.actor == "thief" else "COP"

    # Header
    draw.rectangle((0, 0, width, int(height * 0.13)), fill="#0d1b2e")
    draw.text(
        (int(width * 0.045), int(height * 0.035)),
        "POLICE–THIEF  /  VERIFIED REPLAY",
        font=_font(max(18, width // 50), True),
        fill="#e8f0ff",
    )
    turn_label = f"GAME {game_id}   •   TURN {frame.turn}   •   ACTION {frame.index + 1}"
    label_font = _font(max(14, width // 72), True)
    label_width = draw.textbbox((0, 0), turn_label, font=label_font)[2]
    draw.text(
        (width - label_width - int(width * 0.045), int(height * 0.043)),
        turn_label,
        font=label_font,
        fill=accent,
    )

    margin = int(width * 0.045)
    board_top = int(height * 0.18)
    board_bottom = int(height * 0.91)
    panel_left = int(width * 0.67)
    board_area = min(panel_left - margin * 2, board_bottom - board_top)
    cell = max(24, board_area // board_size)
    grid_px = cell * board_size
    board_left = margin + max(0, (panel_left - margin * 2 - grid_px) // 2)

    # Board shadow and cells
    _rounded(
        draw,
        (board_left - 14, board_top - 14, board_left + grid_px + 14, board_top + grid_px + 14),
        24,
        "#101f33",
    )
    for row in range(board_size):
        for col in range(board_size):
            x0, y0 = board_left + col * cell, board_top + row * cell
            fill = "#17273b" if (row + col) % 2 == 0 else "#142338"
            draw.rectangle(
                (x0, y0, x0 + cell, y0 + cell),
                fill=fill,
                outline="#29405a",
                width=max(1, cell // 35),
            )
            if (row, col) == frame.before:
                draw.rectangle(
                    (x0 + 4, y0 + 4, x0 + cell - 4, y0 + cell - 4),
                    outline="#fbbf24",
                    width=max(3, cell // 16),
                )
            if (row, col) == frame.after:
                draw.rectangle(
                    (x0 + 2, y0 + 2, x0 + cell - 2, y0 + cell - 2),
                    outline=accent,
                    width=max(4, cell // 12),
                )

    # Optional static entities
    for row, col in frame.obstacles:
        if 0 <= row < board_size and 0 <= col < board_size:
            x0, y0 = board_left + col * cell, board_top + row * cell
            pad = cell * 0.2
            draw.rounded_rectangle(
                (x0 + pad, y0 + pad, x0 + cell - pad, y0 + cell - pad),
                radius=8,
                fill="#475569",
                outline="#94a3b8",
                width=2,
            )
    for entity in frame.goals:
        row, col = entity.position
        x, y = board_left + (col + 0.5) * cell, board_top + (row + 0.5) * cell
        r = cell * 0.24
        draw.ellipse((x - r, y - r, x + r, y + r), outline="#fbbf24", width=max(3, cell // 14))
    for entity in frame.items:
        row, col = entity.position
        x, y = board_left + (col + 0.5) * cell, board_top + (row + 0.5) * cell
        r = cell * 0.2
        draw.polygon(
            ((x, y - r), (x + r, y), (x, y + r), (x - r, y)), fill="#c084fc", outline="#f5d0fe"
        )

    # Movement arrow
    if frame.before != frame.after:
        bx = board_left + (frame.before[1] + 0.5) * cell
        by = board_top + (frame.before[0] + 0.5) * cell
        ax = board_left + (frame.after[1] + 0.5) * cell
        ay = board_top + (frame.after[0] + 0.5) * cell
        draw.line((bx, by, ax, ay), fill="#fbbf24", width=max(4, cell // 13))
        angle = math.atan2(ay - by, ax - bx)
        arrow = max(9, cell * 0.18)
        points = [
            (ax, ay),
            (ax - arrow * math.cos(angle - 0.6), ay - arrow * math.sin(angle - 0.6)),
            (ax - arrow * math.cos(angle + 0.6), ay - arrow * math.sin(angle + 0.6)),
        ]
        draw.polygon(points, fill="#fbbf24")

    # Agents; overlap becomes a capture ring.
    for role in ("thief", "cop"):
        position = frame.positions.get(role)
        if position is None:
            continue
        row, col = position
        cx = board_left + int((col + 0.5) * cell)
        cy = board_top + int((row + 0.5) * cell)
        radius = int(cell * (0.30 if role == frame.actor else 0.25))
        color = "#14b8a6" if role == "thief" else "#3b82f6"
        outline = "#99f6e4" if role == "thief" else "#bfdbfe"
        if frame.positions.get("cop") == frame.positions.get("thief"):
            offset = -radius // 3 if role == "cop" else radius // 3
            cx += offset
            draw.ellipse(
                (cx - radius - 6, cy - radius - 6, cx + radius + 6, cy + radius + 6),
                outline="#fb7185",
                width=5,
            )
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=color,
            outline=outline,
            width=max(3, cell // 18),
        )
        letter = "C" if role == "cop" else "T"
        font = _font(max(16, cell // 3), True)
        bbox = draw.textbbox((0, 0), letter, font=font)
        draw.text(
            (cx - (bbox[2] - bbox[0]) / 2, cy - (bbox[3] - bbox[1]) / 2 - bbox[1]),
            letter,
            font=font,
            fill="#ffffff",
        )

    # Coordinate labels
    tiny = _font(max(11, width // 105))
    for i in range(board_size):
        x = board_left + int((i + 0.5) * cell)
        y = board_top + int((i + 0.5) * cell)
        draw.text((x - 4, board_top - 30), str(i), font=tiny, fill="#7890aa")
        draw.text((board_left - 28, y - 7), str(i), font=tiny, fill="#7890aa")

    # Information panel
    px = panel_left
    panel_right = width - margin
    _rounded(
        draw,
        (px, board_top - 14, panel_right, board_top + grid_px + 14),
        24,
        "#101f33",
        "#263c55",
        2,
    )
    inner = px + int(width * 0.025)
    panel_width = panel_right - inner - int(width * 0.025)
    y = board_top + 18
    draw.text(
        (inner, y), f"{actor_name} ACTED", font=_font(max(14, width // 78), True), fill=accent
    )
    y += int(height * 0.055)
    move_name = MOVE_LABELS.get(frame.move, frame.move.title())
    draw.text(
        (inner, y),
        f"{move_name}  {frame.before} → {frame.after}",
        font=_font(max(20, width // 51), True),
        fill="#f8fafc",
    )
    y += int(height * 0.075)

    for role, color in (("cop", "#60a5fa"), ("thief", "#5eead4")):
        pos = frame.positions.get(role)
        draw.ellipse((inner, y + 3, inner + 15, y + 18), fill=color)
        draw.text(
            (inner + 26, y),
            f"{role.title()} position",
            font=_font(max(12, width // 90)),
            fill="#8fa6bf",
        )
        value = str(pos) if pos is not None else "not revealed yet"
        value_font = _font(max(13, width // 82), True)
        value_w = draw.textbbox((0, 0), value, font=value_font)[2]
        draw.text((inner + panel_width - value_w, y), value, font=value_font, fill="#e8f0ff")
        y += int(height * 0.047)

    y += 8
    status = (
        "VERIFIED"
        if frame.verified is True
        else "TAMPERED"
        if frame.verified is False
        else "UNSIGNED"
    )
    status_color = (
        "#34d399" if frame.verified is True else "#fb7185" if frame.verified is False else "#94a3b8"
    )
    draw.text((inner, y), "COMMITMENT", font=_font(max(11, width // 100), True), fill="#7890aa")
    y += int(height * 0.035)
    _rounded(draw, (inner, y, inner + panel_width, y + int(height * 0.046)), 10, "#14283d")
    draw.text(
        (inner + 12, y + 7), status, font=_font(max(11, width // 96), True), fill=status_color
    )
    digest = frame.commitment[:10] + "…" if frame.commitment else "n/a"
    digest_w = draw.textbbox((0, 0), digest, font=tiny)[2]
    draw.text((inner + panel_width - digest_w - 12, y + 8), digest, font=tiny, fill="#8fa6bf")
    y += int(height * 0.075)

    if frame.scores:
        draw.text((inner, y), "SCORE", font=_font(max(11, width // 100), True), fill="#7890aa")
        y += 24
        draw.text(
            (inner, y),
            "  •  ".join(f"{k}: {v}" for k, v in frame.scores.items()),
            font=_font(max(12, width // 90), True),
            fill="#e8f0ff",
        )
        y += int(height * 0.055)
    if frame.collected:
        draw.text((inner, y), "COLLECTED", font=_font(max(11, width // 100), True), fill="#7890aa")
        y += 24
        draw.text(
            (inner, y),
            ", ".join(f"{k}: {v}" for k, v in frame.collected.items()),
            font=_font(max(12, width // 90)),
            fill="#e8f0ff",
        )
        y += int(height * 0.055)

    draw.text((inner, y), "TURN NOTE", font=_font(max(11, width // 100), True), fill="#7890aa")
    y += 25
    note = frame.events[-1] if frame.events else frame.hint or "Recorded legal movement"
    note_color = "#fecdd3" if frame.important else "#d8e5f3"
    for line in _fit_text(draw, note, _font(max(12, width // 88)), panel_width, 3):
        draw.text((inner, y), line, font=_font(max(12, width // 88)), fill=note_color)
        y += int(height * 0.033)

    # Progress rail and legend
    progress_y = height - int(height * 0.045)
    draw.line((margin, progress_y, width - margin, progress_y), fill="#29405a", width=5)
    progress = (frame.index + 1) / max(1, total_frames or frame.index + 1)
    marker_x = margin + int((width - 2 * margin) * min(1.0, progress))
    draw.line((margin, progress_y, marker_x, progress_y), fill=accent, width=5)
    draw.ellipse((marker_x - 7, progress_y - 7, marker_x + 7, progress_y + 7), fill=accent)
    return image


def render_animation(
    frames: list[ReplayFrame], board_size: int, game_id: str, resolution: tuple[int, int]
) -> list[Image.Image]:
    return [render_frame(frame, board_size, game_id, resolution, len(frames)) for frame in frames]


def export_gif(
    images: list[Image.Image], frames: list[ReplayFrame], output: Path, duration_ms: int
) -> None:
    durations = [
        duration_ms * (4 if frame.is_final else 2 if frame.important else 1) for frame in frames
    ]
    images[0].save(
        output,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=True,
    )


def export_mp4(
    images: list[Image.Image], frames: list[ReplayFrame], output: Path, fps: float
) -> None:
    try:
        import imageio.v2 as imageio
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional environment
        raise RuntimeError("MP4 export requires `imageio`, `imageio-ffmpeg`, and `numpy`.") from exc
    with imageio.get_writer(
        output, fps=fps, codec="libx264", quality=8, macro_block_size=None
    ) as writer:
        for image, frame in zip(images, frames, strict=True):
            repeats = 4 if frame.is_final else 2 if frame.important else 1
            array = np.asarray(image)
            for _ in range(repeats):
                writer.append_data(array)


def parse_resolution(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)[xX](\d+)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            "resolution must look like WIDTHxHEIGHT, for example 1280x720"
        )
    width, height = map(int, match.groups())
    if width < 640 or height < 480:
        raise argparse.ArgumentTypeError("resolution must be at least 640x480")
    return width, height


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="input game log JSON")
    parser.add_argument("--output", required=True, type=Path, help="output GIF or MP4 path")
    parser.add_argument(
        "--format", choices=("gif", "mp4"), help="output format; inferred from extension by default"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=650,
        help="normal GIF frame duration in milliseconds (default: 650)",
    )
    parser.add_argument("--fps", type=float, default=2.0, help="MP4 frames per second (default: 2)")
    parser.add_argument(
        "--resolution",
        type=parse_resolution,
        default=(1280, 720),
        help="base resolution, e.g. 1280x720",
    )
    parser.add_argument(
        "--scale", type=float, default=1.0, help="resolution multiplier (default: 1.0)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.duration <= 0:
        raise SystemExit("error: --duration must be greater than zero")
    if args.fps <= 0:
        raise SystemExit("error: --fps must be greater than zero")
    if args.scale <= 0:
        raise SystemExit("error: --scale must be greater than zero")
    output_format = args.format or args.output.suffix.lower().lstrip(".")
    if output_format not in {"gif", "mp4"}:
        raise SystemExit(
            "error: output format must be gif or mp4 (use --format or a supported extension)"
        )
    resolution = tuple(int(dimension * args.scale) for dimension in args.resolution)
    if any(dimension > 4096 for dimension in resolution):
        raise SystemExit("error: scaled resolution cannot exceed 4096 pixels per dimension")
    try:
        frames, board_size, game_id = load_replay(args.input)
        images = render_animation(frames, board_size, game_id, resolution)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if output_format == "gif":
            export_gif(images, frames, args.output, args.duration)
        else:
            export_mp4(images, frames, args.output, args.fps)
    except (UnsupportedLogError, RuntimeError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(f"Created {output_format.upper()} replay with {len(frames)} frames: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
