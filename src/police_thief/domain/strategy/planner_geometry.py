"""Distance helpers shared by the scoring terms."""

from __future__ import annotations

from collections import deque

from police_thief.domain.board import Board, Position


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
