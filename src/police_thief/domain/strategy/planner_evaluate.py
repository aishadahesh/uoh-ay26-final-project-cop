"""Ranking every legal action for the current turn.

Split out of tactical_planner.py and mixed back in."""

from __future__ import annotations

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Move, Position
from police_thief.domain.strategy.planner_types import StrategyPlan
from police_thief.shared.constants import AgentRole


class _EvaluateMixin:
    """Produces the ranked StrategyPlan for a turn."""

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
            if clearances and not loop_detected:
                best_clearance = max(clearances.values())
                hard_excluded.update(
                    move for move, clearance in clearances.items()
                    if clearance < best_clearance
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
