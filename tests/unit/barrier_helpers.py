"""Shared fixtures for the barrier-placement test modules.

Extracted when `test_network_match_barrier.py` was split by theme."""

from pathlib import Path

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Position
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import (
    NetworkMatchRunner,
    NetworkMatchSettings,
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
