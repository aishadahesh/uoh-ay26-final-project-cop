"""Loads `scripts/visualize_game_log.py` by path and exposes it as a module.

The script is not importable as a package, so it is loaded through an
explicit spec. This lives in one module so the load happens exactly once
per session -- it writes `sys.modules`, and executing a Pillow-backed
module twice in one run is not worth risking.

Extracted when `test_visualize_game_log.py` was split by theme."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "visualize_game_log.py"
SPEC = importlib.util.spec_from_file_location("visualize_game_log", SCRIPT)
assert SPEC and SPEC.loader
visualizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = visualizer
SPEC.loader.exec_module(visualizer)


def _entry(step, role, before, after, move, **extra):
    payload = {
        "step": step,
        "role": role,
        "state": {"row": before[0], "col": before[1]},
        "position": list(after),
        "move": move,
        "intent": True,
        "hint": f"{role} moved {move}",
        **extra,
    }
    return {
        "state": payload["state"],
        "move": move,
        "intent": True,
        "payload": payload,
    }
