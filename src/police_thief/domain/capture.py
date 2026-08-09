"""Capture detection (Chapter 3, docs/tasks.md Sec. 3.3.5/3.3.9).

Two ways a thief is captured: the cop occupies the thief's cell (by moving
onto it, or by placing a barrier exactly there), or the thief has no legal
movement left at all (fully boxed in by barriers/board edges -- STAY
remaining technically "legal" does not change this: a thief that can never
again move is treated as captured).

CaptureClaim is a placeholder event type: Chapter 5/6 wraps this in a real
cryptographic commit-reveal signature so a claim becomes independently
auditable rather than a matter of trust between rivals.
"""

from __future__ import annotations

from dataclasses import dataclass

from police_thief.domain.board import Board, Position
from police_thief.shared.constants import AgentRole


def check_capture(cop_position: Position, thief_position: Position) -> bool:
    """True if the cop's position (move or barrier target) lands on the thief."""
    return cop_position == thief_position


def cop_capture_cells(board: Board, cop_position: Position) -> frozenset[Position]:
    """Cells the cop can capture on its next complete turn.

    A cop may first make one legal orthogonal move (or STAY), then—while it
    still has budget—place a barrier on its resulting cell or an adjacent
    cell.  The second footprint matters to escape planning because a barrier
    landing on the thief is an immediate capture.
    """
    after_move = set(board.legal_moves(cop_position).values())
    if board.remaining_barrier_budget <= 0:
        return frozenset(after_move)
    capture_cells = set(after_move)
    for position in after_move:
        capture_cells.update(board.legal_moves(position).values())
    return frozenset(capture_cells)


def is_boxed_in(board: Board, thief_position: Position) -> bool:
    """True if every orthogonal neighbor of the thief is blocked or off-board."""
    neighbors = board.neighbors(thief_position)
    return all(board.is_blocked(n) for n in neighbors)


@dataclass(frozen=True)
class CaptureClaim:
    """Placeholder capture-declaration event.

    Chapter 5/6 replaces bare trust here with a signed commit-reveal
    envelope; this dataclass exists now to fix the shape of "what a claim
    contains" before that trust layer is built.
    """

    claimant: AgentRole
    position: Position
