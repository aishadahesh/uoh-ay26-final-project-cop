"""Board clicks and barrier mode: translating a cell click into a move or a
barrier placement, and refusing when it is not the human's turn.

Split by theme out of the original `test_play_app.py`."""


from police_thief.domain.board import Move, Position
from police_thief.domain.interactive_match import GameMode
from police_thief.gui.play_app import PlayApp
from police_thief.shared.constants import AgentRole
from tests.unit.play_app_helpers import (
    _match,
    _no_schedule,
)


def test_clicking_a_legal_board_cell_applies_the_corresponding_move(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_COP_VS_AGENT, cop=Position(3, 2), thief=Position(6, 6))
    app = PlayApp(root, match)
    app.start()
    app._on_cell_click(3, 3)  # East of (3,2)
    assert match.positions[AgentRole.COP] == Position(3, 3)


def test_clicking_a_cell_that_is_not_a_legal_move_is_a_no_op(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_COP_VS_AGENT, cop=Position(0, 0))
    app = PlayApp(root, match)
    app.start()
    app._on_cell_click(6, 6)
    assert match.turns_played == 0


def test_toggling_barrier_mode_then_clicking_places_a_barrier(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_COP_VS_AGENT, cop=Position(0, 0), thief=Position(6, 6))
    app = PlayApp(root, match)
    app.start()
    app._toggle_barrier_mode()
    assert app._barrier_mode is True
    app._on_cell_click(0, 1)
    assert match.board.is_blocked(Position(0, 1))
    assert app._barrier_mode is False  # reset after placing


def test_barrier_button_is_disabled_when_the_human_controls_the_thief(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.AGENT_VS_HUMAN_THIEF)
    match.apply_move(Move.STAY)  # cop (agent) moves first via direct call; now thief's (human) turn
    app = PlayApp(root, match)
    app.start()
    assert app.barrier_button.cget("state") == "disabled"


def test_toggle_barrier_mode_is_a_no_op_when_it_is_not_the_humans_turn(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.AGENT_VS_HUMAN_THIEF)  # cop (agent) moves first
    app = PlayApp(root, match)
    app.start()
    app._toggle_barrier_mode()
    assert app._barrier_mode is False


def test_cell_click_is_a_no_op_when_it_is_not_the_humans_turn(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.AGENT_VS_HUMAN_THIEF)  # cop (agent) moves first
    app = PlayApp(root, match)
    app.start()
    app._on_cell_click(3, 4)
    assert match.turns_played == 0


def test_clicking_an_illegal_barrier_target_in_barrier_mode_is_a_no_op(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_COP_VS_AGENT, cop=Position(0, 0))
    app = PlayApp(root, match)
    app.start()
    app._toggle_barrier_mode()
    app._on_cell_click(6, 6)  # nowhere near the cop -- MoveRejectedError inside place_barrier
    assert match.turns_played == 0
    assert app._barrier_mode is True  # unchanged -- the attempt never completed


def test_human_vs_human_mode_draws_both_true_positions(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_VS_HUMAN)
    app = PlayApp(root, match)
    app.start()
    assert len(app.canvas._marker_ids) == 4  # two agent markers (oval + text each)
