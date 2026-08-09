from pathlib import Path

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.hints import TemplateHintProvider
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.services.gemini_agent import GeminiDecision
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_match import (
    NetworkMatchRunner,
    NetworkMatchSettings,
    _confirmed_cop_position,
    _infer_public_scent_center,
    _public_barrier_cop_candidates,
    _truthful_capture_claim,
)
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


def test_missing_live_claim_discards_stale_initial_cop_certainty():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = BeliefMap(board)
    belief.set_certain_position(Position(0, 0))

    assert _confirmed_cop_position(belief, None) is None
    assert _confirmed_cop_position(belief, [5, 4]) == Position(5, 4)
    assert belief.arg_max() == Position(5, 4)


def test_confirmed_cop_may_occupy_its_own_newly_blocked_barrier_cell():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    target = Position(5, 5)
    board.apply_declared_barrier(target)
    belief = BeliefMap(board)

    assert _confirmed_cop_position(
        belief,
        [5, 5],
        occupied_blocked_position=target,
    ) == target
    assert belief.belief_at(target) == 0.0


def test_cop_announces_capture_only_on_the_uniquely_identified_thief_cell():
    cop = Position(3, 3)

    assert _truthful_capture_claim(
        AgentRole.COP, cop, (Position(3, 4),),
    ) is None
    assert _truthful_capture_claim(
        AgentRole.COP, cop, (cop, Position(3, 4)),
    ) is None
    assert _truthful_capture_claim(AgentRole.COP, cop, (cop,)) == [3, 3]
    assert _truthful_capture_claim(AgentRole.THIEF, cop, (cop,)) is None


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
        known_opponent_position=Position(4, 1),
    )

    assert advisor.context.legal_moves == (Move.STAY,)
    assert move is Move.STAY
    assert any("capturable on the cop's next turn" in message for message in messages)


def test_public_barrier_candidates_keep_unsafe_actions_away_from_gemini(tmp_path):
    advisor = _NextTurnUnsafeGemini()
    runner = _runner(tmp_path, advisor)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    target = Position(5, 5)
    candidates = _public_barrier_cop_candidates(board, target)
    board.apply_declared_barrier(target)
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(6, 4),
        _CertainBelief(Position(0, 0)),
        plausible_opponent_positions=candidates,
    )
    messages: list[str] = []

    move, _reason = runner._choose_move(
        board,
        _CertainBelief(Position(0, 0)),
        Position(6, 4),
        plan.selected,
        11,
        35,
        messages.append,
        plan=plan,
        plausible_opponent_positions=candidates,
    )

    assert set(candidates) == {
        Position(5, 5),
        Position(4, 5),
        Position(6, 5),
        Position(5, 4),
        Position(5, 6),
    }
    assert advisor.context.legal_moves == (Move.WEST,)
    assert move is Move.WEST
    assert any("publicly plausible current cop cell" in message for message in messages)


def test_fresh_scent_innovation_tracks_recorded_cop_path_not_old_trail():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    scent = ScentField(7, ScentConfig())
    previous_grid: dict[str, float] = {}
    previous_position = Position(0, 0)
    path = (
        Position(1, 0), Position(2, 0), Position(3, 0), Position(4, 0),
        Position(5, 0), Position(5, 1), Position(6, 1), Position(5, 1),
        Position(5, 2), Position(5, 3), Position(5, 4), Position(5, 4),
        Position(4, 4), Position(4, 4), Position(3, 4), Position(2, 4),
        Position(2, 5),
    )

    for current_position in path:
        scent.decay()
        scent.emit(current_position)
        current_grid = NetworkMatchRunner._scent_snapshot(scent, 7)
        inferred = _infer_public_scent_center(
            board,
            previous_grid,
            current_grid,
            decay_rate=0.10,
            min_center_intensity=0.5,
            previous_position=previous_position,
        )
        assert inferred == current_position
        previous_grid = current_grid
        previous_position = current_position


def test_thief_public_hint_is_a_plausible_lie(tmp_path, monkeypatch):
    runner = _runner(tmp_path)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    draws = iter((1, 0))
    monkeypatch.setattr(
        "police_thief.services.network_match.secrets.randbelow",
        lambda _limit: next(draws),
    )
    hint = runner._generate_public_hint(
        TemplateHintProvider(), board, Position(3, 3), Move.EAST, step=4,
    )

    assert hint.intent_truthful is False
    assert hint.text == "I moved west."
