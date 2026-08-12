"""Focused regression tests for path planning and anti-loop behavior."""

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
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


def test_four_candidate_public_set_activates_interception_and_containment():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    candidates = (
        Position(4, 4),
        Position(4, 5),
        Position(5, 4),
        Position(5, 5),
    )
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(0, 0),
        BeliefMap(board),
        plausible_opponent_positions=candidates,
    )

    assert any(item.intercept_distance > 0.0 for item in plan.evaluations)
    assert any(item.containment > 0.0 for item in plan.evaluations)
    assert any(item.escape_routes > 0.0 for item in plan.evaluations)


def test_cop_interception_scores_each_destination_against_full_escape_frontier():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    target = Position(6, 3)
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(4, 3),
        BeliefMap(board),
        plausible_opponent_positions=(target,),
    )

    south = next(item for item in plan.evaluations if item.move is Move.SOUTH)
    east = next(item for item in plan.evaluations if item.move is Move.EAST)

    assert south.intercept_distance < east.intercept_distance
    assert south.escape_routes < east.escape_routes
    assert plan.selected is Move.SOUTH


def test_diffuse_belief_does_not_activate_public_evidence_pursuit_terms():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board, Position(0, 0), BeliefMap(board),
    )

    assert all(item.intercept_distance == 0.0 for item in plan.evaluations)
    assert all(item.containment == 0.0 for item in plan.evaluations)


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


def test_single_backtrack_triggers_replanning_before_it_becomes_abab():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    planner = TacticalPlanner(AgentRole.THIEF)
    a, b = Position(3, 3), Position(3, 4)
    planner.record_move(a, Move.EAST, b)
    planner.record_move(b, Move.WEST, a)

    plan = planner.evaluate(board, a, _belief_at(board, Position(0, 0)))

    assert plan.loop_detected is True
    assert "immediate-backtrack" in plan.loop_reason
    assert Move.EAST in plan.excluded_moves
    assert plan.selected not in (Move.EAST, Move.STAY)


def test_thief_prefers_open_escape_route_over_equal_distance_corner():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board, Position(0, 1), _belief_at(board, Position(1, 1))
    )
    east = next(item for item in plan.evaluations if item.move is Move.EAST)
    west = next(item for item in plan.evaluations if item.move is Move.WEST)

    assert plan.selected is Move.EAST
    assert east.path_distance == west.path_distance
    assert east.mobility > west.mobility


def test_every_currently_legal_move_receives_an_explainable_score():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    own = Position(3, 3)
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board, own, _belief_at(board, Position(1, 1))
    )
    assert {item.move for item in plan.evaluations} == set(board.legal_moves(own))
    assert all(
        "total=" in item.summary()
        and "path=" in item.summary()
        and "escape_routes=" in item.summary()
        and "trap_risk=" in item.summary()
        for item in plan.evaluations
    )


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


def test_cop_rejects_recorded_corner_self_trap_after_leaving_own_barrier():
    """A blocked current cell makes the move into (0, 0) irreversible.

    This reproduces the G003 failure: after placing a barrier at (0, 1),
    the cop moved west into a corner whose other exit, (1, 0), was already
    blocked.  It then had no legal movement for the rest of the game.
    """
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.apply_declared_barrier(Position(1, 0))
    board.apply_declared_barrier(Position(0, 1))

    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(0, 1),
        _belief_at(board, Position(0, 0)),
    )

    west = next(item for item in plan.evaluations if item.move is Move.WEST)
    assert west.destination == Position(0, 0)
    assert west.mobility == 0
    assert Move.WEST in plan.excluded_moves
    assert Move.WEST not in plan.allowed_moves
    assert Move.STAY not in plan.allowed_moves
    assert plan.selected in (Move.EAST, Move.SOUTH)


def test_cop_may_enter_a_dead_end_for_an_exact_capture_opportunity():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.apply_declared_barrier(Position(1, 0))
    board.apply_declared_barrier(Position(0, 1))

    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(0, 1),
        BeliefMap(board),
        known_opponent_position=Position(0, 0),
    )

    assert plan.selected is Move.WEST
    assert Move.WEST in plan.allowed_moves
    assert Move.WEST not in plan.excluded_moves


def test_cop_stays_when_barriers_have_genuinely_boxed_it_in():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    board.apply_declared_barrier(Position(0, 1))
    board.apply_declared_barrier(Position(1, 0))

    plan = TacticalPlanner(AgentRole.COP).evaluate(
        board,
        Position(0, 0),
        _belief_at(board, Position(6, 6)),
    )

    assert plan.selected is Move.STAY
    assert plan.allowed_moves == (Move.STAY,)


def test_thief_uses_confirmed_cop_position_to_avoid_repeated_corner_capture():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(6, 0),
        _belief_at(board, Position(0, 0)),
        known_opponent_position=Position(4, 1),
    )

    assert plan.selected in (Move.NORTH, Move.EAST)
    assert Move.STAY not in plan.allowed_moves


