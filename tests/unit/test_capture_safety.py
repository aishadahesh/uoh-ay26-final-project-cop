from pathlib import Path

from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.services.gemini_agent import GeminiDecision
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import NetworkMatchRunner, NetworkMatchSettings
from police_thief.shared.constants import AgentRole


class _CertainBelief:
    def __init__(self, position: Position) -> None:
        self.position = position

    def arg_max(self) -> Position:
        return self.position

    def top_positions(self, _limit: int = 5):
        return ((self.position, 1.0),)


class _UnsafeGemini:
    def __init__(self) -> None:
        self.context = None

    def usage_snapshot(self):
        return 0, 0

    def choose_move(self, context, _fallback):
        self.context = context
        return GeminiDecision(Move.WEST, "unsafe test response")


class _NextTurnUnsafeGemini(_UnsafeGemini):
    def choose_move(self, context, _fallback):
        self.context = context
        return GeminiDecision(Move.NORTH, "walk into next-turn capture")


def _runner(tmp_path: Path, advisor=None) -> NetworkMatchRunner:
    settings = NetworkMatchSettings(
        role=AgentRole.THIEF,
        local_port=8802,
        opponent_url="https://cop.example/mcp",
        public_url="https://thief.example/mcp",
        game_id="CAPTURE-SAFETY",
        sub_game_number=1,
        shared_config=tmp_path / "game.json",
        output_dir=tmp_path,
    )
    return NetworkMatchRunner(
        settings, PeerInboxes(), gemini_advisor=advisor, transport=object(),
    )


def test_thief_planner_heavily_penalizes_entering_believed_cop_cell():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board, Position(6, 5), _CertainBelief(Position(6, 4)),
    )
    west = next(item for item in plan.evaluations if item.move is Move.WEST)
    assert west.direct_capture_risk == 1.0
    assert Move.WEST not in plan.allowed_moves
    assert plan.selected is not Move.WEST


def test_confirmed_cop_cell_is_excluded_and_unsafe_gemini_is_rejected(tmp_path):
    advisor = _UnsafeGemini()
    runner = _runner(tmp_path, advisor)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    messages: list[str] = []
    move, _reason = runner._choose_move(
        board,
        _CertainBelief(Position(6, 4)),
        Position(6, 5),
        Move.WEST,
        11,
        35,
        messages.append,
        known_opponent_position=Position(6, 4),
    )
    assert move is not Move.WEST
    assert Move.WEST not in advisor.context.legal_moves
    assert advisor.context.known_opponent_position == Position(6, 4)
    assert any("confirmed current cell" in message for message in messages)


def test_thief_exposes_only_guaranteed_safe_action_to_gemini(tmp_path):
    advisor = _NextTurnUnsafeGemini()
    runner = _runner(tmp_path, advisor)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    messages: list[str] = []

    move, _reason = runner._choose_move(
        board,
        _CertainBelief(Position(0, 0)),
        Position(6, 0),
        Move.NORTH,
        7,
        35,
        messages.append,
        known_opponent_position=Position(5, 1),
    )

    assert advisor.context.legal_moves == (Move.STAY,)
    assert move is Move.STAY
    assert any("reachable by the cop on its next move" in message for message in messages)
