"""Two independent peers negotiating, playing, and auditing in memory."""

import json
import queue
import shutil
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
        "local_port": 8801,
        "game_id": "NETWORK-TEST", "sub_game_number": 1,
        "shared_config": project_root / "config" / "game.json",
        "shared_key": b"integration-secret",
    }
    cop_inboxes, thief_inboxes = PeerInboxes(), PeerInboxes()
    cop = NetworkMatchRunner(
        NetworkMatchSettings(
            role=AgentRole.COP, opponent_url="https://thief.example/mcp",
            public_url="https://cop.example/mcp", output_dir=tmp_path / "cop",
            team_name="alpha", members=("Ada", "Grace"),
            opponent_team_name="beta", opponent_members=("Linus", "Margaret"),
            own_cop_repo="https://example.test/a-cop",
            own_thief_repo="https://example.test/a-thief",
            opponent_cop_repo="https://example.test/b-cop",
            opponent_thief_repo="https://example.test/b-thief", **common,
        ),
        cop_inboxes, transport=MemoryTransport(cop_inboxes, thief_inboxes),
    )
    thief = NetworkMatchRunner(
        NetworkMatchSettings(
            role=AgentRole.THIEF, opponent_url="https://cop.example/mcp",
            public_url="https://thief.example/mcp", output_dir=tmp_path / "thief",
            team_name="beta", members=("Linus", "Margaret"),
            opponent_team_name="alpha", opponent_members=("Ada", "Grace"),
            own_cop_repo="https://example.test/b-cop",
            own_thief_repo="https://example.test/b-thief",
            opponent_cop_repo="https://example.test/a-cop",
            opponent_thief_repo="https://example.test/a-thief", **common,
        ),
        thief_inboxes, transport=MemoryTransport(thief_inboxes, cop_inboxes),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(lambda runner: runner.run(Event()), (cop, thief)))

    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert all(result["mutual_sign_off"] for result in results)
    assert results[0]["log_sha256"] == results[1]["log_sha256"]
    assert results[0]["team_a"] == results[1]["team_a"]
    assert results[0]["repo_links"] == results[1]["repo_links"]
    assert (tmp_path / "cop" / "declaration_NETWORK-TEST.json").is_file()
    assert (tmp_path / "thief" / "config_NETWORK-TEST_g01.json").is_file()


def test_two_peers_synchronize_barriers_and_resolve_a_barrier_driven_capture(tmp_path):
    """Sec. 3.3.3/3.3.5/3.3.6 end-to-end: the cop's declared barriers reach
    the thief's own board copy in real time (never sealed like a move), and
    a barrier landing exactly on the thief's true cell (Sec. 3.3.5's other
    capture rule, alongside boxed-in) is independently agreed by both
    peers -- with no external judge -- to end the match in capture.

    cop_start=[2, 0] / thief_start=[0, 0] is an empirically-verified close
    corner scenario. Since the reachable-area-based barrier heuristic
    (domain/strategy/manhattan_brain.py) only spends its budget on a
    genuine chokepoint, it now converges to a capture very quickly here --
    one barrier placement, landing on the thief's actual cell, rather than
    the slower multi-turn boxed-in scenario the pre-enhancement heuristic
    needed several barriers to (unreliably) reach from the same start.
    is_boxed_in's own detection is separately proven at the unit level
    (tests/unit/test_capture.py, test_strategy.py's chokepoint tests) --
    this test's job is proving cross-peer synchronization and the mutual
    audit, not which of Sec. 3.3.5's two capture conditions fires. There is
    no randomness in the deterministic heuristic pipeline (Chapter 6), so
    this is not a flaky timing race -- both peers reach identical local
    truth.
    """
    project_root = Path(__file__).parents[2]
    shared_config = json.loads((project_root / "config" / "game.json").read_text(encoding="utf-8"))
    shared_config["board_and_agents"]["cop_start"] = [2, 0]
    shared_config["board_and_agents"]["thief_start"] = [0, 0]
    shared_config["movement_and_barriers"]["max_moves"] = 30
    # get_git_commit_hash (Sec. 5.5.5) needs a real git working tree as cwd,
    # so this scratch config lives inside the repo rather than tmp_path --
    # cleaned up in the finally block below either way.
    scratch_dir = project_root / "tests" / "integration" / "_scratch_barrier_test"
    scratch_dir.mkdir(exist_ok=True)
    config_path = scratch_dir / "game.json"
    config_path.write_text(json.dumps(shared_config), encoding="utf-8")

    common = {
        "local_port": 8802,
        "game_id": "BARRIER-TEST", "sub_game_number": 1,
        "shared_config": config_path,
        "shared_key": b"integration-secret",
    }
    try:
        cop_inboxes, thief_inboxes = PeerInboxes(), PeerInboxes()
        cop = NetworkMatchRunner(
            NetworkMatchSettings(
                role=AgentRole.COP, opponent_url="https://thief.example/mcp",
                public_url="https://cop.example/mcp", output_dir=tmp_path / "cop",
                team_name="alpha", members=("Ada", "Grace"),
                opponent_team_name="beta", opponent_members=("Linus", "Margaret"),
                own_cop_repo="https://example.test/a-cop",
                own_thief_repo="https://example.test/a-thief",
                opponent_cop_repo="https://example.test/b-cop",
                opponent_thief_repo="https://example.test/b-thief", **common,
            ),
            cop_inboxes, transport=MemoryTransport(cop_inboxes, thief_inboxes),
        )
        thief = NetworkMatchRunner(
            NetworkMatchSettings(
                role=AgentRole.THIEF, opponent_url="https://cop.example/mcp",
                public_url="https://thief.example/mcp", output_dir=tmp_path / "thief",
                team_name="beta", members=("Linus", "Margaret"),
                opponent_team_name="alpha", opponent_members=("Ada", "Grace"),
                own_cop_repo="https://example.test/b-cop",
                own_thief_repo="https://example.test/b-thief",
                opponent_cop_repo="https://example.test/a-cop",
                opponent_thief_repo="https://example.test/a-thief", **common,
            ),
            thief_inboxes, transport=MemoryTransport(thief_inboxes, cop_inboxes),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            paths = list(executor.map(lambda runner: runner.run(Event()), (cop, thief)))
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert all(result["outcome"] == "capture" for result in results)
    assert all(result["mutual_sign_off"] for result in results)
    assert results[0]["log_sha256"] == results[1]["log_sha256"]
    cop_score, thief_score = results[0]["cop_score"], results[0]["thief_score"]
    assert cop_score > thief_score
