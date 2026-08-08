import hashlib
import json
from email import message_from_bytes

from police_thief.services.gmail_report_sender import build_submission_email
from police_thief.services.submission_artifacts import (
    canonical_bytes,
    finalize_submission_bundle,
    public_participant,
    save_submission_validation_report,
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


def _bundle(tmp_path):
    participants = {
        key: public_participant(_identity(key)) for key in ("alpha", "beta")
    }
    rows = []
    for number in (1, 2):
        (tmp_path / f"log_G1_g{number:02d}.json").write_text(
            json.dumps([_record(number, "thief", "E"), _record(number, "police", "S")]),
            encoding="utf-8",
        )
        rows.append({
            "sub_game_number": number,
            "roles": {"alpha": "cop" if number == 1 else "thief", "beta": "thief" if number == 1 else "cop"},
            "started_at": f"2026-08-06T10:0{number}:00+03:00",
            "ended_at": f"2026-08-06T10:0{number}:10+03:00",
            "outcome": "capture" if number == 1 else "survival",
            "score": {"alpha": 20 if number == 1 else 10, "beta": 5},
            "tokens": {"alpha": 100, "beta": 200},
            "mutual_sign_off": True,
        })
    series = {"num_games": 2, "sub_games": rows}
    return finalize_submission_bundle(
        tmp_path, game_id="G1", terms=_terms(), participants=participants,
        series_result=series, game_started_at="2026-08-06T10:00:00+03:00",
        token_budget=200000,
    )


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


def test_submission_email_contains_every_json_attachment(tmp_path):
    paths = _bundle(tmp_path)
    attachments = [(path.name, json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    message = build_submission_email("lecturer@example.com", "signed report", attachments)
    parsed = message_from_bytes(message.as_bytes())
    names = [part.get_filename() for part in parsed.walk() if part.get_filename()]
    assert names == [path.name for path in paths]


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
