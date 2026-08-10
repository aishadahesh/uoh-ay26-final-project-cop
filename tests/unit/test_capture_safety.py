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
    _audit_revealed_trajectory,
    _confirmed_cop_position,
    _infer_public_scent_candidates,
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


def _runner(
    tmp_path: Path,
    advisor=None,
    role: AgentRole = AgentRole.THIEF,
) -> NetworkMatchRunner:
    settings = NetworkMatchSettings(
        role=role,
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


def test_police_always_claims_its_post_move_cell_without_belief_gate():
    cop = Position(3, 3)

    assert _truthful_capture_claim(AgentRole.COP, cop) == [3, 3]
    assert _truthful_capture_claim(AgentRole.THIEF, cop) is None


def test_cop_claims_recorded_step_13_post_move_cell():
    assert _truthful_capture_claim(AgentRole.COP, Position(5, 6)) == [5, 6]


def test_final_audit_detects_recorded_step_13_collision_across_peer_formats():
    thief_moves = (
        "S", "S", "E", "E", "S", "E", "N", "S", "N", "S", "N", "S", "N", "N",
    )
    thief_positions = (
        (4, 3), (5, 3), (5, 4), (5, 5), (6, 5), (6, 6), (5, 6),
        (6, 6), (5, 6), (6, 6), (5, 6), (6, 6), (5, 6), (4, 6),
    )
    police_moves = (
        "E", "S", "E", "S", "E", "S", "S", "E", "S", "E", "N", "S", "E", "S",
    )
    police_positions = (
        (0, 1), (1, 1), (1, 2), (2, 2), (2, 3), (3, 3), (4, 3),
        (4, 4), (5, 4), (5, 5), (4, 5), (5, 5), (5, 6), (6, 6),
    )

    thief_records = [
        {
            "payload": {
                "step": step,
                "role": "thief",
                "state": f"grid=7;self=[{row}, {col}]",
                "move": f"MOVE:{move}",
                "intent": "truth",
            }
        }
        for step, (move, (row, col)) in enumerate(
            zip(thief_moves, thief_positions, strict=True), start=1,
        )
    ]
    previous = Position(0, 0)
    police_records = []
    for step, (move, (row, col)) in enumerate(
        zip(police_moves, police_positions, strict=True), start=1,
    ):
        police_records.append({
            "payload": {
                "step": step,
                "role": "police",
                "state": {"row": previous.row, "col": previous.col},
                "position": [row, col],
                "move": move,
                "intent": True,
            }
        })
        previous = Position(row, col)

    audit = _audit_revealed_trajectory(
        police_records,
        thief_records,
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert audit.errors == ()
    assert audit.coincidence_step == 13
    assert audit.coincidence_after_role == "police"
    assert audit.capture_step is None
    assert audit.trailing_moves == 0


def test_final_audit_accepts_stationary_barrier_action_vocabulary():
    audit = _audit_revealed_trajectory(
        [
            {"payload": {
                "step": 1, "role": "police", "state": "grid=7;self=[1, 0]",
                "move": "MOVE:S", "intent": "truth",
            }},
            {"payload": {
                "step": 2, "role": "police", "state": "grid=7;self=[1, 0]",
                "move": "BARRIER:E", "intent": "truth",
            }},
            {"payload": {
                "step": 3, "role": "police", "state": "grid=7;self=[1, 1]",
                "move": "MOVE:E", "intent": "truth",
            }},
        ],
        [],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert audit.errors == ()
    assert audit.capture_step is None


def test_final_audit_rejects_unknown_action_with_diagonal_position_jump():
    audit = _audit_revealed_trajectory(
        [{"payload": {
            "step": 1, "role": "police", "state": "grid=7;self=[1, 1]",
            "move": "PRIVATE_ACTION", "intent": "truth",
        }}],
        [],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert "more than one orthogonal step" in audit.errors[0]


def test_final_audit_allows_one_acknowledged_stationary_terminal_record():
    police_records = [
        {"payload": {
            "step": 1, "role": "police", "state": {"row": 0, "col": 0},
            "position": [0, 1], "move": "E", "intent": True,
        }},
        {"payload": {
            "step": 2, "role": "police", "state": {"row": 0, "col": 1},
            "position": [0, 2], "move": "E", "intent": True,
            "capture_claim": [0, 2],
        }},
    ]
    thief_records = [
        {"payload": {
            "step": step, "role": "thief", "state": "grid=7;self=[0, 2]",
            "move": "STAY", "intent": "truth",
        }}
        for step in (1, 2)
    ]
    thief_records.append({"payload": {
        "step": 3, "role": "thief", "state": "grid=7;self=[0, 2]",
        "position": [0, 2], "terminal_ack": "capture",
        "claim_response": {"claim": [0, 2], "caught": True},
    }})

    audit = _audit_revealed_trajectory(
        police_records,
        thief_records,
        "police",
        "thief",
        Position(0, 0),
        Position(0, 2),
        7,
        allow_terminal_record=True,
    )

    assert audit.errors == ()
    assert audit.capture_step == 2
    assert audit.capture_after_role == "police"
    assert audit.trailing_moves == 0

    audit_with_extra_move = _audit_revealed_trajectory(
        police_records,
        [
            *thief_records,
            {"payload": {
                "step": 4, "role": "thief", "state": "grid=7;self=[1, 2]",
                "move": "MOVE:S", "intent": "truth",
            }},
        ],
        "police",
        "thief",
        Position(0, 0),
        Position(0, 2),
        7,
        allow_terminal_record=True,
    )
    assert audit_with_extra_move.trailing_moves == 1


def test_final_audit_rejects_a_discontinuous_revealed_position():
    audit = _audit_revealed_trajectory(
        [{
            "payload": {
                "step": 1, "role": "police", "state": {"row": 0, "col": 0},
                "position": [6, 6], "move": "E", "intent": True,
            }
        }],
        [],
        "police",
        "thief",
        Position(0, 0),
        Position(3, 3),
        7,
    )

    assert audit.capture_step is None
    assert "does not match" in audit.errors[0]


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


_CAPPED_KERNEL = {
    (0, 0): 0.90,
    (0, 1): 0.62, (0, -1): 0.62, (1, 0): 0.62, (-1, 0): 0.62,
    (1, 1): 0.42, (1, -1): 0.42, (-1, 1): 0.42, (-1, -1): 0.42,
    (0, 2): 0.20, (0, -2): 0.20, (2, 0): 0.20, (-2, 0): 0.20,
    (1, 2): 0.14, (1, -2): 0.14, (-1, 2): 0.14, (-1, -2): 0.14,
    (2, 1): 0.14, (2, -1): 0.14, (-2, 1): 0.14, (-2, -1): 0.14,
    (2, 2): 0.04, (2, -2): 0.04, (-2, 2): 0.04, (-2, -2): 0.04,
}


def _opponent_capped_step(
    grid: dict[str, float], center: Position, size: int = 7,
) -> dict[str, float]:
    """One turn of the reviewed opponent's scent model: decay by (1-rho),
    deposit the 5x5 kernel, hard-cap every cell at 0.9."""
    decayed = {key: value * 0.9 for key, value in grid.items()}
    for (delta_row, delta_col), deposit in _CAPPED_KERNEL.items():
        row, col = center.row + delta_row, center.col + delta_col
        if 0 <= row < size and 0 <= col < size:
            key = f"{row},{col}"
            decayed[key] = min(0.9, decayed.get(key, 0.0) + deposit)
    return {key: value for key, value in decayed.items() if value > 1e-9}


def test_capped_opponent_step_onto_own_trail_yields_a_set_with_the_true_center():
    """One ordinary step inside the opponent's own kernel: the cap clips the
    center innovation to ~0.34 (< min_center 0.5), so the singleton stage is
    blind, but the fallback set must stay small and contain the true cell."""
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    previous_grid = _opponent_capped_step({}, Position(3, 3))
    current_grid = _opponent_capped_step(previous_grid, Position(3, 4))
    candidates = _infer_public_scent_candidates(
        board, previous_grid, current_grid,
        decay_rate=0.10, min_center_intensity=0.5, emission_cap=0.9,
        previous_positions=(Position(3, 3),),
    )
    assert candidates
    assert len(candidates) <= 4
    assert Position(3, 4) in candidates


def test_saturated_oscillation_tracks_the_true_cell_across_consecutive_turns():
    """The reviewed loss: the thief oscillates (6,6)<->(5,6) while the whole
    neighborhood saturates at the 0.9 cap.  The singleton inference reads an
    innovation of ~0.09 and goes blind; the cap-aware fallback must still
    pin the thief to a small set around the last anchor."""
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    grid: dict[str, float] = {}
    spots = (Position(6, 6), Position(5, 6))
    for turn in range(8):
        grid = _opponent_capped_step(grid, spots[turn % 2])
    first_center = spots[8 % 2]  # (6,6)
    first_grid = _opponent_capped_step(grid, first_center)

    singleton = _infer_public_scent_center(
        board, grid, first_grid,
        decay_rate=0.10, min_center_intensity=0.5,
        previous_position=spots[7 % 2],
    )
    assert singleton is None

    previous_grid = grid
    anchors = (spots[7 % 2],)
    for turn in range(8, 14):
        current_center = spots[turn % 2]
        current_grid = _opponent_capped_step(previous_grid, current_center)
        if turn == 9:
            assert _infer_public_scent_candidates(
                board, previous_grid, current_grid,
                decay_rate=0.10, min_center_intensity=0.5, emission_cap=0.9,
                previous_positions=anchors,
            ) == ()
        candidates = _infer_public_scent_candidates(
            board, previous_grid, current_grid,
            decay_rate=0.10, min_center_intensity=0.5, emission_cap=0.9,
            previous_positions=anchors, max_ambiguity=8,
        )
        assert candidates, f"candidate tracking failed at turn {turn}"
        assert len(candidates) <= 8
        assert current_center in candidates
        anchors = candidates
        previous_grid = current_grid


def test_saturated_scent_without_an_anchor_stays_silent():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    grid: dict[str, float] = {}
    for turn in range(8):
        grid = _opponent_capped_step(grid, Position(6, 6) if turn % 2 else Position(5, 6))
    current_grid = _opponent_capped_step(grid, Position(5, 6))
    candidates = _infer_public_scent_candidates(
        board, grid, current_grid,
        decay_rate=0.10, min_center_intensity=0.5, emission_cap=0.9,
        previous_positions=(),
    )
    assert candidates == ()


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


def test_cop_public_hint_is_also_a_plausible_lie(tmp_path, monkeypatch):
    runner = _runner(tmp_path, role=AgentRole.COP)
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
