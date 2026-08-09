"""The Manhattan-distance heuristic strategy track (Chapter 6, Sec. 6.2.2/6.3).

One of three algorithmically-equal tracks (heuristic / custom / optional
RL) -- per docs/PLAN.md ADR-010, this is the team's chosen baseline. Moves
toward (cop) or away from (thief) the belief map's current best guess,
never the opponent's true position, using the mandatory Manhattan-distance
formula (Sec. 6.3.2) shared with the Chapter 3/4 placeholder policies via
domain/heuristics.py.
"""

from __future__ import annotations

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Move, Position
from police_thief.domain.heuristics import manhattan_distance
from police_thief.domain.strategy.brain_base import BrainBase
from police_thief.domain.strategy.tactical_planner import StrategyPlan, TacticalPlanner
from police_thief.shared.constants import AgentRole


class ManhattanHeuristicBrain(BrainBase):
    """Chases the belief peak if `role` is COP, flees it if THIEF."""

    def __init__(self, role: AgentRole, strategy_seed: int = 0) -> None:
        self.role = role
        self.planner = TacticalPlanner(role, strategy_seed=strategy_seed)
        self.last_plan: StrategyPlan | None = None

    def _decide_move(
        self,
        board: Board,
        own: Position,
        belief: BeliefMap,
        known_opponent_position: Position | None = None,
        plausible_opponent_positions: tuple[Position, ...] = (),
    ) -> Move:
        self.last_plan = self.planner.evaluate(
            board,
            own,
            belief,
            known_opponent_position=known_opponent_position,
            plausible_opponent_positions=plausible_opponent_positions,
        )
        return self.last_plan.selected

    def record_move(self, before: Position, move: Move, after: Position) -> None:
        """Record the action actually executed (Gemini may override the plan)."""
        self.planner.record_move(before, move, after)

    def _pick_move(self, board: Board, own: Position, belief: BeliefMap) -> Position | None:
        """Cop-only: choose the barrier target that most shrinks the
        thief's believed escape space, among `own`'s current cell and its
        open neighbors -- both legal targets per Sec. 3.3.3/3.3.4.

        Enhancement over an earlier nearest-to-belief-peak version: rather
        than blindly nudging toward the believed position, each candidate
        is scored by how much it shrinks the *reachable area* from that
        position (`Board.reachable_area`, a flood fill treating the
        candidate as one more blocked cell) -- a real "does this actually
        corner the thief" measure, not just "is this cell closer to my
        best guess." A candidate that only removes itself from the board
        (no genuine chokepoint yet, a 1-cell drop) is not worth spending
        the budget on; only a candidate that disconnects a larger pocket
        (a drop greater than 1) is placed. This also gives the heuristic
        real budget discipline for free (docs/TODO.md T0256): it stops
        spending a barrier every single turn regardless of usefulness, and
        instead waits until one would actually matter -- e.g. sealing the
        cop's own current cell behind it once that cell is the sole
        doorway into the pocket the thief is believed to be hiding in.

        Already-blocked neighbors are excluded from consideration -- found
        empirically while wiring this into a live match: without this
        filter, an earlier version of this heuristic could keep
        "targeting" the same already-blocked cell turn after turn, wasting
        the entire barrier budget on placements `Board.place_barrier`
        would now reject outright as redundant.
        """
        if self.role is not AgentRole.COP or board.remaining_barrier_budget <= 0:
            return None
        open_neighbors = [
            neighbor for neighbor in board.neighbors(own) if not board.is_blocked(neighbor)
        ]
        # A barrier must never eliminate the cop's last escape route.  This
        # exact failure boxed the cop at (0,3) in the reviewed G001 series and
        # forced ten consecutive STAY turns.
        candidates = [
            candidate
            for candidate in (own, *open_neighbors)
            if (
                len(open_neighbors)
                if candidate == own
                else len(open_neighbors) - 1
            )
            >= 2
        ]
        if not candidates:
            return None
        target = belief.arg_max()
        target_confidence = belief.belief_at(target)
        # Blocking the predicted cell gives a direct capture claim, but it is
        # worth attempting only when public evidence is meaningfully focused.
        # Otherwise a flat/no-scent belief would spend barriers on arbitrary
        # tie-broken cells and gradually wall in the cop.
        if (
            target_confidence >= 0.35
            and target in candidates
            and target != own
        ):
            return target
        structural_candidates = [candidate for candidate in candidates if candidate != target]
        if not structural_candidates:
            return None
        baseline_area = board.reachable_area(target)
        best_area, best_candidate = min(
            (
                (board.reachable_area(target, extra_blocked=candidate), candidate)
                for candidate in structural_candidates
            ),
            key=lambda scored: (scored[0], manhattan_distance(scored[1], target)),
        )
        if baseline_area - best_area <= 1:
            return None
        return best_candidate
