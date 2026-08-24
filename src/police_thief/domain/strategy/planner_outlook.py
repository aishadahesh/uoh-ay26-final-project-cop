"""Forward-looking terms: escape frontier, variation bonus and two-ply
continuation value."""

from __future__ import annotations

import hashlib

from police_thief.domain.board import Board, Move, Position
from police_thief.domain.capture import cop_capture_cells
from police_thief.domain.strategy.planner_geometry import _expected_distance
from police_thief.shared.constants import AgentRole


class _OutlookMixin:
    """Look-ahead scoring terms."""

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
