"""Tests for role-neutral automated match-report email metadata."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import police_thief.services.network_reporting as network_reporting
from police_thief.services.network_reporting import email_result_file, submission_email_subject


def test_submission_email_subject_identifies_series_and_both_groups() -> None:
    settings = SimpleNamespace(
        game_id="G001",
        team_name="uoh-ay26",
        opponent_team_name="Naj Amjad",
    )

    assert submission_email_subject(settings) == (
        "Final Project, Police-Thief result, G001 (uoh-ay26, naj-amjad)"
    )


def test_email_rejects_any_non_aggregate_attachment() -> None:
    settings = SimpleNamespace(game_id="G001")

    with pytest.raises(RuntimeError, match=r"accepts only result_\*\.json"):
        email_result_file(Path("log_G001_g01.json"), object(), settings, lambda _message: None)


def test_email_accepts_canonical_report_filename(tmp_path, monkeypatch) -> None:
    path = tmp_path / "result_uoh-ay26-vs-yanell11-G010.json"
    path.write_text(
        """{
          "game_id": "uoh-ay26-vs-yanell11-G010",
          "links": {"result": "result_uoh-ay26-vs-yanell11-G010.json"}
        }""",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        game_id="G010",
        team_name="uoh-ay26",
        opponent_team_name="yanell11",
        output_dir=tmp_path,
        credentials_path=tmp_path / "credentials.json",
        token_path=tmp_path / "token.json",
        email_recipient="test@example.com",
    )
    params = SimpleNamespace(
        rate_limiter=SimpleNamespace(
            requests_per_minute=30,
            retry_backoff_sec=1,
            max_retries=1,
        )
    )
    sent = {}

    monkeypatch.setattr(
        network_reporting,
        "build_gmail_api_transport",
        lambda *_args: object(),
    )
    monkeypatch.setattr(
        network_reporting,
        "send_match_report",
        lambda **kwargs: sent.update(kwargs) or SimpleNamespace(sent=True),
    )

    email_result_file(path, params, settings, lambda _message: None)

    assert sent["attachment_filename"] == path.name
    assert sent["subject"] == (
        "Final Project, Police-Thief result, "
        "uoh-ay26-vs-yanell11-G010 (uoh-ay26, yanell11)"
    )
