"""Rendering one replay frame to an image."""

from __future__ import annotations

import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover - depends on the caller environment
    raise SystemExit("Pillow is required. Install project dependencies with `uv sync`.") from exc

# This script is run by path, not imported as a package, so its own
# directory has to be importable before the sibling modules below.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_draw import _fit_text, _font, _rounded
from replay_model import MOVE_LABELS, ReplayFrame  # noqa: E402


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
