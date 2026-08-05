"""Tests for the reusable game-log animation renderer."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPT = Path(__file__).parents[2] / "scripts" / "visualize_game_log.py"
SPEC = importlib.util.spec_from_file_location("visualize_game_log", SCRIPT)
assert SPEC and SPEC.loader
visualizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = visualizer
SPEC.loader.exec_module(visualizer)


def _entry(step, role, before, after, move, **extra):
    payload = {
        "step": step,
        "role": role,
        "state": {"row": before[0], "col": before[1]},
        "position": list(after),
        "move": move,
        "intent": True,
        "hint": f"{role} moved {move}",
        **extra,
    }
    return {
        "state": payload["state"],
        "move": move,
        "intent": True,
        "payload": payload,
    }


def test_load_replay_normalizes_roles_positions_and_capture(tmp_path):
    path = tmp_path / "log_G009_g01.json"
    path.write_text(
        json.dumps(
            [
                _entry(1, "thief", (2, 2), (2, 3), "E"),
                _entry(1, "police", (0, 0), (1, 0), "S"),
                _entry(2, "thief", (2, 3), (1, 3), "N"),
                _entry(2, "police", (1, 0), (1, 3), "E"),
            ]
        ),
        encoding="utf-8",
    )

    frames, board_size, game_id = visualizer.load_replay(path)

    assert len(frames) == 4
    assert board_size == 4
    assert game_id == "G009"
    assert frames[-1].positions == {"thief": (1, 3), "cop": (1, 3)}
    assert "CAPTURE" in frames[-1].events[-1]
    assert frames[-1].important is True


def test_wrapped_schema_extracts_optional_entities_scores_and_events(tmp_path):
    path = tmp_path / "wrapped.json"
    path.write_text(
        json.dumps(
            {
                "game_id": "DEMO",
                "board": {
                    "grid_size": 7,
                    "barriers": [[1, 1]],
                    "gems": [{"row": 2, "col": 2, "name": "ruby"}],
                },
                "steps": [
                    _entry(
                        1,
                        "thief",
                        (3, 3),
                        (3, 4),
                        "E",
                        scores={"thief": 5},
                        collected={"gems": 1},
                        fallback=True,
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    frames, board_size, game_id = visualizer.load_replay(path)

    assert board_size == 7
    assert game_id == "DEMO"
    assert frames[0].obstacles == {(1, 1)}
    assert frames[0].items[0].position == (2, 2)
    assert frames[0].scores == {"thief": 5}
    assert frames[0].collected == {"gems": 1}
    assert "Fallback strategy activated" in frames[0].events


def test_invalid_schema_has_a_clear_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"unrelated": []}', encoding="utf-8")
    with pytest.raises(visualizer.UnsupportedLogError, match="unsupported object schema"):
        visualizer.load_replay(path)


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
