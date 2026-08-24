"""Gemini advisor vocabulary: tuning constants, the tactical context handed
to the model, and the decision it returns.

Split out of gemini_agent.py so the prompt/parse half and the advisor half
can both import it without a cycle.
"""


from __future__ import annotations

from dataclasses import dataclass

from police_thief.domain.board import Move, Position
from police_thief.shared.constants import AgentRole

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"

_FALLBACK_MODELS = ("gemini-flash-latest", "gemini-2.5-flash")

DEFAULT_GEMINI_TIMEOUT_SECONDS = 8.0

MIN_GEMINI_HTTP_TIMEOUT_SECONDS = 10.0

DEFAULT_GEMINI_MAX_OUTPUT_TOKENS = 128

MAX_ACTION_ATTEMPTS = 2


class GeminiConfigurationError(RuntimeError):
    """Raised when an agent mode is launched without Gemini credentials."""


@dataclass(frozen=True)
class TacticalContext:
    role: AgentRole
    own_position: Position
    belief_peak: Position
    legal_moves: tuple[Move, ...]
    turn_number: int
    max_turns: int
    remaining_barriers: int
    legal_destinations: tuple[tuple[Move, Position], ...] = ()
    action_scores: tuple[tuple[Move, object], ...] = ()
    board_size: int = 7
    blocked_cells: tuple[Position, ...] = ()
    belief_candidates: tuple[tuple[Position, float], ...] = ()
    recent_positions: tuple[Position, ...] = ()
    recent_actions: tuple[Move, ...] = ()
    repeated_state_warning: str = ""
    sub_game_number: int = 1
    known_opponent_position: Position | None = None


@dataclass(frozen=True)
class GeminiDecision:
    move: Move
    rationale: str
    used_fallback: bool = False
    attempts: int = 1
    rejected: tuple[str, ...] = ()
