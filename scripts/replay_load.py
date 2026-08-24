"""Turning a log file into an ordered list of replay frames."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# This script is run by path, not imported as a package, so its own
# directory has to be importable before the sibling modules below.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_events import _entity_positions, _events, _finalize_frames
from replay_model import Entity, ReplayFrame, UnsupportedLogError, _role, parse_position
from replay_records import _find_mapping, _records_from_root, _verify_record  # noqa: E402


def load_replay(path: Path) -> tuple[list[ReplayFrame], int, str]:
    """Parse a supported JSON log and return normalized replay frames."""
    try:
        root = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise UnsupportedLogError(f"input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise UnsupportedLogError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    records, metadata = _records_from_root(root)
    positions: dict[str, tuple[int, int]] = {}
    known_obstacles: set[tuple[int, int]] = set()
    frames: list[ReplayFrame] = []
    seen_coordinates: list[tuple[int, int]] = []
    recorded_board_sizes: list[int] = []
    filename_match = re.search(r"(?:log|result)_([^_]+)(?:_g\d+)?$", path.stem, re.I)
    inferred_game_id = filename_match.group(1) if filename_match else path.stem
    game_id = str(metadata.get("game_id", metadata.get("id", inferred_game_id)))
    static_sources = [metadata, metadata.get("board", {}) if isinstance(metadata, dict) else {}]

    for index, record in enumerate(records):
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        # Official network logs are chronological and begin with the Thief.
        # Some peer implementations omit ``role`` from otherwise valid sealed
        # payloads, so use the protocol turn order only when no explicit role
        # is available.
        actor = _role(record, "thief" if index % 2 == 0 else "cop")
        move = str(payload.get("move", record.get("move", "?"))).upper()
        state_value = payload.get("state", record.get("state"))
        after = (
            parse_position(payload.get("position"))
            or parse_position(record.get("position"))
            or parse_position(payload.get("after"))
            or (parse_position(state_value) if isinstance(state_value, str) else None)
        )
        before = positions.get(actor)
        if isinstance(state_value, str):
            grid_match = re.search(r"grid\s*=\s*(\d+)(?:\s*[xX]\s*\d+)?", state_value)
            if grid_match:
                recorded_board_sizes.append(int(grid_match.group(1)))
        # Dict state snapshots in native logs describe the pre-move cell.
        # ``grid=...;self=[r,c]`` peer snapshots describe the post-move cell,
        # so derive the first pre-move cell from the declared action instead.
        if before is None and isinstance(state_value, dict):
            before = parse_position(state_value)
        if before is None and after is not None:
            direction = move.removeprefix("MOVE:")
            deltas = {
                "N": (-1, 0),
                "NORTH": (-1, 0),
                "S": (1, 0),
                "SOUTH": (1, 0),
                "E": (0, 1),
                "EAST": (0, 1),
                "W": (0, -1),
                "WEST": (0, -1),
                "STAY": (0, 0),
            }
            delta = deltas.get(direction, (0, 0) if move.startswith("BARRIER:") else None)
            if delta is not None:
                before = after[0] - delta[0], after[1] - delta[1]
        if before is None:
            before = parse_position(state_value)
        if before is None or after is None:
            raise UnsupportedLogError(
                f"step {index + 1} does not provide usable pre/post positions"
            )
        positions.setdefault(actor, before)
        positions[actor] = after
        seen_coordinates.extend((before, after))
        turn_value = payload.get("step", record.get("step", record.get("turn", index + 1)))
        try:
            turn = int(turn_value)
        except (TypeError, ValueError):
            turn = index + 1
        obstacles: set[tuple[int, int]] = set()
        goals: list[Entity] = []
        items: list[Entity] = []
        for source in (*static_sources, payload, record):
            obstacles.update(
                entity.position
                for entity in _entity_positions(
                    source, ("obstacles", "barriers", "blocked", "walls"), "obstacle"
                )
            )
            goals.extend(_entity_positions(source, ("goals", "goal", "targets", "exits"), "goal"))
            items.extend(
                _entity_positions(source, ("gems", "items", "collectibles", "coins"), "item")
            )
        barrier_cell = parse_position(payload.get("barrier_placed")) or parse_position(
            record.get("barrier_placed")
        )
        if barrier_cell is None and move.startswith("BARRIER:"):
            barrier_cell = parse_position(move.split(":", 1)[1])
        if barrier_cell is not None:
            obstacles.add(barrier_cell)
        known_obstacles.update(obstacles)
        obstacles = set(known_obstacles)
        seen_coordinates.extend(obstacles)
        seen_coordinates.extend(entity.position for entity in (*goals, *items))
        scores = _find_mapping(payload, ("scores", "score")) or _find_mapping(
            record, ("scores", "score")
        )
        if not scores:
            scores = {
                key: value
                for key, value in {
                    "cop": payload.get("cop_score", record.get("cop_score")),
                    "thief": payload.get("thief_score", record.get("thief_score")),
                }.items()
                if value is not None
            }
        collected = _find_mapping(
            payload, ("collected", "collected_items", "inventory")
        ) or _find_mapping(record, ("collected", "collected_items", "inventory"))
        commitment = str(record.get("h_commit", record.get("commit", "")))
        frames.append(
            ReplayFrame(
                index=index,
                turn=turn,
                actor=actor,
                move=move,
                before=before,
                after=after,
                positions=dict(positions),
                hint=str(payload.get("hint", record.get("hint", ""))),
                events=_events(record, payload),
                scores=scores,
                collected=collected,
                obstacles=obstacles,
                goals=list(dict.fromkeys(goals)),
                items=list(dict.fromkeys(items)),
                verified=_verify_record(record),
                commitment=commitment,
            )
        )

    board_size = _finalize_frames(frames, metadata, seen_coordinates, recorded_board_sizes)
    return frames, board_size, game_id
