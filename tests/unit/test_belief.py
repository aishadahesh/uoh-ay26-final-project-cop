"""Unit tests for the Bayesian-style belief map (Chapter 6)."""

import pytest

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.scent import ScentConfig, ScentField


@pytest.fixture
def board() -> Board:
    return Board(BoardConfig(grid_size=7, max_barriers=14))


def test_uniform_prior_sums_to_one(board):
    belief = BeliefMap(board)
    assert sum(belief._belief.values()) == pytest.approx(1.0)


def test_uniform_prior_is_equal_across_all_open_cells(board):
    belief = BeliefMap(board)
    values = set(belief._belief.values())
    assert len(values) == 1


def test_public_known_position_can_seed_a_certain_belief(board):
    belief = BeliefMap(board)
    known = Position(3, 3)

    belief.set_certain_position(known)

    assert belief.arg_max() == known
    assert belief.belief_at(known) == 1.0
    assert sum(belief._belief.values()) == pytest.approx(1.0)


def test_certain_belief_rejects_an_illegal_cell(board):
    board.apply_declared_barrier(Position(3, 3))
    belief = BeliefMap(board)

    with pytest.raises(ValueError, match="illegal cell"):
        belief.set_certain_position(Position(3, 3))


def test_blocked_cell_always_has_zero_belief(board):
    board.place_barrier(Position(3, 3), Position(2, 3))
    belief = BeliefMap(board)
    assert belief.belief_at(Position(2, 3)) == 0.0


def test_blocked_cell_is_excluded_from_the_tracked_distribution(board):
    board.place_barrier(Position(3, 3), Position(2, 3))
    belief = BeliefMap(board)
    assert len(belief._belief) == 48


def test_update_from_scent_raises_belief_near_the_emission_center(board):
    scent = ScentField(grid_size=7, config=ScentConfig())
    scent.emit(Position(5, 5))
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    assert belief.belief_at(Position(5, 5)) > belief.belief_at(Position(0, 0))


def test_update_from_scent_stays_normalized(board):
    scent = ScentField(grid_size=7, config=ScentConfig())
    scent.emit(Position(5, 5))
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    assert sum(belief._belief.values()) == pytest.approx(1.0)


def test_arg_max_finds_the_emission_center():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    scent = ScentField(grid_size=7, config=ScentConfig())
    scent.emit(Position(5, 5))
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    assert belief.arg_max() == Position(5, 5)


def test_repeated_updates_with_no_new_evidence_keep_the_peak_stable(board):
    scent = ScentField(grid_size=7, config=ScentConfig())
    scent.emit(Position(5, 5))
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    peak_after_one = belief.arg_max()
    scent.decay()
    belief.update_from_scent(scent)
    assert belief.arg_max() == peak_after_one


def test_update_from_scent_does_not_crash_when_every_cell_is_blocked():
    """Degenerate edge case (a real match could never start with zero open
    cells -- start positions must be legal), but update_from_scent should
    still degrade gracefully rather than raising a ZeroDivisionError.
    """
    board = Board(BoardConfig(grid_size=2, max_barriers=10))
    for row in range(2):
        for col in range(2):
            pos = Position(row, col)
            if not board.is_blocked(pos):
                board.place_barrier(pos, pos)
    belief = BeliefMap(board)
    assert belief._belief == {}
    scent = ScentField(grid_size=2, config=ScentConfig())
    belief.update_from_scent(scent)  # must not raise
    assert belief._belief == {}


def test_blocked_cell_never_becomes_the_peak_even_with_scent_there():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.place_barrier(Position(5, 4), Position(5, 5))
    scent = ScentField(grid_size=7, config=ScentConfig())
    scent.emit(Position(5, 5))  # scent still physically emits there
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    assert belief.arg_max() != Position(5, 5)
