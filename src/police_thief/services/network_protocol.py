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


class NetworkProtocolError(ValueError):
    """Raised when a peer message is malformed, incompatible, or tampered."""


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
        return message


@dataclass(frozen=True)
class AuditPayload:
    sender: str
    records: list[dict]
    result_claim: str
    token_usage: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AuditPayload:
        try:
            payload = cls(**data)
        except (TypeError, ValueError) as exc:
            raise NetworkProtocolError(f"malformed audit payload: {exc}") from exc
        if payload.sender not in WIRE_ROLES.values() or not isinstance(payload.records, list):
            raise NetworkProtocolError("invalid audit sender or records")
        return payload


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
    failed: list[int] = []
    seen: set[int] = set()
    saw_step0 = False
    for record in records:
        try:
            step = int(record["payload"]["step"])
            commit = str(record["commit"])
        except (KeyError, TypeError, ValueError):
            failed.append(-1)
            continue
        if step == 0:
            valid_step0 = (
                not saw_step0
                and record["payload"].get("type") == "system_spec"
                and verify_record(record)
            )
            saw_step0 = True
            if not valid_step0:
                failed.append(0)
            continue
        if step in seen:
            failed.append(step)
            continue
        seen.add(step)
        if expected_commits.get(step) != commit or not verify_record(record):
            failed.append(step)
    failed.extend(sorted(set(expected_commits) - seen))
    if require_step0 and not saw_step0:
        failed.append(0)
    return not failed, failed
