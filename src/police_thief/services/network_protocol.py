"""Versioned wire contract for reference-compatible peer matches."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

PROTOCOL_NAME = "police-thief-mcp"
PROTOCOL_VERSION = "3.0.0"
WIRE_ROLES = {"cop": "police", "thief": "thief"}
CONTROL_KINDS = frozenset({"enable", "status", "restart", "quit"})
ALLOWED_WIN_CLAIMS = frozenset({"boxed_in", "survival"})


class NetworkProtocolError(ValueError):
    """Raised when a peer message is malformed, incompatible, or tampered."""


def _is_coordinate(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    )


def validate_claim_response(
    response: dict | None, expected_claims: list[list[int]] | None = None,
) -> None:
    """Validate structure and, when known, bind a response to our last claim."""
    if response is None:
        return
    if not isinstance(response, dict) or not isinstance(response.get("caught"), bool):
        raise NetworkProtocolError("claim_response must contain a boolean caught value")
    claim = response.get("claim")
    if not _is_coordinate(claim):
        raise NetworkProtocolError("claim_response.claim must be a two-integer coordinate")
    if expected_claims is not None and claim not in expected_claims:
        raise NetworkProtocolError(
            f"claim_response references {claim!r}, expected one of {expected_claims!r}"
        )


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(payload: dict, nonce: str) -> str:
    return hashlib.sha256(f"{_canonical(payload)}|{nonce}".encode()).hexdigest()


def seal_payload(payload: dict) -> dict:
    nonce = secrets.token_hex(32)
    return {"payload": payload, "nonce": nonce, "commit": _digest(payload, nonce)}


def verify_record(record: dict) -> bool:
    try:
        return secrets.compare_digest(
            str(record["commit"]),
            _digest(record["payload"], str(record["nonce"])),
        )
    except (KeyError, TypeError):
        return False


def create_agreement(
    terms: dict, identity: dict, conformance: dict | None = None,
) -> dict:
    nonce = secrets.token_hex(16)
    agreement = {
        "terms": terms,
        "nonce": nonce,
        "signature": _digest(terms, nonce),
        "identity": identity,
    }
    if conformance is not None:
        agreement["conformance"] = conformance
    return agreement


def verify_agreement(message: dict, expected_terms: dict) -> dict:
    try:
        terms = message["terms"]
        nonce = str(message["nonce"])
        signature = str(message["signature"])
        identity = dict(message.get("identity", {}))
    except (KeyError, TypeError, ValueError) as exc:
        raise NetworkProtocolError(f"malformed negotiation message: {exc}") from exc
    if not isinstance(terms, dict):
        raise NetworkProtocolError(
            f"malformed negotiation message: terms must be an object, got {type(terms).__name__}"
        )
    if terms != expected_terms:
        differing = sorted(
            key
            for key in set(terms) | set(expected_terms)
            if terms.get(key) != expected_terms.get(key)
        )
        details = ", ".join(
            f"{key}: local={expected_terms.get(key)!r}, opponent={terms.get(key)!r}"
            for key in differing
        )
        raise NetworkProtocolError(f"opponent game terms do not match: {details}")
    if not secrets.compare_digest(signature, _digest(terms, nonce)):
        raise NetworkProtocolError("opponent negotiation signature is invalid")
    return identity


@dataclass(frozen=True)
class TurnMessage:
    step: int
    sender: str
    hint: str
    smell_grid: dict
    commit: str
    timestamp: str
    barrier_placed: list[int] | None = None
    capture_claim: list[int] | None = None
    claim_response: dict | None = None
    win_claim: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TurnMessage:
        try:
            message = cls(**data)
        except (TypeError, ValueError) as exc:
            raise NetworkProtocolError(f"malformed turn message: {exc}") from exc
        if message.sender not in WIRE_ROLES.values() or message.step < 1:
            raise NetworkProtocolError("invalid turn sender or step")
        if len(message.commit) != 64:
            raise NetworkProtocolError("turn commitment must be a SHA-256 digest")
        for field, value in (
            ("barrier_placed", message.barrier_placed),
            ("capture_claim", message.capture_claim),
        ):
            if value is not None and not _is_coordinate(value):
                raise NetworkProtocolError(f"{field} must be a two-integer coordinate")
        validate_claim_response(message.claim_response)
        if (
            message.win_claim is not None
            and (
                not isinstance(message.win_claim, dict)
                or message.win_claim.get("type") not in ALLOWED_WIN_CLAIMS
            )
        ):
            raise NetworkProtocolError(
                "win_claim.type must be either 'boxed_in' or 'survival'"
            )
        return message


@dataclass(frozen=True)
class AuditPayload:
    sender: str
    records: list[dict]
    result_claim: str
    token_usage: dict | None = None
    # Optional final-consensus field agreed cross-team: each side sends the
    # canonical series SHA-256 so mutual agreement is confirmed explicitly
    # rather than inferred from each peer's own arithmetic.
    consensus_sha: str | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        if self.consensus_sha is None:
            payload.pop("consensus_sha")
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> AuditPayload:
        allowed = set(cls.__dataclass_fields__)
        try:
            payload = cls(**{key: value for key, value in data.items() if key in allowed})
        except (TypeError, ValueError) as exc:
            raise NetworkProtocolError(f"malformed audit payload: {exc}") from exc
        if payload.sender not in WIRE_ROLES.values() or not isinstance(payload.records, list):
            raise NetworkProtocolError("invalid audit sender or records")
        if payload.consensus_sha is not None and (
            not isinstance(payload.consensus_sha, str)
            or len(payload.consensus_sha) != 64
            or any(char not in "0123456789abcdef" for char in payload.consensus_sha)
        ):
            raise NetworkProtocolError("consensus_sha must be 64 lowercase hexadecimal characters")
        return payload


@dataclass(frozen=True)
class AuditVerification:
    """Detailed audit verdict without conflating syntax with tampering.

    ``cryptographic_failure`` is true only when a live commitment cannot be
    revealed faithfully (missing reveal, changed commitment, or invalid
    nonce/hash).  A structurally incompatible record remains unverified, but
    is not by itself proof of cryptographic forgery.
    """

    verified: bool
    failed_steps: tuple[int, ...]
    cryptographic_failure: bool
    errors: tuple[str, ...]

@dataclass(frozen=True)
class ControlMessage:
    kind: str
    sender: str
    sub_game_number: int = 1
    status: str = ""
    step_budget: float = 0.0
    payload: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ControlMessage:
        allowed = set(cls.__dataclass_fields__)
        try:
            message = cls(**{key: value for key, value in data.items() if key in allowed})
        except (TypeError, ValueError) as exc:
            raise NetworkProtocolError(f"malformed control message: {exc}") from exc
        if message.kind not in CONTROL_KINDS or message.sender not in WIRE_ROLES.values():
            raise NetworkProtocolError("invalid control kind or sender")
        return message


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def audit_records(
    records: list[dict],
    expected_commits: dict[int, str],
    *,
    require_step0: bool = False,
) -> tuple[bool, list[int]]:
    """Verify revealed records against the commitments seen during play.

    The lecturer's v3 reference peer includes one extra, self-verifying
    ``system_spec`` record at step 0.  It cannot have a prior turn commitment
    because it is never sent as a turn, so it is validated separately while
    all positive steps must still match the exact commitments received live.
    """
    verdict = verify_audit_records(
        records, expected_commits, require_step0=require_step0,
    )
    return verdict.verified, list(verdict.failed_steps)


def verify_audit_records(
    records: list[dict],
    expected_commits: dict[int, str],
    *,
    require_step0: bool = False,
) -> AuditVerification:
    """Return an evidence-rich audit verdict.

    The caller needs this distinction to apply the rulebook correctly:
    cryptographic forgery/incomplete reveal is a technical loss, whereas a
    wire-envelope parse incompatibility preserves the played outcome with
    mutual sign-off disabled.
    """
    failed: list[int] = []
    errors: list[str] = []
    cryptographic_failure = False
    seen: set[int] = set()
    saw_step0 = False
    auxiliary_kinds = {"capture_answer", "survival_claim"}
    for index, record in enumerate(records):
        payload = record.get("payload") if isinstance(record, dict) else None
        if isinstance(payload, dict) and payload.get("kind") in auxiliary_kinds:
            kind = payload.get("kind")
            try:
                int(payload.get("at_step", payload.get("step", payload.get("steps"))))
                str(record["commit"])
                str(record["nonce"])
            except (KeyError, TypeError, ValueError):
                failed.append(-1)
                errors.append(
                    f"records[{index}] {kind} must contain step/at_step, nonce, and commit"
                )
                continue
            if not verify_record(record):
                failed.append(-1)
                cryptographic_failure = True
                errors.append(f"records[{index}] {kind} nonce/commit verification failed")
            continue
        try:
            step = int(record["payload"]["step"])
            commit = str(record["commit"])
        except (KeyError, TypeError, ValueError):
            failed.append(-1)
            errors.append(
                f"records[{index}] must contain payload.step and top-level commit"
            )
            continue
        if step == 0:
            duplicate_step0 = saw_step0
            correct_type = record["payload"].get("type") == "system_spec"
            valid_commit = verify_record(record)
            valid_step0 = not duplicate_step0 and correct_type and valid_commit
            saw_step0 = True
            if not valid_step0:
                failed.append(0)
                if duplicate_step0:
                    errors.append("duplicate Step-0 system_spec record")
                if not correct_type:
                    errors.append("Step 0 must have payload.type='system_spec'")
                if not valid_commit:
                    cryptographic_failure = True
                    errors.append("Step-0 nonce/commit verification failed")
            continue
        if step in seen:
            failed.append(step)
            errors.append(f"duplicate revealed step {step}")
            continue
        seen.add(step)
        expected = expected_commits.get(step)
        if expected is None:
            failed.append(step)
            errors.append(f"unexpected revealed step {step} had no live commitment")
            continue
        if expected != commit:
            failed.append(step)
            cryptographic_failure = True
            errors.append(f"step {step} does not match its live commitment")
            continue
        if not verify_record(record):
            failed.append(step)
            cryptographic_failure = True
            errors.append(f"step {step} nonce/commit verification failed")
    missing = sorted(set(expected_commits) - seen)
    if missing:
        failed.extend(missing)
        cryptographic_failure = True
        errors.extend(f"missing reveal for committed step {step}" for step in missing)
    if require_step0 and not saw_step0:
        failed.append(0)
        errors.append("required Step-0 system_spec record is missing")
    return AuditVerification(
        verified=not failed,
        failed_steps=tuple(failed),
        cryptographic_failure=cryptographic_failure,
        errors=tuple(errors),
    )
