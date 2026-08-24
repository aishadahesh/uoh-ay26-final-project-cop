"""Session lifecycle: end-of-match messaging, starting a new game, and
tearing the window down.

Split by theme out of the original `test_play_app.py`."""

from tkinter import messagebox

from police_thief.domain.board import Move, Position
from police_thief.domain.interactive_match import GameMode
from police_thief.gui.play_app import PlayApp
from tests.unit.play_app_helpers import (
    _match,
    _no_schedule,
)


def test_match_end_disables_controls_and_shows_a_result_message(root, monkeypatch):
    _no_schedule(monkeypatch)
    shown = []
    monkeypatch.setattr(messagebox, "showinfo", lambda title, message: shown.append(message))
    match = _match(GameMode.HUMAN_COP_VS_AGENT, cop=Position(3, 2), thief=Position(3, 3))
    app = PlayApp(root, match)
    app.start()
    app._on_human_move(Move.EAST)  # captures immediately
    assert match.is_finished is True
    assert shown == ["Capture!"]
    assert all(b.cget("state") == "disabled" for b in app.move_buttons.values())
    assert "Capture!" in app.status_label.cget("text")


def test_new_game_button_calls_the_session_callback(root, monkeypatch):
    _no_schedule(monkeypatch)
    calls = []
    app = PlayApp(root, _match(GameMode.HUMAN_VS_HUMAN), on_new_game=lambda: calls.append(True) or True)
    app.start()
    app.new_game_button.invoke()
    assert calls == [True]


def test_canceling_new_game_resumes_the_current_match(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_VS_HUMAN)
    app = PlayApp(root, match, on_new_game=lambda: False)
    app.start()
    app.new_game_button.invoke()
    assert app._paused is False
    assert app.shell.winfo_exists()


def test_close_destroys_the_session_shell(root, monkeypatch):
    _no_schedule(monkeypatch)
    app = PlayApp(root, _match(GameMode.HUMAN_VS_HUMAN))
    shell = app.shell
    app.start()
    app.close()
    assert app._closed is True
    assert not shell.winfo_exists()
