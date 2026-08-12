import hashlib
import json

from police_thief.services.commit_reveal import audit_log
from police_thief.services.network_match import NetworkMatchRunner


def _record(payload: dict, nonce: str = "peer-nonce") -> dict:
    serialized = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return {
        "payload": payload,
        "nonce": nonce,
        "commit": hashlib.sha256(f"{serialized}|{nonce}".encode()).hexdigest(),
    }


def test_combined_log_preserves_move_without_optional_state_or_intent() -> None:
    peer = _record({
        "step": 2, "role": "police", "position": [2, 3], "move": "E",
    })

    entries = NetworkMatchRunner._combined_log([], [peer], "thief", "police")

    assert len(entries) == 1
    assert entries[0].state is None
    assert entries[0].intent is None
    assert entries[0].payload == peer["payload"]
    assert entries[0].h_commit == peer["commit"]
    assert audit_log(entries).verified is True
