"""Shared fixtures for the interactive play-window test modules.

Extracted when `test_play_app.py` was split by theme."""

import tkinter as tk

from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.interactive_match import GameMode, InteractiveMatch


def _match(mode: GameMode, cop=None, thief=None, max_moves: int = 35, max_barriers: int = 14) -> InteractiveMatch:
    board = Board(BoardConfig(grid_size=7, max_barriers=max_barriers))
    return InteractiveMatch(board, cop or Position(0, 0), thief or Position(3, 3), mode, max_moves)


def _no_schedule(monkeypatch):
    """Prevent any real root.after() callback from firing during a test."""
    monkeypatch.setattr(tk.Misc, "after", lambda self, ms, func=None, *a: None)
