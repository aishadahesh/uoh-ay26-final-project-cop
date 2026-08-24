"""Shared fixtures for the submission-artifact test modules: a stub identity,
agreed terms, a turn record, and a complete six-sub-game bundle.

Extracted when `test_submission_artifacts.py` was split by theme."""

import hashlib
import json

from police_thief.services.submission_artifacts import (
    canonical_bytes,
    finalize_submission_bundle,
    public_participant,
)


def _identity(group_id):
    return {
        "group_id": group_id,
        "group_name": group_id,
        "members": [f"{group_id}-one", f"{group_id}-two"],
        "repos": {
            "cop": f"https://github.com/{group_id}/cop",
            "thief": f"https://github.com/{group_id}/thief",
        },
        "mcp_servers": {"police": f"https://{group_id}.example/mcp"},
        "llm_model": "gemini-test",
        "spec": {"os": "test", "cpu_cores": 4, "ram_gb": 8},
        "git_commit_hash": ("a" if group_id == "alpha" else "b") * 40,
        "protocol": {"version": "3.0.0"},
    }


def _terms():
    return {
        "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1,
        "emit_intensity": 0.9, "min_center_intensity": 0.5,
        "max_steps": 35, "barriers_max": 14, "setting": "New York",
        "hint_max_words": 15, "axis_origin_corner": "top-left",
        "axis_start_index": 0, "thief_start": [3, 3],
        "cop_start": [0, 0], "num_games": 2,
    }


def _record(step, role, move):
    payload = {
        "step": step, "role": role, "state": {"row": 0, "col": 0},
        "position": [0, 1], "move": move, "intent": True, "hint": "public",
    }
    nonce = f"nonce-{step}-{role}"
    commit = hashlib.sha256(canonical_bytes(payload) + b"|" + nonce.encode()).hexdigest()
    return {"payload": payload, "nonce": nonce, "h_commit": commit}


def _bundle(tmp_path, scores=None):
    participants = {
        key: public_participant(_identity(key)) for key in ("alpha", "beta")
    }
    rows = []
    for number in (1, 2):
        log_path = tmp_path / f"log_G1_g{number:02d}.json"
        log_path.write_text(
            json.dumps([_record(number, "thief", "E"), _record(number, "police", "S")]),
            encoding="utf-8",
        )
        rows.append({
            "sub_game_number": number,
            "roles": {"alpha": "cop" if number == 1 else "thief", "beta": "thief" if number == 1 else "cop"},
            "started_at": f"2026-08-06T10:0{number}:00+03:00",
            "ended_at": f"2026-08-06T10:0{number}:10+03:00",
            "outcome": "capture" if number == 1 else "survival",
            "score": (
                scores[number - 1] if scores
                else {"alpha": 20 if number == 1 else 10, "beta": 5}
            ),
            "tokens": {"alpha": 100, "beta": 200},
            "mutual_sign_off": True,
            "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
        })
    series = {
        "num_games": 2,
        "sub_games": rows,
        "consensus_confirmed": True,
    }
    return finalize_submission_bundle(
        tmp_path, game_id="G1", terms=_terms(), participants=participants,
        series_result=series, game_started_at="2026-08-06T10:00:00+03:00",
        token_budget=200000,
    )
