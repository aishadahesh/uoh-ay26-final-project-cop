"""Unit tests for BrainBase/ManhattanHeuristicBrain and config-driven loading."""

import pytest

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.heuristics import manhattan_distance
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.strategy.brain_base import BrainBase
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.shared.config import ConfigError, load_strategy_class
from police_thief.shared.constants import AgentRole


def test_brain_base_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BrainBase()  # type: ignore[abstract]


def test_brain_base_default_pick_move_is_none():
    class MinimalBrain(BrainBase):
        def _decide_move(self, board, own, belief):
            return None

    brain = MinimalBrain()
    assert brain._pick_move(None, None, None) is None


class DummyCustomBrain(BrainBase):
    """A minimal, distinct BrainBase subclass used only to prove
    load_strategy_class actually reads and imports the configured dotted
    path, rather than always falling back to the default.
    """

    def _decide_move(self, board, own, belief):
        return None


def _belief_peaked_at(board: Board, peak: Position) -> BeliefMap:
    scent = ScentField(grid_size=board.config.grid_size, config=ScentConfig())
    scent.emit(peak)
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    return belief


def test_cop_brain_moves_toward_the_belief_peak():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    move = brain._decide_move(board, Position(0, 0), belief)
    new_pos = board.apply_move(Position(0, 0), move)
    assert manhattan_distance(new_pos, Position(5, 5)) < manhattan_distance(Position(0, 0), Position(5, 5))


def test_thief_brain_moves_away_from_the_belief_peak():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.THIEF)
    move = brain._decide_move(board, Position(4, 4), belief)
    new_pos = board.apply_move(Position(4, 4), move)
    assert manhattan_distance(new_pos, Position(5, 5)) > manhattan_distance(Position(4, 4), Position(5, 5))


def test_cop_brain_declines_to_place_a_barrier_in_fully_open_space():
    """Enhancement over an earlier nearest-to-belief-peak version: blocking
    any cell in wide-open space merely removes that one cell from the
    board (no genuine chokepoint), so the heuristic now conserves its
    budget instead of spending one every single turn regardless of
    usefulness (docs/TODO.md T0256)."""
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(0, 0))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    assert brain._pick_move(board, Position(3, 3), belief) is None
    assert board.remaining_barrier_budget == 14


def test_cop_brain_seals_its_own_cell_as_the_sole_doorway_into_a_pocket():
    """The core of the reachable-area enhancement: once the cop's own
    current cell is the only remaining connection between a pocket (where
    the thief is believed to be) and the rest of the board, blocking it --
    legal per Sec. 3.3.4, the cop's own cell -- disconnects the whole
    pocket, a real cornering move the old nearest-to-target heuristic had
    no way to recognize (it never even considered the cop's own cell)."""
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    # Wall off the {(0,0), (0,1), (1,0)} pocket everywhere except through
    # the cop's own current cell, (1,1).
    board.place_barrier(Position(0, 2), Position(0, 2))
    board.place_barrier(Position(2, 0), Position(2, 0))
    belief = _belief_peaked_at(board, Position(0, 0))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    target = brain._pick_move(board, Position(1, 1), belief)
    assert target == Position(1, 1)


def test_cop_brain_declines_to_place_a_barrier_once_budget_exhausted():
    board = Board(BoardConfig(grid_size=7, max_barriers=0))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    assert brain._pick_move(board, Position(0, 0), belief) is None


def test_cop_brain_excludes_already_blocked_neighbors_from_barrier_target():
    """Real bug found empirically while wiring this into a live network
    match: without this filter, the heuristic kept re-targeting the same
    already-blocked cell every turn, wasting the entire barrier budget on
    placements Board.place_barrier now rejects outright as redundant."""
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    only_neighbor_toward_target = min(
        board.neighbors(Position(0, 0)),
        key=lambda n: manhattan_distance(n, Position(5, 5)),
    )
    board.place_barrier(Position(0, 0), only_neighbor_toward_target)
    target = brain._pick_move(board, Position(0, 0), belief)
    assert target != only_neighbor_toward_target
    assert target in board.neighbors(Position(0, 0))
    assert not board.is_blocked(target)


def test_thief_brain_never_places_a_barrier():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.THIEF)
    assert brain._pick_move(board, Position(4, 4), belief) is None


def test_cop_brain_pick_move_handles_a_cell_with_no_orthogonal_neighbors():
    """Defensive-only branch: unreachable via the config loader (which
    enforces grid_size >= 7), but a 1x1 board constructed directly bypasses
    that floor -- proving _pick_move degrades to None rather than crashing.
    """
    board = Board(BoardConfig(grid_size=1, max_barriers=14))
    belief = _belief_peaked_at(board, Position(0, 0))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    assert brain._pick_move(board, Position(0, 0), belief) is None


def test_load_strategy_class_raises_on_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="missing per-peer config file"):
        load_strategy_class(AgentRole.COP, tmp_path)


def test_load_strategy_class_defaults_to_manhattan_brain_when_unset(tmp_path):
    _write_toml(tmp_path, AgentRole.COP, "[network]\nmy_port=1\nopponent_url='x'\n")
    cls = load_strategy_class(AgentRole.COP, tmp_path)
    assert cls is ManhattanHeuristicBrain


def test_load_strategy_class_loads_a_custom_class_distinct_from_the_default(tmp_path):
    """Points at DummyCustomBrain (this test module), not ManhattanHeuristicBrain
    -- proving the config value is actually read, not just falling through to
    the same default by coincidence.
    """
    _write_toml(
        tmp_path,
        AgentRole.COP,
        "[strategy]\ncop_class = 'tests.unit.test_strategy:DummyCustomBrain'\n",
    )
    cls = load_strategy_class(AgentRole.COP, tmp_path)
    assert cls is DummyCustomBrain
    assert cls is not ManhattanHeuristicBrain


def test_load_strategy_class_never_reads_the_other_roles_key(tmp_path):
    """Only cop_class is read for role=COP, even if thief_class is also present."""
    _write_toml(
        tmp_path,
        AgentRole.COP,
        "[strategy]\nthief_class = 'nonexistent.module:Nope'\n",
    )
    cls = load_strategy_class(AgentRole.COP, tmp_path)
    assert cls is ManhattanHeuristicBrain  # falls back; thief_class is irrelevant to the cop


def test_load_strategy_class_rejects_malformed_dotted_path(tmp_path):
    _write_toml(tmp_path, AgentRole.COP, "[strategy]\ncop_class = 'not-a-valid-path'\n")
    with pytest.raises(ConfigError, match="module:Class"):
        load_strategy_class(AgentRole.COP, tmp_path)


def test_load_strategy_class_rejects_a_class_that_is_not_a_brain(tmp_path):
    _write_toml(tmp_path, AgentRole.COP, "[strategy]\ncop_class = 'police_thief.domain.board:Position'\n")
    with pytest.raises(ConfigError, match="not a BrainBase subclass"):
        load_strategy_class(AgentRole.COP, tmp_path)


def _write_toml(tmp_path, role: AgentRole, content: str) -> None:
    role_dir = tmp_path / role.value
    role_dir.mkdir(parents=True, exist_ok=True)
    (role_dir / "game.toml").write_text(content, encoding="utf-8")
