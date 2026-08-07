"""Unit tests for cryptographically locking the shared config (Chapter 5)."""

import json
from pathlib import Path

from police_thief.shared.game_config import config_fingerprint

_BASE_CONFIG = json.loads(Path("config/game.json").read_text(encoding="utf-8"))


def _write(directory: Path, data: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "game.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_fingerprint_is_a_64_character_hex_digest(tmp_path):
    fp = config_fingerprint(_write(tmp_path, _BASE_CONFIG))
    assert len(fp) == 64
    assert all(ch in "0123456789abcdef" for ch in fp)


def test_fingerprint_is_stable_for_identical_content(tmp_path):
    a = config_fingerprint(_write(tmp_path / "a", _BASE_CONFIG))
    b = config_fingerprint(_write(tmp_path / "b", _BASE_CONFIG))
    assert a == b


def test_fingerprint_is_independent_of_key_order(tmp_path):
    """Two byte-different-but-semantically-identical files must fingerprint
    the same way -- canonical serialization, not raw bytes, is hashed.
    """
    reordered = dict(reversed(list(_BASE_CONFIG.items())))
    original_fp = config_fingerprint(_write(tmp_path / "a", _BASE_CONFIG))
    reordered_fp = config_fingerprint(_write(tmp_path / "b", reordered))
    assert original_fp == reordered_fp


def test_fingerprint_changes_if_the_fixed_pheromone_decay_changes(tmp_path):
    """The whole point of Sec. 4.2.6's "cryptographic locking": any change
    to scent parameters -- even ones the loader itself treats as fixed --
    is detectable via the fingerprint before load_match_parameters is
    even called.
    """
    tampered = json.loads(json.dumps(_BASE_CONFIG))
    tampered["pheromones"]["pheromone_decay"] = 0.20
    original_fp = config_fingerprint(_write(tmp_path / "a", _BASE_CONFIG))
    tampered_fp = config_fingerprint(_write(tmp_path / "b", tampered))
    assert original_fp != tampered_fp


def test_fingerprint_changes_if_any_board_parameter_changes(tmp_path):
    tampered = json.loads(json.dumps(_BASE_CONFIG))
    tampered["board_and_agents"]["grid_size"] = 9
    original_fp = config_fingerprint(_write(tmp_path / "a", _BASE_CONFIG))
    tampered_fp = config_fingerprint(_write(tmp_path / "b", tampered))
    assert original_fp != tampered_fp
