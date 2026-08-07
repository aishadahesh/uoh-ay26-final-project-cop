"""Unit tests for the shared config/game.json loader (Chapter 3)."""

import json
from pathlib import Path

import pytest

from police_thief.domain.board import Position
from police_thief.shared.game_config import GameConfigError, load_match_parameters

VALID_CONFIG: dict = {
    "schema_version": "1.00",
    "agreed_between": ["cop", "thief"],
    "board_and_agents": {
        "grid_size": 7,
        "num_agents": 2,
        "thief_start": [3, 3],
        "cop_start": [0, 0],
        "axis_origin_corner": "top-left",
        "axis_start_index": 0,
    },
    "movement_and_barriers": {
        "move_set": ["N", "S", "E", "W", "STAY"],
        "max_barriers": 14,
        "max_moves": 35,
        "survival_threshold": 35,
    },
    "scoring": {
        "capture_cop": 20,
        "capture_thief": 5,
        "survival_cop": 5,
        "survival_thief": 10,
        "tie_score": 2,
        "technical_loss": 0,
    },
    "pheromones": {
        "pheromone_center_intensity": 0.9,
        "pheromone_min_center_intensity": 0.5,
        "pheromone_decay": 0.10,
        "pheromone_grid_size": 5,
    },
    "world": {
        "map_area": "New York",
        "hint_max_words": 15,
    },
    "network_and_league": {
        "response_timeout_sec": 30,
        "watchdog_timeout_sec": 60,
        "num_games": 6,
        "diversity_reward": 10,
        "min_games_to_pass": 2,
        "max_games_per_team": 10,
        "token_budget_per_series": 200000,
    },
    "rate_limiter_gatekeeper": {
        "requests_per_minute": 30,
        "concurrent_requests": 2,
        "retry_backoff_sec": 5,
        "max_retries": 3,
        "queue_depth": 100,
    },
}


def _write(tmp_path, data: dict):
    path = tmp_path / "game.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_match_parameters_reads_the_real_shipped_config():
    params = load_match_parameters(Path("config/game.json"))
    assert params.board.grid_size == 7
    assert params.cop_start == Position(0, 0)
    assert params.thief_start == Position(3, 3)


def test_load_match_parameters_parses_a_valid_config(tmp_path):
    params = load_match_parameters(_write(tmp_path, VALID_CONFIG))
    assert params.board.grid_size == 7
    assert params.board.max_barriers == 14
    assert params.scoring.capture_cop == 20
    assert params.max_moves == 35
    assert params.survival_threshold == 35
    assert params.scent.center_intensity == 0.9
    assert params.scent.min_center_intensity == 0.5
    assert params.scent.decay_rate == 0.10
    assert params.scent.field_size == 5
    assert params.world.map_area == "New York"
    assert params.world.hint_max_words == 15
    assert params.network_league.response_timeout_sec == 30
    assert params.network_league.watchdog_timeout_sec == 60
    assert params.network_league.token_budget_per_series == 200000
    assert params.rate_limiter.requests_per_minute == 30
    assert params.rate_limiter.queue_depth == 100


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("diversity_reward", 5),
        ("min_games_to_pass", 1),
        ("max_games_per_team", 20),
    ],
)
def test_load_match_parameters_rejects_non_fixed_network_league_values(tmp_path, field, bad_value):
    """App. F Table 18: these league-policy fields remain fixed."""
    data = json.loads(json.dumps(VALID_CONFIG))
    data["network_and_league"][field] = bad_value
    with pytest.raises(GameConfigError, match="must be exactly"):
        load_match_parameters(_write(tmp_path, data))


@pytest.mark.parametrize("num_games", [1, 2, 6, 10])
def test_load_match_parameters_accepts_agreed_series_size(tmp_path, num_games):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["network_and_league"]["num_games"] = num_games
    assert load_match_parameters(_write(tmp_path, data)).network_league.num_games == num_games


