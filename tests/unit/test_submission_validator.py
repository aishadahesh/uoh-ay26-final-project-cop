"""The submission validator: what it accepts, what it rejects, and the shape
of the errors it reports.

Split by theme out of the original `test_submission_artifacts.py`."""

import hashlib
import json

from police_thief.services.submission_artifacts import (
    canonical_bytes,
    validate_submission_directory,
)
from tests.unit.submission_fixtures import (
    _bundle,
)


def test_validator_accepts_opponent_specific_move_notation(tmp_path):
    _bundle(tmp_path)
    path = tmp_path / "log_G1_g01.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    record = document["records"][0]
    record["payload"]["move"] = "MOVE:E"
    record["commit"] = hashlib.sha256(
        canonical_bytes(record["payload"])
        + b"|"
        + record["nonce"].encode()
    ).hexdigest()
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    errors, _ = validate_submission_directory(tmp_path, "G1")
    assert not any(error.field.endswith("payload.move") for error in errors)


def test_validator_reports_exact_file_field_expected_and_received(tmp_path):
    _bundle(tmp_path)
    path = tmp_path / "config_G1_g02.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sub_game_number"] = 99
    path.write_text(json.dumps(data), encoding="utf-8")
    errors, _ = validate_submission_directory(tmp_path, "G1")
    error = next(item for item in errors if item.field == "sub_game_number")
    assert error.filename == "config_G1_g02.json"
    assert error.expected == 2
    assert error.received == 99


def test_validator_rejects_private_information(tmp_path):
    _bundle(tmp_path)
    path = tmp_path / "result_G1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["api_key"] = "secret"
    path.write_text(json.dumps(data), encoding="utf-8")
    errors, _ = validate_submission_directory(tmp_path, "G1")
    assert any(item.code == "private_information_exposed" for item in errors)


def test_tied_series_totals_carry_the_fixed_tie_credit(tmp_path):
    # Tie Rule (Sec. 9.2.8-9.2.9 / Appendix F Table 17 row 5): a tied
    # cumulative series credits each side +2 on top of its raw subtotal.
    _bundle(tmp_path, scores=[{"alpha": 20, "beta": 5}, {"alpha": 5, "beta": 20}])
    result = json.loads((tmp_path / "result_G1.json").read_text(encoding="utf-8"))
    final = result["final_result"]
    assert final["series_tie"] is True
    assert final["winner_group"] is None
    assert final["total_score"] == {"alpha": 27, "beta": 27}
    errors, _ = validate_submission_directory(tmp_path, "G1")
    assert errors == []


def test_validator_rejects_a_tied_series_missing_the_tie_credit(tmp_path):
    _bundle(tmp_path, scores=[{"alpha": 20, "beta": 5}, {"alpha": 5, "beta": 20}])
    path = tmp_path / "result_G1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["final_result"]["total_score"] = {"alpha": 25, "beta": 25}
    path.write_text(json.dumps(data), encoding="utf-8")
    errors, _ = validate_submission_directory(tmp_path, "G1")
    error = next(item for item in errors if item.field == "final_result.total_score")
    assert error.code == "derived_value_mismatch"
    assert error.expected == {"alpha": 27, "beta": 27}
