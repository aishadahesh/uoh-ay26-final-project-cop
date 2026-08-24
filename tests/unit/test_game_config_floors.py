"""The mandatory floors and fixed values: rate limiter, scent, grid size,
barrier count, and the agreed series size.

Split by theme out of the original `test_game_config.py`."""

import json

import pytest

from police_thief.shared.game_config import GameConfigError, load_match_parameters
from tests.unit.game_config_fixtures import VALID_CONFIG, _write


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


def test_load_match_parameters_rejects_grid_size_below_floor(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["board_and_agents"]["grid_size"] = 5
    with pytest.raises(GameConfigError, match="below the mandatory floor"):
        load_match_parameters(_write(tmp_path, data))


def test_load_match_parameters_rejects_max_barriers_below_floor(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["movement_and_barriers"]["max_barriers"] = 5
    with pytest.raises(GameConfigError, match="below the mandatory floor"):
        load_match_parameters(_write(tmp_path, data))
