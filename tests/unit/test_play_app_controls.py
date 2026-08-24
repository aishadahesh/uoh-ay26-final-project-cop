"""Move buttons and turn gating: which controls are live on a human turn, an
agent turn, and after the match ends.

Split by theme out of the original `test_play_app.py`."""

import tkinter as tk

from police_thief.domain.board import Move, Position
from police_thief.domain.interactive_match import GameMode
from police_thief.gui.play_app import PlayApp
from police_thief.shared.constants import AgentRole
from tests.unit.play_app_helpers import (
    _match,
    _no_schedule,
)


def test_starting_on_a_human_turn_enables_only_the_legal_move_buttons(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_COP_VS_AGENT, cop=Position(0, 0))  # cop moves first, human here
    app = PlayApp(root, match)
    app.start()
    assert app.move_buttons[Move.SOUTH].cget("state") == "normal"
    assert app.move_buttons[Move.EAST].cget("state") == "normal"
    assert app.move_buttons[Move.STAY].cget("state") == "normal"
    assert app.move_buttons[Move.NORTH].cget("state") == "disabled"
    assert app.move_buttons[Move.WEST].cget("state") == "disabled"


def test_starting_on_an_agent_turn_disables_every_control_and_schedules_the_agent(root, monkeypatch):
    scheduled = []
    monkeypatch.setattr(tk.Misc, "after", lambda self, ms, func: scheduled.append(func))
    match = _match(GameMode.AGENT_VS_HUMAN_THIEF)  # cop moves first, and cop is the agent here
    app = PlayApp(root, match)
    app.start()
    assert all(b.cget("state") == "disabled" for b in app.move_buttons.values())
    assert app.barrier_button.cget("state") == "disabled"
    assert len(scheduled) == 1


def test_clicking_a_move_button_applies_the_move_and_advances(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_COP_VS_AGENT, cop=Position(0, 0))
    app = PlayApp(root, match)
    app.start()
    app.move_buttons[Move.EAST].invoke()
    assert match.positions[AgentRole.COP] == Position(0, 1)
    assert match.current_role is AgentRole.THIEF


def test_clicking_an_illegal_move_button_is_a_no_op(root, monkeypatch):
    _no_schedule(monkeypatch)
    match = _match(GameMode.HUMAN_COP_VS_AGENT, cop=Position(0, 0))
    app = PlayApp(root, match)
    app.start()
    app._on_human_move(Move.NORTH)  # off the board -- disabled, but call the handler directly to prove it's a no-op
    assert match.positions[AgentRole.COP] == Position(0, 0)
    assert match.turns_played == 0


def test_agent_turn_callback_applies_the_agents_move_and_advances(root, monkeypatch):
    scheduled = []
    monkeypatch.setattr(tk.Misc, "after", lambda self, ms, func: scheduled.append(func))
    match = _match(GameMode.AGENT_VS_HUMAN_THIEF)
    app = PlayApp(root, match)
    app.start()
    assert match.current_role is AgentRole.COP
    scheduled.pop()()  # fire the scheduled agent turn
    assert match.current_role is AgentRole.THIEF
    assert match.turns_played == 1


def test_a_stale_scheduled_agent_turn_after_the_match_already_ended_is_a_no_op(root, monkeypatch):
    """`after()` isn't cancelled when the match ends some other way -- a
    stale scheduled agent turn firing afterward must not crash or apply a
    move to a finished match."""
    scheduled = []
    monkeypatch.setattr(tk.Misc, "after", lambda self, ms, func: scheduled.append(func))
    match = _match(GameMode.AGENT_VS_HUMAN_THIEF, cop=Position(3, 2), thief=Position(3, 3))
    app = PlayApp(root, match)
    app.start()
    stale_agent_turn = scheduled.pop()
    match.apply_move(Move.EAST)  # the agent (cop) captures immediately via a direct call
    assert match.is_finished is True
    stale_agent_turn()  # must not raise or double-apply
    assert match.turns_played == 1
