"""Tests for role-neutral automated match-report email metadata."""

from types import SimpleNamespace

from police_thief.services.network_reporting import submission_email_subject


def test_submission_email_subject_identifies_series_and_both_groups() -> None:
    settings = SimpleNamespace(
        game_id="G001",
        team_name="uoh-ay26",
        opponent_team_name="Naj Amjad",
    )

    assert submission_email_subject(settings) == (
        "Final Project, Police-Thief result, G001 (uoh-ay26, naj-amjad)"
    )
