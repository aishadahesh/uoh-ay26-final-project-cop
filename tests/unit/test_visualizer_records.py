"""Real recorded record shapes: inferring roles, accumulating barriers, and
reading a legacy peer's string state as a post-move position.

Split by theme out of the original `test_visualize_game_log.py`."""

from __future__ import annotations

import json

from tests.unit.visualizer_loader import (
    visualizer,
)


def test_actual_network_record_shape_infers_roles_and_accumulates_barriers(tmp_path):
    def sealed(payload, nonce):
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        import hashlib

        return {
            "payload": payload,
            "nonce": nonce,
            "commit": hashlib.sha256(f"{canonical}|{nonce}".encode()).hexdigest(),
        }

    records = [
        sealed(
            {
                "step": 1,
                "state": "grid=7x7;self=[4, 3];barriers=[]",
                "position": [4, 3],
                "move": "MOVE:SOUTH",
                "intent": "truth",
            },
            "thief-1",
        ),
        sealed(
            {
                "step": 1,
                "state": "grid=7x7;self=[0, 1];barriers=[]",
                "position": [0, 1],
                "move": "MOVE:EAST",
                "intent": "truth",
                "capture_claim": [0, 1],
            },
            "cop-1",
        ),
        sealed(
            {
                "step": 2,
                "state": "grid=7x7;self=[4, 3];barriers=[]",
                "position": [4, 3],
                "move": "STAY",
                "intent": "truth",
                "claim_response": {"claim": [0, 1], "caught": False},
            },
            "thief-2",
        ),
        sealed(
            {
                "step": 2,
                "state": "grid=7x7;self=[0, 1];barriers=[[1, 1]]",
                "position": [0, 1],
                "move": "BARRIER:[1, 1]",
                "intent": "truth",
                "barrier_placed": [1, 1],
            },
            "cop-2",
        ),
    ]
    path = tmp_path / "log_G009_g01.json"
    path.write_text(
        json.dumps(
            {
                "game_id": "G009",
                "records": records,
                "summary": {"result": "survival", "steps": 2},
            }
        ),
        encoding="utf-8",
    )

    frames, board_size, game_id = visualizer.load_replay(path)

    assert [frame.actor for frame in frames] == ["thief", "cop", "thief", "cop"]
    assert frames[0].before == (3, 3)
    assert frames[1].before == (0, 0)
    assert frames[-1].obstacles == {(1, 1)}
    assert all(frame.verified is True for frame in frames)
    assert board_size == 7
    assert game_id == "G009"


def test_legacy_peer_record_uses_string_state_as_post_move_position(tmp_path):
    path = tmp_path / "log_G002_g03.json"
    path.write_text(
        json.dumps(
            {
                "game_id": "G002",
                "records": [
                    {
                        "payload": {
                            "step": 1,
                            "role": "thief",
                            "state": "grid=7;self=[3, 4]",
                            "move": "MOVE:E",
                            "intent": "truth",
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    frames, board_size, _ = visualizer.load_replay(path)

    assert frames[0].before == (3, 3)
    assert frames[0].after == (3, 4)
    assert board_size == 7
