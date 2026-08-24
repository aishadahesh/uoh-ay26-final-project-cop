"""Capture safety: belief gating, confirmed-cop exclusion, and truthful claims.

Split by theme out of the original `test_capture_safety.py`."""


from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.services.network_match import (
    _audit_revealed_trajectory,
    _confirmed_cop_position,
    _public_barrier_cop_candidates,
    _truthful_capture_claim,
)
from police_thief.shared.constants import AgentRole
from tests.unit.capture_safety_helpers import (
    _CertainBelief,
    _NextTurnUnsafeGemini,
    _runner,
    _UnsafeGemini,
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


def test_stationary_barrier_capture_requires_and_accepts_truthful_response():
    audit = _audit_revealed_trajectory(
        [{"payload": {
            "step": 1, "role": "police",
            "state": {"row": 0, "col": 0},
            "position": [0, 0], "move": "STAY", "intent": True,
            "barrier_placed": [0, 1], "capture_claim": [0, 0],
        }}],
        [{"payload": {
            "step": 2, "role": "thief",
            "state": {"row": 0, "col": 1},
            "position": [0, 1], "terminal_ack": "capture",
            "claim_response": {"claim": [0, 1], "caught": True},
        }}],
        "police",
        "thief",
        Position(0, 0),
        Position(0, 1),
        7,
        allow_terminal_record=True,
    )

    assert audit.errors == ()
    assert audit.capture_step == 1
    assert audit.capture_after_role == "police"


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


def test_thief_exposes_all_safe_actions_under_one_action_capture_range(tmp_path):
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

    assert advisor.context.legal_moves == (Move.NORTH, Move.EAST, Move.STAY)
    assert move in advisor.context.legal_moves
    assert not any("capturable on the cop's next turn" in message for message in messages)


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
    assert any("capturable on the cop's next turn" in message for message in messages)
