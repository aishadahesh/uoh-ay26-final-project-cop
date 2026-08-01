"""Unit tests for board geometry, movement, and barrier placement (Chapter 3)."""

import pytest

from police_thief.domain.board import Board, BoardConfig, Move, MoveRejectedError, Position


@pytest.fixture
def board() -> Board:
    return Board(BoardConfig(grid_size=7, max_barriers=14))


def test_default_grid_size_matches_mandatory_minimum():
    assert BoardConfig().grid_size == 7


def test_default_max_barriers_matches_mandatory_minimum():
    assert BoardConfig().max_barriers == 14


def test_is_within_bounds_true_for_origin_and_far_corner(board):
    assert board.is_within_bounds(Position(0, 0))
    assert board.is_within_bounds(Position(6, 6))


@pytest.mark.parametrize("pos", [Position(-1, 0), Position(0, -1), Position(7, 0), Position(0, 7)])
def test_is_within_bounds_false_outside_grid(board, pos):
    assert not board.is_within_bounds(pos)


def test_neighbors_returns_four_orthogonal_cells_in_open_space(board):
    neighbors = board.neighbors(Position(3, 3))
    assert set(neighbors) == {Position(2, 3), Position(4, 3), Position(3, 2), Position(3, 4)}


def test_neighbors_excludes_out_of_bounds_cells_at_corner(board):
    neighbors = board.neighbors(Position(0, 0))
    assert set(neighbors) == {Position(1, 0), Position(0, 1)}


def test_neighbors_never_returns_diagonal_cells(board):
    for neighbor in board.neighbors(Position(3, 3)):
        assert neighbor.row == 3 or neighbor.col == 3


@pytest.mark.parametrize(
    ("move", "expected"),
    [
        (Move.NORTH, Position(2, 3)),
        (Move.SOUTH, Position(4, 3)),
        (Move.EAST, Position(3, 4)),
        (Move.WEST, Position(3, 2)),
        (Move.STAY, Position(3, 3)),
    ],
)
def test_apply_move_moves_exactly_one_cell_in_the_right_direction(board, move, expected):
    assert board.apply_move(Position(3, 3), move) == expected


def test_apply_move_rejects_leaving_the_board(board):
    with pytest.raises(MoveRejectedError):
        board.apply_move(Position(0, 0), Move.NORTH)


def test_apply_move_rejects_entering_a_blocked_cell(board):
    board.place_barrier(Position(3, 3), Position(2, 3))
    with pytest.raises(MoveRejectedError):
        board.apply_move(Position(3, 3), Move.NORTH)


def test_apply_move_rejects_non_move_input(board):
    with pytest.raises(MoveRejectedError):
        board.apply_move(Position(3, 3), "NE")  # type: ignore[arg-type]


def test_stay_always_succeeds_even_on_a_barrier_the_agent_itself_placed(board):
    """A cop may legally barrier its own cell; STAY there must still work (Sec. 3.3.4)."""
    board.place_barrier(Position(3, 3), Position(3, 3))
    assert board.apply_move(Position(3, 3), Move.STAY) == Position(3, 3)


def test_place_barrier_on_own_cell_is_allowed(board):
    board.place_barrier(Position(3, 3), Position(3, 3))
    assert board.is_blocked(Position(3, 3))


def test_place_barrier_on_adjacent_cell_is_allowed(board):
    board.place_barrier(Position(3, 3), Position(2, 3))
    assert board.is_blocked(Position(2, 3))


def test_place_barrier_rejects_non_adjacent_target(board):
    with pytest.raises(MoveRejectedError):
        board.place_barrier(Position(3, 3), Position(0, 0))


def test_place_barrier_decrements_remaining_budget(board):
    assert board.remaining_barrier_budget == 14
    board.place_barrier(Position(3, 3), Position(2, 3))
    assert board.remaining_barrier_budget == 13


def test_place_barrier_fails_once_budget_exhausted():
    board = Board(BoardConfig(grid_size=7, max_barriers=1))
    board.place_barrier(Position(3, 3), Position(2, 3))
    with pytest.raises(MoveRejectedError, match="budget exhausted"):
        board.place_barrier(Position(3, 3), Position(3, 2))


def test_place_barrier_rejects_an_already_blocked_target(board):
    """Real bug found empirically: a heuristic that keeps re-targeting the
    same already-blocked cell must not be allowed to silently waste budget
    on a no-op (docs/tasks.md Sec. 3.3.7)."""
    board.place_barrier(Position(3, 3), Position(2, 3))
    with pytest.raises(MoveRejectedError, match="already blocked"):
        board.place_barrier(Position(3, 3), Position(2, 3))
    assert board.remaining_barrier_budget == 13


def test_barrier_is_permanent_for_the_rest_of_the_match(board):
    board.place_barrier(Position(3, 3), Position(2, 3))
    assert board.is_blocked(Position(2, 3))
    # No API exists to unblock it -- the only assertion possible is that it
    # stays blocked no matter how many times we check.
    assert board.is_blocked(Position(2, 3))


def test_legal_moves_in_open_space_includes_all_five_moves(board):
    legal = board.legal_moves(Position(3, 3))
    assert set(legal) == {Move.NORTH, Move.SOUTH, Move.EAST, Move.WEST, Move.STAY}
    assert legal[Move.NORTH] == Position(2, 3)
    assert legal[Move.STAY] == Position(3, 3)


def test_legal_moves_at_a_corner_excludes_off_board_directions(board):
    legal = board.legal_moves(Position(0, 0))
    assert set(legal) == {Move.SOUTH, Move.EAST, Move.STAY}


def test_legal_moves_excludes_a_blocked_neighbor(board):
    board.place_barrier(Position(3, 3), Position(2, 3))
    legal = board.legal_moves(Position(3, 3))
    assert Move.NORTH not in legal
    assert set(legal) == {Move.SOUTH, Move.EAST, Move.WEST, Move.STAY}


def test_legal_moves_always_includes_stay_even_when_fully_boxed_in(board):
    for neighbor in board.neighbors(Position(3, 3)):
        board.place_barrier(Position(3, 3), neighbor)
    legal = board.legal_moves(Position(3, 3))
    assert set(legal) == {Move.STAY}


def test_apply_declared_barrier_blocks_the_cell(board):
    board.apply_declared_barrier(Position(2, 2))
    assert board.is_blocked(Position(2, 2))


def test_apply_declared_barrier_decrements_remaining_budget(board):
    assert board.remaining_barrier_budget == 14
    board.apply_declared_barrier(Position(2, 2))
    assert board.remaining_barrier_budget == 13


def test_apply_declared_barrier_does_not_validate_adjacency(board):
    """Unlike place_barrier, this trusts the declaration -- the receiving
    peer has no cop_pos of its own to validate against (Sec. 3.3.6: barrier
    declarations are public/plaintext, never re-verified live)."""
    board.apply_declared_barrier(Position(6, 6))  # nowhere near anything -- must not raise
    assert board.is_blocked(Position(6, 6))
