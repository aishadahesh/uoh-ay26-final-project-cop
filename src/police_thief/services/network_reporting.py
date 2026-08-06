"""Automatic Gmail delivery for a completed cross-computer match."""

from __future__ import annotations

import json
from pathlib import Path

from police_thief.services.anomaly_detector import AnomalyDetector
from police_thief.services.gatekeeper import Gatekeeper, Http429BackoffPolicy
from police_thief.services.gmail_oauth import build_gmail_api_transport
from police_thief.services.gmail_report_sender import send_match_report, send_submission_bundle
from police_thief.services.submission_artifacts import validate_submission_directory
from police_thief.services.quota_manager import QuotaManager
from police_thief.services.token_bucket import TokenBucket


def email_result_file(path: Path, params, settings, emit) -> None:
    """Send the mandatory result JSON through OAuth and all Gatekeeper layers."""
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
        subject=f"Police-Thief result {settings.game_id} ({settings.role.value})",
        json_payload=payload,
        attachment_filename=path.name,
    )
    if not result.sent:
        raise RuntimeError(f"automatic Gmail report failed: {result}")
    emit(f"Automatic JSON email sent to {settings.email_recipient}")


def email_submission_files(paths: list[Path], params, settings, emit) -> None:
    """Validate, then email the complete PDF-mandated JSON attachment set."""
    errors, required = validate_submission_directory(settings.output_dir, settings.game_id)
    if errors:
        raise RuntimeError(
            "submission JSON validation failed before email:\n"
            + "\n".join(str(error) for error in errors)
        )
    if [path.resolve() for path in paths] != [path.resolve() for path in required]:
        raise RuntimeError(
            f"submission attachment set mismatch: expected {[p.name for p in required]}, "
            f"received {[p.name for p in paths]}"
        )
    rate = params.rate_limiter
    gatekeeper = Gatekeeper(
        QuotaManager(500, settings.output_dir / "gmail_quota.json"),
        TokenBucket(rate.requests_per_minute, rate.requests_per_minute / 60.0),
        AnomalyDetector(rate.requests_per_minute, 60.0),
    )
    transport = build_gmail_api_transport(settings.credentials_path, settings.token_path)
    attachments = [
        (path.name, json.loads(path.read_text(encoding="utf-8"))) for path in required
    ]
    result = send_submission_bundle(
        gatekeeper=gatekeeper,
        transport=transport,
        backoff_policy=Http429BackoffPolicy(rate.retry_backoff_sec, rate.max_retries),
        to_addr=settings.email_recipient,
        subject=f"Police-Thief signed report {settings.game_id} ({settings.role.value})",
        attachments=attachments,
    )
    if not result.sent:
        raise RuntimeError(f"automatic Gmail submission failed: {result}")
    emit(
        f"Automatic JSON email sent to {settings.email_recipient} "
        f"with {len(required)} validated attachments"
    )
