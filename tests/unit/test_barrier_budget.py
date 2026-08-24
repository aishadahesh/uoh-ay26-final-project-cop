"""When a barrier turn is spent at all: role, open space, budget exhaustion,
and evidence too weak to justify one.

Split by theme out of the original `test_network_match_barrier.py`."""


from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.shared.constants import AgentRole
from tests.unit.barrier_helpers import (
    _belief_peaked_at,
    _noop_emit,
    _runner,
)


def test_maybe_place_barrier_returns_none_for_thief():
    runner = _runner(AgentRole.THIEF)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.THIEF)
    result = runner._maybe_place_barrier(board, Position(4, 4), belief, brain, _noop_emit, step=1)
    assert result is None
    assert board.remaining_barrier_budget == 14


def test_maybe_place_barrier_declines_in_fully_open_space():
    """The reachable-area heuristic conserves the budget until a
    candidate actually shrinks the thief's escape space by more than
    itself -- never true in wide-open space (docs/TODO.md T0256)."""
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    result = runner._maybe_place_barrier(board, Position(0, 0), belief, brain, _noop_emit, step=1)
    assert result is None
    assert board.remaining_barrier_budget == 14


def test_maybe_place_barrier_places_and_returns_the_target_for_cop():
    """A genuine chokepoint scenario: the cop's own current cell, (1, 1),
    is the sole doorway into the pocket the thief is believed to be in."""
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.place_barrier(Position(0, 2), Position(0, 2))
    board.place_barrier(Position(2, 0), Position(2, 0))
    belief = _belief_peaked_at(board, Position(0, 0))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    result = runner._maybe_place_barrier(board, Position(1, 1), belief, brain, _noop_emit, step=1)
    assert result == [1, 1]
    assert board.is_blocked(Position(1, 1))
    assert board.remaining_barrier_budget == 11


def test_maybe_place_barrier_returns_none_once_budget_exhausted():
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=0))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    result = runner._maybe_place_barrier(board, Position(0, 0), belief, brain, _noop_emit, step=1)
    assert result is None


def test_adjacent_belief_peak_alone_does_not_spend_a_barrier_turn():
    """G005 regression: belief remains useful for pursuit, not certainty."""
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(3, 4))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)

    result = runner._maybe_place_barrier(
        board,
        Position(3, 3),
        belief,
        brain,
        _noop_emit,
        step=20,
        public_thief_candidates=(),
    )

    assert result is None
    assert board.remaining_barrier_budget == 14


def test_diffuse_public_candidates_do_not_spend_a_barrier():
    """A small set alone is insufficient when no target constrains the set."""
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(0, 0))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)

    result = runner._maybe_place_barrier(
        board,
        Position(3, 3),
        belief,
        brain,
        _noop_emit,
        step=10,
        public_thief_candidates=(Position(0, 0), Position(0, 6)),
    )

    assert result is None
    assert board.remaining_barrier_budget == 14
