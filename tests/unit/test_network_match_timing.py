"""Diagnostics for deterministic network move selection."""

from pathlib import Path

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.shared.constants import AgentRole


class _Advisor:
    def __init__(self) -> None:
        self.calls = 0

    def choose_move(self, _context, _fallback):
        self.calls += 1
        raise AssertionError("live network strategy must not call Gemini")


def _runner(advisor: _Advisor) -> NetworkMatchRunner:
    settings = NetworkMatchSettings(
        role=AgentRole.COP,
        local_port=8801,
        opponent_url="https://peer.example/mcp",
        public_url="https://local.example/mcp",
        game_id="TIMING-TEST",
        sub_game_number=1,
        shared_config=Path("config/game.json"),
        output_dir=Path("unused"),
    )
    return NetworkMatchRunner(
        settings,
        PeerInboxes(),
        gemini_advisor=advisor,
        transport=object(),
    )


def test_move_selection_uses_brain_fallback_without_gemini(monkeypatch):
    advisor = _Advisor()
    runner = _runner(advisor)
    board = Board(BoardConfig())
    belief = BeliefMap(board)
    messages: list[str] = []
    timestamps = iter((10.0, 11.2))
    monkeypatch.setattr(
        "police_thief.services.network_match.time.monotonic",
        lambda: next(timestamps),
    )

    move, _reason = runner._choose_move(
        board,
        belief,
        Position(0, 0),
        Move.EAST,
        step=3,
        max_steps=35,
        emit=messages.append,
    )

    assert move is Move.EAST
    assert advisor.calls == 0
    assert messages == ["Step 3: planner selected EAST (E); valid=True"]
