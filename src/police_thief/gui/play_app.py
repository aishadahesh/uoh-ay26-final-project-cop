"""Interactive command-center GUI for local Police-Thief matches."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from contextlib import suppress

from police_thief.domain.interactive_match import InteractiveMatch
from police_thief.gui.play_app_input import _InputMixin
from police_thief.gui.play_app_layout import _KEY_MOVES, _LayoutMixin
from police_thief.gui.play_app_render import _RenderMixin
from police_thief.services.gemini_agent import GeminiAgentAdvisor

AGENT_MOVE_DELAY_MS = 500


class PlayApp(_LayoutMixin, _RenderMixin, _InputMixin):
    """Drive one InteractiveMatch through a polished, keyboard-friendly UI."""

    def __init__(
        self,
        master: tk.Misc,
        match: InteractiveMatch,
        gemini_advisor: GeminiAgentAdvisor | None = None,
        on_new_game: Callable[[], bool] | None = None,
    ) -> None:
        self.master = master
        self.match = match
        self.gemini_advisor = gemini_advisor
        self.on_new_game = on_new_game
        self._barrier_mode = False
        self._agent_after_id: str | None = None
        self._paused = False
        self._closed = False
        self._build_ui()

    def start(self) -> None:
        self._advance()

    def _advance(self) -> None:
        if self._closed or self._paused:
            return
        if self.match.is_finished:
            self._show_result()
            return
        if self.match.is_human_turn():
            self._enable_human_controls()
        else:
            self._disable_human_controls()
            self._agent_after_id = self.master.after(AGENT_MOVE_DELAY_MS, self._agent_turn)
        self._render()

    def _agent_turn(self) -> None:
        self._agent_after_id = None
        if self._closed or self._paused or self.match.is_finished:
            return
        self.status_label.config(text=f"◌  {self.match.current_role.value.upper()} / GEMINI THINKING")
        self.master.update_idletasks()
        self.match.apply_move(self.match.agent_move(self._gemini_move if self.gemini_advisor else None))
        self._advance()

    def _request_new_game(self) -> None:
        """Pause this match while the owner reopens the mission selector."""
        if self.on_new_game is None or self._closed:
            return
        self._paused = True
        if self._agent_after_id is not None:
            with suppress(tk.TclError):
                self.master.after_cancel(self._agent_after_id)
            self._agent_after_id = None
        changed = self.on_new_game()
        if not changed and not self._closed:
            self._paused = False
            self._advance()

    def close(self) -> None:
        """Stop pending callbacks, remove bindings, and destroy this session UI."""
        self._closed = True
        if self._agent_after_id is not None:
            with suppress(tk.TclError):
                self.master.after_cancel(self._agent_after_id)
            self._agent_after_id = None
        for sequence in (*_KEY_MOVES, "b"):
            self.master.unbind(sequence)
        self.shell.destroy()








