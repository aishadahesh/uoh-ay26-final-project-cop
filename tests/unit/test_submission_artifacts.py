import hashlib
import json
from email import message_from_bytes

from police_thief.services.gmail_report_sender import build_report_email
from police_thief.services.submission_artifacts import (
    canonical_bytes,
    finalize_submission_bundle,
    public_participant,
    save_submission_validation_report,
    series_consensus_payload,
    validate_submission_directory,
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


def test_series_consensus_payload_matches_exact_cross_team_preimage():
    series = {
        "sub_games": [
            {
                "sub_game_number": 2,
                "outcome": "capture",
                "roles": {"beta": "cop", "alpha": "thief"},
                "score": {"beta": 20, "alpha": 5},
                "log_sha256": "b" * 64,
                "steps": 14,
                "tokens": {"alpha": 1, "beta": 2},
            },
            {
                "sub_game_number": 1,
                "outcome": "survival",
                "roles": {"beta": "thief", "alpha": "cop"},
                "score": {"beta": 5, "alpha": 10},
                "log_sha256": "a" * 64,
                "steps": 35,
            },
        ],
        "team_scores": {"alpha": 15, "beta": 25},
        "winner": "beta",
    }

    assert series_consensus_payload("G002", "shared-uid", series) == {
        "game_id": "G002",
        "game_uid": "shared-uid",
        "sub_games": [
            {
                "sub_game_number": 1,
                "result": "survival",
                "roles": {"alpha": "police", "beta": "thief"},
                "score": {"alpha": 10, "beta": 5},
                "winner_group": "alpha",
            },
            {
                "sub_game_number": 2,
                "result": "capture",
                "roles": {"alpha": "thief", "beta": "police"},
                "score": {"alpha": 5, "beta": 20},
                "winner_group": "beta",
            },
        ],
    }


def test_finalize_builds_and_validates_all_required_json(tmp_path):
    paths = _bundle(tmp_path)
    assert [path.name for path in paths] == [
        "declaration_G1.json", "config_G1_g01.json", "config_G1_g02.json",
        "log_G1_g01.json", "log_G1_g02.json", "result_G1.json",
    ]
    errors, required = validate_submission_directory(tmp_path, "G1")
    assert errors == []
    assert required == paths
    uids = {json.loads(path.read_text(encoding="utf-8"))["game_uid"] for path in paths}
    assert len(uids) == 1


def test_submission_files_are_pretty_printed_without_changing_canonical_data(tmp_path):
    paths = _bundle(tmp_path)

    for path in paths:
        text = path.read_text(encoding="utf-8")
        parsed = json.loads(text)
        assert len(text.splitlines()) > 1
        compact = canonical_bytes(parsed)
        assert b"\n" not in compact
        assert json.loads(compact) == parsed


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


def test_six_game_email_contains_only_the_aggregate_result():
    message = build_report_email(
        "lecturer@example.com", "signed report", {"game_id": "G001"}, "result_G001.json",
    )
    parsed = message_from_bytes(message.as_bytes())

    attached = [part.get_filename() for part in parsed.walk() if part.get_filename()]
    assert attached == ["result_G001.json"]


def test_failed_bundle_validation_is_saved_as_structured_json(tmp_path):
    _bundle(tmp_path)
    declaration = tmp_path / "declaration_G1.json"
    data = json.loads(declaration.read_text(encoding="utf-8"))
    data["groups"]["group_1"]["github_commit"] = ""
    declaration.write_text(json.dumps(data), encoding="utf-8")
    errors, _ = validate_submission_directory(tmp_path, "G1")

    path = save_submission_validation_report(tmp_path, "G1", errors, "not sent")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["valid"] is False
    assert report["message"] == "not sent"
    assert any(error["field"].endswith("github_commit") for error in report["errors"])
