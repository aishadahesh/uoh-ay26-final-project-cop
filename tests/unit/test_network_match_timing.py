"""Timing diagnostics for Gemini-backed network move selection."""

from pathlib import Path

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.services.gemini_agent import GeminiDecision
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.services.network_match import (
    BOUNDARY_FIRST_TURN_TIMEOUT_SECONDS,
    _turn_timeout,
)
from police_thief.shared.constants import AgentRole


class _Advisor:
    def __init__(self, decision: GeminiDecision) -> None:
        self.decision = decision

    def choose_move(self, _context, _fallback):
        return self.decision


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


def test_move_selection_emits_source_duration_and_reason(monkeypatch):
    advisor = _Advisor(
        GeminiDecision(
            move=Move.EAST,
            rationale="Closing on the belief peak.",
            used_fallback=False,
        )
    )
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
        Move.STAY,
        step=3,
        max_steps=35,
        emit=messages.append,
    )

    assert move is Move.EAST
    assert messages == [
        "Step 3: Gemini selected EAST (E); valid=True; attempts=1",
        "Step 3: Gemini (1.2s) - Closing on the belief peak.",
    ]


def test_first_turn_uses_boundary_timeout() -> None:
    assert _turn_timeout(120.0, 1) == BOUNDARY_FIRST_TURN_TIMEOUT_SECONDS


def test_later_turns_keep_response_timeout() -> None:
    assert _turn_timeout(120.0, 2) == 120.0
