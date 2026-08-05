"""Focused regression tests for path planning and anti-loop behavior."""

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.shared.constants import AgentRole


def _belief_at(board: Board, target: Position) -> BeliefMap:
    belief = BeliefMap(board)
    belief._belief = {position: float(position == target) for position in belief._belief}
    return belief


def test_cop_uses_an_alternative_path_when_direct_route_is_blocked():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.place_barrier(Position(0, 0), Position(0, 1))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), _belief_at(board, Position(0, 4))
    )
    assert plan.selected is Move.SOUTH
    assert plan.selected in plan.allowed_moves


def test_detected_abab_loop_excludes_reversal_and_stay_when_alternatives_exist():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    planner = TacticalPlanner(AgentRole.COP)
    a, b = Position(0, 0), Position(0, 1)
    planner.record_move(a, Move.EAST, b)
    planner.record_move(b, Move.WEST, a)
    planner.record_move(a, Move.EAST, b)
    plan = planner.evaluate(board, b, _belief_at(board, Position(0, 6)))
    assert plan.loop_detected is True
    assert "oscillation" in plan.loop_reason
    assert Move.WEST in plan.excluded_moves
    assert Move.STAY in plan.excluded_moves
    assert plan.selected not in (Move.WEST, Move.STAY)


def test_thief_prefers_open_escape_route_over_equal_distance_corner():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board, Position(0, 1), _belief_at(board, Position(1, 1))
    )
    assert plan.selected is Move.EAST


def test_every_currently_legal_move_receives_an_explainable_score():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    own = Position(3, 3)
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board, own, _belief_at(board, Position(1, 1))
    )
    assert {item.move for item in plan.evaluations} == set(board.legal_moves(own))
    assert all("total=" in item.summary() and "path=" in item.summary() for item in plan.evaluations)


def test_gemini_allowed_moves_exclude_materially_worse_legal_actions():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), _belief_at(board, Position(6, 6))
    )
    assert set(plan.allowed_moves) == {Move.EAST, Move.SOUTH}
    assert Move.STAY not in plan.allowed_moves


def test_subgame_seed_varies_only_equally_strong_opening_routes():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_at(board, Position(5, 5))
    first = TacticalPlanner(AgentRole.COP, strategy_seed=1).evaluate(
        board, Position(0, 0), belief
    )
    second = TacticalPlanner(AgentRole.COP, strategy_seed=2).evaluate(
        board, Position(0, 0), belief
    )
    assert {first.selected, second.selected} == {Move.EAST, Move.SOUTH}
    assert next(item for item in first.evaluations if item.move is first.selected).path_distance == next(
        item for item in second.evaluations if item.move is second.selected
    ).path_distance
