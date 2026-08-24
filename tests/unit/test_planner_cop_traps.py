"""The cop must not trap itself: corner self-traps, dead ends entered only
for an exact capture, and genuinely boxed-in positions.

Split by theme out of the original `test_tactical_planner.py`."""

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.shared.constants import AgentRole
from tests.unit.tactical_planner_helpers import (
    _belief_at,
)


def test_cop_rejects_recorded_corner_self_trap_after_leaving_own_barrier():
    """A blocked current cell makes the move into (0, 0) irreversible.

    This reproduces the G003 failure: after placing a barrier at (0, 1),
    the cop moved west into a corner whose other exit, (1, 0), was already
    blocked.  It then had no legal movement for the rest of the game.
    """
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.apply_declared_barrier(Position(1, 0))
    board.apply_declared_barrier(Position(0, 1))

    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(0, 1),
        _belief_at(board, Position(0, 0)),
    )

    west = next(item for item in plan.evaluations if item.move is Move.WEST)
    assert west.destination == Position(0, 0)
    assert west.mobility == 0
    assert Move.WEST in plan.excluded_moves
    assert Move.WEST not in plan.allowed_moves
    assert Move.STAY not in plan.allowed_moves
    assert plan.selected in (Move.EAST, Move.SOUTH)


def test_cop_may_enter_a_dead_end_for_an_exact_capture_opportunity():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.apply_declared_barrier(Position(1, 0))
    board.apply_declared_barrier(Position(0, 1))

    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(0, 1),
        BeliefMap(board),
        known_opponent_position=Position(0, 0),
    )

    assert plan.selected is Move.WEST
    assert Move.WEST in plan.allowed_moves
    assert Move.WEST not in plan.excluded_moves


def test_cop_stays_when_barriers_have_genuinely_boxed_it_in():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.apply_declared_barrier(Position(0, 1))
    board.apply_declared_barrier(Position(1, 0))

    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(0, 0),
        _belief_at(board, Position(6, 6)),
    )

    assert plan.selected is Move.STAY
    assert plan.allowed_moves == (Move.STAY,)


def test_cop_on_own_blocked_barrier_cell_still_threatens_adjacent_cells():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    barrier_target = Position(5, 5)
    board.apply_declared_barrier(barrier_target)
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(6, 4),
        _belief_at(board, Position(0, 0)),
        plausible_opponent_positions=(barrier_target,),
    )

    north = next(item for item in plan.evaluations if item.move is Move.NORTH)
    assert north.proximity_risk == 1.0
    assert Move.NORTH not in plan.allowed_moves
