"""Shared builders for the GUI test modules: a peaked belief map and the two
log-entry factories the replay viewer tests render from.

Extracted when `test_gui.py` was split by the widget under test."""


from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, BoardConfig, Position
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.services.commit_reveal import LogEntry, commit

# tk_root/root fixtures live in tests/unit/conftest.py, shared across every
# GUI test file -- Tkinter does not reliably support creating more than one
# session-scoped Tk() root within a single process.


def _belief_peaked_at(grid_size: int, peak: Position) -> tuple[Board, BeliefMap]:
    board = Board(BoardConfig(grid_size=grid_size, max_barriers=14))
    scent = ScentField(grid_size=grid_size, config=ScentConfig())
    scent.emit(peak)
    belief = BeliefMap(board)
    belief.update_from_scent(scent)
    return board, belief


def _make_entries(n: int) -> list[LogEntry]:
    entries = []
    for i in range(n):
        c = commit(state={"turn": i}, move="N", intent=True)
        entries.append(LogEntry(state={"turn": i}, move="N", intent=True, nonce=c.nonce, h_commit=c.h_commit))
    return entries


def _make_positional_entries(coords: list[tuple[int, int]]) -> list[LogEntry]:
    entries = []
    for row, col in coords:
        c = commit(state={"row": row, "col": col}, move="N", intent=True)
        entries.append(
            LogEntry(state={"row": row, "col": col}, move="N", intent=True, nonce=c.nonce, h_commit=c.h_commit)
        )
    return entries
