"""Rendering and the command-line entry point.

Split by theme out of the original `test_visualize_game_log.py`."""

from __future__ import annotations

import json

from PIL import Image

from tests.unit.visualizer_loader import (
    _entry,
    visualizer,
)


def test_render_frame_uses_requested_resolution(tmp_path):
    path = tmp_path / "log_X_g01.json"
    path.write_text(json.dumps([_entry(1, "thief", (0, 0), (0, 1), "E")]), encoding="utf-8")
    frames, board_size, game_id = visualizer.load_replay(path)
    image = visualizer.render_frame(frames[0], board_size, game_id, (800, 600), 1)
    assert image.size == (800, 600)


def test_cli_creates_nested_gif_output(tmp_path):
    source = tmp_path / "log_X_g01.json"
    source.write_text(
        json.dumps(
            [
                _entry(1, "thief", (0, 0), (0, 1), "E"),
                _entry(1, "police", (2, 2), (1, 2), "N"),
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "nested" / "replay.gif"

    assert (
        visualizer.main(
            [
                "--input",
                str(source),
                "--output",
                str(output),
                "--resolution",
                "800x600",
                "--duration",
                "50",
            ]
        )
        == 0
    )
    assert output.is_file()
    with Image.open(output) as gif:
        assert gif.n_frames == 2
        assert gif.size == (800, 600)
