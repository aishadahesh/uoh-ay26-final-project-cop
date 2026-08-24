"""Prompt construction and response parsing for the Gemini advisor.

Split out of gemini_agent.py and mixed into GeminiAgentAdvisor, so the
advisor keeps its own method names and every existing call site works.
"""


from __future__ import annotations

import json
import re

from police_thief.domain.board import Move, Position
from police_thief.services.gemini_types import (
    TacticalContext,
)
from police_thief.shared.constants import AgentRole


def _positions(values: tuple[Position, ...]) -> list[tuple[int, int]]:
    return [(position.row, position.col) for position in values]


def _positions_with_weights(
    values: tuple[tuple[Position, float], ...],
) -> list[tuple[int, int, float]]:
    return [(position.row, position.col, round(weight, 4)) for position, weight in values]


class _GeminiPromptMixin:
    """Builds the tactical prompt and parses the model's reply."""

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