@pytest.mark.parametrize("num_games", [0, 11])
def test_load_match_parameters_rejects_series_size_outside_allowed_range(tmp_path, num_games):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["network_and_league"]["num_games"] = num_games
    with pytest.raises(GameConfigError, match="num_games must be between 1"):
        load_match_parameters(_write(tmp_path, data))


@pytest.mark.parametrize(
    ("field", "bad_value", "floor_name"),
    [
        ("requests_per_minute", 10, "requests_per_minute"),
        ("concurrent_requests", 1, "concurrent_requests"),
        ("retry_backoff_sec", 1, "retry_backoff_sec"),
        ("max_retries", 1, "max_retries"),
        ("queue_depth", 10, "queue_depth"),
    ],
)
def test_load_match_parameters_rejects_rate_limiter_values_below_floor(
    tmp_path, field, bad_value, floor_name
):
    """App. F Table 19: every rate-limiter field is a MINIMUM, never lowered."""
    data = json.loads(json.dumps(VALID_CONFIG))
    data["rate_limiter_gatekeeper"][field] = bad_value
    with pytest.raises(GameConfigError, match="below the mandatory floor"):
        load_match_parameters(_write(tmp_path, data))


def test_load_match_parameters_allows_raising_rate_limiter_values_above_floor(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["rate_limiter_gatekeeper"]["requests_per_minute"] = 60
    params = load_match_parameters(_write(tmp_path, data))
    assert params.rate_limiter.requests_per_minute == 60


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("pheromone_center_intensity", 0.5),
        ("pheromone_min_center_intensity", 0.4),
        ("pheromone_decay", 0.20),
        ("pheromone_grid_size", 7),
    ],
)
def test_load_match_parameters_rejects_non_fixed_scent_values(tmp_path, field, bad_value):
    """Sec. 4.2: scent params are FIXED, not minimums -- any deviation is rejected."""
    data = json.loads(json.dumps(VALID_CONFIG))
    data["pheromones"][field] = bad_value
    with pytest.raises(GameConfigError, match="must be exactly"):
        load_match_parameters(_write(tmp_path, data))


def test_load_match_parameters_raises_on_missing_file(tmp_path):
    with pytest.raises(GameConfigError, match="missing shared match config"):
        load_match_parameters(tmp_path / "does_not_exist.json")


def test_load_match_parameters_raises_on_missing_section(tmp_path):
    broken = {k: v for k, v in VALID_CONFIG.items() if k != "scoring"}
    with pytest.raises(GameConfigError, match="malformed shared config"):
        load_match_parameters(_write(tmp_path, broken))


def test_load_match_parameters_rejects_grid_size_below_floor(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["board_and_agents"]["grid_size"] = 5
    with pytest.raises(GameConfigError, match="below the mandatory floor"):
        load_match_parameters(_write(tmp_path, data))


def test_load_match_parameters_rejects_unsupported_schema_version(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["schema_version"] = "99.99"
    with pytest.raises(GameConfigError, match="unsupported schema_version"):
        load_match_parameters(_write(tmp_path, data))


def test_load_match_parameters_rejects_max_barriers_below_floor(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["movement_and_barriers"]["max_barriers"] = 5
    with pytest.raises(GameConfigError, match="below the mandatory floor"):
        load_match_parameters(_write(tmp_path, data))


def test_load_match_parameters_rejects_identical_start_positions(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["board_and_agents"]["thief_start"] = data["board_and_agents"]["cop_start"]
    with pytest.raises(GameConfigError, match="same cell"):
        load_match_parameters(_write(tmp_path, data))


def test_load_match_parameters_rejects_out_of_bounds_cop_start(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["board_and_agents"]["cop_start"] = [99, 99]
    with pytest.raises(GameConfigError, match="outside the"):
        load_match_parameters(_write(tmp_path, data))


def test_load_match_parameters_rejects_out_of_bounds_thief_start(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["board_and_agents"]["thief_start"] = [-1, 0]
    with pytest.raises(GameConfigError, match="outside the"):
        load_match_parameters(_write(tmp_path, data))
