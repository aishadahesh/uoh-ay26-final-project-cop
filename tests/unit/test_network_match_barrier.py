"""Unit tests for NetworkMatchRunner._maybe_place_barrier (Sec. 3.3.3/3.3.6)."""

from pathlib import Path

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import (
    NetworkMatchRunner,
    NetworkMatchSettings,
    _public_candidate_set_is_moving,
    _updated_candidate_stability,
)
from police_thief.shared.constants import AgentRole


def _runner(role: AgentRole) -> NetworkMatchRunner:
    settings = NetworkMatchSettings(
        role=role,
        local_port=8801,
        opponent_url="https://peer.example/mcp",
        public_url="https://local.example/mcp",
        game_id="UNIT-TEST",
        sub_game_number=1,
        shared_config=Path("config/game.json"),
        output_dir=Path("unused"),
    )
    return NetworkMatchRunner(settings, PeerInboxes(), transport=object())


def _belief_peaked_at(board: Board, peak: Position) -> BeliefMap:
    scent = ScentField(grid_size=board.config.grid_size, config=ScentConfig())
    scent.emit(peak)
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    return belief


def _noop_emit(_message: str) -> None:
    pass


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


def test_moving_ambiguous_blob_keeps_pursuing_instead_of_blocking_its_trail():
    """G004 g01 placed five barriers while the scent blob translated.

    A stable copy of the same set remains actionable (covered above), but a
    moving ambiguous set must not consume the Police movement turn.
    """
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(6, 3))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)

    result = runner._maybe_place_barrier(
        board,
        Position(5, 3),
        belief,
        brain,
        _noop_emit,
        step=13,
        public_thief_candidates=(
            Position(5, 3),
            Position(6, 2),
            Position(6, 3),
            Position(6, 4),
        ),
        candidates_are_moving=True,
    )

    assert result is None
    assert board.remaining_barrier_budget == 14


def test_public_candidate_motion_uses_only_set_translation():
    previous = (
        Position(5, 4),
        Position(6, 3),
        Position(6, 4),
        Position(6, 5),
    )
    translated_west = (
        Position(5, 3),
        Position(6, 2),
        Position(6, 3),
        Position(6, 4),
    )

    assert _public_candidate_set_is_moving(previous, translated_west) is True
    assert _public_candidate_set_is_moving(previous, previous) is False


def test_shape_change_counts_as_moving_even_when_centroid_barely_changes():
    previous = (
        Position(3, 1), Position(3, 2), Position(4, 1), Position(4, 2),
    )
    reshaped_trail = (
        Position(2, 2), Position(3, 1), Position(3, 2), Position(4, 1),
    )

    assert _public_candidate_set_is_moving(previous, reshaped_trail) is True


def test_ambiguous_support_requires_two_stable_transitions_before_barrier():
    support = (
        Position(5, 5), Position(6, 4), Position(6, 5), Position(6, 6),
    )

    first = _updated_candidate_stability(support, support, 0)
    second = _updated_candidate_stability(support, support, first)

    assert first == 1
    assert second == 2
    assert _updated_candidate_stability(
        support, support[:-1], second,
    ) == 0


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
