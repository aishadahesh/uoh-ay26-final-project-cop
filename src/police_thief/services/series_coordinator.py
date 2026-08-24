"""OS-process coordinator for an alternating multi-game network series."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from police_thief.services.series_state import (
    _archive_incomplete_attempt,
    _completed_result,
    _load_state,
    _save_state,
    mark_subgame_finished,
)
from police_thief.shared.constants import AgentRole
from police_thief.shared.game_config import load_match_parameters

__all__ = ["mark_subgame_finished", "role_for_series_game", "run_series"]


def role_for_series_game(first_role: AgentRole, sub_game_number: int) -> AgentRole:
    if sub_game_number < 1:
        raise ValueError("sub_game_number must be positive")
    if sub_game_number % 2 == 1:
        return first_role
    return AgentRole.THIEF if first_role is AgentRole.COP else AgentRole.COP



def run_series(
    *,
    current_role: AgentRole,
    first_role: AgentRole,
    current_repo: Path,
    sibling_repo: Path,
    config_root: Path,
    output_dir: Path,
    game_id: str,
    first_sub_game: int,
) -> Path:
    """Run each role in a fresh process and keep all public artifacts together."""
    params = load_match_parameters(config_root / "game.json")
    num_games = params.network_league.num_games
    if not 1 <= first_sub_game <= num_games:
        raise ValueError(f"first sub-game must be between 1 and {num_games}")
    if not sibling_repo.is_dir():
        raise RuntimeError(f"sibling repository not found: {sibling_repo}")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / f"series_{game_id}_state.json"
    state = _load_state(state_path, game_id)
    start_number = first_sub_game
    for number in range(first_sub_game, num_games + 1):
        result = _completed_result(output_dir, game_id, number)
        if result is None:
            start_number = number
            break
        result_path = output_dir / f"result_{game_id}_g{number:02d}.json"
        completed_at = datetime.fromtimestamp(
            result_path.stat().st_mtime,
        ).astimezone().isoformat()
        state.setdefault("games", {}).setdefault(str(number), {}).update({
            "role": (
                "police"
                if role_for_series_game(first_role, number) is AgentRole.COP
                else "thief"
            ),
            "started_at": state.get("series_started_at", completed_at),
            "ended_at": completed_at,
        })
        start_number = number + 1
    _save_state(state_path, state)

    if start_number > first_sub_game:
        print(
            f"Resuming {game_id}: mutually signed artifacts verified through sub-game "
            f"{start_number - 1}"
        )
    if start_number > num_games:
        final_path = output_dir / f"result_{game_id}.json"
        if final_path.is_file():
            print(f"Series already complete -- final result saved to {final_path}")
            return final_path
        start_number = num_games
        print(
            "All sub-games exist but final consensus is missing; replaying only "
            f"sub-game {num_games} so the live endpoint can complete finalization"
        )

    for number in range(start_number, num_games + 1):
        _archive_incomplete_attempt(output_dir, game_id, number)
        role = role_for_series_game(first_role, number)
        repo = current_repo if role is current_role else sibling_repo
        role_name = "police" if role is AgentRole.COP else "thief"
        state = _load_state(state_path, game_id)
        state.setdefault("games", {})[str(number)] = {
            "role": role_name,
            "started_at": datetime.now().astimezone().isoformat(),
        }
        _save_state(state_path, state)
        print(f"Starting sub-game {number}/{num_games} as {role_name.upper()} from {repo}")
        command = [
            sys.executable, "-m", "police_thief", "peer", "--role", role_name,
            "--config-root", str(repo / "config"),
            "--single-subgame", "--sub-game-number", str(number),
            "--output-directory", str(output_dir),
            "--series-state", str(state_path),
            "--series-first-role", (
                "police" if first_role is AgentRole.COP else "thief"
            ),
        ]
        if number == num_games:
            command.append("--finalize-series")
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = str(repo / "src") + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
        completed = subprocess.run(
            command, cwd=repo, env=environment, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"sub-game {number} ({role_name}) exited with code "
                f"{completed.returncode}; series stopped without fabricating later results"
            )

    final_path = output_dir / f"result_{game_id}.json"
    if not final_path.is_file():
        raise RuntimeError(f"six games completed but aggregate result is missing: {final_path}")
    print(f"Six-game series complete -- final result saved to {final_path}")
    return final_path
