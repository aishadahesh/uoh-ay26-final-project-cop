"""Final revealed-trajectory audit: the records it must accept.

Split by theme out of the original `test_capture_safety.py`."""


from police_thief.domain.board import Position
from police_thief.services.network_match import (
    _audit_revealed_trajectory,
)


def test_final_audit_detects_recorded_step_13_collision_across_peer_formats():
    thief_moves = (
        "S", "S", "E", "E", "S", "E", "N", "S", "N", "S", "N", "S", "N", "N",
    )
    thief_positions = (
        (4, 3), (5, 3), (5, 4), (5, 5), (6, 5), (6, 6), (5, 6),
        (6, 6), (5, 6), (6, 6), (5, 6), (6, 6), (5, 6), (4, 6),
    )
    police_moves = (
        "E", "S", "E", "S", "E", "S", "S", "E", "S", "E", "N", "S", "E", "S",
    )
    police_positions = (
        (0, 1), (1, 1), (1, 2), (2, 2), (2, 3), (3, 3), (4, 3),
        (4, 4), (5, 4), (5, 5), (4, 5), (5, 5), (5, 6), (6, 6),
    )

    thief_records = [
        {
            "payload": {
                "step": step,
                "role": "thief",
                "state": f"grid=7;self=[{row}, {col}]",
                "move": f"MOVE:{move}",
                "intent": "truth",
            }
        }
        for step, (move, (row, col)) in enumerate(
            zip(thief_moves, thief_positions, strict=True), start=1,
        )
    ]
    previous = Position(0, 0)
    police_records = []
    for step, (move, (row, col)) in enumerate(
        zip(police_moves, police_positions, strict=True), start=1,
    ):
        police_records.append({
            "payload": {
                "step": step,
                "role": "police",
                "state": {"row": previous.row, "col": previous.col},
                "position": [row, col],
                "move": move,
                "intent": True,
            }
        })
        previous = Position(row, col)

    audit = _audit_revealed_trajectory(
        police_records,
        thief_records,
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert audit.errors == ()
    assert audit.coincidence_step == 13
    assert audit.coincidence_after_role == "police"
    assert audit.capture_step is None
    assert audit.trailing_moves == 0


def test_final_audit_accepts_stationary_barrier_action_vocabulary():
    audit = _audit_revealed_trajectory(
        [
            {"payload": {
                "step": 1, "role": "police", "state": "grid=7;self=[1, 0]",
                "move": "MOVE:S", "intent": "truth",
            }},
            {"payload": {
                "step": 2, "role": "police", "state": "grid=7;self=[1, 0]",
                "move": "BARRIER:E", "intent": "truth",
            }},
            {"payload": {
                "step": 3, "role": "police", "state": "grid=7;self=[1, 1]",
                "move": "MOVE:E", "intent": "truth",
            }},
        ],
        [],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert audit.errors == ()
    assert audit.capture_step is None


def test_final_audit_accepts_stationary_declared_barrier():
    audit = _audit_revealed_trajectory(
        [{"payload": {
            "step": 1, "role": "police",
            "state": {"row": 0, "col": 0},
            "position": [0, 0], "move": "STAY", "intent": True,
            "barrier_placed": [0, 1], "capture_claim": [0, 0],
        }}],
        [],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert audit.errors == ()
