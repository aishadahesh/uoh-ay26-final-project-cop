"""Regressions taken from real recorded matches: the thief must not replay a
route that previously got it captured.

Split by theme out of the original `test_tactical_planner.py`."""

from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.shared.constants import AgentRole
from tests.unit.tactical_planner_helpers import (
    _belief_at,
)


def test_thief_does_not_repeat_the_recorded_seven_turn_capture_route():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_at(board, Position(0, 0))
    planner = TacticalPlanner(AgentRole.THIEF, strategy_seed=2)
    thief = Position(3, 3)
    cop = Position(0, 0)
    recorded_cop_moves = (
        Move.SOUTH,
        Move.SOUTH,
        Move.EAST,
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.WEST,
    )
    selected: list[Move] = []

    for cop_move in recorded_cop_moves:
        plan = planner.evaluate(
            board,
            thief,
            belief,
            known_opponent_position=cop,
        )
        before = thief
        thief = board.apply_move(thief, plan.selected)
        planner.record_move(before, plan.selected, thief)
        selected.append(plan.selected)
        assert thief != cop

        cop = board.apply_move(cop, cop_move)
        assert thief != cop

    assert selected != [
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.WEST,
        Move.WEST,
        Move.WEST,
        Move.NORTH,
    ]


def test_thief_escapes_recorded_south_east_pursuit_using_public_scent():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_at(board, Position(0, 0))
    scent = ScentField(7, ScentConfig())
    brain = ManhattanHeuristicBrain(AgentRole.THIEF, strategy_seed=4)
    thief = Position(3, 3)
    cop = Position(0, 0)
    recorded_cop_moves = (
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.EAST,
        Move.EAST,
        Move.EAST,
        Move.EAST,
        Move.SOUTH,
    )

    for index, cop_move in enumerate(recorded_cop_moves):
        known_cop = cop if index == 0 else None
        move = brain._decide_move(
            board, thief, belief, known_opponent_position=known_cop,
        )
        before = thief
        thief = board.apply_move(thief, move)
        brain.record_move(before, move, thief)
        assert thief != cop

        cop = board.apply_move(cop, cop_move)
        assert thief != cop
        scent.decay()
        scent.emit(cop)
        belief.update_from_scent(scent)

    assert abs(thief.row - cop.row) + abs(thief.col - cop.col) >= 3
