"""Premium mode launcher for interactive play."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from police_thief.domain.interactive_match import MODE_LABELS, GameMode
from police_thief.gui.theme import COLORS, FONT, configure_window, install_styles

_MODE_COPY = {
    GameMode.AGENT_VS_AGENT: ("AUTONOMOUS", "Watch two heuristic agents adapt under fog of war."),
    GameMode.NETWORK_AGENT_VS_AGENT: (
        "MCP NETWORK",
        "Connect two autonomous peers running on different computers.",
    ),
    GameMode.HUMAN_COP_VS_AGENT: ("PURSUIT", "Track scent, shape the board, and close the net."),
    GameMode.AGENT_VS_HUMAN_THIEF: ("EVASION", "Outthink the pursuing agent and survive 35 turns."),
    GameMode.HUMAN_VS_HUMAN: ("HOTSEAT", "A shared-board tactical duel for two local players."),
}


class ModeSelectDialog:
    def __init__(self, master: tk.Misc) -> None:
        self.result: GameMode | None = None
        self.window = tk.Toplevel(master)
        configure_window(self.window, title="ShadowGrid | Mission Select", min_size=(720, 620))
        install_styles(self.window)
        self.window.geometry("780x660")
        # On Windows, making a Toplevel transient to a withdrawn root also
        # withdraws the child. The CLI intentionally hides its empty root
        # while this launcher is open, so only attach a transient parent when
        # that parent is actually viewable.
        if master.winfo_viewable():
            self.window.transient(master)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        self._mode_var = tk.StringVar(value=GameMode.AGENT_VS_AGENT.value)
        self._mode_var.trace_add("write", self._refresh_selection)
        self._cards: dict[GameMode, tuple[tk.Frame, tk.Label, tk.Label]] = {}

        shell = ttk.Frame(self.window, style="App.TFrame", padding=30)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="SHADOWGRID", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            shell, text="POLICE / THIEF  •  DECENTRALIZED TACTICAL LAB",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 22))
        tk.Label(
            shell, text="SELECT MISSION PROFILE", bg=COLORS["bg"], fg=COLORS["accent"],
            font=(FONT, 10, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        for mode, label in MODE_LABELS.items():
            self._build_card(shell, mode, label)

        footer = ttk.Frame(shell, style="App.TFrame")
        footer.pack(fill="x", pady=(22, 0))
        ttk.Label(
            footer, text="ENTER  Start mission     ↑/↓  Review modes",
            style="Subtitle.TLabel",
        ).pack(side="left")
        self.start_button = ttk.Button(
            footer, text="LAUNCH MISSION  →", style="Accent.TButton", command=self._on_start,
        )
        self.start_button.pack(side="right")

        self.window.bind("<Return>", lambda _event: self._on_start())
        self.window.bind("<Up>", lambda _event: self._cycle(-1))
        self.window.bind("<Down>", lambda _event: self._cycle(1))
        self._refresh_selection()
        self.window.update_idletasks()
        self._center()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        self.window.grab_set()

    def _build_card(self, parent: tk.Misc, mode: GameMode, label: str) -> None:
        frame = tk.Frame(parent, bg=COLORS["surface"], highlightthickness=1, padx=16, pady=12)
        frame.pack(fill="x", pady=5)
        tag, description = _MODE_COPY[mode]
        heading = tk.Label(frame, text=label, anchor="w", font=(FONT, 11, "bold"))
        heading.pack(fill="x")
        copy = tk.Label(
            frame, text=f"{tag}  •  {description}", anchor="w", font=(FONT, 9),
        )
        copy.pack(fill="x", pady=(4, 0))
        for widget in (frame, heading, copy):
            widget.bind("<Button-1>", lambda _event, value=mode.value: self._mode_var.set(value))
            widget.configure(cursor="hand2")
        self._cards[mode] = (frame, heading, copy)

    def _refresh_selection(self, *_args: object) -> None:
        selected = GameMode(self._mode_var.get())
        for mode, (frame, heading, copy) in self._cards.items():
            active = mode is selected
            background = COLORS["surface_alt"] if active else COLORS["surface"]
            frame.configure(
                bg=background,
                highlightbackground=COLORS["accent"] if active else COLORS["border"],
                highlightcolor=COLORS["accent"] if active else COLORS["border"],
                highlightthickness=2 if active else 1,
            )
            heading.configure(bg=background, fg=COLORS["text"])
            copy.configure(bg=background, fg=COLORS["accent"] if active else COLORS["muted"])

    def _cycle(self, delta: int) -> None:
        modes = list(GameMode)
        current = modes.index(GameMode(self._mode_var.get()))
        self._mode_var.set(modes[(current + delta) % len(modes)].value)

    def _center(self) -> None:
        top = self.window.winfo_toplevel()
        width, height = top.winfo_width(), top.winfo_height()
        x = max(0, (top.winfo_screenwidth() - width) // 2)
        y = max(0, (top.winfo_screenheight() - height) // 2)
        top.geometry(f"{width}x{height}+{x}+{y}")

    def _on_start(self) -> None:
        self.result = GameMode(self._mode_var.get())
        self.window.grab_release()
        self.window.destroy()

    def show(self) -> GameMode | None:
        self.window.wait_window()
        return self.result
