"""Bayesian-style belief map over the opponent's likely location (Chapter 6).

docs/tasks.md Sec. 6.3: both agents maintain a probabilistic heatmap b(s)
over the opponent's position, built from the scent field (the one
always-truthful channel, Chapter 4) and updated as new evidence arrives.
Blocked cells always carry zero belief; the peak (arg max_s b(s)) is only
ever a best guess, never certainty (Sec. 6.3.5).

No single Bayes update formula is marked MANDATORY in the rulebook (only
the scent decay formula and the Manhattan-distance move-choice formula
are) -- this implements a standard, principled posterior-proportional-to-
prior-times-likelihood update, using scent intensity as the likelihood
signal.
"""

from __future__ import annotations

from police_thief.domain.board import Board, Position
from police_thief.domain.scent import ScentField

_LIKELIHOOD_EPSILON = 0.01  # keeps unvisited cells possible, never impossible


class BeliefMap:
    """A normalized probability distribution over this board's open cells."""

    def __init__(self, board: Board) -> None:
        self._board = board
        self._belief: dict[Position, float] = {}
        self._reset_to_uniform_prior()

    def _open_cells(self) -> list[Position]:
        size = self._board.config.grid_size
        return [
            Position(r, c)
            for r in range(size)
            for c in range(size)
            if not self._board.is_blocked(Position(r, c))
        ]

    def _reset_to_uniform_prior(self) -> None:
        open_cells = self._open_cells()
        prior = 1.0 / len(open_cells) if open_cells else 0.0
        self._belief = dict.fromkeys(open_cells, prior)

    def belief_at(self, pos: Position) -> float:
        """0.0 for any blocked or otherwise untracked cell."""
        return self._belief.get(pos, 0.0)

    def update_from_scent(self, scent_field: ScentField) -> None:
        """Posterior proportional to prior * likelihood(scent), renormalized.

        Blocked cells are excluded from the distribution entirely (rather
        than included and forced to 0), since they can never legally hold
        the opponent -- this keeps the remaining mass correctly normalized
        to 1 across only the cells that could possibly be true.
        """
        open_cells = self._open_cells()
        # First apply the legal one-turn motion model (stay or move to one
        # orthogonal open neighbor). Without this prediction step, repeated
        # multiplication can permanently lock the peak onto an old scent cell
        # even after the hidden opponent has moved away.
        predicted = dict.fromkeys(open_cells, 0.0)
        for source, probability in self._belief.items():
            destinations = tuple(self._board.legal_moves(source).values())
            share = probability / len(destinations)
            for destination in destinations:
                if destination in predicted:
                    predicted[destination] += share
        unnormalized = {
            pos: predicted.get(pos, 0.0)
            * (scent_field.intensity_at(pos) + _LIKELIHOOD_EPSILON)
            for pos in open_cells
        }
        total = sum(unnormalized.values())
        if total <= 0:
            self._reset_to_uniform_prior()
            return
        self._belief = {pos: value / total for pos, value in unnormalized.items()}

    def arg_max(self) -> Position:
        """The current best guess -- a peak, never a certainty (Sec. 6.3.5)."""
        return max(self._belief, key=self._belief.get)

    def top_positions(self, limit: int = 5) -> tuple[tuple[Position, float], ...]:
        """Highest-probability legal cells for uncertainty-aware planning."""
        if limit <= 0:
            return ()
        return tuple(
            sorted(self._belief.items(), key=lambda item: item[1], reverse=True)[:limit]
        )