def test_thief_does_not_invent_an_illegal_move_then_barrier_capture_range():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(3, 6),
        _belief_at(board, Position(0, 0)),
        known_opponent_position=Position(3, 3),
    )

    west = next(item for item in plan.evaluations if item.move is Move.WEST)
    assert west.destination == Position(3, 5)
    assert west.proximity_risk == 0.0

    no_barrier_board = Board(BoardConfig(grid_size=7, max_barriers=0))
    no_barrier_plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        no_barrier_board,
        Position(3, 6),
        _belief_at(no_barrier_board, Position(0, 0)),
        known_opponent_position=Position(3, 3),
    )
    no_barrier_west = next(
        item for item in no_barrier_plan.evaluations if item.move is Move.WEST
    )
    assert no_barrier_west.proximity_risk == west.proximity_risk


def test_thief_treats_belief_proximity_as_a_hard_constraint():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(1, 6),
        _belief_at(board, Position(2, 5)),
    )

    # WEST, SOUTH, and STAY are within the Police's one-action capture
    # footprint. NORTH is the sole destination at a safe graph distance.
    assert Move.WEST not in plan.allowed_moves
    assert Move.SOUTH not in plan.allowed_moves
    assert plan.allowed_moves == (Move.STAY,)
    assert plan.selected is Move.STAY


def test_public_barrier_evidence_breaks_recorded_step_11_capture_route():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    barrier_target = Position(5, 5)
    plausible_cop_positions = (
        barrier_target,
        *board.neighbors(barrier_target),
    )
    board.apply_declared_barrier(barrier_target)

    plan = TacticalPlanner(AgentRole.THIEF, strategy_seed=2).evaluate(
        board,
        Position(6, 4),
        _belief_at(board, Position(0, 0)),
        plausible_opponent_positions=plausible_cop_positions,
    )

    # In the recorded loss, NORTH entered the cop's actual cell (5,4), and
    # EAST was another plausible cop cell.  WEST is the safe escape corridor.
    assert Move.NORTH not in plan.allowed_moves
    assert Move.EAST not in plan.allowed_moves
    assert plan.selected is Move.WEST


def test_cop_on_own_blocked_barrier_cell_still_threatens_adjacent_cells():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    barrier_target = Position(5, 5)
    board.apply_declared_barrier(barrier_target)
    plan = TacticalPlanner(AgentRole.THIEF).evaluate(
        board,
        Position(6, 4),
        _belief_at(board, Position(0, 0)),
        plausible_opponent_positions=(barrier_target,),
    )

    north = next(item for item in plan.evaluations if item.move is Move.NORTH)
    assert north.proximity_risk == 1.0
    assert Move.NORTH not in plan.allowed_moves


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


def test_thief_escapes_recorded_south_east_pursuit_using_public_scent():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    belief = _belief_at(board, Position(0, 0))
    scent = ScentField(7, ScentConfig())
    brain = ManhattanHeuristicBrain(AgentRole.THIEF, strategy_seed=4)
    thief = Position(3, 3)
    cop = Position(0, 0)
    recorded_cop_moves = (
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.SOUTH,
        Move.EAST,
        Move.EAST,
        Move.EAST,
        Move.EAST,
        Move.SOUTH,
    )

    for index, cop_move in enumerate(recorded_cop_moves):
        known_cop = cop if index == 0 else None
        move = brain._decide_move(
            board, thief, belief, known_opponent_position=known_cop,
        )
        before = thief
        thief = board.apply_move(thief, move)
        brain.record_move(before, move, thief)
        assert thief != cop

        cop = board.apply_move(cop, cop_move)
        assert thief != cop
        scent.decay()
        scent.emit(cop)
        belief.update_from_scent(scent)

    assert abs(thief.row - cop.row) + abs(thief.col - cop.col) >= 3


def test_thief_avoids_deeper_boundary_cells_before_police_can_seal_corner():
    """Regression for G003 g02/g04/g06.

    At (1,5) with the Police publicly known at (2,4), NORTH and EAST are
    immediately safe but both enter boundary corridors. WEST/SOUTH are in the
    Police capture footprint. The planner must refuse both moves that go
    deeper into the top/right boundary and retain the least restrictive safe
    tier instead of voluntarily entering a corner that two barriers can seal.
    """
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    cop = Position(2, 4)
    plan = TacticalPlanner(AgentRole.THIEF, strategy_seed=2).evaluate(
        board,
        Position(1, 5),
        _belief_at(board, cop),
        known_opponent_position=cop,
    )

    assert Move.NORTH not in plan.allowed_moves
    assert Move.EAST not in plan.allowed_moves
    assert plan.selected is Move.STAY


def test_thief_does_not_enter_corner_when_no_interior_escape_exists():
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    cop = Position(1, 4)
    plan = TacticalPlanner(AgentRole.THIEF, strategy_seed=2).evaluate(
        board,
        Position(0, 5),
        _belief_at(board, cop),
        known_opponent_position=cop,
    )

    assert plan.selected is Move.STAY
    assert Move.EAST not in plan.allowed_moves


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
