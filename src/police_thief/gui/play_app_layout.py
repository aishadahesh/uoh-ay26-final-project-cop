"""Widget construction for the interactive play window.

Split out of play_app.py; moved verbatim into `_build_ui`, which
`__init__` now calls as its last step.
"""


from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from police_thief.domain.board import Move
from police_thief.domain.interactive_match import MODE_LABELS
from police_thief.gui.board_canvas import BoardCanvas
from police_thief.gui.theme import COLORS, FONT, MONO_FONT, configure_window, install_styles

_DIRECTIONS = [
    ("N", "NORTH", "↑"), ("S", "SOUTH", "↓"), ("E", "EAST", "→"),
    ("W", "WEST", "←"), ("HOLD", "STAY", "•"),
]

_KEY_MOVES = {"<Up>": Move.NORTH, "<Down>": Move.SOUTH, "<Right>": Move.EAST,
              "<Left>": Move.WEST, "<space>": Move.STAY}

__all__ = ["_LayoutMixin"]


class _LayoutMixin:
    """Builds the whole widget tree onto the window."""

    def _build_ui(self) -> None:
        master = self.master
        match = self.match
        configure_window(master, title="ShadowGrid | Tactical Command", min_size=(900, 650))
        install_styles(master)

        self.shell = ttk.Frame(master, style="App.TFrame", padding=22)
        self.shell.pack(fill="both", expand=True)
        header = ttk.Frame(self.shell, style="App.TFrame")
        header.pack(fill="x", pady=(0, 16))
        title_box = ttk.Frame(header, style="App.TFrame")
        title_box.pack(side="left")
        ttk.Label(title_box, text="SHADOWGRID", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text=MODE_LABELS[match.mode].upper(), style="Subtitle.TLabel").pack(anchor="w")
        header_actions = ttk.Frame(header, style="App.TFrame")
        header_actions.pack(side="right")
        self.new_game_button = tk.Button(
            header_actions, text="↻  NEW GAME", command=self._request_new_game,
            bg=COLORS["surface"], fg=COLORS["text"], activebackground=COLORS["border"],
            activeforeground=COLORS["text"], relief="flat", bd=0, padx=14, pady=10,
            font=(FONT, 9, "bold"), cursor="hand2",
        )
        self.new_game_button.pack(side="left", padx=(0, 10))
        self.status_label = tk.Label(
            header_actions, font=(FONT, 12, "bold"), bg=COLORS["surface_alt"],
            fg=COLORS["accent"], padx=18, pady=10,
        )
        self.status_label.pack(side="right")

        content = ttk.Frame(self.shell, style="App.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        board_card = ttk.Frame(content, style="Card.TFrame", padding=18)
        ttk.Label(board_card, text="TACTICAL MAP", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            board_card, text="Select a glowing legal cell or use the movement console.",
            style="CardText.TLabel",
        ).pack(anchor="w", pady=(2, 12))
        board_wrap = tk.Frame(board_card, bg=COLORS["surface"])
        board_wrap.pack(expand=True)
        self.canvas = BoardCanvas(board_wrap, grid_size=match.board.config.grid_size, cell_size=54)
        self.canvas.configure(bg=COLORS["surface"], highlightbackground=COLORS["border"])
        self.canvas.pack()

        sidebar = ttk.Frame(content, style="Card.TFrame", padding=18, width=300)
        sidebar.grid(row=0, column=1, sticky="ns", padx=(14, 0))
        sidebar.grid_propagate(False)
        board_card.grid(row=0, column=0, sticky="nsew")
        ttk.Label(sidebar, text="MISSION TELEMETRY", style="CardTitle.TLabel").pack(anchor="w")
        telemetry = ttk.Frame(sidebar, style="Surface.TFrame")
        telemetry.pack(fill="x", pady=(10, 18))
        self.turn_label = ttk.Label(telemetry, style="Telemetry.TLabel")
        self.turn_label.pack(fill="x")
        self.role_label = ttk.Label(telemetry, style="Telemetry.TLabel")
        self.role_label.pack(fill="x")
        self.barriers_label = ttk.Label(telemetry, style="Telemetry.TLabel")
        self.barriers_label.pack(fill="x")
        self.gemini_label = tk.Label(
            sidebar, text="GEMINI  OFFLINE", bg=COLORS["surface"], fg=COLORS["muted"],
            font=(MONO_FONT, 8, "bold"), justify="left", wraplength=250,
        )
        self.gemini_label.pack(fill="x", pady=(0, 18))

        ttk.Label(sidebar, text="MOVEMENT CONSOLE", style="CardTitle.TLabel").pack(anchor="w")
        pad = ttk.Frame(sidebar, style="Card.TFrame")
        pad.pack(pady=10)
        self.move_buttons: dict[Move, tk.Button] = {}
        positions = {Move.NORTH: (0, 1), Move.WEST: (1, 0), Move.STAY: (1, 1),
                     Move.EAST: (1, 2), Move.SOUTH: (2, 1)}
        for label, move_name, icon in _DIRECTIONS:
            move = Move[move_name]
            button = tk.Button(
                pad, text=f"{icon}\n{label}", width=7, bg=COLORS["surface_alt"],
                fg=COLORS["text"], activebackground=COLORS["border"],
                activeforeground=COLORS["text"], disabledforeground=COLORS["muted"],
                relief="flat", bd=0, padx=7, pady=7, font=(FONT, 9, "bold"),
                command=lambda m=move: self._on_human_move(m),
            )
            button.grid(row=positions[move][0], column=positions[move][1], padx=3, pady=3)
            self.move_buttons[move] = button

        self.barrier_button = tk.Button(
            sidebar, text="＋  DEPLOY BARRIER", bg=COLORS["accent"], fg=COLORS["bg"],
            activebackground=COLORS["accent_hover"], activeforeground=COLORS["bg"],
            disabledforeground=COLORS["muted"], relief="flat", bd=0, padx=12, pady=10,
            font=(FONT, 10, "bold"),
            command=self._toggle_barrier_mode,
        )
        self.barrier_button.pack(fill="x", pady=(12, 8))
        self.hint_label = tk.Label(
            sidebar, text="ARROWS move  •  SPACE holds\nB toggles barrier placement",
            bg=COLORS["surface"], fg=COLORS["muted"], font=(MONO_FONT, 8), justify="left",
        )
        self.hint_label.pack(anchor="w", pady=(10, 0))
        for sequence, move in _KEY_MOVES.items():
            master.bind(sequence, lambda _event, m=move: self._on_human_move(m))
        master.bind("b", lambda _event: self._toggle_barrier_mode())
