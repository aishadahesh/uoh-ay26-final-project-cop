"""Drawing the board and result banner for the interactive play window."""

from __future__ import annotations

from tkinter import messagebox

from police_thief.domain.board import Position
from police_thief.domain.live_view_model import TurnState, build_live_view_model
from police_thief.domain.scoring import MatchOutcome
from police_thief.gui.theme import COLORS
from police_thief.shared.constants import AgentRole

_ROLE_LABEL = {AgentRole.COP: "C", AgentRole.THIEF: "T"}

_ROLE_FILL = {AgentRole.COP: COLORS["cop"], AgentRole.THIEF: COLORS["thief"]}

_BARRIER_COLOR = COLORS["barrier"]

_OUTCOME_TEXT = {MatchOutcome.CAPTURE: "Capture!", MatchOutcome.SURVIVAL: "The thief survives!"}


class _RenderMixin:
    """Board rendering and end-of-match display."""

    def _render(self) -> None:
        view = self.match.visible_view_for_current()
        human_turn = self.match.is_human_turn()
        turn_word = "YOUR" if human_turn else "AGENT"
        role_name = view.own_role.value.upper()
        self.status_label.config(text=f"●  {role_name} / {turn_word} TURN")
        self.turn_label.config(text=f"TURN      {self.match.turns_played + 1:02} / {self.match.max_moves:02}")
        self.role_label.config(text=f"ACTIVE    {role_name}")
        barriers_used = (
            self.match.board.config.max_barriers - self.match.board.remaining_barrier_budget
        )
        self.barriers_label.config(
            text=f"BARRIERS  {barriers_used:02} / {self.match.board.config.max_barriers:02}"
        )
        self.barrier_button.config(text="CANCEL PLACEMENT" if self._barrier_mode else "＋  DEPLOY BARRIER")
        self.canvas.clear_markers()
        legal_cells = ({(p.row, p.col) for p in self.match.legal_moves().values()}
                       if human_turn and not self._barrier_mode else set())
        self.canvas.highlight_legal_cells(legal_cells)
        if view.belief is not None:
            vm = build_live_view_model(
                view.own_position, view.belief, self.match.board,
                TurnState.YOUR_TURN if human_turn else TurnState.LOCKED,
                role_label=_ROLE_LABEL[view.own_role],
            )
            for cell in vm.cells:
                self.canvas.set_cell_color(cell.position.row, cell.position.col, cell.color)
            self.canvas.draw_agent(view.own_position.row, view.own_position.col,
                                   _ROLE_LABEL[view.own_role], _ROLE_FILL[view.own_role])
        else:
            for row in range(self.match.board.config.grid_size):
                for col in range(self.match.board.config.grid_size):
                    pos = Position(row, col)
                    self.canvas.set_cell_color(row, col, _BARRIER_COLOR if self.match.board.is_blocked(pos) else COLORS["cell"])
            self.canvas.draw_agent(view.own_position.row, view.own_position.col,
                                   _ROLE_LABEL[view.own_role], _ROLE_FILL[view.own_role])
            if view.opponent_position is not None:
                other = AgentRole.THIEF if view.own_role is AgentRole.COP else AgentRole.COP
                self.canvas.draw_agent(view.opponent_position.row, view.opponent_position.col,
                                       _ROLE_LABEL[other], _ROLE_FILL[other])

    def _show_result(self) -> None:
        self._disable_human_controls()
        text = _OUTCOME_TEXT.get(self.match.outcome, str(self.match.outcome))
        self.status_label.config(text=f"MATCH OVER / {text}", fg=COLORS["success"])
        messagebox.showinfo("Match Over", text)

    def _enable_human_controls(self) -> None:
        legal = self.match.legal_moves()
        for move, button in self.move_buttons.items():
            button.config(state="normal" if move in legal else "disabled")
        is_cop = self.match.current_role is AgentRole.COP
        self.barrier_button.config(state="normal" if is_cop else "disabled")
        self.canvas.set_click_handler(self._on_cell_click)

    def _disable_human_controls(self) -> None:
        for button in self.move_buttons.values():
            button.config(state="disabled")
        self.barrier_button.config(state="disabled")
        self.canvas.set_click_handler(None)
        self._barrier_mode = False
