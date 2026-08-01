"""Discrete board geometry, movement, and barrier placement (Chapter 3).

docs/tasks.md Sec. 3.1: there is no external judge -- physics laws are
self-enforced by each agent from the same shared config (config/game.json,
see shared/game_config.py), never hardcoded, and never negotiated
downward below the Mandatory Parameters Table's floors.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class MoveRejectedError(ValueError):
    """Raised whenever an attempted move or barrier placement is illegal.

    docs/tasks.md Sec. 3.3.2/3.3.9: an illegal move must be rejected, never
    silently executed. Callers (the future turn loop / Orchestrator, Ch.8)
    catch this and turn it into a technical-loss outcome.
    """


class Move(StrEnum):
    """The only five legal actions per turn -- diagonal movement is forbidden."""

    NORTH = "N"
    SOUTH = "S"
    EAST = "E"
    WEST = "W"
    STAY = "STAY"


_DELTA: dict[Move, tuple[int, int]] = {
    Move.NORTH: (-1, 0),
    Move.SOUTH: (1, 0),
    Move.EAST: (0, 1),
    Move.WEST: (0, -1),
    Move.STAY: (0, 0),
}


@dataclass(frozen=True)
class Position:
    """An immutable, hashable grid cell (row, col)."""

    row: int
    col: int

    def translated(self, delta: tuple[int, int]) -> Position:
        return Position(self.row + delta[0], self.col + delta[1])


@dataclass(frozen=True)
class BoardConfig:
    """The board's fixed physical laws, loaded from config/game.json.

    grid_size defaults to 7 (Mandatory Parameters Table minimum); origin
    corner and start index are negotiable between teams but must be
    identical on both sides (docs/tasks.md Sec. 3.2.2).
    """

    grid_size: int = 7
    axis_origin_corner: str = "top-left"
    axis_start_index: int = 0
    max_barriers: int = 14


class Board:
    """A grid_size x grid_size board with a set of permanent barrier cells."""

    def __init__(self, config: BoardConfig) -> None:
        self.config = config
        self._blocked: set[Position] = set()
        self._barriers_placed = 0

    @property
    def remaining_barrier_budget(self) -> int:
        return self.config.max_barriers - self._barriers_placed

    def is_within_bounds(self, pos: Position) -> bool:
        return 0 <= pos.row < self.config.grid_size and 0 <= pos.col < self.config.grid_size

    def is_blocked(self, pos: Position) -> bool:
        return pos in self._blocked

    def neighbors(self, pos: Position) -> list[Position]:
        """The up-to-4 orthogonal neighbors that are within bounds (barrier-agnostic)."""
        candidates = (pos.translated(_DELTA[m]) for m in (Move.NORTH, Move.SOUTH, Move.EAST, Move.WEST))
        return [p for p in candidates if self.is_within_bounds(p)]

    def apply_move(self, pos: Position, move: Move) -> Position:
        """Return the resulting position, or raise MoveRejectedError if illegal.

        STAY always succeeds unconditionally: it does not "enter" a new
        cell, so bounds/blocked checks (which govern entering a cell) do
        not apply -- otherwise a cop barrier placed on its own occupied
        cell (legal per Sec. 3.3.4) would wrongly make its own STAY illegal.
        """
        if not isinstance(move, Move):
            raise MoveRejectedError(f"not a legal move: {move!r}")
        if move is Move.STAY:
            return pos
        target = pos.translated(_DELTA[move])
        if not self.is_within_bounds(target):
            raise MoveRejectedError(f"{move} from {pos} leaves the board")
        if self.is_blocked(target):
            raise MoveRejectedError(f"{move} from {pos} enters a blocked cell {target}")
        return target

    def legal_moves(self, pos: Position) -> dict[Move, Position]:
        """Every `Move` (including `STAY`) legal from `pos` right now, mapped
        to its resulting position.

        Used by the interactive play mode (a human player's move-pad/
        click-to-move UI) to know which moves/cells to offer -- reuses
        `apply_move`'s own validation rather than duplicating the
        bounds/blocked logic a second time.
        """
        legal: dict[Move, Position] = {}
        for move in Move:
            try:
                legal[move] = self.apply_move(pos, move)
            except MoveRejectedError:
                continue
        return legal

    def reachable_area(self, source: Position, extra_blocked: Position | None = None) -> int:
        """Count of open cells reachable from `source` by a flood fill,
        optionally treating `extra_blocked` as one more blocked cell.

        Used to evaluate a *candidate* barrier placement's real effect on
        an opponent's escape space before actually placing it (Sec. 3.3.8's
        "spatial-engineering" framing) -- e.g. distinguishing a barrier
        that merely removes one open cell from a barrier that seals off an
        entire pocket. `source` itself counts as blocked if it equals
        `extra_blocked` (an already-fully-enclosed source has zero
        reachable area, not one).
        """
        if source == extra_blocked or self.is_blocked(source):
            return 0
        visited = {source}
        queue: deque[Position] = deque([source])
        while queue:
            current = queue.popleft()
            for neighbor in self.neighbors(current):
                if neighbor in visited or neighbor == extra_blocked or self.is_blocked(neighbor):
                    continue
                visited.add(neighbor)
                queue.append(neighbor)
        return len(visited)

    def place_barrier(self, cop_pos: Position, target: Position) -> None:
        """Place a permanent barrier at `target`; must be cop_pos itself or adjacent.

        Irreversible: once blocked, a cell has no "unblock" path in this API.
        Rejects a `target` that is already blocked -- a real bug found
        empirically while wiring this up live: a heuristic that doesn't
        skip already-blocked candidates would otherwise "spend" real
        budget on a cell that was already permanently blocked, silently
        wasting Sec. 3.3.7's resource-management budget on a no-op.
        """
        if target != cop_pos and target not in self.neighbors(cop_pos):
            raise MoveRejectedError(f"barrier target {target} is not adjacent to {cop_pos}")
        if self.is_blocked(target):
            raise MoveRejectedError(f"{target} is already blocked -- placing there again would waste budget")
        if self.remaining_barrier_budget <= 0:
            raise MoveRejectedError("barrier budget exhausted")
        self._blocked.add(target)
        self._barriers_placed += 1

    def apply_declared_barrier(self, target: Position) -> None:
        """Mark `target` blocked on a *receiving* peer's own local board copy.

        docs/tasks.md Sec. 3.3.6: barrier placements are declared publicly
        and in real time -- unlike a move, they are never sealed inside the
        commit-reveal envelope (see `services/network_match.py`). The
        opponent's own process never called `place_barrier` itself (it has
        no `cop_pos`/budget of its own to validate against), so this method
        simply trusts the declaration and marks the cell blocked, keeping
        both sides' board state in sync. A dishonest declaration is not
        re-validated here -- Sec. 3.3.9 already assigns that job to the
        end-of-match cross-audit (`services/commit_reveal.py::audit_log`),
        not to live per-turn re-verification.

        Idempotent: a redundant re-declaration of an already-blocked cell
        (e.g. the sender's own bug, or the same barrier echoed twice) marks
        nothing new and does not double-count against the tracked total --
        this side isn't the one whose budget it would even be.
        """
        if self.is_blocked(target):
            return
        self._blocked.add(target)
        self._barriers_placed += 1
