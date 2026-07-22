"""Gemini-backed tactical move selection for interactive agent modes.

Gemini receives local truth only and may select only from moves already
declared legal by the deterministic board engine. Invalid output, quota
errors, and network failures fall back to the caller's validated heuristic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from police_thief.domain.board import Move, Position
from police_thief.shared.constants import AgentRole

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
_FALLBACK_MODELS = ("gemini-flash-latest", "gemini-2.5-flash")


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


@dataclass(frozen=True)
class GeminiDecision:
    move: Move
    rationale: str
    used_fallback: bool = False


class GeminiAgentAdvisor:
    """Ask Gemini for a legal tactical move and retain a human-readable reason."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        if client is not None:
            self._client = client
            return
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise GeminiConfigurationError(
                "Agent modes require GEMINI_API_KEY in .env or the process environment."
            )
        from google import genai

        self._client = genai.Client(api_key=key)

    def choose_move(self, context: TacticalContext, fallback: Move) -> GeminiDecision:
        """Return Gemini's legal move, or the deterministic fallback on any failure."""
        prompt = self._prompt(context)
        last_error: Exception | None = None
        candidates = dict.fromkeys((self.model, *_FALLBACK_MODELS))
        for model in candidates:
            try:
                response = self._client.models.generate_content(model=model, contents=prompt)
                return self._parse_response(response.text or "", context.legal_moves, fallback)
            except Exception as exc:  # noqa: BLE001 - try next model before safe fallback
                last_error = exc
        assert last_error is not None
        return GeminiDecision(
            move=fallback,
            rationale=(
                f"Gemini unavailable after {len(candidates)} models: "
                f"{self._safe_error(last_error)} Heuristic fallback used."
            ),
            used_fallback=True,
        )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        """Expose a useful provider error without ever leaking configured keys."""
        message = " ".join(str(exc).split())
        for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            secret = os.getenv(variable)
            if secret:
                message = message.replace(secret, "<redacted>")
        concise = message[:120].rstrip()
        return f"{type(exc).__name__} - {concise}" if concise else type(exc).__name__

    @staticmethod
    def _prompt(context: TacticalContext) -> str:
        objective = "close distance to the believed thief" if context.role is AgentRole.COP else "increase distance from the believed cop"
        legal = ", ".join(move.name for move in context.legal_moves)
        return (
            "You are the tactical reasoning layer in a partially observable police-thief grid game. "
            "Opponent coordinates are unavailable; reason only from the belief map. "
            "Choose exactly one supplied legal move.\n"
            f"Role: {context.role.value}\n"
            f"Objective: {objective}\n"
            f"Own position: ({context.own_position.row}, {context.own_position.col})\n"
            f"Belief-map peak: ({context.belief_peak.row}, {context.belief_peak.col})\n"
            f"Turn: {context.turn_number}/{context.max_turns}\n"
            f"Remaining barrier budget: {context.remaining_barriers}\n"
            f"Legal moves: {legal}\n"
            "Reply on one line only as MOVE|brief tactical reason. "
            "MOVE must exactly match one legal move name."
        )

    @staticmethod
    def _parse_response(text: str, legal_moves: tuple[Move, ...], fallback: Move) -> GeminiDecision:
        move_text, separator, reason = text.strip().partition("|")
        legal_by_name = {move.name: move for move in legal_moves}
        selected = legal_by_name.get(move_text.strip().upper())
        if selected is None:
            return GeminiDecision(
                move=fallback,
                rationale="Gemini returned an invalid move; heuristic fallback used.",
                used_fallback=True,
            )
        rationale = reason.strip() if separator and reason.strip() else "Gemini selected this legal tactical move."
        return GeminiDecision(move=selected, rationale=rationale[:180])
