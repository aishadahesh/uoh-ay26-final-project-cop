"""The two payloads that cross the wire during play: a turn and a control
message."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from police_thief.services.protocol_constants import (
    ALLOWED_WIN_CLAIMS,
    CONTROL_KINDS,
    WIRE_ROLES,
    NetworkProtocolError,
)


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
