"""On-disk series state: the per-sub-game progress file the coordinator
reads between OS processes, plus archival of incomplete attempts.

Split out of `series_coordinator.py` so the state file's format and the
process-launching logic that consumes it live apart. `series_coordinator`
re-exports `mark_subgame_finished`, which `main.py` imports from there.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

__all__ = [
    "mark_subgame_finished",
]


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
