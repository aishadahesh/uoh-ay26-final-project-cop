"""Shared fixtures for the capture-safety test modules.

Extracted from `test_capture_safety.py` when it was split by theme, so the
stub belief/Gemini doubles, the runner factory and the saturated-scent
kernel are defined once and imported by each themed module."""

from pathlib import Path

from police_thief.domain.board import Move, Position
from police_thief.services.gemini_agent import GeminiDecision
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import (
    NetworkMatchRunner,
    NetworkMatchSettings,
)
from police_thief.shared.constants import AgentRole


class _CertainBelief:
    def __init__(self, position: Position) -> None:
        self.position = position

    def arg_max(self) -> Position:
        return self.position

    def top_positions(self, _limit: int = 5):
        return ((self.position, 1.0),)


class _UnsafeGemini:
    def __init__(self) -> None:
        self.context = None

    def usage_snapshot(self):
        return 0, 0

    def choose_move(self, context, _fallback):
        self.context = context
        return GeminiDecision(Move.WEST, "unsafe test response")


class _NextTurnUnsafeGemini(_UnsafeGemini):
    def choose_move(self, context, _fallback):
        self.context = context
        return GeminiDecision(Move.NORTH, "walk into next-turn capture")


def _runner(
    tmp_path: Path,
    advisor=None,
    role: AgentRole = AgentRole.THIEF,
) -> NetworkMatchRunner:
    settings = NetworkMatchSettings(
        role=role,
        local_port=8802,
        opponent_url="https://cop.example/mcp",
        public_url="https://thief.example/mcp",
        game_id="CAPTURE-SAFETY",
        sub_game_number=1,
        shared_config=tmp_path / "game.json",
        output_dir=tmp_path,
    )
    return NetworkMatchRunner(
        settings, PeerInboxes(), gemini_advisor=advisor, transport=object(),
    )


def _opponent_capped_step(
    grid: dict[str, float], center: Position, size: int = 7,
) -> dict[str, float]:
    """One turn of the reviewed opponent's scent model: decay by (1-rho),
    deposit the 5x5 kernel, hard-cap every cell at 0.9."""
    decayed = {key: value * 0.9 for key, value in grid.items()}
    for (delta_row, delta_col), deposit in _CAPPED_KERNEL.items():
        row, col = center.row + delta_row, center.col + delta_col
        if 0 <= row < size and 0 <= col < size:
            key = f"{row},{col}"
            decayed[key] = min(0.9, decayed.get(key, 0.0) + deposit)
    return {key: value for key, value in decayed.items() if value > 1e-9}


_CAPPED_KERNEL = {
    (0, 0): 0.90,
    (0, 1): 0.62, (0, -1): 0.62, (1, 0): 0.62, (-1, 0): 0.62,
    (1, 1): 0.42, (1, -1): 0.42, (-1, 1): 0.42, (-1, -1): 0.42,
    (0, 2): 0.20, (0, -2): 0.20, (2, 0): 0.20, (-2, 0): 0.20,
    (1, 2): 0.14, (1, -2): 0.14, (-1, 2): 0.14, (-1, -2): 0.14,
    (2, 1): 0.14, (2, -1): 0.14, (-2, 1): 0.14, (-2, -1): 0.14,
    (2, 2): 0.04, (2, -2): 0.04, (-2, 2): 0.04, (-2, -2): 0.04,
}
