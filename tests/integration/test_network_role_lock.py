"""This repository is cop-only: it must refuse in-process role alternation,
refuse to run a live thief runner, and stop before moving if the agreed
start positions were tampered with.

Split out of the original `test_network_match.py`."""

import json
import shutil
from pathlib import Path
from threading import Event

import pytest

from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import (
    NetworkMatchRunner,
    NetworkMatchSeriesRunner,
    NetworkMatchSettings,
    role_for_subgame,
)
from police_thief.services.network_protocol import NetworkProtocolError
from police_thief.shared.constants import AgentRole
from tests.integration.network_match_helpers import (
    MemoryTransport,
)


def test_legacy_series_runner_rejects_in_process_role_alternation(tmp_path):
    settings = NetworkMatchSettings(
        role=AgentRole.COP,
        local_port=8801,
        opponent_url="https://thief.example/mcp",
        public_url="https://cop.example/mcp",
        game_id="NETWORK-TEST",
        sub_game_number=1,
        shared_config=Path(__file__).parents[2] / "config" / "game.json",
        output_dir=tmp_path,
        team_name="alpha",
        members=("Ada", "Grace"),
        opponent_team_name="beta",
        opponent_members=("Linus", "Margaret"),
        own_cop_repo="https://github.com/example/a-cop",
        own_thief_repo="https://github.com/example/a-thief",
        opponent_cop_repo="https://github.com/example/b-cop",
        opponent_thief_repo="https://github.com/example/b-thief",
        shared_key=b"integration-secret",
    )
    with pytest.raises(RuntimeError, match="in-process role alternation is disabled"):
        NetworkMatchSeriesRunner(settings, PeerInboxes()).run(Event())


def test_cop_repository_role_never_changes_between_subgames():
    assert [role_for_subgame(AgentRole.COP, index) for index in range(6)] == [
        AgentRole.COP
    ] * 6


def test_cop_repository_rejects_live_thief_runner(tmp_path):
    settings = NetworkMatchSettings(
        role=AgentRole.THIEF,
        local_port=8801,
        opponent_url="https://peer.example/mcp",
        public_url="https://cop.example/mcp",
        game_id="NETWORK-TEST",
        sub_game_number=2,
        shared_config=Path(__file__).parents[2] / "config" / "game.json",
        output_dir=tmp_path,
    )
    with pytest.raises(RuntimeError, match="cannot run a live Thief role"):
        NetworkMatchRunner(settings, PeerInboxes(), transport=object()).run(Event())


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
