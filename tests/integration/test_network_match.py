"""Two independent peers negotiating, playing, and auditing in memory."""

import json
import queue
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.shared.constants import AgentRole


class MemoryTransport:
    def __init__(self, own: PeerInboxes, peer: PeerInboxes) -> None:
        self.own = own
        self.peer = peer

    def exchange_agreement(self, message, timeout):
        self.peer.agreements.put(message)
        return self.own.agreements.get(timeout=timeout)

    def send_turn(self, message, _timeout):
        self.peer.turns.put(message)

    def receive_turn(self, timeout):
        return self.own.turns.get(timeout=timeout)

    def exchange_audit(self, payload, timeout):
        self.peer.audits.put(payload)
        return self.own.audits.get(timeout=timeout)

    def send_control(self, message, timeout=2.0):
        self.peer.controls.put(message)

    def poll_control(self):
        try:
            return self.own.controls.get_nowait()
        except queue.Empty:
            return None


def test_two_peers_negotiate_play_and_mutually_audit(tmp_path):
    project_root = Path(__file__).parents[2]
    common = {
        "local_port": 8801, "public_url": "https://local.example/mcp",
        "game_id": "NETWORK-TEST", "sub_game_number": 1,
        "shared_config": project_root / "config" / "game.json",
        "team_name": "test-team", "members": ("Ada", "Grace"),
        "opponent_team_name": "rival-team",
        "opponent_members": ("Linus", "Margaret"),
        "own_cop_repo": "https://example.test/a-cop",
        "own_thief_repo": "https://example.test/a-thief",
        "opponent_cop_repo": "https://example.test/b-cop",
        "opponent_thief_repo": "https://example.test/b-thief",
        "shared_key": b"integration-secret",
    }
    cop_inboxes, thief_inboxes = PeerInboxes(), PeerInboxes()
    cop = NetworkMatchRunner(
        NetworkMatchSettings(
            role=AgentRole.COP, opponent_url="https://thief.example/mcp",
            output_dir=tmp_path / "cop", **common,
        ),
        cop_inboxes, transport=MemoryTransport(cop_inboxes, thief_inboxes),
    )
    thief = NetworkMatchRunner(
        NetworkMatchSettings(
            role=AgentRole.THIEF, opponent_url="https://cop.example/mcp",
            output_dir=tmp_path / "thief", **common,
        ),
        thief_inboxes, transport=MemoryTransport(thief_inboxes, cop_inboxes),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(lambda runner: runner.run(Event()), (cop, thief)))

    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert all(result["mutual_sign_off"] for result in results)
    assert results[0]["log_sha256"] == results[1]["log_sha256"]
    assert (tmp_path / "cop" / "declaration_NETWORK-TEST.json").is_file()
    assert (tmp_path / "thief" / "config_NETWORK-TEST_g01.json").is_file()
