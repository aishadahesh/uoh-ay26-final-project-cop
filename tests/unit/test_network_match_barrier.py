"""Unit tests for NetworkMatchRunner._maybe_place_barrier (Sec. 3.3.3/3.3.6)."""

from pathlib import Path

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.shared.constants import AgentRole


def _runner(role: AgentRole) -> NetworkMatchRunner:
    settings = NetworkMatchSettings(
        role=role, local_port=8801, opponent_url="https://peer.example/mcp",
        public_url="https://local.example/mcp", game_id="UNIT-TEST", sub_game_number=1,
        shared_config=Path("config/game.json"), output_dir=Path("unused"),
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


def test_maybe_place_barrier_places_and_returns_the_target_for_cop():
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    result = runner._maybe_place_barrier(board, Position(0, 0), belief, brain, _noop_emit, step=1)
    assert result is not None
    target = Position(*result)
    assert board.is_blocked(target)
    assert board.remaining_barrier_budget == 13


def test_maybe_place_barrier_returns_none_once_budget_exhausted():
    runner = _runner(AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=0))
    belief = _belief_peaked_at(board, Position(5, 5))
    brain = ManhattanHeuristicBrain(role=AgentRole.COP)
    result = runner._maybe_place_barrier(board, Position(0, 0), belief, brain, _noop_emit, step=1)
    assert result is None
