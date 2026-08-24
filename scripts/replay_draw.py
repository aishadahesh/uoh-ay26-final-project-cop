"""Low-level drawing helpers: fonts, rounded rectangles, text fitting."""

from __future__ import annotations

try:
    from PIL import ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - depends on the caller environment
    raise SystemExit("Pillow is required. Install project dependencies with `uv sync`.") from exc

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

# This script is run by path, not imported as a package, so its own
# directory has to be importable before the sibling import below.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_model import ReplayFrame  # noqa: E402


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


def _draw_agents(
    draw: ImageDraw.ImageDraw,
    frame: ReplayFrame,
    *,
    board_left: int,
    board_top: int,
    cell: int,
    width: int,
) -> None:
    """Draw both agents; overlap becomes a capture ring.

    Extracted verbatim from `render_frame`.
    """
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
