"""Canonical serialisation, digests, sealed turn payloads and the signed
negotiation agreement."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from police_thief.services.protocol_constants import (
    NetworkProtocolError,
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


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
