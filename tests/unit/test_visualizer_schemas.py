"""Replay loading across the log schemas the visualizer accepts, and the
error raised for one it does not.

Split by theme out of the original `test_visualize_game_log.py`."""

from __future__ import annotations

import json

import pytest

from tests.unit.visualizer_loader import (
    _entry,
    visualizer,
)


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
