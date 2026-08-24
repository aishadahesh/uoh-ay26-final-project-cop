"""The replay viewer's playback controls: play/pause toggling, auto-advance,
stale scheduled ticks, and jump-to-step.

Split out of the original `test_gui.py`."""

import tkinter as tk

from police_thief.domain.replay import ReplaySession
from police_thief.gui.replay_gui import ReplayGUI

# tk_root/root fixtures live in tests/unit/conftest.py, shared across every
# GUI test file -- Tkinter does not reliably support creating more than one
# session-scoped Tk() root within a single process.
from tests.unit.gui_helpers import (
    _make_entries,
)


def test_replay_gui_play_button_starts_paused(root):
    session = ReplaySession(_make_entries(3))
    gui = ReplayGUI(root, session)
    assert gui.play_button.cget("text") == "Play"
    assert gui._playing is False


def test_replay_gui_play_button_toggles_to_pause_and_back(root):
    session = ReplaySession(_make_entries(3))
    gui = ReplayGUI(root, session)
    gui.play_button.invoke()
    assert gui.play_button.cget("text") == "Pause"
    assert gui._playing is True
    gui.play_button.invoke()
    assert gui.play_button.cget("text") == "Play"
    assert gui._playing is False


def test_replay_gui_auto_play_advances_through_every_step_then_stops(root, monkeypatch):
    session = ReplaySession(_make_entries(4))
    gui = ReplayGUI(root, session)
    scheduled: list = []
    monkeypatch.setattr(tk.Misc, "after", lambda self, ms, func: scheduled.append(func))

    gui.play_button.invoke()
    assert gui.step_label.cget("text") == "Step 2 / 4"
    while scheduled:
        scheduled.pop(0)()
    assert gui.step_label.cget("text") == "Step 4 / 4"
    assert gui.play_button.cget("text") == "Play"  # auto-stopped at the end
    assert gui._playing is False


def test_replay_gui_a_stale_scheduled_tick_after_pause_does_nothing(root, monkeypatch):
    """`after()` isn't cancelled on pause -- a tick already scheduled before
    the user paused can still fire. It must be a no-op, not silently
    resume/advance the replay."""
    session = ReplaySession(_make_entries(4))
    gui = ReplayGUI(root, session)
    scheduled: list = []
    monkeypatch.setattr(tk.Misc, "after", lambda self, ms, func: scheduled.append(func))

    gui.play_button.invoke()  # schedules exactly one stale tick
    stale_tick = scheduled.pop()
    gui.play_button.invoke()  # pause before that tick fires
    assert gui._playing is False

    stale_tick()  # the stale, already-scheduled callback fires late
    assert gui.step_label.cget("text") == "Step 2 / 4"  # unchanged by the stale tick
    assert gui._playing is False


def test_replay_gui_previous_button_stops_auto_play(root, monkeypatch):
    session = ReplaySession(_make_entries(4))
    gui = ReplayGUI(root, session)
    monkeypatch.setattr(tk.Misc, "after", lambda self, ms, func: None)
    gui.play_button.invoke()
    assert gui._playing is True
    gui.prev_button.invoke()
    assert gui._playing is False
    assert gui.play_button.cget("text") == "Play"


def test_replay_gui_jump_to_step_moves_directly_to_the_requested_step(root):
    session = ReplaySession(_make_entries(10))
    gui = ReplayGUI(root, session)
    gui.jump_entry.insert(0, "7")
    gui.jump_button.invoke()
    assert gui.step_label.cget("text") == "Step 7 / 10"


def test_replay_gui_jump_to_step_clamps_an_out_of_range_target(root):
    session = ReplaySession(_make_entries(5))
    gui = ReplayGUI(root, session)
    gui.jump_entry.insert(0, "999")
    gui.jump_button.invoke()
    assert gui.step_label.cget("text") == "Step 5 / 5"


def test_replay_gui_jump_to_step_ignores_non_numeric_input_without_crashing(root):
    session = ReplaySession(_make_entries(5))
    gui = ReplayGUI(root, session)
    gui.jump_entry.insert(0, "not-a-number")
    gui.jump_button.invoke()  # must not raise
    assert gui.step_label.cget("text") == "Step 1 / 5"
