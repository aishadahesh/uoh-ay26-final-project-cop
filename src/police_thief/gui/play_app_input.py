"""Human input handling: move buttons, board clicks and barrier mode."""

from __future__ import annotations

from police_thief.domain.board import Move, MoveRejectedError, Position
from police_thief.gui.theme import COLORS
from police_thief.services.gemini_agent import TacticalContext
from police_thief.shared.constants import AgentRole


class _InputMixin:
    """Translates clicks into moves and barrier placements."""

    def _on_human_move(self, move: Move) -> None:
        if self.match.is_finished or not self.match.is_human_turn() or move not in self.match.legal_moves():
            return
        self._barrier_mode = False
        self.match.apply_move(move)
        self._advance()

    def _toggle_barrier_mode(self) -> None:
        if self.match.is_finished or not self.match.is_human_turn() or self.match.current_role is not AgentRole.COP:
            return
        self._barrier_mode = not self._barrier_mode
        self._render()

    def _on_cell_click(self, row: int, col: int) -> None:
        if self.match.is_finished or not self.match.is_human_turn():
            return
        position = Position(row, col)
        if self._barrier_mode:
            try:
                self.match.place_barrier(position)
            except (MoveRejectedError, ValueError):
                return
            self._barrier_mode = False
            self._advance()
            return
        move = next((m for m, p in self.match.legal_moves().items() if p == position), None)
        if move is not None:
            self.match.apply_move(move)
            self._advance()

    def _gemini_move(
        self,
        role: AgentRole,
        own_position: Position,
        belief_peak: Position,
        legal_moves: tuple[Move, ...],
        fallback: Move,
    ) -> Move:
        """Bridge the pure match callback to the external Gemini service."""
        if self.gemini_advisor is None:
            return fallback
        decision = self.gemini_advisor.choose_move(
            TacticalContext(
                role=role,
                own_position=own_position,
                belief_peak=belief_peak,
                legal_moves=legal_moves,
                turn_number=self.match.turns_played + 1,
                max_turns=self.match.max_moves,
                remaining_barriers=self.match.board.remaining_barrier_budget,
            ),
            fallback,
        )
        prefix = "FALLBACK" if decision.used_fallback else "GEMINI"
        color = COLORS["warning"] if decision.used_fallback else COLORS["accent"]
        self.gemini_label.config(
            text=f"{prefix}  {decision.move.name}\n{decision.rationale}", fg=color
        )
        return decision.move
