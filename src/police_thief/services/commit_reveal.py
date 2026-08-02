"""Commit-Reveal cryptographic protocol over SHA-256 (Chapter 5).

docs/tasks.md Sec. 5.1-5.4: in a referee-less P2P match, "hindsight
rewriting" (changing a move after the fact) is the central cheating risk.
The fix is mathematical, not contractual: a commitment cryptographically
binds a side to State+Move+Intent before either side reveals anything,
using a fresh Nonce to defeat both hash reuse and dictionary attacks
(Blum 1983's "coin-flipping over the telephone"; the Zero-Knowledge framing
is Goldwasser-Micali-Rackoff 1989 -- Sec. 5.3).

This module implements only the crypto primitives (commit/verify) and the
end-of-match mutual audit over a whole log. The actual 4-step network
protocol sequencing (Commit -> Acknowledge -> Reveal -> Audit, enforced so
steps cannot be skipped or reordered) is Chapter 8's Orchestrator/state-
machine responsibility -- not built here.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any

NONCE_BYTES = 32  # 256 bits, matching the SHA-256 digest size


def canonical_json(data: Any) -> bytes:
    """Deterministic serialization: sorted keys, fixed separators.

    docs/tasks.md Sec. 5.2.4: both peers must hash byte-identical input --
    this is field-name-based canonical serialization, not ad hoc string
    concatenation, so key order never affects the resulting hash.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def generate_nonce() -> str:
    """A fresh, cryptographically-secure Nonce -- never `random` (Sec. 5.2.3)."""
    return secrets.token_hex(NONCE_BYTES)


@dataclass(frozen=True)
class Commitment:
    """The Step-1 output: only h_commit is ever sent; nonce stays secret
    until Step 4 (Final Reveal / Audit)."""

    h_commit: str
    nonce: str


def commit(state: Any, move: Any, intent: Any, nonce: str | None = None) -> Commitment:
    """H_commit = SHA256(State || Move || Intent || Nonce). (Sec. 5.2.2)

    A fresh nonce is generated unless one is supplied -- verify() supplies
    the already-revealed nonce to recompute and check a prior commitment.
    """
    nonce = nonce if nonce is not None else generate_nonce()
    payload = canonical_json({"state": state, "move": move, "intent": intent, "nonce": nonce})
    digest = hashlib.sha256(payload).hexdigest()
    return Commitment(h_commit=digest, nonce=nonce)


def verify(state: Any, move: Any, intent: Any, nonce: str, h_commit: str) -> bool:
    """Recompute the commitment and compare in constant time. (Sec. 5.2.8)

    Constant-time comparison (secrets.compare_digest) avoids leaking timing
    information about how much of the hash matched -- irrelevant for a
    256-bit digest's brute-force resistance, but it is the correct,
    unconditional habit for comparing secrets/digests.
    """
    recomputed = commit(state, move, intent, nonce=nonce).h_commit
    return secrets.compare_digest(recomputed, h_commit)


@dataclass(frozen=True)
class LogEntry:
    """One committed-and-revealed step, ready for post-match audit."""

    state: Any
    move: Any
    intent: Any
    nonce: str
    h_commit: str
    # Network-v3 commitments cover the complete canonical wire payload,
    # while older/local logs cover only state/move/intent.  Retaining the
    # payload lets the Replay Viewer verify either format correctly.
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class AuditResult:
    """docs/tasks.md Sec. 5.4.2: a single mismatch is decisive, not
    statistical -- tampered_index pinpoints exactly which step failed.
    """

    verified: bool
    tampered_index: int | None = None


def audit_log(entries: list[LogEntry]) -> AuditResult:
    """Recompute and check every entry; stop at the first mismatch found.

    The outcome on the board becomes irrelevant the moment any entry fails
    -- cryptography, not human judgment, is the decisive factor (Sec. 5.4.2).
    """
    for index, entry in enumerate(entries):
        if entry.payload is None:
            valid = verify(entry.state, entry.move, entry.intent, entry.nonce, entry.h_commit)
        else:
            mirrors_payload = (
                entry.state == entry.payload.get("state")
                and entry.move == entry.payload.get("move")
                and entry.intent == entry.payload.get("intent")
            )
            serialized = json.dumps(
                entry.payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            )
            recomputed = hashlib.sha256(f"{serialized}|{entry.nonce}".encode()).hexdigest()
            valid = mirrors_payload and secrets.compare_digest(recomputed, entry.h_commit)
        if not valid:
            return AuditResult(verified=False, tampered_index=index)
    return AuditResult(verified=True)
