"""Validated Gemini tactical move selection with one corrective retry."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

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


class GeminiAgentAdvisor:
    """Ask Gemini for a move, repair bad output, and execute only legal actions."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        allow_fallback_models: bool | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _float_env("GEMINI_TIMEOUT_SECONDS", DEFAULT_GEMINI_TIMEOUT_SECONDS)
        )
        self.http_timeout_seconds = max(self.timeout_seconds, MIN_GEMINI_HTTP_TIMEOUT_SECONDS)
        self.allow_fallback_models = (
            allow_fallback_models
            if allow_fallback_models is not None
            else _truthy_env("GEMINI_ENABLE_MODEL_FALLBACKS")
        )
        self._input_tokens = 0
        self._output_tokens = 0
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
            http_options={
                "timeout": int(self.http_timeout_seconds * 1000),
                "retry_options": {"attempts": 1},
            },
        )

    def choose_move(self, context: TacticalContext, fallback: Move) -> GeminiDecision:
        legal = tuple(dict.fromkeys(context.legal_moves))
        if not legal:
            raise ValueError(
                "Gemini cannot choose an action because no legal actions were supplied"
            )
        safe_fallback = (
            fallback if fallback in legal else (Move.STAY if Move.STAY in legal else legal[0])
        )
        models = tuple(
            dict.fromkeys(
                (self.model, *_FALLBACK_MODELS) if self.allow_fallback_models else (self.model,)
            )
        )
        rejected: list[str] = []
        last_error: Exception | None = None
        total_attempts = 0
        for model in models:
            prompt = self._prompt(context)
            for attempt in range(1, MAX_ACTION_ATTEMPTS + 1):
                total_attempts += 1
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config={
                            "temperature": 0,
                            "max_output_tokens": DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
                            "http_options": {
                                "timeout": int(self.http_timeout_seconds * 1000),
                                "retry_options": {"attempts": 1},
                            },
                        },
                    )
                    self._record_usage(response)
                    text = response.text or ""
                    parsed, rejection = self._parse_response(text, legal)
                    if parsed is not None:
                        move, reason = parsed
                        return GeminiDecision(
                            move,
                            reason,
                            attempts=total_attempts,
                            rejected=tuple(rejected),
                        )
                    rejected.append(rejection)
                    if attempt < MAX_ACTION_ATTEMPTS:
                        prompt = self._repair_prompt(context, text, rejection)
                except Exception as exc:  # provider/model failure; another model may recover
                    last_error = exc
                    break
        if rejected:
            cause = rejected[-1]
        elif last_error is not None:
            cause = f"provider unavailable: {self._safe_error(last_error)}"
        else:
            cause = "Gemini returned no usable response"
        return GeminiDecision(
            safe_fallback,
            f"Fallback activated after {total_attempts} Gemini attempt(s): {cause}. Selected {safe_fallback.name} ({safe_fallback.value}).",
            used_fallback=True,
            attempts=total_attempts,
            rejected=tuple(rejected),
        )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = " ".join(str(exc).split())
        for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            secret = os.getenv(variable)
            if secret:
                message = message.replace(secret, "<redacted>")
        concise = message[:120].rstrip()
        return f"{type(exc).__name__} - {concise}" if concise else type(exc).__name__

    def usage_snapshot(self) -> tuple[int, int]:
        """Cumulative successfully reported Gemini input/output tokens."""
        return self._input_tokens, self._output_tokens

    def _record_usage(self, response: Any) -> None:
        metadata = getattr(response, "usage_metadata", None)
        if metadata is None:
            return
        self._input_tokens += _usage_value(
            metadata, "prompt_token_count", "input_token_count"
        )
        self._output_tokens += _usage_value(
            metadata, "candidates_token_count", "output_token_count"
        )

    @staticmethod
    def _prompt(context: TacticalContext) -> str:
        destinations = dict(context.legal_destinations)
        scores = dict(context.action_scores)
        actions = []
        for move in context.legal_moves:
            destination = destinations.get(move)
            location = f" -> ({destination.row},{destination.col})" if destination else ""
            score = scores.get(move)
            safety = f"; planner_score={score}" if score is not None else ""
            actions.append(f"{move.name} [{move.value}]{location}{safety}")
        objective = (
            "intercept the believed thief"
            if context.role is AgentRole.COP
            else (
                "survive: maximize distance from the believed cop, preserve multiple future exits, avoid dead ends, and avoid STAY unless safer"
            )
        )
        confirmed = (
            f"({context.known_opponent_position.row},{context.known_opponent_position.col})"
            if context.known_opponent_position is not None else "UNKNOWN"
        )
        return (
            "You are the primary tactical policy for a partially observable grid game.\n"
            "Choose ONLY one action from ALLOWED_ACTIONS. Every omitted direction is illegal now (off-board or blocked). "
            "Never invent a direction, coordinate, diagonal, barrier action, or prose-only answer.\n"
            f"ROLE={context.role.value}\nOBJECTIVE={objective}\n"
            f"OWN_POSITION=({context.own_position.row},{context.own_position.col})\n"
            f"CONFIRMED_OPPONENT_POSITION={confirmed}\n"
            "If CONFIRMED_OPPONENT_POSITION is known, never enter that cell. "
            "For a thief, actions the cop can capture on its very next move are also "
            "omitted whenever a guaranteed-safe alternative exists. Treat "
            "ALLOWED_ACTIONS as a strict tactical safety boundary, not merely the "
            "board's geometric move list.\n"
            f"BELIEVED_OPPONENT=({context.belief_peak.row},{context.belief_peak.col}) (estimate, not truth)\n"
            f"BELIEF_CANDIDATES={_positions_with_weights(context.belief_candidates)}\n"
            f"BOARD_SIZE={context.board_size}x{context.board_size}\n"
            f"BLOCKED_CELLS={_positions(context.blocked_cells)}\n"
            f"RECENT_POSITIONS={_positions(context.recent_positions)}\n"
            f"RECENT_ACTIONS={[move.name for move in context.recent_actions]}\n"
            f"REPEATED_STATE_WARNING={context.repeated_state_warning or 'none'}\n"
            f"SUB_GAME={context.sub_game_number}\n"
            f"TURN={context.turn_number}/{context.max_turns}\nREMAINING_BARRIERS={context.remaining_barriers}\n"
            f"ALLOWED_ACTIONS={'; '.join(actions)}\n"
            'Return strict JSON only: {"action":"EXACT_NAME","reason":"brief tactical reason"}.'
        )

    @classmethod
    def _repair_prompt(cls, context: TacticalContext, rejected_text: str, rejection: str) -> str:
        clipped = " ".join(rejected_text.split())[:160]
        return (
            cls._prompt(context)
            + f"\nYour previous response was rejected: {rejection}. PREVIOUS={clipped!r}. "
            "Correct it now. Copy exactly one action NAME from ALLOWED_ACTIONS and return JSON only."
        )

    @staticmethod
    def _parse_response(
        text: str, legal_moves: tuple[Move, ...]
    ) -> tuple[tuple[Move, str] | None, str]:
        raw = text.strip()
        if not raw:
            return None, "empty response"
        action = ""
        reason = ""
        try:
            candidate = raw
            if "```" in candidate:
                candidate = re.sub(
                    r"^.*?```(?:json)?\s*|\s*```.*$", "", candidate, flags=re.I | re.S
                )
            data = json.loads(candidate)
            if not isinstance(data, dict):
                return None, "JSON response is not an object"
            action = str(data.get("action") or data.get("move") or "")
            reason = str(data.get("reason") or data.get("rationale") or "")
        except (json.JSONDecodeError, TypeError):
            move_text, separator, trailing = raw.partition("|")
            action = move_text
            reason = trailing if separator else ""
        cleaned = action.strip().upper()
        for prefix in ("MOVE:", "MOVE=", "MOVE ", "ACTION:", "ACTION=", "ACTION "):
            if cleaned.startswith(prefix):
                cleaned = cleaned.removeprefix(prefix).strip()
        aliases = {move.name: move for move in legal_moves}
        aliases.update({move.value: move for move in legal_moves})
        aliases.update(
            {
                "UP": Move.NORTH,
                "DOWN": Move.SOUTH,
                "LEFT": Move.WEST,
                "RIGHT": Move.EAST,
                "WAIT": Move.STAY,
            }
        )
        selected = aliases.get(cleaned)
        if selected not in legal_moves:
            allowed = ", ".join(move.name for move in legal_moves)
            shown = cleaned[:40] or "<missing>"
            return (
                None,
                f"action {shown!r} is unavailable or malformed; allowed actions: {allowed}",
            )
        return (
            selected,
            reason.strip()[:180] or "Gemini selected a validated legal tactical move.",
        ), ""


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _usage_value(metadata: Any, *names: str) -> int:
    for name in names:
        value = metadata.get(name) if isinstance(metadata, dict) else getattr(metadata, name, None)
        if isinstance(value, int) and value >= 0:
            return value
    return 0


def _positions(values: tuple[Position, ...]) -> list[tuple[int, int]]:
    return [(position.row, position.col) for position in values]


def _positions_with_weights(
    values: tuple[tuple[Position, float], ...],
) -> list[tuple[int, int, float]]:
    return [(position.row, position.col, round(weight, 4)) for position, weight in values]
