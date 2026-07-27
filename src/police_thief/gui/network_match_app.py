"""Live command center for a cross-computer MCP match."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from contextlib import suppress
from tkinter import messagebox, ttk

from police_thief.gui.theme import COLORS, FONT, MONO_FONT, configure_window, install_styles
from police_thief.services.gemini_agent import GeminiAgentAdvisor
from police_thief.services.mcp_server import build_peer_server, run_peer_server
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings


class NetworkMatchApp:
    def __init__(
        self, master: tk.Misc, settings: NetworkMatchSettings,
        gemini_advisor: GeminiAgentAdvisor,
        on_new_game: Callable[[], bool] | None = None,
    ) -> None:
        self.master = master
        self.settings = settings
        self.on_new_game = on_new_game
        self.runner = NetworkMatchRunner(settings, gemini_advisor)
        self.stop_event = threading.Event()
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.closed = False
        configure_window(master, title="ShadowGrid | MCP Network Arena", min_size=(900, 650))
        install_styles(master)
        self.shell = ttk.Frame(master, style="App.TFrame", padding=26)
        self.shell.pack(fill="both", expand=True)
        self._build()

    def _build(self) -> None:
        header = ttk.Frame(self.shell, style="App.TFrame")
        header.pack(fill="x", pady=(0, 18))
        title = ttk.Frame(header, style="App.TFrame")
        title.pack(side="left")
        ttk.Label(title, text="SHADOWGRID", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="DISTRIBUTED MCP ARENA", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Button(
            header, text="NEW GAME", style="Secondary.TButton", command=self._new_game,
        ).pack(side="right")

        cards = ttk.Frame(self.shell, style="App.TFrame")
        cards.pack(fill="x")
        for label, value in (
            ("ROLE", self.settings.role.value.upper()),
            ("LOCAL ENDPOINT", f"0.0.0.0:{self.settings.local_port}/mcp"),
            ("GAME", f"{self.settings.game_id} / G{self.settings.sub_game_number:02d}"),
        ):
            card = ttk.Frame(cards, style="Card.TFrame", padding=14)
            card.pack(side="left", fill="x", expand=True, padx=5)
            ttk.Label(card, text=label, style="CardText.TLabel").pack(anchor="w")
            ttk.Label(card, text=value, style="CardTitle.TLabel").pack(anchor="w", pady=(4, 0))

        endpoint = ttk.Frame(self.shell, style="Card.TFrame", padding=18)
        endpoint.pack(fill="x", pady=16)
        ttk.Label(endpoint, text="PEER ROUTING", style="CardTitle.TLabel").pack(anchor="w")
        for caption, value in (
            ("SHARE WITH OPPONENT", self.settings.public_url),
            ("OPPONENT URL", self.settings.opponent_url),
        ):
            tk.Label(
                endpoint, text=f"{caption:<22} {value}", bg=COLORS["surface"],
                fg=COLORS["accent"], font=(MONO_FONT, 9), anchor="w",
            ).pack(fill="x", pady=(8, 0))

        console = ttk.Frame(self.shell, style="Card.TFrame", padding=18)
        console.pack(fill="both", expand=True)
        ttk.Label(console, text="SECURE MATCH TELEMETRY", style="CardTitle.TLabel").pack(anchor="w")
        self.status = tk.Label(
            console, text="INITIALIZING PEER", bg=COLORS["surface"], fg=COLORS["warning"],
            font=(FONT, 11, "bold"), anchor="w",
        )
        self.status.pack(fill="x", pady=(8, 10))
        self.log = tk.Text(
            console, bg=COLORS["surface_alt"], fg=COLORS["text"],
            insertbackground=COLORS["text"], relief="flat", state="disabled",
            font=(MONO_FONT, 9), padx=12, pady=12, height=14,
        )
        self.log.pack(fill="both", expand=True)

    def start(self) -> None:
        threading.Thread(target=self._serve, daemon=True, name="mcp-peer-server").start()
        threading.Thread(target=self._run_match, daemon=True, name="network-match").start()
        self.master.after(100, self._drain_events)

    def _serve(self) -> None:
        try:
            server = build_peer_server(
                peer_name=f"{self.settings.role.value}_peer", receive_handler=self.runner.receive,
            )
            self.events.put(("log", f"MCP server listening on port {self.settings.local_port}"))
            run_peer_server(server, host="0.0.0.0", port=self.settings.local_port)
        except Exception as exc:
            self.events.put(("error", f"MCP server failed: {exc}"))

    def _run_match(self) -> None:
        try:
            path = self.runner.run(self.stop_event, lambda text: self.events.put(("log", text)))
            self.events.put(("done", f"Verified result ready: {path}"))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        if self.closed:
            return
        while True:
            try:
                kind, message = self.events.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state="normal")
            self.log.insert("end", f"> {message}\n")
            self.log.see("end")
            self.log.configure(state="disabled")
            if kind == "done":
                self.status.configure(text="MATCH COMPLETE", fg=COLORS["success"])
            elif kind == "error":
                self.status.configure(text="NETWORK MATCH FAILED", fg=COLORS["danger"])
                messagebox.showerror("Network match", message, parent=self.master)
            else:
                self.status.configure(text="PEER ONLINE", fg=COLORS["accent"])
        self.master.after(100, self._drain_events)

    def _new_game(self) -> None:
        if self.on_new_game is not None:
            self.on_new_game()

    def close(self) -> None:
        self.closed = True
        self.stop_event.set()
        with suppress(tk.TclError):
            self.shell.destroy()
