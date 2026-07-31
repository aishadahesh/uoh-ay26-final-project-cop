"""Integration tests: the Orchestrator driving a real turn over a real
FastMCP network call (Chapter 8).

Not mocked -- these spin up a genuine local FastMCP server (the same
pattern proven in Chapter 2's test_mcp_http_roundtrip.py) and drive a real
Board/BeliefMap/ManhattanHeuristicBrain (Chapters 3/6) through the
Orchestrator's full state-machine cycle, sending a real commitment hash
over real HTTP -- closing the placeholder gap left open since Chapter 2's
MoveEnvelope docstring ("signature becomes a real SHA-256 commitment in
Chapter 5/6").
"""

import socket
import threading
import time
from unittest.mock import patch

import pytest

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.services.commit_reveal import verify
from police_thief.services.deadline_tracker import DeadlineTracker
from police_thief.services.log_manager import LogManager
from police_thief.services.mcp_server import PeerInboxes, build_peer_server, run_peer_server
from police_thief.services.orchestrator import Orchestrator
from police_thief.services.state_machine import MatchState
from police_thief.services.watchdog import Watchdog
from police_thief.shared.constants import AgentRole


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_opponent_url():
    port = _free_port()
    mcp = build_peer_server("integration_test_opponent", PeerInboxes())
    thread = threading.Thread(
        target=lambda: run_peer_server(mcp, host="127.0.0.1", port=port),
        daemon=True,
    )
    thread.start()
    time.sleep(1.0)
    yield f"http://127.0.0.1:{port}/mcp"


def _belief_peaked_at(board: Board, peak: Position) -> BeliefMap:
    scent = ScentField(grid_size=board.config.grid_size, config=ScentConfig())
    scent.emit(peak)
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    return belief


async def test_orchestrator_completes_a_full_turn_against_a_real_opponent(running_opponent_url):
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    orchestrator = Orchestrator(
        brain=ManhattanHeuristicBrain(AgentRole.COP),
        opponent_url=running_opponent_url,
        deadline_tracker=DeadlineTracker(timeout_seconds=5.0, max_retries=1),
        watchdog=Watchdog(timeout_seconds=60.0),
        log_manager=LogManager(),
    )

    result = await orchestrator.run_turn(board, Position(0, 0), belief)

    assert result.state == MatchState.WAITING_FOR_OPPONENT
    assert result.move is not None
    assert result.h_commit is not None


async def test_orchestrator_logs_a_verifiable_entry_after_a_successful_turn(running_opponent_url):
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    orchestrator = Orchestrator(
        brain=ManhattanHeuristicBrain(AgentRole.COP),
        opponent_url=running_opponent_url,
        deadline_tracker=DeadlineTracker(timeout_seconds=5.0, max_retries=1),
        watchdog=Watchdog(timeout_seconds=60.0),
        log_manager=LogManager(),
    )

    await orchestrator.run_turn(board, Position(0, 0), belief)

    assert len(orchestrator.log_manager.entries) == 1
    entry = orchestrator.log_manager.entries[0]
    assert verify(entry.state, entry.move, entry.intent, entry.nonce, entry.h_commit)


async def test_orchestrator_heartbeats_the_watchdog_across_a_successful_turn(running_opponent_url):
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    watchdog = Watchdog(timeout_seconds=60.0)
    orchestrator = Orchestrator(
        brain=ManhattanHeuristicBrain(AgentRole.COP),
        opponent_url=running_opponent_url,
        deadline_tracker=DeadlineTracker(timeout_seconds=5.0, max_retries=1),
        watchdog=watchdog,
        log_manager=LogManager(),
    )

    await orchestrator.run_turn(board, Position(0, 0), belief)

    assert watchdog.shutdown_triggered is False


async def test_orchestrator_declares_technical_loss_when_the_opponent_is_unreachable():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    orchestrator = Orchestrator(
        brain=ManhattanHeuristicBrain(AgentRole.COP),
        opponent_url="http://127.0.0.1:1/mcp",  # nobody is listening
        deadline_tracker=DeadlineTracker(timeout_seconds=1.0, max_retries=1),
        watchdog=Watchdog(timeout_seconds=60.0),
        log_manager=LogManager(),
    )

    result = await orchestrator.run_turn(board, Position(0, 0), belief)

    assert result.state == MatchState.TECHNICAL_LOSS
    assert result.move is None
    assert result.h_commit is None
    assert orchestrator.log_manager.entries == []  # nothing is logged on a failed turn


async def test_orchestrator_declares_technical_loss_if_self_verification_ever_fails(
    running_opponent_url,
):
    """Defensive-only branch: commit()/verify() are deterministic and always
    agree when called with matching arguments (as the Orchestrator always
    does), so this cannot occur in practice -- mocked here only to prove
    the Orchestrator reacts correctly if it somehow ever did, rather than
    silently trusting an unverified commitment.
    """
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    orchestrator = Orchestrator(
        brain=ManhattanHeuristicBrain(AgentRole.COP),
        opponent_url=running_opponent_url,
        deadline_tracker=DeadlineTracker(timeout_seconds=5.0, max_retries=1),
        watchdog=Watchdog(timeout_seconds=60.0),
        log_manager=LogManager(),
    )

    with patch("police_thief.services.orchestrator.verify", return_value=False):
        result = await orchestrator.run_turn(board, Position(0, 0), belief)

    assert result.state == MatchState.TECHNICAL_LOSS
    assert orchestrator.log_manager.entries == []


async def test_orchestrator_state_machine_is_terminal_after_technical_loss():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_peaked_at(board, Position(5, 5))
    orchestrator = Orchestrator(
        brain=ManhattanHeuristicBrain(AgentRole.COP),
        opponent_url="http://127.0.0.1:1/mcp",
        deadline_tracker=DeadlineTracker(timeout_seconds=1.0, max_retries=0),
        watchdog=Watchdog(timeout_seconds=60.0),
        log_manager=LogManager(),
    )

    await orchestrator.run_turn(board, Position(0, 0), belief)

    assert orchestrator.state_machine.is_terminal is True
