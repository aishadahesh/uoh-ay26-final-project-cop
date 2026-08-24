"""Final revealed-trajectory audit: the records it must reject, and the one
terminal record it tolerates.

Split by theme out of the original `test_capture_safety.py`."""


from police_thief.domain.board import Position
from police_thief.services.network_match import (
    _audit_revealed_trajectory,
)


def test_final_audit_rejects_move_and_barrier_in_the_same_turn():
    audit = _audit_revealed_trajectory(
        [{"payload": {
            "step": 1, "role": "police",
            "state": {"row": 0, "col": 0},
            "position": [0, 1], "move": "E", "intent": True,
            "barrier_placed": [0, 0], "capture_claim": [0, 1],
        }}],
        [],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert any("barrier placement must consume" in error for error in audit.errors)


def test_final_audit_rejects_a_thief_barrier_declaration():
    audit = _audit_revealed_trajectory(
        [],
        [{"payload": {
            "step": 1, "role": "thief",
            "state": {"row": 3, "col": 3},
            "position": [3, 3], "move": "STAY", "intent": True,
            "barrier_placed": [3, 4],
        }}],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert any("thief illegally declared a barrier" in error for error in audit.errors)


def test_final_audit_rejects_unknown_action_with_diagonal_position_jump():
    audit = _audit_revealed_trajectory(
        [{"payload": {
            "step": 1, "role": "police", "state": "grid=7;self=[1, 1]",
            "move": "PRIVATE_ACTION", "intent": "truth",
        }}],
        [],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert "more than one orthogonal step" in audit.errors[0]


def test_final_audit_allows_one_acknowledged_stationary_terminal_record():
    police_records = [
        {"payload": {
            "step": 1, "role": "police", "state": {"row": 0, "col": 0},
            "position": [0, 1], "move": "E", "intent": True,
        }},
        {"payload": {
            "step": 2, "role": "police", "state": {"row": 0, "col": 1},
            "position": [0, 2], "move": "E", "intent": True,
            "capture_claim": [0, 2],
        }},
    ]
    thief_records = [
        {"payload": {
            "step": step, "role": "thief", "state": "grid=7;self=[0, 2]",
            "move": "STAY", "intent": "truth",
        }}
        for step in (1, 2)
    ]
    thief_records.append({"payload": {
        "step": 3, "role": "thief", "state": "grid=7;self=[0, 2]",
        "position": [0, 2], "terminal_ack": "capture",
        "claim_response": {"claim": [0, 2], "caught": True},
    }})

    audit = _audit_revealed_trajectory(
        police_records,
        thief_records,
        "police",
        "thief",
        Position(0, 0),
        Position(0, 2),
        7,
        allow_terminal_record=True,
    )

    assert audit.errors == ()
    assert audit.capture_step == 2
    assert audit.capture_after_role == "police"
    assert audit.trailing_moves == 0

    audit_with_extra_move = _audit_revealed_trajectory(
        police_records,
        [
            *thief_records,
            {"payload": {
                "step": 4, "role": "thief", "state": "grid=7;self=[1, 2]",
                "move": "MOVE:S", "intent": "truth",
            }},
        ],
        "police",
        "thief",
        Position(0, 0),
        Position(0, 2),
        7,
        allow_terminal_record=True,
    )
    assert audit_with_extra_move.trailing_moves == 1


def test_final_audit_rejects_a_discontinuous_revealed_position():
    audit = _audit_revealed_trajectory(
        [{
            "payload": {
                "step": 1, "role": "police", "state": {"row": 0, "col": 0},
                "position": [6, 6], "move": "E", "intent": True,
            }
        }],
        [],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert audit.capture_step is None
    assert "does not match" in audit.errors[0]
