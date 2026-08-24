"""History-aware, obstacle-aware movement planning using local truth only."""

from __future__ import annotations

import hashlib
from collections import Counter, deque
from dataclasses import dataclass

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Move, Position
from police_thief.domain.capture import cop_capture_cells
from police_thief.shared.constants import AgentRole


@dataclass(frozen=True)
class ActionEvaluation:
    move: Move
    destination: Position
    total: float
    path_distance: float
    mobility: int
    future_value: float
    revisit_penalty: float
    loop_penalty: float
    dead_end_penalty: float
    variation_bonus: float
    direct_capture_risk: float = 0.0
    proximity_risk: float = 0.0
    escape_routes: float = 0.0
    trap_risk: float = 0.0
    intercept_distance: float = 0.0
    containment: float = 0.0
    escape_space: float = 0.0
    boundary_penalty: float = 0.0

    def summary(self) -> str:
        return (
            f"total={self.total:.2f}, path={self.path_distance:.2f}, "
            f"mobility={self.mobility}, future={self.future_value:.2f}, "
            f"revisit={self.revisit_penalty:.2f}, loop={self.loop_penalty:.2f}, "
            f"dead_end={self.dead_end_penalty:.2f}, variation={self.variation_bonus:.2f}, "
            f"direct_capture_risk={self.direct_capture_risk:.3f}, "
            f"proximity_risk={self.proximity_risk:.3f}, "
            f"escape_routes={self.escape_routes:.2f}, trap_risk={self.trap_risk:.3f}, "
            f"boundary={self.boundary_penalty:.2f}"
        )


@dataclass(frozen=True)
class StrategyPlan:
    selected: Move
    evaluations: tuple[ActionEvaluation, ...]
    allowed_moves: tuple[Move, ...]
    loop_detected: bool
    loop_reason: str
    excluded_moves: tuple[Move, ...]
    recent_positions: tuple[Position, ...]
    recent_actions: tuple[Move, ...]


