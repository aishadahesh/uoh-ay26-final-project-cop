"""Shared helper for the tactical-planner test modules.

Extracted when `test_tactical_planner.py` was split by theme."""

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Position


def _belief_at(board: Board, target: Position) -> BeliefMap:
    belief = BeliefMap(board)
    belief._belief = {position: float(position == target) for position in belief._belief}
    return belief
