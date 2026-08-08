"""Gmail report sending: MIME construction, base64url encoding, and the
Gatekeeper-guarded, 429-aware send pipeline (Chapter 9, Sec. 9.3.1-9.3.15).

The real, OAuth-authenticated Gmail API service builder (Sec. 9.3.1's
`get_service()`, Sec. I.3/T0438-T0450) requires an actual Google Cloud
project, a configured OAuth consent screen, and a locally-authorized
`token.json` -- a manual, per-team setup step that cannot be performed
inside this coding session (there is no real Gmail account/OAuth client to
authorize against here). What this module builds instead is everything that
*can* be proven correct without one: MIME message construction, the
JSON-attachment-only mandate (Sec. 9.3.15 -- free-text reports are
forbidden), and the Gatekeeper-guarded send pipeline with 429 backoff. All
of it is exercised in tests via an injectable `transport` callable, so the
pipeline's correctness never depends on a real network call to Gmail --
the same "inject the boundary, test the logic for real" approach already
used for `DeadlineTracker`/`Watchdog` (Chapter 8).
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from police_thief.services.gatekeeper import Gatekeeper, GatekeeperBlockReason, Http429BackoffPolicy


class GmailRateLimitedError(RuntimeError):
    """Raised by a transport to signal Gmail's HTTP 429 Too Many Requests."""


class GmailSendError(RuntimeError):
    """Raised by a transport for any other (non-429) send failure."""


Transport = Callable[[str], dict]


def build_report_email(
    to_addr: str, subject: str, json_payload: dict, attachment_filename: str
) -> MIMEMultipart:
    """Sec. 9.3.15: the report is never sent as free text -- only as a JSON
    attachment. The message body itself is a fixed, non-substantive
    placeholder; all real content lives in the attached, machine-parseable
    JSON file, never in a string a caller could substitute free text into.

    The `isinstance` check is a *runtime* enforcement of that rule, not just
    a type hint: Python does not check type hints on its own, and Sec. 9.3.15
    calls a free-text report an outright [FORBIDDEN] case, not merely a
    style preference -- so the rejection must actually happen in code, not
    only on paper.
    """
    if not isinstance(json_payload, dict | list):
        raise TypeError(
            f"json_payload must be a JSON-serializable dict or list, not {type(json_payload).__name__} "
            "-- free-text reports are forbidden (Sec. 9.3.15)"
        )
    message = MIMEMultipart()
    message["to"] = to_addr
    message["subject"] = subject
    message.attach(MIMEText("Automated match report attached as JSON. See attachment.", "plain"))

    json_bytes = json.dumps(json_payload, indent=2, sort_keys=True).encode("utf-8")
    attachment = MIMEApplication(json_bytes, _subtype="json")
    attachment.add_header("Content-Disposition", "attachment", filename=attachment_filename)
    message.attach(attachment)
    return message


def encode_for_gmail_api(message: MIMEMultipart) -> str:
    """Gmail API's `users.messages.send` requires the raw RFC 2822 message,
    base64url-encoded (T0453)."""
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


@dataclass(frozen=True)
class SendAttempt:
    """One logged send attempt, for local audit (T0459)."""

    subject: str
    success: bool
    reason: str | None = None


@dataclass(frozen=True)
class SendResult:
    sent: bool
    attempts: tuple[SendAttempt, ...]
    blocked_reason: GatekeeperBlockReason | None = None


def send_match_report(
    gatekeeper: Gatekeeper,
    transport: Transport,
    backoff_policy: Http429BackoffPolicy,
    to_addr: str,
    subject: str,
    json_payload: dict,
    attachment_filename: str,
    sleep: Callable[[float], None] = time.sleep,
) -> SendResult:
    """Send one report through the Gatekeeper, retrying on 429 per the
    backoff schedule (Sec. 9.3.13-9.3.14), and logging every attempt.

    Blind retries on a temporary error could exacerbate quota exhaustion --
    so a 429 backs off for `retry_backoff_seconds` before each retry, up to
    `max_retries`, exactly mirroring the "declared failure, not indefinite
    waiting" discipline already applied to Chapter 8's DeadlineTracker.
    """
    decision = gatekeeper.submit()
    if not decision.allowed:
        return SendResult(sent=False, attempts=(), blocked_reason=decision.reason)

    message = build_report_email(to_addr, subject, json_payload, attachment_filename)
    raw = encode_for_gmail_api(message)

    attempts: list[SendAttempt] = []
    schedule = [0.0, *backoff_policy.backoff_schedule()]
    for wait_seconds in schedule:
        if wait_seconds:
            sleep(wait_seconds)
        try:
            transport(raw)
            attempts.append(SendAttempt(subject=subject, success=True))
            return SendResult(sent=True, attempts=tuple(attempts))
        except GmailRateLimitedError:
            attempts.append(SendAttempt(subject=subject, success=False, reason="rate_limited_429"))
            continue
        except GmailSendError as exc:
            attempts.append(SendAttempt(subject=subject, success=False, reason=str(exc)))
            return SendResult(sent=False, attempts=tuple(attempts))

    return SendResult(sent=False, attempts=tuple(attempts))
