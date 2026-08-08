"""Focused regression tests for path planning and anti-loop behavior."""

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.strategy.tactical_planner import TacticalPlanner
from police_thief.shared.constants import AgentRole


def _belief_at(board: Board, target: Position) -> BeliefMap:
    belief = BeliefMap(board)
    belief._belief = {position: float(position == target) for position in belief._belief}
    return belief


def test_cop_uses_an_alternative_path_when_direct_route_is_blocked():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.place_barrier(Position(0, 0), Position(0, 1))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), _belief_at(board, Position(0, 4))
    )
    assert plan.selected is Move.SOUTH
    assert plan.selected in plan.allowed_moves


def test_detected_abab_loop_excludes_reversal_and_stay_when_alternatives_exist():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    planner = TacticalPlanner(AgentRole.COP)
    a, b = Position(0, 0), Position(0, 1)
    planner.record_move(a, Move.EAST, b)
    planner.record_move(b, Move.WEST, a)
    planner.record_move(a, Move.EAST, b)
    plan = planner.evaluate(board, b, _belief_at(board, Position(0, 6)))
    assert plan.loop_detected is True
    assert "oscillation" in plan.loop_reason
    assert Move.WEST in plan.excluded_moves
    assert Move.STAY in plan.excluded_moves
    assert plan.selected not in (Move.WEST, Move.STAY)


def test_thief_prefers_open_escape_route_over_equal_distance_corner():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board, Position(0, 1), _belief_at(board, Position(1, 1))
    )
    assert plan.selected is Move.EAST


def test_every_currently_legal_move_receives_an_explainable_score():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    own = Position(3, 3)
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board, own, _belief_at(board, Position(1, 1))
    )
    assert {item.move for item in plan.evaluations} == set(board.legal_moves(own))
    assert all("total=" in item.summary() and "path=" in item.summary() for item in plan.evaluations)


def test_gemini_allowed_moves_exclude_materially_worse_legal_actions():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), _belief_at(board, Position(6, 6))
    )
    assert set(plan.allowed_moves) == {Move.EAST, Move.SOUTH}
    assert Move.STAY not in plan.allowed_moves


def test_subgame_seed_varies_only_equally_strong_opening_routes():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_at(board, Position(5, 5))
    first = TacticalPlanner(AgentRole.COP, strategy_seed=1).evaluate(
        board, Position(0, 0), belief
    )
    second = TacticalPlanner(AgentRole.COP, strategy_seed=2).evaluate(
        board, Position(0, 0), belief
    )
    assert {first.selected, second.selected} == {Move.EAST, Move.SOUTH}
    assert next(item for item in first.evaluations if item.move is first.selected).path_distance == next(
        item for item in second.evaluations if item.move is second.selected
    ).path_distance


def test_cop_never_stays_while_a_search_move_is_available():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), _belief_at(board, Position(0, 0))
    )

    assert Move.STAY not in plan.allowed_moves
    assert plan.selected is not Move.STAY


def test_thief_uses_confirmed_cop_position_to_avoid_repeated_corner_capture():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(6, 0),
        _belief_at(board, Position(0, 0)),
        known_opponent_position=Position(5, 1),
    )

    assert plan.selected is Move.STAY
    assert plan.allowed_moves == (Move.STAY,)


def test_thief_does_not_repeat_the_recorded_seven_turn_capture_route():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_at(board, Position(0, 0))
    planner = TacticalPlanner(AgentRole.THIEF, strategy_seed=2)
    thief = Position(3, 3)
    cop = Position(0, 0)
    recorded_cop_moves = (
        Move.SOUTH,
        Move.SOUTH,
        Move.EAST,
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.WEST,
    )
    selected: list[Move] = []

    for cop_move in recorded_cop_moves:
        plan = planner.evaluate(
            board,
            thief,
            belief,
            known_opponent_position=cop,
        )
        before = thief
        thief = board.apply_move(thief, plan.selected)
        planner.record_move(before, plan.selected, thief)
        selected.append(plan.selected)
        assert thief != cop

        cop = board.apply_move(cop, cop_move)
        assert thief != cop

    assert selected != [
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.WEST,
        Move.WEST,
        Move.WEST,
        Move.NORTH,
    ]


def test_cop_captures_the_recorded_game_one_path_without_stalling():
    class ZeroScent:
        @staticmethod
        def intensity_at(_position):
            return 0.0

    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = BeliefMap(board)
    belief.set_certain_position(Position(3, 3))
    planner = TacticalPlanner(AgentRole.COP, strategy_seed=1)
    cop = Position(0, 0)
    thief = Position(3, 3)
    thief_moves = (
        Move.EAST,
        Move.EAST,
        Move.SOUTH,
        Move.EAST,
        Move.SOUTH,
        *(Move.STAY for _ in range(19)),
        Move.NORTH,
        Move.SOUTH,
        Move.STAY,
        Move.STAY,
        Move.WEST,
        Move.WEST,
        Move.NORTH,
        Move.STAY,
    )
    cop_moves: list[Move] = []

    for thief_move in thief_moves:
        thief = board.apply_move(thief, thief_move)
        belief.update_from_scent(ZeroScent())
        plan = planner.evaluate(board, cop, belief)
        before = cop
        cop = board.apply_move(cop, plan.selected)
        planner.record_move(before, plan.selected, cop)
        cop_moves.append(plan.selected)
        if cop == thief:
            break

    assert cop == thief == Position(4, 4)
    assert len(cop_moves) == 32
    assert Move.STAY not in cop_moves
