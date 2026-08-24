"""Scoring a single candidate move -- the heuristic the strategy rests on,
moved verbatim."""

from __future__ import annotations

from collections import Counter

from police_thief.domain.board import Board, Move, Position
from police_thief.domain.capture import cop_capture_cells
from police_thief.domain.strategy.planner_geometry import _expected_distance, _shortest_distance
from police_thief.domain.strategy.planner_types import ActionEvaluation
from police_thief.shared.constants import AgentRole


class _ScoreMoveMixin:
    """Scores one candidate action."""

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
            escape_space = sum(
                probability
                * (0.0 if destination == target else board.reachable_area(destination, extra_blocked=target))
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
                + 0.6 * escape_space
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
