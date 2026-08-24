"""The `play` subcommand: launch the interactive GUI."""

from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import messagebox

from police_thief.cli.args import (
    DEFAULT_CONFIG_ROOT,
)
from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.shared.constants import AgentRole


def _play(args: argparse.Namespace) -> None:
    """The interactive, mode-selectable play window (see main.py's own
    module docstring and domain/interactive_match.py for scope/rationale).

    `args` is unused today (no CLI flags yet) but kept for a consistent
    handler signature alongside `_serve`/`_simulate`/`_replay`/`_demo`.
    """
    from dotenv import load_dotenv

    from police_thief.domain.interactive_match import (
        InteractiveMatch,
        PlayerType,
        controller_for,
    )
    from police_thief.gui.mode_select import ModeSelectDialog
    from police_thief.gui.network_match_app import NetworkMatchApp
    from police_thief.gui.network_setup import NetworkSetupDialog
    from police_thief.gui.play_app import PlayApp
    from police_thief.services.gemini_agent import GeminiAgentAdvisor, GeminiConfigurationError

    root = tk.Tk()
    root.withdraw()
    load_dotenv()
    current_app: PlayApp | NetworkMatchApp | None = None

    def select_and_start() -> bool:
        nonlocal current_app
        mode = ModeSelectDialog(root).show()
        if mode is None:
            return False

        if mode.value == "network_agent_vs_agent":
            try:
                gemini_advisor = GeminiAgentAdvisor()
            except GeminiConfigurationError as exc:
                root.deiconify()
                messagebox.showerror(
                    "Gemini API key required",
                    f"{exc}\n\nCopy .env-example to .env and set GEMINI_API_KEY, then launch again.",
                    parent=root,
                )
                return False
            settings = NetworkSetupDialog(root, DEFAULT_CONFIG_ROOT.parent).show()
            if settings is None:
                return False
            if current_app is not None:
                current_app.close()
            root.deiconify()
            current_app = NetworkMatchApp(
                root, settings, gemini_advisor, on_new_game=select_and_start,
            )
            current_app.start()
            return True

        has_agent = any(
            controller_for(mode, role) is PlayerType.AGENT for role in AgentRole
        )
        gemini_advisor = None
        if has_agent:
            try:
                gemini_advisor = GeminiAgentAdvisor()
            except GeminiConfigurationError as exc:
                root.deiconify()
                messagebox.showerror(
                    "Gemini API key required",
                    f"{exc}\n\nCopy .env-example to .env and set GEMINI_API_KEY, then launch again.",
                    parent=root,
                )
                return False

        if current_app is not None:
            current_app.close()
        board = Board(BoardConfig(grid_size=7, max_barriers=14))
        match = InteractiveMatch(board, Position(0, 0), Position(3, 3), mode, max_moves=35)
        root.deiconify()
        root.title("Police-Thief - Interactive Play")
        current_app = PlayApp(
            root, match, gemini_advisor=gemini_advisor, on_new_game=select_and_start
        )
        current_app.start()
        return True

    if not select_and_start():
        root.destroy()
        return
    root.mainloop()
