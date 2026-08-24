"""Validating the filled-in form and assembling NetworkMatchSettings."""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from police_thief.services.network_match import NetworkMatchSettings
from police_thief.services.network_match_config import (
    DEFAULT_REPORT_EMAIL,
    validate_mcp_url,
)
from police_thief.shared.constants import AgentRole


class _StartMixin:
    """Turns the form into match settings."""

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
