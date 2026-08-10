"""Two independent peers negotiating, playing, and auditing in memory."""

import json
import queue
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from police_thief.services.mcp_client import PeerClientError
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import (
    NetworkMatchRunner,
    NetworkMatchSeriesRunner,
    NetworkMatchSettings,
)
from police_thief.services.network_protocol import NetworkProtocolError
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
        try:
            return self.own.turns.get(timeout=timeout)
        except queue.Empty as exc:
            # Matches McpPeerTransport.receive_turn's real behavior, so a
            # peer that stops sending turns fails the same way in tests as
            # it does in a real live match (PeerClientError, not a raw
            # queue.Empty NetworkMatchRunner.run() has no reason to expect).
            raise PeerClientError("opponent turn timed out") from exc

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


class _DisconnectingTransport:
    """Wraps a working transport but starts raising PeerClientError on
    send_turn after `fail_after` successful sends -- simulating an
    opponent's tunnel/process dropping mid-match, a real failure a live
    match hit (a 502 from a dead ngrok tunnel; a queue.Empty timeout on the
    receiving side) that used to crash the whole process."""

    def __init__(self, inner, fail_after: int) -> None:
        self._inner = inner
        self._fail_after = fail_after
        self._sends = 0

    def exchange_agreement(self, message, timeout):
        return self._inner.exchange_agreement(message, timeout)

    def send_turn(self, message, timeout):
        self._sends += 1
        if self._sends > self._fail_after:
            raise PeerClientError("simulated opponent disconnect")
        self._inner.send_turn(message, timeout)

    def receive_turn(self, timeout):
        return self._inner.receive_turn(timeout)

    def exchange_audit(self, payload, timeout):
        return self._inner.exchange_audit(payload, timeout)

    def send_control(self, message, timeout=2.0):
        self._inner.send_control(message, timeout)

    def poll_control(self):
        return self._inner.poll_control()


def _team_config(tmp_path, source, name, group_id, members, repos, num_games=6):
    target = tmp_path / name / "game.json"
    target.parent.mkdir(parents=True)
    game = json.loads(source.read_text(encoding="utf-8"))
    game["network_and_league"]["num_games"] = num_games
    target.write_text(json.dumps(game), encoding="utf-8")
    timeout = game["network_and_league"]["response_timeout_sec"]
    target.with_suffix(".toml").write_text(
        f'version = "1.00"\n[game]\ngroup_name = "{name}"\n'
        f'group_id = "{group_id}"\nsub_game_number = 1\n'
        f'members = {json.dumps(list(members))}\nrepos = {json.dumps(repos)}\n'
        f'[network]\nmy_port = 8801\nopponent_url = "https://peer.example/mcp"\n'
        f'turn_timeout_seconds = {timeout}\n',
        encoding="utf-8",
    )
    # JSON inline tables are valid TOML except for ':' separators; normalize.
    text = target.with_suffix(".toml").read_text(encoding="utf-8")
    text = text.replace('"cop":', 'cop =').replace('"thief":', 'thief =')
    target.with_suffix(".toml").write_text(text, encoding="utf-8")
    return target


