"""The pre-game conformance schema: protected keys, rule profile, the TOML
section vocabulary, and the small issue-reporting primitives.

Split out of pregame_validation.py, which re-exports what callers use."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

VALIDATOR_VERSION = "1.0.0"

_SCHEMA: dict[str, dict[str, type | tuple[type, ...]]] = {
    "board_and_agents": {
        "grid_size": int, "num_agents": int, "thief_start": list,
        "cop_start": list, "axis_origin_corner": str, "axis_start_index": int,
    },
    "movement_and_barriers": {
        "move_set": list, "max_barriers": int, "max_moves": int,
        "survival_threshold": int,
    },
    "scoring": {
        "capture_cop": int, "capture_thief": int, "survival_cop": int,
        "survival_thief": int, "tie_score": int, "technical_loss": int,
    },
    "pheromones": {
        "pheromone_center_intensity": (int, float),
        "pheromone_min_center_intensity": (int, float),
        "pheromone_decay": (int, float), "pheromone_grid_size": int,
    },
    "world": {"map_area": str, "hint_max_words": int},
    "network_and_league": {
        "response_timeout_sec": (int, float),
        "watchdog_timeout_sec": (int, float), "num_games": int,
        "diversity_reward": int, "min_games_to_pass": int,
        "max_games_per_team": int, "token_budget_per_series": int,
    },
    "rate_limiter_gatekeeper": {
        "requests_per_minute": int, "concurrent_requests": int,
        "retry_backoff_sec": (int, float), "max_retries": int,
        "queue_depth": int,
    },
}

_TOP_LEVEL = {"schema_version", "agreed_between", *_SCHEMA}

_PROTECTED: dict[str, Any] = {
    "schema_version": "1.2",
    "board_and_agents.grid_size": 7,
    "board_and_agents.num_agents": 2,
    "board_and_agents.thief_start": [3, 3],
    "board_and_agents.cop_start": [0, 0],
    "board_and_agents.axis_origin_corner": "top-left",
    "board_and_agents.axis_start_index": 0,
    "movement_and_barriers.move_set": ["N", "S", "E", "W", "STAY"],
    "movement_and_barriers.max_barriers": 14,
    "movement_and_barriers.max_moves": 35,
    "movement_and_barriers.survival_threshold": 35,
    "scoring.capture_cop": 20, "scoring.capture_thief": 5,
    "scoring.survival_cop": 5, "scoring.survival_thief": 10,
    "scoring.tie_score": 2, "scoring.technical_loss": 0,
    "pheromones.pheromone_center_intensity": 0.9,
    "pheromones.pheromone_min_center_intensity": 0.5,
    "pheromones.pheromone_decay": 0.1,
    "pheromones.pheromone_grid_size": 5,
    "world.hint_max_words": 15,
    "network_and_league.diversity_reward": 10,
    "network_and_league.min_games_to_pass": 2,
    "network_and_league.max_games_per_team": 10,
    "network_and_league.token_budget_per_series": 200000,
    "rate_limiter_gatekeeper.requests_per_minute": 30,
    "rate_limiter_gatekeeper.concurrent_requests": 2,
    "rate_limiter_gatekeeper.retry_backoff_sec": 5,
    "rate_limiter_gatekeeper.max_retries": 3,
    "rate_limiter_gatekeeper.queue_depth": 100,
}

_RULE_PROFILE = {
    "capture": "same-cell-or-thief-boxed-in",
    "information_model": "local-truth-commit-reveal",
    "movement": ["N", "S", "E", "W", "STAY"],
    "turn_order": "thief-then-police",
}

_TOML_TOP = {"version", "game", "network", "strategy", "trash_talk", "llm", "email"}

_TOML_GAME = {"group_name", "group_id", "sub_game_number", "members", "repos"}

_TOML_NETWORK = {"my_port", "opponent_url", "turn_timeout_seconds"}

_PRIVATE_SECTIONS = {"strategy", "trash_talk", "llm", "email"}

_GITHUB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/#]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class ValidationIssue:
    scope: str
    file: str
    field: str
    code: str
    expected: Any
    received: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _at(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _issue(scope: str, file: str, field: str, code: str, expected: Any, received: Any) -> ValidationIssue:
    return ValidationIssue(scope, file, field, code, expected, received)


def _strict_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    if isinstance(value, bool) and expected is not bool:
        return False
    return isinstance(value, expected)
