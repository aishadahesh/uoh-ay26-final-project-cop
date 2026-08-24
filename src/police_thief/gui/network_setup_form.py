"""Row builders for the two-computer setup dialog."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from police_thief.gui.theme import COLORS, FONT


class _FormMixin:
    """Builds labelled form rows."""

    def _row(
        self, parent, label: str, key: str, choices: tuple[str, ...] = (),
        second_key: str | None = None, secret: bool = False,
    ) -> None:
        ttk.Label(parent, text=label, style="Subtitle.TLabel").pack(anchor="w", pady=(8, 3))
        if choices:
            widget = ttk.Combobox(parent, textvariable=self.vars[key], values=choices, state="readonly")
        else:
            widget = tk.Entry(
                parent, textvariable=self.vars[key], bg=COLORS["surface_alt"],
                fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat",
                font=(FONT, 10), show="*" if secret else "",
            )
        if second_key is None:
            widget.pack(fill="x", ipady=5)
            return
        row = ttk.Frame(parent, style="App.TFrame")
        row.pack(fill="x")
        widget.pack(in_=row, side="left", fill="x", expand=True, ipady=5, padx=(0, 5))
        tk.Entry(
            row, textvariable=self.vars[second_key], bg=COLORS["surface_alt"],
            fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", font=(FONT, 10),
        ).pack(side="left", fill="x", expand=True, ipady=5, padx=(5, 0))

    @staticmethod
    def _section_label(parent, text: str) -> None:
        tk.Label(
            parent, text=text, bg=COLORS["bg"], fg=COLORS["accent"],
            font=(FONT, 10, "bold"), anchor="w",
        ).pack(fill="x", pady=(18, 0))

    def _toggle_email(self) -> None:
        state = "normal" if self.vars["email"].get() else "disabled"
        self.email_entry.configure(state=state)
