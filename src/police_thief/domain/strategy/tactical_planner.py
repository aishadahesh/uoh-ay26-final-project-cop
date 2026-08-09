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

    def summary(self) -> str:
        return (
            f"total={self.total:.2f}, path={self.path_distance:.2f}, "
            f"mobility={self.mobility}, future={self.future_value:.2f}, "
            f"revisit={self.revisit_penalty:.2f}, loop={self.loop_penalty:.2f}, "
            f"dead_end={self.dead_end_penalty:.2f}, variation={self.variation_bonus:.2f}, "
            f"direct_capture_risk={self.direct_capture_risk:.3f}, "
            f"proximity_risk={self.proximity_risk:.3f}, "
            f"escape_routes={self.escape_routes:.2f}, trap_risk={self.trap_risk:.3f}"
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
        # Retain visit pressure for the entire mini-game, not just the short
        # loop-detection window.  With an empty scent grid the former behavior
        # forgot old cells and repeatedly searched the same central corridor.
        visits = self._visits.copy()
        evaluations = tuple(
            self._score_move(board, own, move, destination, belief_targets, visits, loop_detected)
            for move, destination in legal.items()
        )
        hard_excluded: set[Move] = set()
        # An active cop must keep searching whenever at least one movement is
        # possible.  STAY remains legal for protocol correctness, but is not a
        # strategic candidate unless barriers have genuinely boxed the cop in.
        if self.role is AgentRole.COP and any(move is not Move.STAY for move in legal):
            hard_excluded.add(Move.STAY)
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
        if self.role is AgentRole.COP:
            current_distance = _expected_distance(board, own, targets)
            progress = current_distance - expected_distance
            # Pursuit terms are gated on a genuinely focused target: with an
            # exact/near-exact public fix (a fresh scent center, a barrier
            # deduction, or a published cell) they stop the cop from
            # tail-chasing; against a flat searching belief they would only
            # add noise to the sweep that the plain distance objective and
            # revisit pressure already handle well.
            focused = max((probability for _, probability in targets), default=0.0) >= 0.3
            if focused:
                # Interception: a fleeing thief does not wait on its scent
                # peak.  Also score the destination against each believed
                # cell's best one-step flight from our CURRENT cell, so the
                # cop cuts the corner instead of following decayed scent.
                intercept_distance = sum(
                    probability
                    * _shortest_distance(board, destination, _evasive_reply(board, target, own))
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
            escape_space = sum(
                probability
                * (0.0 if destination == target else board.reachable_area(destination, extra_blocked=target))
                for target, probability in targets
            ) / weight
            total = (
                9.0 * capture_margin
                + 3.0 * future_value
                + 2.2 * mobility
                + 5.0 * escape_routes
                + 0.6 * escape_space
                - revisit_penalty
                - loop_penalty
                - dead_end_penalty
                + variation_bonus
                - 1000.0 * direct_capture_risk
                - 250.0 * proximity_risk
                - 300.0 * trap_risk
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


def _evasive_reply(board: Board, target: Position, chaser: Position) -> Position:
    """The believed thief's best one-step flight from `chaser`: the legal
    destination maximizing BFS distance, with a deterministic tie-break."""
    options = set(board.legal_moves(target).values())
    return max(
        options,
        key=lambda cell: (_shortest_distance(board, chaser, cell), -cell.row, -cell.col),
    )


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
