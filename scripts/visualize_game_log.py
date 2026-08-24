#!/usr/bin/env python3
"""Convert Police-Thief JSON logs into polished animated GIF or MP4 replays."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - depends on the caller environment
    raise SystemExit("Pillow is required. Install project dependencies with `uv sync`.") from exc

# This script is run by path, not imported as a package, so its own
# directory has to be importable before the sibling modules below.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_load import load_replay  # noqa: E402
from replay_model import ReplayFrame, UnsupportedLogError  # noqa: E402
from replay_render import render_frame  # noqa: E402


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
