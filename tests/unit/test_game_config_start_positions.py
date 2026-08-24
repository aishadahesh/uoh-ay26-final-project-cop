"""Agreed start positions must be distinct and inside the board.

Split by theme out of the original `test_game_config.py`."""

import json

import pytest

from police_thief.shared.game_config import GameConfigError, load_match_parameters
from tests.unit.game_config_fixtures import VALID_CONFIG, _write


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
