"""Thief-side evasion: treating belief proximity and public barrier evidence
as constraints on the escape route.

Split by theme out of the original `test_tactical_planner.py`."""

from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.shared.constants import AgentRole
from tests.unit.tactical_planner_helpers import (
    _belief_at,
)


def test_thief_prefers_open_escape_route_over_equal_distance_corner():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board, Position(0, 1), _belief_at(board, Position(1, 1))
    )
    east = next(item for item in plan.evaluations if item.move is Move.EAST)
    west = next(item for item in plan.evaluations if item.move is Move.WEST)

    assert plan.selected is Move.EAST
    assert east.path_distance == west.path_distance
    assert east.mobility > west.mobility


def test_thief_uses_confirmed_cop_position_to_avoid_repeated_corner_capture():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(6, 0),
        _belief_at(board, Position(0, 0)),
        known_opponent_position=Position(4, 1),
    )

    assert plan.selected in (Move.NORTH, Move.EAST)
    assert Move.STAY not in plan.allowed_moves


def test_thief_does_not_invent_an_illegal_move_then_barrier_capture_range():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(3, 6),
        _belief_at(board, Position(0, 0)),
        known_opponent_position=Position(3, 3),
    )

    west = next(item for item in plan.evaluations if item.move is Move.WEST)
    assert west.destination == Position(3, 5)
    assert west.proximity_risk == 0.0

    no_barrier_board = Board(BoardConfig(grid_size=7, max_barriers=0))
    no_barrier_plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        no_barrier_board,
        Position(3, 6),
        _belief_at(no_barrier_board, Position(0, 0)),
        known_opponent_position=Position(3, 3),
    )
    no_barrier_west = next(
        item for item in no_barrier_plan.evaluations if item.move is Move.WEST
    )
    assert no_barrier_west.proximity_risk == west.proximity_risk


def test_thief_treats_belief_proximity_as_a_hard_constraint():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(1, 6),
        _belief_at(board, Position(2, 5)),
    )

    # WEST, SOUTH, and STAY are within the Police's one-action capture
    # footprint. NORTH is the sole destination at a safe graph distance.
    assert Move.WEST not in plan.allowed_moves
    assert Move.SOUTH not in plan.allowed_moves
    assert plan.allowed_moves == (Move.STAY,)
    assert plan.selected is Move.STAY


def test_public_barrier_evidence_breaks_recorded_step_11_capture_route():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    barrier_target = Position(5, 5)
    plausible_cop_positions = (
        barrier_target,
        *board.neighbors(barrier_target),
    )
    board.apply_declared_barrier(barrier_target)

    plan = TacticalPlanner(AgentRole.THIEF, strategy_seed=2).evaluate(
        board,
        Position(6, 4),
        _belief_at(board, Position(0, 0)),
        plausible_opponent_positions=plausible_cop_positions,
    )

    # In the recorded loss, NORTH entered the cop's actual cell (5,4), and
    # EAST was another plausible cop cell.  WEST is the safe escape corridor.
    assert Move.NORTH not in plan.allowed_moves
    assert Move.EAST not in plan.allowed_moves
    assert plan.selected is Move.WEST