class TacticalPlanner:
    """Score legal moves and suppress actions that continue a detected loop."""

    STRATEGIC_SCORE_MARGIN = 1.0

    def __init__(
        self, role: AgentRole, history_limit: int = 12, strategy_seed: int = 0
    ) -> None:
        self.role = role
        self.strategy_seed = strategy_seed
        self._positions: deque[Position] = deque(maxlen=history_limit)
        self._moves: deque[Move] = deque(maxlen=history_limit)
        self._visits: Counter[Position] = Counter()

    @property
    def recent_positions(self) -> tuple[Position, ...]:
        return tuple(self._positions)

    @property
    def recent_moves(self) -> tuple[Move, ...]:
        return tuple(self._moves)

    def record_move(self, before: Position, move: Move, after: Position) -> None:
        if not self._positions or self._positions[-1] != before:
            self._positions.append(before)
            self._visits[before] += 1
        self._moves.append(move)
        self._positions.append(after)
        self._visits[after] += 1

    def evaluate(
        self,
        board: Board,
        own: Position,
        belief: BeliefMap,
        known_opponent_position: Position | None = None,
        plausible_opponent_positions: tuple[Position, ...] = (),
    ) -> StrategyPlan:
        legal = board.legal_moves(own)
        if not legal:
            raise RuntimeError("board returned no legal moves (STAY must always be legal)")
        loop_detected, loop_reason = self._detect_loop(own)
        # Exact public evidence wins.  A public barrier is the next strongest
        # clue: its target proves that the cop occupies either that cell or an
        # orthogonally adjacent one.  Only when neither exists do we use the
        # probabilistic scent belief.  No hidden opponent state is consulted.
        if known_opponent_position is not None:
            belief_targets = ((known_opponent_position, 1.0),)
        elif plausible_opponent_positions:
            candidates = tuple(dict.fromkeys(plausible_opponent_positions))
            probability = 1.0 / len(candidates)
            belief_targets = tuple((position, probability) for position in candidates)
        else:
            belief_targets = belief.top_positions(5)
        evidence_backed = (
            known_opponent_position is not None or bool(plausible_opponent_positions)
        )
        # Retain visit pressure for the entire mini-game, not just the short
        # loop-detection window.  With an empty scent grid the former behavior
        # forgot old cells and repeatedly searched the same central corridor.
        visits = self._visits.copy()
        evaluations = tuple(
            self._score_move(
                board,
                own,
                move,
                destination,
                belief_targets,
                visits,
                loop_detected,
                evidence_backed,
            )
            for move, destination in legal.items()
        )
        hard_excluded: set[Move] = set()
        # An active cop must keep searching whenever at least one movement is
        # possible.  STAY remains legal for protocol correctness, but is not a
        # strategic candidate unless barriers have genuinely boxed the cop in.
        if self.role is AgentRole.COP:
            mobile_moves = tuple(
                item
                for item in evaluations
                if item.move is not Move.STAY and item.mobility > 0
            )
            if any(move is not Move.STAY for move in legal):
                hard_excluded.add(Move.STAY)
            if mobile_moves:
                # A barrier may legally be placed on the cop's occupied cell.
                # After leaving that blocked cell, however, the cop cannot move
                # back through it.  Entering a pocket with zero onward moves
                # therefore boxes the cop in permanently and forces STAY for
                # every remaining turn.  Treat that as a safety constraint,
                # not a score penalty, whenever a mobile route exists.
                #
                # The sole exception is an exact, publicly established
                # opponent position: landing there is an immediate capture
                # opportunity and must not be discarded merely because the
                # capture cell itself is a dead end.  A scent/belief peak is
                # not exact evidence and cannot invoke this exception.
                hard_excluded.update(
                    item.move
                    for item in evaluations
                    if (
                        item.move is not Move.STAY
                        and item.mobility == 0
                        and item.destination != known_opponent_position
                    )
                )
        if self.role is AgentRole.THIEF:
            # Risk is a constraint, not merely a score.  The former planner
            # hard-filtered danger only when the cop published an exact cell;
            # with scent/boundary evidence it could still accept a high-scoring
            # move directly into capture.  Eliminate each risk tier whenever a
            # safer legal alternative exists, while retaining at least one move
            # when the thief is genuinely cornered.
            safety_pool = evaluations
            direct_safe = tuple(
                item for item in safety_pool if item.direct_capture_risk == 0.0
            )
            if direct_safe:
                hard_excluded.update(
                    item.move for item in safety_pool if item.direct_capture_risk > 0.0
                )
                safety_pool = direct_safe
            proximity_safe = tuple(
                item for item in safety_pool if item.proximity_risk == 0.0
            )
            if proximity_safe:
                hard_excluded.update(
                    item.move for item in safety_pool if item.proximity_risk > 0.0
                )
                safety_pool = proximity_safe
            trap_safe = tuple(item for item in safety_pool if item.trap_risk == 0.0)
            if trap_safe:
                hard_excluded.update(
                    item.move for item in safety_pool if item.trap_risk > 0.0
                )
                safety_pool = trap_safe
            # A currently safe boundary move can still hand the Police an
            # irreversible two-barrier corner trap. If an equally safe option
            # remains farther from the boundary, keep the Thief in that tier.
            # This is a hard strategic constraint because Gemini may otherwise
            # override a small numeric preference with a near-tied edge move.
            clearances = {
                item.move: min(
                    item.destination.row,
                    item.destination.col,
                    board.config.grid_size - 1 - item.destination.row,
                    board.config.grid_size - 1 - item.destination.col,
                )
                for item in safety_pool
            }
            # Only the board edge itself is a hard constraint. Excluding every
            # move below the BEST available clearance made this a filter rather
            # than a preference, and on a 7x7 the single centre cell (3,3) has
            # strictly greater clearance than all four of its neighbours -- so
            # a thief standing there, which is exactly the mandated thief_start,
            # had every move but STAY eliminated and could never leave. In the
            # yanell11 G010 logs our thief sat on (3,3) for ten consecutive
            # turns while the cop walled the board around it, in all three
            # sub-games it played as thief. Relative centrality is already
            # priced by boundary_penalty in _score_move; this constraint now
            # only keeps the thief off the edge, where the Police can build an
            # irreversible two-barrier corner trap.
            if clearances and not loop_detected:
                interior = {
                    move for move, clearance in clearances.items() if clearance >= 1
                }
                if interior:
                    hard_excluded.update(
                        move for move, clearance in clearances.items() if clearance < 1
                    )

        excluded: set[Move] = set(hard_excluded)
        if loop_detected and len(evaluations) > 1:
            recent_cells = set(tuple(self._positions)[-2:])
            for item in evaluations:
                if item.move is Move.STAY or item.destination in recent_cells:
                    excluded.add(item.move)
        if len(excluded) == len(evaluations):
            # Relax history preferences before safety constraints.  This lets
            # a cornered thief STAY when every movement can be captured next
            # turn, instead of re-enabling a losing move merely to break a loop.
            hard_safe = tuple(
                item for item in evaluations if item.move not in hard_excluded
            )
            retained = max(hard_safe or evaluations, key=self._rank_key)
            excluded.discard(retained.move)
        admissible = tuple(item for item in evaluations if item.move not in excluded)
        candidates = admissible or evaluations
        best_score = max(item.total for item in candidates)
        strategic = tuple(
            item
            for item in candidates
            if item.total >= best_score - self.STRATEGIC_SCORE_MARGIN
        )
        selected = max(strategic, key=self._rank_key).move
        return StrategyPlan(
            selected=selected,
            evaluations=tuple(sorted(evaluations, key=self._rank_key, reverse=True)),
            # Gemini may choose among genuinely close alternatives, but cannot
            # override the planner with a legal yet strategically poor action.
            allowed_moves=tuple(item.move for item in strategic),
            loop_detected=loop_detected,
            loop_reason=loop_reason,
            excluded_moves=tuple(move for move in legal if move in excluded),
            recent_positions=tuple(self._positions),
            recent_actions=tuple(self._moves),
        )

    @staticmethod
    def _rank_key(item: ActionEvaluation) -> tuple[float, int, int]:
        # Stable deterministic tie-break: moving beats STAY, then enum order from Board.
        return item.total, int(item.move is not Move.STAY), -list(Move).index(item.move)

    def _detect_loop(self, own: Position) -> tuple[bool, str]:
        positions = tuple(self._positions)
        moves = tuple(self._moves)
        if len(positions) >= 3 and positions[-3] == positions[-1]:
            return True, "ABA immediate-backtrack oscillation"
        if len(positions) >= 4 and positions[-4] == positions[-2] and positions[-3] == positions[-1]:
            return True, "ABAB position oscillation"
        if len(moves) >= 4 and moves[-4] == moves[-2] and moves[-3] == moves[-1]:
            return True, "ABAB action oscillation"
        if positions.count(own) >= 3:
            return True, "current cell visited at least three times"
        if len(moves) >= 2 and moves[-1] is Move.STAY and moves[-2] is Move.STAY:
            return True, "consecutive STAY actions"
        return False, ""

    def _score_move(
        self,
        board: Board,
        own: Position,
        move: Move,
        destination: Position,
        targets: tuple[tuple[Position, float], ...],
        visits: Counter[Position],
        loop_detected: bool,
        evidence_backed: bool,
    ) -> ActionEvaluation:
        distances = [(_shortest_distance(board, destination, target), probability) for target, probability in targets]
        weight = sum(probability for _, probability in distances) or 1.0
        expected_distance = sum(distance * probability for distance, probability in distances) / weight
        direct_capture_risk = sum(
            probability
            for target, probability in targets
            if destination == target
        ) / weight
        proximity_risk = sum(
            probability
            for target, probability in targets
            if destination in cop_capture_cells(board, target)
        ) / weight
        mobility = sum(candidate is not Move.STAY for candidate in board.legal_moves(destination))
        future_value = self._future_value(board, destination, targets)
        escape_routes, trap_risk = self._escape_outlook(board, destination, targets)
        revisit_penalty = 4.0 * visits[destination]
        loop_penalty = 0.0
        if len(self._positions) >= 2 and destination == self._positions[-2]:
            loop_penalty += 15.0
        if self._moves and move == self._moves[-1]:
            loop_penalty += 2.0
        if move is Move.STAY:
            loop_penalty += 9.0
        if loop_detected and (move is Move.STAY or destination in set(tuple(self._positions)[-2:])):
            loop_penalty += 25.0
        dead_end_penalty = 24.0 if mobility <= 1 else (12.0 if mobility == 2 else 0.0)
        variation_bonus = self._variation_bonus(own, move)

        intercept_distance = 0.0
        containment = 0.0
        escape_space = 0.0
        boundary_penalty = 0.0
        if self.role is AgentRole.COP:
            current_distance = _expected_distance(board, own, targets)
            progress = current_distance - expected_distance
            # Interception and containment require public evidence provenance,
            # not an arbitrary probability threshold. A four-cell public set
            # is actionable even though each cell has only 0.25 mass, while a
            # diffuse belief fallback must not perturb the established sweep.
            if evidence_backed:
                # Interception: evaluate the worst legal one-step flight from
                # EACH proposed destination.  The former implementation chose
                # one evasive reply relative to the cop's current cell and
                # reused it for every action.  That made the cop follow a
                # moving scent peak one step behind instead of selecting the
                # move that covers the whole escape frontier.
                intercept_distance = sum(
                    probability
                    * max(
                        _shortest_distance(board, destination, reply)
                        for reply in set(board.legal_moves(target).values())
                    )
                    for target, probability in targets
                ) / weight
                # Occupying an exit is useful even on an otherwise open board,
                # where reachable-area containment is identical for almost
                # every move.  Count the local escape edges that remain after
                # the proposed destination is treated as the cop's capture
                # cell; fewer routes means genuine pressure rather than trail
                # following.
                escape_routes = sum(
                    probability
                    * sum(
                        reply != destination
                        for reply in set(board.legal_moves(target).values())
                        if reply != target
                    )
                    for target, probability in targets
                ) / weight
                # Containment: the escape space the believed thief keeps if
                # we stand at `destination`.  Standing in a pocket's doorway
                # collapses this area and turns barriers already on the
                # board into a cage; plain distance-chasing never sees that.
                containment = sum(
                    probability
                    * (0 if destination == target else board.reachable_area(target, extra_blocked=destination))
                    for target, probability in targets
                ) / weight
            total = (
                -10.0 * expected_distance
                - 4.0 * intercept_distance
                + 7.0 * progress
                + 1.4 * mobility
                + 2.0 * future_value
                - 0.35 * containment
                - 3.5 * escape_routes
                - revisit_penalty
                - loop_penalty
                - 0.4 * dead_end_penalty
                + variation_bonus
            )
        else:
            # Assume the believed cop takes its best one-step approach, then value
            # our best following escape. This is a conservative two-ply safety view.
            capture_margin = max(0.0, expected_distance - 1.0)
            # Open-space preference: reachable area with the believed cop
            # treated as one more wall.  Slipping into a region whose sole
            # doorway the cop occupies reads as ~zero escape space here even
            # when one-step mobility still looks healthy.
            # Worst-case room left once the cop spends its next barrier. The
            # earlier version read plain reachable area, which against a
            # partition-and-shrink cop stays flat while the wall is built and
            # then collapses in a single turn -- in the yanell11 G010 logs our
            # thief sat on the doorway cell for ten turns watching its area
            # drift 48 -> 45, then lost 20 cells in one move and was captured
            # six turns later, three times identically.
            escape_space = sum(
                probability
                * (0.0 if destination == target else self._sealable_escape_space(board, destination, target))
                for target, probability in targets
            ) / weight
            # Current mobility overvalues an arena edge. The Police may spend
            # its turn permanently removing one adjacent cell, so three legal
            # moves at an edge can become one irreversible exit in two turns.
            # Prefer interior escape space while it is safe to do so; the hard
            # capture-risk filters above still take priority.
            boundary_clearance = min(
                destination.row,
                destination.col,
                board.config.grid_size - 1 - destination.row,
                board.config.grid_size - 1 - destination.col,
            )
            edge_count = int(
                destination.row in (0, board.config.grid_size - 1)
            ) + int(destination.col in (0, board.config.grid_size - 1))
            boundary_penalty = 20.0 * edge_count
            if boundary_clearance == 1:
                boundary_penalty += 6.0
            total = (
                9.0 * capture_margin
                + 3.0 * future_value
                + 2.2 * mobility
                + 5.0 * escape_routes
                # Room to run is the thief's real currency: at 0.6 a cell it
                # was worth less than one edge-avoidance step, so the planner
                # preferred a central cell in a closing pocket over an edge
                # cell in open board. Space now outranks cosmetic centrality.
                + 3.0 * escape_space
                - revisit_penalty
                - loop_penalty
                - dead_end_penalty
                + variation_bonus
                - 1000.0 * direct_capture_risk
                - 250.0 * proximity_risk
                - 300.0 * trap_risk
                - boundary_penalty
            )
        return ActionEvaluation(
            move=move,
            destination=destination,
            total=total,
            path_distance=expected_distance,
            mobility=mobility,
            future_value=future_value,
            revisit_penalty=revisit_penalty,
            loop_penalty=loop_penalty,
            dead_end_penalty=dead_end_penalty,
            variation_bonus=variation_bonus,
            direct_capture_risk=direct_capture_risk,
            proximity_risk=proximity_risk,
            escape_routes=escape_routes,
            trap_risk=trap_risk,
            intercept_distance=intercept_distance,
            containment=containment,
            escape_space=escape_space,
            boundary_penalty=boundary_penalty,
        )

    def _escape_outlook(
        self,
        board: Board,
        destination: Position,
        targets: tuple[tuple[Position, float], ...],
    ) -> tuple[float, float]:
        """Conservatively score the thief's next escape after the cop responds.

        For each public-belief cop candidate, the cop is allowed its best legal
        reply. We then count thief continuations that also stay outside the
        cop's following one-step capture range. This is a small three-ply
        search over legal board moves; it uses no private opponent state.
        """
        if self.role is AgentRole.COP:
            return 0.0, 0.0
        weight = sum(probability for _, probability in targets) or 1.0
        thief_continuations = set(board.legal_moves(destination).values())
        expected_routes = 0.0
        trapped_weight = 0.0

        def safe_continuation_count(cop_reply: Position) -> int:
            if cop_reply == destination:
                return 0
            next_capture_cells = cop_capture_cells(board, cop_reply)
            return sum(
                continuation not in next_capture_cells
                for continuation in thief_continuations
            )

        for target, probability in targets:
            if destination in cop_capture_cells(board, target):
                worst_case_routes = 0
            else:
                worst_case_routes = min(
                    safe_continuation_count(cop_reply)
                    for cop_reply in set(board.legal_moves(target).values())
                )
            expected_routes += probability * worst_case_routes
            if worst_case_routes == 0:
                trapped_weight += probability
        return expected_routes / weight, trapped_weight / weight

    def _sealable_escape_space(
        self,
        board: Board,
        destination: Position,
        cop: Position,
    ) -> float:
        """Escape space left if the cop spends its next turn sealing us in.

        Plain reachable area is a lagging signal against a wall-builder: it
        barely moves while the wall goes up and then collapses in one turn,
        far too late to run. The cop may place a barrier on its own cell or
        any open neighbour (Sec. 3.3.3-3.3.4), so the honest figure is the
        WORST area over those placements -- which drops as soon as the cop
        is one move from a chokepoint, not after it has already stepped
        through it.
        """
        options = [cop, *(n for n in board.neighbors(cop) if not board.is_blocked(n))]
        worst = board.reachable_area(destination, extra_blocked=cop)
        for cell in options:
            if cell == destination:
                return 0.0
            worst = min(worst, board.reachable_area(destination, extra_blocked=cell))
        return float(worst)

    def _variation_bonus(self, own: Position, move: Move) -> float:
        """Small stable preference that varies only strategically close choices.

        A league sub-game seed prevents six fresh planners from replaying the
        same symmetric opening. The bonus is deliberately below 0.5, far less
        than the objective terms, so it cannot rescue a materially worse move.
        Seed zero preserves the historical deterministic unit-test baseline.
        """
        if self.strategy_seed == 0:
            return 0.0
        material = (
            f"{self.strategy_seed}:{self.role.value}:{len(self._moves) + 1}:"
            f"{own.row}:{own.col}:{move.value}"
        ).encode()
        value = int.from_bytes(hashlib.sha256(material).digest()[:4], "big")
        return (value / 0xFFFFFFFF) * 0.89

    def _future_value(
        self,
        board: Board,
        destination: Position,
        targets: tuple[tuple[Position, float], ...],
    ) -> float:
        next_positions = [
            candidate
            for move, candidate in board.legal_moves(destination).items()
            if move is not Move.STAY
        ] or [destination]
        future_distances = [_expected_distance(board, candidate, targets) for candidate in next_positions]
        if self.role is AgentRole.COP:
            # Higher is better, so negate the shortest continuation distance.
            return -min(future_distances)
        return max(future_distances)


def _expected_distance(
    board: Board,
    source: Position,
    targets: tuple[tuple[Position, float], ...],
) -> float:
    weight = sum(probability for _, probability in targets) or 1.0
    return sum(_shortest_distance(board, source, target) * probability for target, probability in targets) / weight


def _shortest_distance(board: Board, start: Position, goal: Position) -> int:
    """Breadth-first path distance around barriers; Manhattan is its lower bound."""
    if start == goal:
        return 0
    queue: deque[tuple[Position, int]] = deque([(start, 0)])
    visited = {start}
    while queue:
        current, distance = queue.popleft()
        for neighbor in board.neighbors(current):
            # A cop may legally place a barrier on its occupied cell.  Such a
            # cell is blocked for entry but is still the distance target.
            if neighbor == goal:
                return distance + 1
            if neighbor in visited or board.is_blocked(neighbor):
                continue
            visited.add(neighbor)
            queue.append((neighbor, distance + 1))
    return board.config.grid_size ** 2 + 1
