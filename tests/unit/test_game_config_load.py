"""Loading match parameters: the real shipped config, a valid synthetic one,
and the errors raised for missing or unsupported input.

Split by theme out of the original `test_game_config.py`."""

import json
from pathlib import Path

import pytest

from police_thief.domain.board import Position
from police_thief.shared.game_config import GameConfigError, load_match_parameters
from tests.unit.game_config_fixtures import VALID_CONFIG, _write


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


def test_load_match_parameters_raises_on_missing_file(tmp_path):
    with pytest.raises(GameConfigError, match="missing shared match config"):
        load_match_parameters(tmp_path / "does_not_exist.json")


def test_load_match_parameters_raises_on_missing_section(tmp_path):
    broken = {k: v for k, v in VALID_CONFIG.items() if k != "scoring"}
    with pytest.raises(GameConfigError, match="malformed shared config"):
        load_match_parameters(_write(tmp_path, broken))


def test_load_match_parameters_rejects_unsupported_schema_version(tmp_path):
    data = json.loads(json.dumps(VALID_CONFIG))
    data["schema_version"] = "99.99"
    with pytest.raises(GameConfigError, match="unsupported schema_version"):
        load_match_parameters(_write(tmp_path, data))
