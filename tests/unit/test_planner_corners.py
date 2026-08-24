"""Corner and boundary discipline: keeping interior escape options alive
rather than being sealed against an edge.

Split by theme out of the original `test_tactical_planner.py`."""

from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.shared.constants import AgentRole
from tests.unit.tactical_planner_helpers import (
    _belief_at,
)


def test_thief_avoids_deeper_boundary_cells_before_police_can_seal_corner():
    """Regression for G003 g02/g04/g06.

    At (1,5) with the Police publicly known at (2,4), NORTH and EAST are
    immediately safe but both enter boundary corridors. WEST/SOUTH are in the
    Police capture footprint. The planner must refuse both moves that go
    deeper into the top/right boundary and retain the least restrictive safe
    tier instead of voluntarily entering a corner that two barriers can seal.
    """
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    cop = Position(2, 4)
    plan = TacticalPlanner(AgentRole.THIEF, strategy_seed=2).evaluate(
        board,
        Position(1, 5),
        _belief_at(board, cop),
        known_opponent_position=cop,
    )

    assert Move.NORTH not in plan.allowed_moves
    assert Move.EAST not in plan.allowed_moves
    assert plan.selected is Move.STAY


def test_thief_does_not_enter_corner_when_no_interior_escape_exists():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    cop = Position(1, 4)
    plan = TacticalPlanner(AgentRole.THIEF, strategy_seed=2).evaluate(
        board,
        Position(0, 5),
        _belief_at(board, cop),
        known_opponent_position=cop,
    )

    assert plan.selected is Move.STAY
    assert Move.EAST not in plan.allowed_moves
