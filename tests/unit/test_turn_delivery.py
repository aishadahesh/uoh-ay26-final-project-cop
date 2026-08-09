"""At-least-once turn delivery and ordering contract tests."""

import pytest

from police_thief.services.network_match import _OrderedTurnReceiver
from police_thief.services.network_protocol import NetworkProtocolError


def _turn(step: int, commit: str, *, timestamp: str = "2026-08-09T10:00:00Z") -> dict:
    return {
        "step": step,
        "sender": "thief",
        "hint": "Moving safely.",
        "smell_grid": {},
        "commit": commit,
        "timestamp": timestamp,
        "barrier_placed": None,
        "capture_claim": None,
        "claim_response": None,
        "win_claim": None,
    }


class _Transport:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = list(messages)
        self.timeouts: list[float] = []

    def receive_turn(self, timeout: float) -> dict:
        self.timeouts.append(timeout)
        return self.messages.pop(0)


def test_receiver_absorbs_redelivery_without_renewing_deadline(monkeypatch):
    first = _turn(11, "a" * 64)
    duplicate = _turn(11, "a" * 64, timestamp="2026-08-09T10:00:04Z")
    twelfth = _turn(12, "b" * 64)
    transport = _Transport([first, duplicate, twelfth])
    receiver = _OrderedTurnReceiver(transport)
    messages: list[str] = []

    assert receiver.receive("thief", 11, 10.0, messages.append).step == 11
    clock = iter((100.0, 100.0, 103.0))
    monkeypatch.setattr(
        "police_thief.services.network_match.time.monotonic", lambda: next(clock),
    )
    assert receiver.receive("thief", 12, 10.0, messages.append).step == 12

    assert transport.timeouts[-2:] == [10.0, 7.0]
    assert any("absorbed duplicate" in message for message in messages)


def test_receiver_rejects_same_slot_with_different_commit():
    transport = _Transport([_turn(11, "a" * 64), _turn(11, "b" * 64)])
    receiver = _OrderedTurnReceiver(transport)
    receiver.receive("thief", 11, 10.0, lambda _message: None)

    with pytest.raises(NetworkProtocolError, match="equivocated"):
        receiver.receive("thief", 12, 10.0, lambda _message: None)


def test_receiver_buffers_future_turn_and_replays_it_in_order():
    transport = _Transport([_turn(12, "b" * 64), _turn(11, "a" * 64)])
    receiver = _OrderedTurnReceiver(transport)
    messages: list[str] = []

    assert receiver.receive("thief", 11, 10.0, messages.append).step == 11
    assert receiver.receive("thief", 12, 10.0, messages.append).step == 12

    assert len(transport.timeouts) == 2
    assert any("buffered early" in message for message in messages)
    assert any("replaying buffered" in message for message in messages)
