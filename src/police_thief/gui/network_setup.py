"""Configuration dialog for cross-computer Agent-vs-Agent matches.

This repo is the cop side only: the role selector below is locked to
"cop" regardless of what config/network_match.json's `peer.role` says,
since this repo has no thief private config to actually run as the
thief in a live match (see main.py's module docstring).
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlparse

from police_thief.gui.theme import COLORS, FONT, configure_window, install_styles
from police_thief.services.network_match import NetworkMatchSettings
from police_thief.shared.constants import AgentRole

DEFAULT_REPORT_EMAIL = "rmisegal+uoh26finalgame@gmail.com"


def load_network_defaults(path: Path, project_root: Path) -> dict:
    """Flatten the editable network launcher JSON into Tkinter field defaults."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        peer = raw["peer"]
        match = raw["match"]
        team1 = raw["team_1"]
        team2 = raw["team_2"]
        email = raw["email"]
        team1_members = list(team1["members"])
        team2_members = list(team2["members"])
        if len(team1_members) != 2 or len(team2_members) != 2:
            raise ValueError("each team must contain exactly two members")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid network defaults file {path}: {exc}") from exc
    output = Path(str(match.get("output_directory", "results/network")))
    if not output.is_absolute():
        output = project_root / output
    return {
        "role": str(peer.get("role", "cop")),
        "port": str(peer.get("local_port", 8801)),
        "opponent": str(peer.get("opponent_url", "https://opponent.example/mcp")),
        "public": str(peer.get("public_url", "https://your-tunnel.example/mcp")),
        "game": str(match.get("game_id", "G001")),
        "subgame": str(match.get("sub_game_number", 1)),
        "output": str(output),
        "secret": str(match.get("shared_match_secret", "")),
        "team1_name": str(team1.get("name", "")),
        "team1_member1": str(team1_members[0]),
        "team1_member2": str(team1_members[1]),
        "own_cop": str(team1.get("repos", {}).get("cop", "")),
        "own_thief": str(team1.get("repos", {}).get("thief", "")),
        "team2_name": str(team2.get("name", "")),
        "team2_member1": str(team2_members[0]),
        "team2_member2": str(team2_members[1]),
        "opponent_cop": str(team2.get("repos", {}).get("cop", "")),
        "opponent_thief": str(team2.get("repos", {}).get("thief", "")),
        "email": bool(email.get("automatic", False)),
        "email_recipient": str(email.get("recipient", DEFAULT_REPORT_EMAIL)),
    }


def validate_mcp_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path.endswith("/mcp"):
        raise ValueError("URL must be http(s) and end with /mcp")
    return url