@pytest.mark.parametrize("num_games", [1, 6])
def test_two_peers_play_agreed_series_with_role_alternation(
    tmp_path, monkeypatch, num_games,
):
    project_root = Path(__file__).parents[2]
    monkeypatch.setattr(
        "police_thief.services.pregame_validation.inspect_public_repository",
        lambda *_args: ([], [{"status": "verified-test-double"}]),
    )
    monkeypatch.setattr(
        "police_thief.services.network_match.get_git_commit_hash", lambda _path: "a" * 40,
    )
    alpha_repos = {
        "cop": "https://github.com/example/a-cop",
        "thief": "https://github.com/example/a-thief",
    }
    beta_repos = {
        "cop": "https://github.com/example/b-cop",
        "thief": "https://github.com/example/b-thief",
    }
    alpha_config = _team_config(
        tmp_path, project_root / "config" / "game.json", "alpha", "alpha",
        ("Ada", "Grace"), alpha_repos, num_games,
    )
    beta_config = _team_config(
        tmp_path, project_root / "config" / "game.json", "beta", "beta",
        ("Linus", "Margaret"), beta_repos, num_games,
    )
    common = {
        "local_port": 8801,
        "game_id": "NETWORK-TEST", "sub_game_number": 1,
        "shared_key": b"integration-secret",
    }
    cop_inboxes, thief_inboxes = PeerInboxes(), PeerInboxes()
    cop = NetworkMatchSeriesRunner(
        NetworkMatchSettings(
            role=AgentRole.COP, opponent_url="https://thief.example/mcp",
            public_url="https://cop.example/mcp", output_dir=tmp_path / "cop",
            team_name="alpha", members=("Ada", "Grace"),
            opponent_team_name="beta", opponent_members=("Linus", "Margaret"),
            own_cop_repo=alpha_repos["cop"], own_thief_repo=alpha_repos["thief"],
            opponent_cop_repo=beta_repos["cop"], opponent_thief_repo=beta_repos["thief"],
            shared_config=alpha_config, **common,
        ),
        cop_inboxes, transport=MemoryTransport(cop_inboxes, thief_inboxes),
    )
    thief = NetworkMatchSeriesRunner(
        NetworkMatchSettings(
            role=AgentRole.THIEF, opponent_url="https://cop.example/mcp",
            public_url="https://thief.example/mcp", output_dir=tmp_path / "thief",
            team_name="beta", members=("Linus", "Margaret"),
            opponent_team_name="alpha", opponent_members=("Ada", "Grace"),
            own_cop_repo=beta_repos["cop"], own_thief_repo=beta_repos["thief"],
            opponent_cop_repo=alpha_repos["cop"], opponent_thief_repo=alpha_repos["thief"],
            shared_config=beta_config, **common,
        ),
        thief_inboxes, transport=MemoryTransport(thief_inboxes, cop_inboxes),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        paths = list(executor.map(lambda runner: runner.run(Event()), (cop, thief)))

    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert all(result["mutual_agreement"]["confirmed"] for result in results)
    assert len({result["mutual_agreement"]["sha256"] for result in results}) == 1
    assert all(result["num_sub_games"] == num_games for result in results)
    assert results[0]["game_uid"] == results[1]["game_uid"]
    assert results[0]["final_result"]["total_score"] == results[1]["final_result"]["total_score"]
    assert [game["roles"]["alpha"] for game in results[0]["sub_games"]] == [
        "police" if index % 2 == 0 else "thief" for index in range(num_games)
    ]
    assert [game["roles"]["beta"] for game in results[0]["sub_games"]] == [
        "thief" if index % 2 == 0 else "police" for index in range(num_games)
    ]
    for number in range(1, num_games + 1):
        assert (tmp_path / "cop" / f"log_NETWORK-TEST_g{number:02d}.json").is_file()
        assert (tmp_path / "thief" / f"config_NETWORK-TEST_g{number:02d}.json").is_file()
    assert (tmp_path / "cop" / "declaration_NETWORK-TEST.json").is_file()
    assert (tmp_path / "cop" / "result_NETWORK-TEST.json").is_file()

    trajectories = set()
    for number in range(1, num_games + 1):
        log_document = json.loads(
            (tmp_path / "cop" / f"log_NETWORK-TEST_g{number:02d}.json").read_text(
                encoding="utf-8"
            )
        )
        records = log_document["records"]
        moves = [
            record["payload"]
            for record in records
            if record.get("payload", {}).get("move")
        ]
        trajectories.add(
            tuple((move["role"], move["move"], tuple(move["position"])) for move in moves)
        )
    assert len(trajectories) >= min(2, num_games), (
        "multi-game series must not replay one identical trajectory"
    )


@pytest.mark.skip(
    reason="obsolete: live pre-game repository/configuration validation is intentionally disabled"
)
def test_modified_protected_start_positions_stop_before_any_move(tmp_path):
    """A former strategy scenario changed protected starts; it must now fail closed."""
    project_root = Path(__file__).parents[2]
    shared_config = json.loads((project_root / "config" / "game.json").read_text(encoding="utf-8"))
    shared_config["board_and_agents"]["cop_start"] = [2, 0]
    shared_config["board_and_agents"]["thief_start"] = [0, 0]
    # get_git_commit_hash (Sec. 5.5.5) needs a real git working tree as cwd,
    # so this scratch config lives inside the repo rather than tmp_path --
    # cleaned up in the finally block below either way.
    scratch_dir = project_root / "tests" / "integration" / "_scratch_barrier_test"
    scratch_dir.mkdir(exist_ok=True)
    config_path = scratch_dir / "game.json"
    config_path.write_text(json.dumps(shared_config), encoding="utf-8")

    try:
        cop_inboxes, thief_inboxes = PeerInboxes(), PeerInboxes()
        cop = NetworkMatchRunner(
            NetworkMatchSettings(
                local_port=8802, game_id="BARRIER-TEST", sub_game_number=1,
                shared_config=config_path, shared_key=b"integration-secret",
                role=AgentRole.COP, opponent_url="https://thief.example/mcp",
                public_url="https://cop.example/mcp", output_dir=tmp_path / "cop",
                team_name="alpha", members=("Ada", "Grace"),
                opponent_team_name="beta", opponent_members=("Linus", "Margaret"),
                own_cop_repo="https://example.test/a-cop",
                own_thief_repo="https://example.test/a-thief",
                opponent_cop_repo="https://example.test/b-cop",
                opponent_thief_repo="https://example.test/b-thief",
            ),
            cop_inboxes, transport=MemoryTransport(cop_inboxes, thief_inboxes),
        )
        with pytest.raises(NetworkProtocolError, match="protected_value_mismatch"):
            cop.run(Event())
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
    report = json.loads((tmp_path / "cop" / "validation_BARRIER-TEST_g01.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert thief_inboxes.turns.empty()
    assert not list((tmp_path / "cop").glob("result_*.json"))


def test_a_mid_match_disconnect_resolves_to_technical_loss_on_both_sides(tmp_path, monkeypatch):
    """Reproduces a real failure: the cop's transport starts raising
    PeerClientError after one successful turn (the opponent's tunnel
    dropping mid-match). Both sides used to crash the whole process with an
    unhandled traceback; NetworkMatchRunner.run() now catches this and
    writes a technical-loss result (Sec. 9.2, 0/0) instead, on both sides:
    the cop directly (it saw the failure), and the thief indirectly (it
    stops receiving turns and its own receive_turn call times out).
    """
    project_root = Path(__file__).parents[2]
    shared_config = json.loads((project_root / "config" / "game.json").read_text(encoding="utf-8"))
    # A short timeout keeps the thief's inevitable receive_turn timeout (it
    # never learns the cop disconnected) fast rather than the real 30s floor.
    shared_config["network_and_league"]["response_timeout_sec"] = 2
    scratch_dir = project_root / "tests" / "integration" / "_scratch_disconnect_test"
    scratch_dir.mkdir(exist_ok=True)
    source_path = scratch_dir / "source.json"
    source_path.write_text(json.dumps(shared_config), encoding="utf-8")
    monkeypatch.setattr(
        "police_thief.services.pregame_validation.inspect_public_repository",
        lambda *_args: ([], [{"status": "verified-test-double"}]),
    )
    monkeypatch.setattr(
        "police_thief.services.network_match.get_git_commit_hash", lambda _path: "a" * 40,
    )
    alpha_repos = {"cop": "https://github.com/example/a-cop", "thief": "https://github.com/example/a-thief"}
    beta_repos = {"cop": "https://github.com/example/b-cop", "thief": "https://github.com/example/b-thief"}
    alpha_config = _team_config(scratch_dir, source_path, "alpha", "alpha", ("Ada", "Grace"), alpha_repos)
    beta_config = _team_config(scratch_dir, source_path, "beta", "beta", ("Linus", "Margaret"), beta_repos)

    common = {
        "local_port": 8802,
        "game_id": "DISCONNECT-TEST", "sub_game_number": 1,
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
                own_cop_repo=alpha_repos["cop"], own_thief_repo=alpha_repos["thief"],
                opponent_cop_repo=beta_repos["cop"], opponent_thief_repo=beta_repos["thief"],
                shared_config=alpha_config, **common,
            ),
            cop_inboxes,
            transport=_DisconnectingTransport(MemoryTransport(cop_inboxes, thief_inboxes), fail_after=1),
        )
        thief = NetworkMatchRunner(
            NetworkMatchSettings(
                role=AgentRole.THIEF, opponent_url="https://cop.example/mcp",
                public_url="https://thief.example/mcp", output_dir=tmp_path / "thief",
                team_name="beta", members=("Linus", "Margaret"),
                opponent_team_name="alpha", opponent_members=("Ada", "Grace"),
                own_cop_repo=beta_repos["cop"], own_thief_repo=beta_repos["thief"],
                opponent_cop_repo=alpha_repos["cop"], opponent_thief_repo=alpha_repos["thief"],
                shared_config=beta_config, **common,
            ),
            thief_inboxes, transport=MemoryTransport(thief_inboxes, cop_inboxes),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            paths = list(executor.map(lambda runner: runner.run(Event()), (cop, thief)))
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert all(result["outcome"] == "technical_loss" for result in results)
    assert all(result["cop_score"] == 0 for result in results)
    assert all(result["thief_score"] == 0 for result in results)
    assert all(result["mutual_sign_off"] is False for result in results)
