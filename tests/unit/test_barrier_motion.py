"""Distinguishing a moving candidate blob from a stationary one, so barriers
are not spent blocking a trail the thief has already left.

Split by theme out of the original `test_network_match_barrier.py`."""


from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.services.network_match import (
    _public_candidate_set_is_moving,
    _updated_candidate_stability,
)
from police_thief.shared.constants import AgentRole
from tests.unit.barrier_helpers import (
    _belief_peaked_at,
    _noop_emit,
    _runner,
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
