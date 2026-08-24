"""A mid-match disconnect must resolve to a technical loss on both sides.

Kept in its own module: this is the suite's one known failing test, which
the README records as an open gap (TODO T0522/T0622). Isolating it keeps
the rest of the integration tier independently green.

Split out of the original `test_network_match.py`."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import (
    NetworkMatchRunner,
    NetworkMatchSettings,
)
from police_thief.shared.constants import AgentRole
from tests.integration.network_match_helpers import (
    MemoryTransport,
    _DisconnectingTransport,
    _team_config,
)


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
        "police_thief.services.pregame_peer_check.inspect_public_repository",
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
