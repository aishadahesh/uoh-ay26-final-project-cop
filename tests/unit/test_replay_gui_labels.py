"""The replay viewer's static readouts: step counter, audit verdict, per-step
detail, summary counts, and board markers.

Split out of the original `test_gui.py`."""

import dataclasses

from police_thief.domain.replay import ReplaySession
from police_thief.gui.replay_gui import ReplayGUI

# tk_root/root fixtures live in tests/unit/conftest.py, shared across every
# GUI test file -- Tkinter does not reliably support creating more than one
# session-scoped Tk() root within a single process.
from tests.unit.gui_helpers import (
    _make_entries,
    _make_positional_entries,
)


def test_replay_gui_shows_step_one_of_n_on_construction(root):
    session = ReplaySession(_make_entries(5))
    gui = ReplayGUI(root, session)
    assert gui.step_label.cget("text") == "Step 1 / 5"


def test_replay_gui_shows_verified_ok_in_green_on_a_clean_log(root):
    session = ReplaySession(_make_entries(3))
    gui = ReplayGUI(root, session)
    assert gui.status_label.cget("text") == "Verified OK"
    assert gui.status_label.cget("fg") == "#2e7d32"


def test_replay_gui_shows_tampered_in_red_at_the_tampered_step(root):
    entries = _make_entries(4)
    tampered = list(entries)
    tampered[1] = dataclasses.replace(tampered[1], move="TAMPERED")
    session = ReplaySession(tampered)
    gui = ReplayGUI(root, session)
    gui.next_button.invoke()  # advance to step index 1 (the tampered one)
    assert gui.status_label.cget("text") == "TAMPERED"
    assert gui.status_label.cget("fg") == "#c62828"


def test_replay_gui_next_button_advances_the_step_label(root):
    session = ReplaySession(_make_entries(4))
    gui = ReplayGUI(root, session)
    gui.next_button.invoke()
    assert gui.step_label.cget("text") == "Step 2 / 4"


def test_replay_gui_previous_button_retreats_the_step_label(root):
    session = ReplaySession(_make_entries(4))
    gui = ReplayGUI(root, session)
    gui.next_button.invoke()
    gui.next_button.invoke()
    gui.prev_button.invoke()
    assert gui.step_label.cget("text") == "Step 2 / 4"


def test_replay_gui_detail_label_reflects_the_current_steps_move(root):
    session = ReplaySession(_make_entries(2))
    gui = ReplayGUI(root, session)
    assert "move='N'" in gui.detail_label.cget("text")


def test_replay_gui_summary_label_shows_verified_and_tampered_counts(root):
    entries = _make_entries(5)
    tampered = list(entries)
    tampered[2] = dataclasses.replace(tampered[2], move="X")
    session = ReplaySession(tampered)
    gui = ReplayGUI(root, session)
    assert gui.summary_label.cget("text") == "2 verified / 3 tampered (of 5 total steps)"


def test_replay_gui_draws_no_board_markers_for_an_unrecognized_state_shape(root):
    """T0431's own resolution: LogEntry.state stays intentionally generic --
    a shape this GUI doesn't recognize (e.g. the synthetic {"turn": i} used
    elsewhere in this file) means "nothing to draw," never a crash."""
    session = ReplaySession(_make_entries(3))
    gui = ReplayGUI(root, session)
    assert gui.canvas._marker_ids == []


def test_replay_gui_draws_an_agent_marker_for_a_recognized_row_col_state(root):
    session = ReplaySession(_make_positional_entries([(0, 0), (0, 1), (1, 1)]))
    gui = ReplayGUI(root, session)
    assert len(gui.canvas._marker_ids) == 2  # just the agent marker (oval + text) at step 1


def test_replay_gui_accumulates_a_trail_as_steps_advance(root):
    session = ReplaySession(_make_positional_entries([(0, 0), (0, 1), (1, 1)]))
    gui = ReplayGUI(root, session)
    gui.next_button.invoke()
    gui.next_button.invoke()
    # 2 trail dots (steps 1-2) + 1 agent marker (oval + text) at step 3
    assert len(gui.canvas._marker_ids) == 4
