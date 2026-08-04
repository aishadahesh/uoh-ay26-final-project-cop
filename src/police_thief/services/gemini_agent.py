"""Gemini-backed tactical move selection for interactive agent modes.

Gemini receives local truth only and may select only from moves already
declared legal by the deterministic board engine. Invalid output, quota
errors, and network failures fall back to the caller's validated heuristic.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from police_thief.domain.board import Move, Position
from police_thief.shared.constants import AgentRole

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_GEMINI_TIMEOUT_SECONDS = 8.0
MIN_GEMINI_HTTP_TIMEOUT_SECONDS = 10.0
MAX_GEMINI_OUTPUT_TOKENS = 64
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
        self.timeout_seconds = self._timeout_seconds()
        # The per-turn budget (GEMINI_TIMEOUT_SECONDS) may legitimately be set
        # tighter than a single HTTP call needs to plausibly succeed, and is
        # also the deadline other callers race against (the network turn
        # timeout). Bounding the raw HTTP client timeout to a separate, more
        # forgiving floor means a tight per-turn budget doesn't by itself
        # guarantee every call fails before the provider even replies.
        self.http_timeout_seconds = max(self.timeout_seconds, MIN_GEMINI_HTTP_TIMEOUT_SECONDS)
        self.timeout_milliseconds = max(1, round(self.http_timeout_seconds * 1000))
        self.enable_model_fallbacks = self._env_flag("GEMINI_ENABLE_MODEL_FALLBACKS")
        if client is not None:
            self._client = client
            return
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise GeminiConfigurationError(
                "Agent modes require GEMINI_API_KEY in .env or the process environment."
            )
        from google import genai

        self._client = genai.Client(
            api_key=key,
            http_options=self._http_options(),
        )

    def choose_move(self, context: TacticalContext, fallback: Move) -> GeminiDecision:
        """Return Gemini's legal move, or the deterministic fallback on any failure."""
        prompt = self._prompt(context)
        last_error: Exception | None = None
        candidates = (
            tuple(dict.fromkeys((self.model, *_FALLBACK_MODELS)))
            if self.enable_model_fallbacks
            else (self.model,)
        )
        for model in candidates:
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "temperature": 0,
                        "max_output_tokens": MAX_GEMINI_OUTPUT_TOKENS,
                        "http_options": self._http_options(),
                    },
                )
                return self._parse_response(response.text or "", context.legal_moves, fallback)
            except Exception as exc:  # noqa: BLE001 - provider errors must not end a match
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
    def _timeout_seconds() -> float:
        """Load a positive per-request timeout, falling back safely on bad input."""
        raw_value = os.getenv("GEMINI_TIMEOUT_SECONDS", str(DEFAULT_GEMINI_TIMEOUT_SECONDS))
        try:
            timeout = float(raw_value)
        except ValueError:
            return DEFAULT_GEMINI_TIMEOUT_SECONDS
        return (
            timeout
            if math.isfinite(timeout) and timeout > 0
            else DEFAULT_GEMINI_TIMEOUT_SECONDS
        )

    def _http_options(self) -> dict[str, object]:
        """Bound one provider attempt and disable SDK-level retry delays."""
        return {
            "timeout": self.timeout_milliseconds,
            "retry_options": {"attempts": 1},
        }

    @staticmethod
    def _env_flag(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

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
        legal = ", ".join(f"{move.name} ({move.value})" for move in context.legal_moves)
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
            "MOVE must exactly match one legal move name or code."
        )

    @staticmethod
    def _parse_response(text: str, legal_moves: tuple[Move, ...], fallback: Move) -> GeminiDecision:
        move_text, separator, reason = text.strip().partition("|")
        cleaned = move_text.strip().upper()
        for prefix in ("MOVE:", "MOVE=", "MOVE "):
            if cleaned.startswith(prefix):
                cleaned = cleaned.removeprefix(prefix).strip()
        legal_by_name = {move.name: move for move in legal_moves}
        legal_by_name.update({move.value: move for move in legal_moves})
        selected = legal_by_name.get(cleaned)
        if selected is None:
            return GeminiDecision(
                move=fallback,
                rationale="Gemini returned an invalid move; heuristic fallback used.",
                used_fallback=True,
            )
        rationale = reason.strip() if separator and reason.strip() else "Gemini selected this legal tactical move."
        return GeminiDecision(move=selected, rationale=rationale[:180])
