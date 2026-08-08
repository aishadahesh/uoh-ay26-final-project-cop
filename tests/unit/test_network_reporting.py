"""Tests for role-neutral automated match-report email metadata."""

from pathlib import Path
from types import SimpleNamespace

import pytest

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

    with pytest.raises(RuntimeError, match="accepts only result_G001.json"):
        email_result_file(Path("log_G001_g01.json"), object(), settings, lambda _message: None)
