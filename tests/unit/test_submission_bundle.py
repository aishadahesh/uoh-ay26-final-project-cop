"""Building the submission bundle: the consensus pre-image, per-sub-game
commit hashes, pretty-printing, and the aggregate result email.

Split by theme out of the original `test_submission_artifacts.py`."""

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
from tests.unit.submission_fixtures import (
    _bundle,
    _identity,
    _record,
    _terms,
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


def test_final_result_uses_each_subgames_actual_commit_hashes(tmp_path):
    participants = {
        key: public_participant(_identity(key)) for key in ("alpha", "beta")
    }
    rows = []
    for number in (1, 2):
        log_path = tmp_path / f"log_G1_g{number:02d}.json"
        log_path.write_text(
            json.dumps([_record(number, "thief", "E")]), encoding="utf-8",
        )
        rows.append({
            "sub_game_number": number,
            "roles": {"alpha": "cop", "beta": "thief"},
            "started_at": f"2026-08-06T10:0{number}:00+03:00",
            "ended_at": f"2026-08-06T10:0{number}:10+03:00",
            "outcome": "survival",
            "score": {"alpha": 5, "beta": 10},
            "tokens": {"alpha": 0, "beta": 0},
            "mutual_sign_off": True,
            "github_commit": {
                "alpha": str(number) * 40,
                "beta": ("a" if number == 1 else "b") * 40,
            },
        })
    finalize_submission_bundle(
        tmp_path, game_id="G1", terms=_terms(), participants=participants,
        series_result={"num_games": 2, "sub_games": rows, "consensus_confirmed": True},
        game_started_at="2026-08-06T10:00:00+03:00", token_budget=200000,
    )
    result = json.loads((tmp_path / "result_G1.json").read_text(encoding="utf-8"))
    assert result["sub_games"][0]["github_commit"] == rows[0]["github_commit"]
    assert result["sub_games"][1]["github_commit"] == rows[1]["github_commit"]


def test_submission_files_are_pretty_printed_without_changing_canonical_data(tmp_path):
    paths = _bundle(tmp_path)

    for path in paths:
        text = path.read_text(encoding="utf-8")
        parsed = json.loads(text)
        assert len(text.splitlines()) > 1
        compact = canonical_bytes(parsed)
        assert b"\n" not in compact
        assert json.loads(compact) == parsed


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
