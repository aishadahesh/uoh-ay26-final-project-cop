"""The public hint each role emits is a plausible lie, not its real intent.

Split by theme out of the original `test_capture_safety.py`."""


from police_thief.domain.board import Board, BoardConfig, Move, Position
from police_thief.domain.hints import TemplateHintProvider
from police_thief.shared.constants import AgentRole
from tests.unit.capture_safety_helpers import (
    _runner,
)


def test_thief_public_hint_is_a_plausible_lie(tmp_path, monkeypatch):
    runner = _runner(tmp_path)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    draws = iter((1, 0))
    monkeypatch.setattr(
        "police_thief.services.network_match.secrets.randbelow",
        lambda _limit: next(draws),
    )
    hint = runner._generate_public_hint(
        TemplateHintProvider(), board, Position(3, 3), Move.EAST, step=4,
    )

    assert hint.intent_truthful is False
    assert hint.text == "I moved west."


def test_cop_public_hint_is_also_a_plausible_lie(tmp_path, monkeypatch):
    runner = _runner(tmp_path, role=AgentRole.COP)
    board = Board(BoardConfig(grid_size=7, max_barriers=14))
    draws = iter((1, 0))
    monkeypatch.setattr(
        "police_thief.services.network_match.secrets.randbelow",
        lambda _limit: next(draws),
    )
    hint = runner._generate_public_hint(
        TemplateHintProvider(), board, Position(3, 3), Move.EAST, step=4,
    )

    assert hint.intent_truthful is False
    assert hint.text == "I moved west."
