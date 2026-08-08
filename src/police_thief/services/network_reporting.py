"""Automatic Gmail delivery for a completed cross-computer match."""

from __future__ import annotations

import json
from pathlib import Path

from police_thief.services.anomaly_detector import AnomalyDetector
from police_thief.services.gatekeeper import Gatekeeper, Http429BackoffPolicy
from police_thief.services.gmail_oauth import build_gmail_api_transport
from police_thief.services.gmail_report_sender import send_match_report
from police_thief.services.quota_manager import QuotaManager
from police_thief.services.token_bucket import TokenBucket


def submission_email_subject(settings) -> str:
    """Build one role-neutral subject for the complete alternating-role series."""
    group_1_id = settings.team_name.strip().lower().replace(" ", "-")
    group_2_id = settings.opponent_team_name.strip().lower().replace(" ", "-")
    return (
        f"Final Project, Police-Thief result, {settings.game_id} "
        f"({group_1_id}, {group_2_id})"
    )


def email_result_file(path: Path, params, settings, emit) -> None:
    """Send the mandatory result JSON through OAuth and all Gatekeeper layers."""
    expected_filename = f"result_{settings.game_id}.json"
    if path.name != expected_filename:
        raise RuntimeError(
            f"automatic email accepts only {expected_filename}, received {path.name}"
        )
    rate = params.rate_limiter
    gatekeeper = Gatekeeper(
        QuotaManager(500, settings.output_dir / "gmail_quota.json"),
        TokenBucket(rate.requests_per_minute, rate.requests_per_minute / 60.0),
        AnomalyDetector(rate.requests_per_minute, 60.0),
    )
    transport = build_gmail_api_transport(settings.credentials_path, settings.token_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = send_match_report(
        gatekeeper=gatekeeper,
        transport=transport,
        backoff_policy=Http429BackoffPolicy(rate.retry_backoff_sec, rate.max_retries),
        to_addr=settings.email_recipient,
        subject=submission_email_subject(settings),
        json_payload=payload,
        attachment_filename=path.name,
    )
    if not result.sent:
        raise RuntimeError(f"automatic Gmail report failed: {result}")
    emit(f"Automatic JSON email sent to {settings.email_recipient}")
