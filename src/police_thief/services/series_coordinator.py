"""OS-process coordinator for an alternating multi-game network series."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from police_thief.shared.constants import AgentRole
from police_thief.shared.game_config import load_match_parameters

SUBGAME_LAUNCH_ATTEMPTS = 3
SUBGAME_RELAUNCH_DELAY_SECONDS = 3.0


def role_for_series_game(first_role: AgentRole, sub_game_number: int) -> AgentRole:
    if sub_game_number < 1:
        raise ValueError("sub_game_number must be positive")
    if sub_game_number % 2 == 1:
        return first_role
    return AgentRole.THIEF if first_role is AgentRole.COP else AgentRole.COP


def _load_state(path: Path, game_id: str) -> dict:
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if value.get("game_id") == game_id:
            return value
    return {
        "game_id": game_id,
        "series_started_at": datetime.now().astimezone().isoformat(),
        "games": {},
    }


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _completed_result(output_dir: Path, game_id: str, number: int) -> dict | None:
    result_path = output_dir / f"result_{game_id}_g{number:02d}.json"
    log_path = output_dir / f"log_{game_id}_g{number:02d}.json"
    if not result_path.is_file() or not log_path.is_file():
        return None
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        result.get("game_id") != game_id
        or int(result.get("sub_game_number", -1)) != number
        or result.get("outcome") not in {"capture", "survival", "technical_loss", "timeout"}
        or result.get("mutual_sign_off") is not True
    ):
        return None
    return result


def _load_subgame_result(output_dir: Path, game_id: str, number: int) -> dict:
    result_path = output_dir / f"result_{game_id}_g{number:02d}.json"
    if not result_path.is_file():
        raise RuntimeError(
            f"sub-game {number} finished but result file is missing: {result_path}"
        )
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"sub-game {number} wrote an unreadable result file") from exc
    if result.get("game_id") != game_id or int(result.get("sub_game_number", -1)) != number:
        raise RuntimeError(f"sub-game {number} wrote a result for a different game")
    return result


def _archive_incomplete_attempt(output_dir: Path, game_id: str, number: int) -> None:
    names = (
        f"config_{game_id}_g{number:02d}.json",
        f"log_{game_id}_g{number:02d}.json",
        f"result_{game_id}_g{number:02d}.json",
    )
    existing = [output_dir / name for name in names if (output_dir / name).is_file()]
    if not existing:
        return
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")
    archive = output_dir / "attempts" / f"{game_id}_g{number:02d}_{stamp}"
    archive.mkdir(parents=True, exist_ok=False)
    for source in existing:
        shutil.copy2(source, archive / source.name)
    print(f"Archived prior incomplete sub-game {number} artifacts to {archive}")


def mark_subgame_finished(path: Path, game_id: str, sub_game_number: int) -> None:
    state = _load_state(path, game_id)
    row = state.setdefault("games", {}).setdefault(str(sub_game_number), {})
    row["ended_at"] = datetime.now().astimezone().isoformat()
    _save_state(path, state)


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
        role = role_for_series_game(first_role, number)
        repo = current_repo if role is current_role else sibling_repo
        role_name = "police" if role is AgentRole.COP else "thief"
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
        result = None
        last_returncode = 0
        for attempt in range(1, SUBGAME_LAUNCH_ATTEMPTS + 1):
            _archive_incomplete_attempt(output_dir, game_id, number)
            state = _load_state(state_path, game_id)
            state.setdefault("games", {})[str(number)] = {
                "role": role_name,
                "started_at": datetime.now().astimezone().isoformat(),
                "attempt": attempt,
            }
            _save_state(state_path, state)
            suffix = (
                ""
                if attempt == 1
                else f" (launch attempt {attempt}/{SUBGAME_LAUNCH_ATTEMPTS})"
            )
            print(
                f"Starting sub-game {number}/{num_games} as "
                f"{role_name.upper()} from {repo}{suffix}"
            )
            completed = subprocess.run(
                command, cwd=repo, env=environment, check=False,
            )
            last_returncode = completed.returncode
            result_path = output_dir / f"result_{game_id}_g{number:02d}.json"
            if result_path.is_file():
                result = _load_subgame_result(output_dir, game_id, number)
                break
            if attempt < SUBGAME_LAUNCH_ATTEMPTS:
                print(
                    f"sub-game {number} ({role_name}) exited with code "
                    f"{completed.returncode} before writing a result; relaunching "
                    f"in {SUBGAME_RELAUNCH_DELAY_SECONDS:g}s"
                )
                time.sleep(SUBGAME_RELAUNCH_DELAY_SECONDS)
                continue
            if completed.returncode != 0:
                raise RuntimeError(
                    f"sub-game {number} ({role_name}) exited with code "
                    f"{completed.returncode} after {SUBGAME_LAUNCH_ATTEMPTS} "
                    "launch attempts; series stopped without fabricating later results"
                )
            raise RuntimeError(
                f"sub-game {number} ({role_name}) finished without writing "
                f"a result after {SUBGAME_LAUNCH_ATTEMPTS} launch attempts"
            )
        if result is None:
            raise RuntimeError(
                f"sub-game {number} ({role_name}) produced no result; "
                f"last child exit code was {last_returncode}"
            )
        if result.get("outcome") == "technical_loss" or result.get("mutual_sign_off") is not True:
            raise RuntimeError(
                f"sub-game {number} ({role_name}) ended as "
                f"{result.get('outcome')!r} with mutual_sign_off="
                f"{result.get('mutual_sign_off')!r}; series stopped for diagnosis/replay"
            )

    final_path = output_dir / f"result_{game_id}.json"
    if not final_path.is_file():
        raise RuntimeError(f"six games completed but aggregate result is missing: {final_path}")
    print(f"Six-game series complete -- final result saved to {final_path}")
    return final_path
