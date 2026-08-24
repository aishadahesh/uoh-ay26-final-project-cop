"""Cop-side planning: routing around blockages, public-evidence pursuit,
interception and containment.

Split by theme out of the original `test_tactical_planner.py`."""

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.shared.constants import AgentRole
from tests.unit.tactical_planner_helpers import (
    _belief_at,
)


def test_cop_uses_an_alternative_path_when_direct_route_is_blocked():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.place_barrier(Position(0, 0), Position(0, 1))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), _belief_at(board, Position(0, 4))
    )
    assert plan.selected is Move.SOUTH
    assert plan.selected in plan.allowed_moves


def test_four_candidate_public_set_activates_interception_and_containment():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    candidates = (
        Position(4, 4),
        Position(4, 5),
        Position(5, 4),
        Position(5, 5),
    )
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(0, 0),
        BeliefMap(board),
        plausible_opponent_positions=candidates,
    )

    assert any(item.intercept_distance > 0.0 for item in plan.evaluations)
    assert any(item.containment > 0.0 for item in plan.evaluations)
    assert any(item.escape_routes > 0.0 for item in plan.evaluations)


def test_cop_interception_scores_each_destination_against_full_escape_frontier():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    target = Position(6, 3)
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(4, 3),
        BeliefMap(board),
        plausible_opponent_positions=(target,),
    )

    south = next(item for item in plan.evaluations if item.move is Move.SOUTH)
    east = next(item for item in plan.evaluations if item.move is Move.EAST)

    assert south.intercept_distance < east.intercept_distance
    assert south.escape_routes < east.escape_routes
    assert plan.selected is Move.SOUTH


def test_diffuse_belief_does_not_activate_public_evidence_pursuit_terms():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), BeliefMap(board),
    )

    assert all(item.intercept_distance == 0.0 for item in plan.evaluations)
    assert all(item.containment == 0.0 for item in plan.evaluations)


def test_cop_never_stays_while_a_search_move_is_available():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), _belief_at(board, Position(0, 0))
    )

    assert Move.STAY not in plan.allowed_moves
    assert plan.selected is not Move.STAY


def test_cop_captures_the_recorded_game_one_path_without_stalling():
    class ZeroScent:
        @staticmethod
        def intensity_at(_position):
            return 0.0

    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = BeliefMap(board)
    belief.set_certain_position(Position(3, 3))
    planner = TacticalPlanner(AgentRole.COP, strategy_seed=1)
    cop = Position(0, 0)
    thief = Position(3, 3)
    thief_moves = (
        Move.EAST,
        Move.EAST,
        Move.SOUTH,
        Move.EAST,
        Move.SOUTH,
        *(Move.STAY for _ in range(19)),
        Move.NORTH,
        Move.SOUTH,
        Move.STAY,
        Move.STAY,
        Move.WEST,
        Move.WEST,
        Move.NORTH,
        Move.STAY,
    )
    cop_moves: list[Move] = []

    for thief_move in thief_moves:
        thief = board.apply_move(thief, thief_move)
        belief.update_from_scent(ZeroScent())
        plan = planner.evaluate(board, cop, belief)
        before = cop
        cop = board.apply_move(cop, plan.selected)
        planner.record_move(before, plan.selected, cop)
        cop_moves.append(plan.selected)
        if cop == thief:
            break

    assert cop == thief == Position(4, 4)
    assert len(cop_moves) == 32
    assert Move.STAY not in cop_moves
