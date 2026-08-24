"""History-aware, obstacle-aware movement planning using local truth only."""

from __future__ import annotations

from collections import Counter, deque

from police_thief.domain.board import Move, Position
from police_thief.domain.strategy.planner_evaluate import _EvaluateMixin
from police_thief.domain.strategy.planner_outlook import _OutlookMixin
from police_thief.domain.strategy.planner_scoring import _ScoreMoveMixin
from police_thief.domain.strategy.planner_types import ActionEvaluation, StrategyPlan
from police_thief.shared.constants import AgentRole

__all__ = ["ActionEvaluation", "StrategyPlan", "TacticalPlanner"]




class TacticalPlanner(_EvaluateMixin, _ScoreMoveMixin, _OutlookMixin):
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
