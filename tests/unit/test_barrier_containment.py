"""Walling in a cornered or singleton public candidate, and refusing to do so
when the wall would seal the cop instead.

Split by theme out of the original `test_network_match_barrier.py`."""


from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.shared.constants import AgentRole
from tests.unit.barrier_helpers import (
    _belief_peaked_at,
    _noop_emit,
    _runner,
)


def test_cornered_adjacent_public_candidate_is_walled():
    """The reviewed live-match endgame: the thief oscillates between (0, 0)
    and (1, 0) while the adjacent cop never spends a barrier.  With the
    fresh public scent candidate on the cornered cell (two exits at most),
    the cop must wall it -- a capture claim if the thief is still there, a
    sealed pocket if it slipped to the corner."""
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(1, 0))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    result = runner._maybe_place_barrier(
        board,
        Position(1, 1),
        belief,
        brain,
        _noop_emit,
        step=30,
        public_thief_candidates=(Position(1, 0),),
    )
    assert result == [1, 0]
    assert board.is_blocked(Position(1, 0))


def test_adjacent_singleton_public_candidate_is_challenged_in_open_space():
    """Fresh focused evidence must close a distance-one chase.

    Pure movement lets an equally fast thief remain one cell ahead forever.
    A legal barrier on the adjacent candidate both issues a capture challenge
    and permanently removes that escape cell if the inference was stale.
    """
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    result = runner._maybe_place_barrier(
        board,
        Position(3, 3),
        belief,
        brain,
        _noop_emit,
        step=10,
        public_thief_candidates=(Position(3, 4),),
    )
    assert result == [3, 4]
    assert board.is_blocked(Position(3, 4))
    assert board.remaining_barrier_budget == 13


def test_saturated_boundary_candidates_get_a_multi_cell_containment_barrier():
    """Regression for the G003 Police losses.

    The capped public scent can truthfully narrow the Thief only to a small
    cluster.  The old singleton-only closer ignored this evidence and followed
    the Thief around the boundary at distance one.  Blocking (6,5) both
    challenges one candidate and removes an escape edge from (6,4)/(6,6).
    """
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(6, 6))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)

    result = runner._maybe_place_barrier(
        board,
        Position(5, 5),
        belief,
        brain,
        _noop_emit,
        step=11,
        public_thief_candidates=(
            Position(5, 5),
            Position(6, 4),
            Position(6, 5),
            Position(6, 6),
        ),
    )

    assert result == [6, 5]
    assert board.is_blocked(Position(6, 5))
    assert (
        len(
            [
                neighbor
                for neighbor in board.neighbors(Position(5, 5))
                if not board.is_blocked(neighbor)
            ]
        )
        >= 2
    )


def test_moving_fresh_singleton_still_gets_capture_challenge():
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
        step=10,
        public_thief_candidates=(Position(3, 4),),
        candidates_are_moving=True,
    )

    assert result == [3, 4]
    assert board.is_blocked(Position(3, 4))


def test_cornered_candidate_is_not_walled_when_it_would_seal_the_cop():
    """The cop keeps at least two escapes of its own: with only two open
    neighbors left, walling the candidate would repeat the reviewed G001
    self-boxing failure, so the rule must decline."""
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.place_barrier(Position(0, 1), Position(0, 1))
    board.place_barrier(Position(2, 1), Position(2, 1))
    belief = _belief_peaked_at(board, Position(1, 0))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    result = runner._maybe_place_barrier(
        board,
        Position(1, 1),
        belief,
        brain,
        _noop_emit,
        step=30,
        public_thief_candidates=(Position(1, 0),),
    )
    assert result is None
    assert not board.is_blocked(Position(1, 0))
