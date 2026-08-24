"""Inferring the opponent's cell from the public scent field alone.

Split by theme out of the original `test_capture_safety.py`."""


from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.services.network_match import (
    NetworkMatchRunner,
    _infer_public_scent_candidates,
    _infer_public_scent_center,
)
from tests.unit.capture_safety_helpers import (
    _opponent_capped_step,
)


def test_fresh_scent_innovation_tracks_recorded_cop_path_not_old_trail():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    scent = ScentField(7, ScentConfig())
    previous_grid: dict[str, float] = {}
    previous_position = Position(0, 0)
    path = (
        Position(1, 0), Position(2, 0), Position(3, 0), Position(4, 0),
        Position(5, 0), Position(5, 1), Position(6, 1), Position(5, 1),
        Position(5, 2), Position(5, 3), Position(5, 4), Position(5, 4),
        Position(4, 4), Position(4, 4), Position(3, 4), Position(2, 4),
        Position(2, 5),
    )

    for current_position in path:
        scent.decay()
        scent.emit(current_position)
        current_grid = NetworkMatchRunner._scent_snapshot(scent, 7)
        inferred = _infer_public_scent_center(
            board,
            previous_grid,
            current_grid,
            decay_rate=0.10,
            min_center_intensity=0.5,
            previous_position=previous_position,
        )
        assert inferred == current_position
        previous_grid = current_grid
        previous_position = current_position


def test_capped_opponent_step_onto_own_trail_yields_a_set_with_the_true_center():
    """One ordinary step inside the opponent's own kernel: the cap clips the
    center innovation to ~0.34 (< min_center 0.5), so the singleton stage is
    blind, but the fallback set must stay small and contain the true cell."""
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    previous_grid = _opponent_capped_step({}, Position(3, 3))
    current_grid = _opponent_capped_step(previous_grid, Position(3, 4))
    candidates = _infer_public_scent_candidates(
        board, previous_grid, current_grid,
        decay_rate=0.10, min_center_intensity=0.5, emission_cap=0.9,
        previous_positions=(Position(3, 3),),
    )
    assert candidates
    assert len(candidates) <= 4
    assert Position(3, 4) in candidates


def test_saturated_oscillation_tracks_the_true_cell_across_consecutive_turns():
    """The reviewed loss: the thief oscillates (6,6)<->(5,6) while the whole
    neighborhood saturates at the 0.9 cap.  The singleton inference reads an
    innovation of ~0.09 and goes blind; the cap-aware fallback must still
    pin the thief to a small set around the last anchor."""
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    grid: dict[str, float] = {}
    spots = (Position(6, 6), Position(5, 6))
    for turn in range(8):
        grid = _opponent_capped_step(grid, spots[turn % 2])
    first_center = spots[8 % 2]  # (6,6)
    first_grid = _opponent_capped_step(grid, first_center)

    singleton = _infer_public_scent_center(
        board, grid, first_grid,
        decay_rate=0.10, min_center_intensity=0.5,
        previous_position=spots[7 % 2],
    )
    assert singleton is None

    previous_grid = grid
    anchors = (spots[7 % 2],)
    for turn in range(8, 14):
        current_center = spots[turn % 2]
        current_grid = _opponent_capped_step(previous_grid, current_center)
        candidates = _infer_public_scent_candidates(
            board, previous_grid, current_grid,
            decay_rate=0.10, min_center_intensity=0.5, emission_cap=0.9,
            previous_positions=anchors, max_ambiguity=8,
        )
        assert candidates, f"candidate tracking failed at turn {turn}"
        assert len(candidates) <= 8
        assert current_center in candidates
        anchors = candidates
        previous_grid = current_grid


def test_default_saturated_scent_tracking_keeps_bounded_candidates():
    """The live policy retains a bounded capped-field support.

    A 5x5 capped field can yield more than eight reachable cells while the
    agent crosses its own trail. Discarding them made a trail cell look exact.
    """
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    grid: dict[str, float] = {}
    spots = (Position(6, 6), Position(5, 6))
    for turn in range(8):
        grid = _opponent_capped_step(grid, spots[turn % 2])
    anchors = (spots[7 % 2],)

    for turn in range(8, 14):
        center = spots[turn % 2]
        current = _opponent_capped_step(grid, center)
        candidates = _infer_public_scent_candidates(
            board, grid, current,
            decay_rate=0.10, min_center_intensity=0.5, emission_cap=0.9,
            previous_positions=anchors,
        )
        assert candidates
        assert len(candidates) <= 16
        assert center in candidates
        anchors, grid = candidates, current


def test_capped_g005_route_never_promotes_a_trail_cell_over_true_center():
    """Regression for both G005 Cop losses against sharNamr's capped field."""
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    grid: dict[str, float] = {}
    anchors = (Position(3, 3),)
    route = (
        Position(4, 3), Position(5, 3), Position(5, 4), Position(5, 5),
        Position(6, 5), Position(5, 5), Position(6, 5), Position(5, 5),
        Position(6, 5), Position(6, 4), Position(6, 3), Position(6, 2),
        Position(6, 1), Position(5, 1), Position(4, 1), Position(3, 1),
        Position(2, 1), Position(1, 1), Position(1, 2), Position(1, 3),
        Position(1, 4), Position(1, 5), Position(0, 5), Position(1, 5),
        Position(2, 5), Position(3, 5), Position(4, 5), Position(5, 5),
        Position(6, 5), Position(5, 5), Position(5, 4), Position(5, 5),
        Position(6, 5), Position(6, 6),
    )

    for step, center in enumerate(route, 1):
        current = _opponent_capped_step(grid, center)
        candidates = _infer_public_scent_candidates(
            board,
            grid,
            current,
            decay_rate=0.10,
            min_center_intensity=0.5,
            emission_cap=0.9,
            previous_positions=anchors,
        )
        assert center in candidates, f"lost true center at G005 step {step}"
        anchors, grid = candidates, current


def test_saturated_scent_without_an_anchor_stays_silent():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    grid: dict[str, float] = {}
    for turn in range(8):
        grid = _opponent_capped_step(grid, Position(6, 6) if turn % 2 else Position(5, 6))
    current_grid = _opponent_capped_step(grid, Position(5, 6))
    candidates = _infer_public_scent_candidates(
        board, grid, current_grid,
        decay_rate=0.10, min_center_intensity=0.5, emission_cap=0.9,
        previous_positions=(),
    )
    assert candidates == ()