class NetworkSetupDialog:
    def __init__(self, master: tk.Misc, project_root: Path) -> None:
        self.project_root = project_root
        defaults_path = project_root / "config" / "network_match.json"
        try:
            defaults = load_network_defaults(defaults_path, project_root)
        except (OSError, ValueError) as exc:
            messagebox.showwarning(
                "Network defaults",
                f"{exc}\n\nBuilt-in defaults will be used.",
                parent=master,
            )
            defaults = {}
        self.result: NetworkMatchSettings | None = None
        self.window = tk.Toplevel(master)
        configure_window(self.window, title="ShadowGrid | Network Match", min_size=(660, 560))
        install_styles(self.window)
        screen_height = self.window.winfo_screenheight()
        window_height = min(820, max(600, screen_height - 120))
        self.window.geometry(f"800x{window_height}")
        self.vars = {
            "role": tk.StringVar(value="cop"),  # this repo is cop-only; see module docstring
            "port": tk.StringVar(value=defaults.get("port", "8801")),
            "opponent": tk.StringVar(value=defaults.get("opponent", "https://opponent.example/mcp")),
            "public": tk.StringVar(value=defaults.get("public", "https://your-tunnel.example/mcp")),
            "game": tk.StringVar(value=defaults.get("game", "G001")),
            "subgame": tk.StringVar(value=defaults.get("subgame", "1")),
            "output": tk.StringVar(value=defaults.get("output", str(project_root / "results" / "network"))),
            "team1_name": tk.StringVar(value=defaults.get("team1_name", "")),
            "team1_member1": tk.StringVar(value=defaults.get("team1_member1", "")),
            "team1_member2": tk.StringVar(value=defaults.get("team1_member2", "")),
            "team2_name": tk.StringVar(value=defaults.get("team2_name", "")),
            "team2_member1": tk.StringVar(value=defaults.get("team2_member1", "")),
            "team2_member2": tk.StringVar(value=defaults.get("team2_member2", "")),
            "own_cop": tk.StringVar(value=defaults.get("own_cop", "")),
            "own_thief": tk.StringVar(value=defaults.get("own_thief", "")),
            "opponent_cop": tk.StringVar(value=defaults.get("opponent_cop", "")),
            "opponent_thief": tk.StringVar(value=defaults.get("opponent_thief", "")),
            "secret": tk.StringVar(value=defaults.get("secret", "")),
            "email": tk.BooleanVar(value=defaults.get("email", False)),
            "email_recipient": tk.StringVar(
                value=defaults.get("email_recipient", DEFAULT_REPORT_EMAIL),
            ),
        }
        viewport = tk.Frame(self.window, bg=COLORS["bg"])
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            viewport, bg=COLORS["bg"], highlightthickness=0, borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        shell = ttk.Frame(canvas, style="App.TFrame", padding=28)
        shell_window = canvas.create_window((0, 0), window=shell, anchor="nw")

        def resize_content(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_width(event) -> None:
            canvas.itemconfigure(shell_window, width=event.width)

        def scroll(event) -> None:
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        shell.bind("<Configure>", resize_content)
        canvas.bind("<Configure>", resize_width)
        self.window.bind_all("<MouseWheel>", scroll)
        self.window.protocol("WM_DELETE_WINDOW", self._close)
        ttk.Label(shell, text="NETWORK MATCH", style="Title.TLabel").pack(anchor="w")
        ttk.Label(shell, text="TWO COMPUTERS  •  FASTMCP  •  SIGNED MOVES", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 18))
        self._row(shell, "This computer's role", "role", choices=("cop",))
        self._row(shell, "Local MCP port", "port")
        self._row(shell, "Opponent public URL (must end /mcp)", "opponent")
        self._row(shell, "This peer's public tunnel URL", "public")
        self._row(shell, "Shared game ID", "game")
        self._row(shell, "Sub-game number", "subgame")
        self._section_label(shell, "TEAM 1 - THIS COMPUTER")
        self._row(shell, "Team 1 name", "team1_name")
        self._row(shell, "Team 1 - member 1", "team1_member1")
        self._row(shell, "Team 1 - member 2", "team1_member2")
        self._row(shell, "Team 1 Cop / Thief repository URLs", "own_cop", second_key="own_thief")
        self._section_label(shell, "TEAM 2 - OPPONENT")
        self._row(shell, "Team 2 name", "team2_name")
        self._row(shell, "Team 2 - member 1", "team2_member1")
        self._row(shell, "Team 2 - member 2", "team2_member2")
        self._row(
            shell, "Team 2 Cop / Thief repository URLs", "opponent_cop",
            second_key="opponent_thief",
        )
        self._row(shell, "Shared match secret (same on both computers)", "secret", secret=True)
        self._row(shell, "JSON output directory", "output")
        tk.Checkbutton(
            shell, text="Automatically email result JSON after mutual match completion",
            variable=self.vars["email"], bg=COLORS["bg"], fg=COLORS["text"],
            selectcolor=COLORS["surface_alt"], activebackground=COLORS["bg"],
            activeforeground=COLORS["text"], font=(FONT, 9), command=self._toggle_email,
        ).pack(anchor="w", pady=12)
        ttk.Label(shell, text="Result email recipient", style="Subtitle.TLabel").pack(
            anchor="w", pady=(0, 3),
        )
        self.email_entry = tk.Entry(
            shell, textvariable=self.vars["email_recipient"], bg=COLORS["surface_alt"],
            fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat",
            font=(FONT, 10), disabledbackground=COLORS["surface"],
            disabledforeground=COLORS["muted"],
        )
        self.email_entry.pack(fill="x", ipady=5)
        self._toggle_email()
        tk.Label(
            shell,
            text="Run an ngrok/Localtonet tunnel to the local port. Give your public /mcp URL to the opponent, and paste their URL above.",
            bg=COLORS["surface"], fg=COLORS["muted"], wraplength=650, justify="left", padx=14, pady=12,
        ).pack(fill="x", pady=(6, 18))
        buttons = ttk.Frame(shell, style="App.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="CANCEL", style="Secondary.TButton", command=self._close).pack(side="left")
        self.start_button = ttk.Button(buttons, text="START NETWORK PEER →", style="Accent.TButton", command=self._start)
        self.start_button.pack(side="right")
        self.window.update_idletasks()
        self.window.deiconify()
        self.window.lift()
        self.window.grab_set()

    def _close(self) -> None:
        self.window.unbind_all("<MouseWheel>")
        if self.window.grab_current() is self.window:
            self.window.grab_release()
        self.window.destroy()

    def _toggle_email(self) -> None:
        state = "normal" if self.vars["email"].get() else "disabled"
        self.email_entry.configure(state=state)

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

    def _start(self) -> None:
        try:
            role = AgentRole(self.vars["role"].get())
            port = int(self.vars["port"].get())
            if not 1 <= port <= 65535:
                raise ValueError("local port must be between 1 and 65535")
            opponent = validate_mcp_url(self.vars["opponent"].get())
            public = validate_mcp_url(self.vars["public"].get())
            game_id = self.vars["game"].get().strip()
            if not game_id:
                raise ValueError("game ID is required")
            subgame = int(self.vars["subgame"].get())
            required = (
                "team1_name", "team1_member1", "team1_member2", "team2_name",
                "team2_member1", "team2_member2", "own_cop", "own_thief",
                "opponent_cop", "opponent_thief", "secret",
            )
            missing = [key for key in required if not self.vars[key].get().strip()]
            if missing:
                raise ValueError("team identity, all four repository URLs, and shared secret are required")
            recipient = self.vars["email_recipient"].get().strip()
            if self.vars["email"].get() and (
                "@" not in recipient or recipient.startswith("@") or recipient.endswith("@")
            ):
                raise ValueError("enter a valid result email recipient")
        except ValueError as exc:
            messagebox.showerror("Invalid network setup", str(exc), parent=self.window)
            return
        self.result = NetworkMatchSettings(
            role=role, local_port=port, opponent_url=opponent, public_url=public,
            game_id=game_id, sub_game_number=subgame,
            shared_config=self.project_root / "config" / "game.json",
            output_dir=Path(self.vars["output"].get()),
            team_name=self.vars["team1_name"].get().strip(),
            members=(
                self.vars["team1_member1"].get().strip(),
                self.vars["team1_member2"].get().strip(),
            ),
            opponent_team_name=self.vars["team2_name"].get().strip(),
            opponent_members=(
                self.vars["team2_member1"].get().strip(),
                self.vars["team2_member2"].get().strip(),
            ),
            own_cop_repo=self.vars["own_cop"].get().strip(),
            own_thief_repo=self.vars["own_thief"].get().strip(),
            opponent_cop_repo=self.vars["opponent_cop"].get().strip(),
            opponent_thief_repo=self.vars["opponent_thief"].get().strip(),
            shared_key=self.vars["secret"].get().encode(),
            email_mode="real" if self.vars["email"].get() else "dry_run",
            email_recipient=recipient or DEFAULT_REPORT_EMAIL,
            credentials_path=self.project_root / "credentials.json",
            token_path=self.project_root / "token.json",
        )
        self._close()

    def show(self) -> NetworkMatchSettings | None:
        self.window.wait_window()
        return self.result
