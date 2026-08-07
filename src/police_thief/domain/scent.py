"""Pheromone emission and decay -- Stigmergy for partial observability (Chapter 4).

docs/tasks.md Sec. 4.1-4.2: indirect coordination through changing the shared
environment, inspired by ant colonies. Every agent emits a scent field around
its own position every turn; scent is natural and non-fakeable -- unlike a
verbal hint (Chapter 6), no one can suppress or falsify it. Each side reads
only the OTHER side's scent field, never its own (docs/tasks.md Sec. 4.1.3,
4.3.3) -- this module doesn't enforce that access pattern itself (it has no
concept of "which side is asking"), it just names each field after who
*emits* it, so callers keep that symmetry straight.

Turning a scent field into a probabilistic guess about the opponent's
location (a belief map) is Chapter 6's territory -- this module only
implements the mandatory emission/decay mechanics themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from police_thief.domain.board import Position


@dataclass(frozen=True)
class ScentConfig:
    """The Mandatory Parameters Table's scent values -- all three are FIXED,
    not minimums: docs/tasks.md Sec. 4.2 marks center_intensity, decay_rate,
    and field_size as fixed constants, not team-negotiable floors.
    """

    center_intensity: float = 0.9
    decay_rate: float = 0.10
    field_size: int = 5


class ScentField:
    """One agent's emitted scent across the board, decaying every turn.

    Implements the mandatory update equation exactly (docs/tasks.md Sec. 4.2.4):
        tau_ij(t+1) = max(0, (1 - rho) * tau_ij(t) + delta_tau_ij)

    Calling decay() then emit() once per turn reproduces this in two steps:
    decay() computes (1 - rho) * tau_ij(t) for every tracked cell, and the
    following emit() adds delta_tau_ij on top for cells within this turn's
    footprint. Storage is a sparse dict (board is small; no need for a dense
    array), so untouched cells are implicitly 0.0.
    """

    def __init__(self, grid_size: int, config: ScentConfig | None = None) -> None:
        self.grid_size = grid_size
        self.config = config or ScentConfig()
        self._radius = self.config.field_size // 2
        self._intensity: dict[Position, float] = {}

    def intensity_at(self, pos: Position) -> float:
        return self._intensity.get(pos, 0.0)

    def _emission_delta(self, center: Position, cell: Position) -> float:
        """Radial (Manhattan-distance) falloff within the field's radius.

        The rulebook fixes the field size and center intensity exactly, but
        leaves the interpolation shape as an implementation choice ("falls
        off radially") -- this uses a simple linear falloff to 0 at the edge
        of the field, consistent with the project's orthogonal-only board.
        """
        distance = abs(center.row - cell.row) + abs(center.col - cell.col)
        if distance > self._radius:
            return 0.0
        return self.config.center_intensity * (1 - distance / (self._radius + 1))

    def emit(self, position: Position) -> None:
        """Add this turn's emission footprint centered on `position`."""
        r = self._radius
        for dr in range(-r, r + 1):
            for dc in range(-r, r + 1):
                cell = Position(position.row + dr, position.col + dc)
                if not (0 <= cell.row < self.grid_size and 0 <= cell.col < self.grid_size):
                    continue
                delta = self._emission_delta(position, cell)
                if delta > 0:
                    self._intensity[cell] = self._intensity.get(cell, 0.0) + delta

    def decay(self) -> None:
        """Apply (1 - rho) forgetting to every currently-tracked cell."""
        rho = self.config.decay_rate
        for cell in list(self._intensity):
            value = max(0.0, (1 - rho) * self._intensity[cell])
            if value <= 0.0:
                del self._intensity[cell]
            else:
                self._intensity[cell] = value
