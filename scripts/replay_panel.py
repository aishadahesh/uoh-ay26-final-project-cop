"""The information panel beside the board: hint, events, progress rail
and legend.

Extracted verbatim from `render_frame`; every value it read from the
renderer's scope is now an explicit keyword argument.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import ImageDraw
except ImportError as exc:  # pragma: no cover - depends on the caller environment
    raise SystemExit("Pillow is required. Install project dependencies with `uv sync`.") from exc

# This script is run by path, not imported as a package, so its own
# directory has to be importable before the sibling modules below.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_draw import _fit_text, _font, _rounded  # noqa: E402
from replay_model import MOVE_LABELS, ReplayFrame  # noqa: E402


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    frame: ReplayFrame,
    *,
    width: int,
    height: int,
    margin: int,
    panel_left: int,
    board_top: int,
    grid_px: int,
    accent: str,
    actor_name: str,
    total_frames: int,
) -> None:
    tiny = _font(max(11, width // 105))
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
