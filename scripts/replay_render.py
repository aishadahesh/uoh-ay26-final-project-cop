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

from replay_draw import (
    _draw_agents,  # noqa: E402
    _font,
    _rounded,
)
from replay_model import ReplayFrame  # noqa: E402
from replay_panel import _draw_panel  # noqa: E402


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

    _draw_agents(
        draw, frame,
        board_left=board_left, board_top=board_top, cell=cell, width=width,
    )
    # Coordinate labels
    tiny = _font(max(11, width // 105))
    for i in range(board_size):
        x = board_left + int((i + 0.5) * cell)
        y = board_top + int((i + 0.5) * cell)
        draw.text((x - 4, board_top - 30), str(i), font=tiny, fill="#7890aa")
        draw.text((board_left - 28, y - 7), str(i), font=tiny, fill="#7890aa")

    _draw_panel(
        draw, frame,
        width=width, height=height, margin=margin, panel_left=panel_left,
        board_top=board_top, grid_px=grid_px, accent=accent,
        actor_name=actor_name, total_frames=total_frames,
    )
    return image
