from types import SimpleNamespace

import pytest

from police_thief.domain.board import Move, Position
from police_thief.services.gemini_agent import GeminiAgentAdvisor, TacticalContext
from police_thief.shared.constants import AgentRole


class _FakeModels:
    def __init__(self, text: str = "EAST|Closing on the strongest scent signal.", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


def _context() -> TacticalContext:
    return TacticalContext(
        role=AgentRole.COP,
        own_position=Position(0, 0),
        belief_peak=Position(0, 6),
        legal_moves=(Move.SOUTH, Move.EAST, Move.STAY),
        turn_number=1,
        max_turns=35,
        remaining_barriers=14,
    )


@pytest.fixture(autouse=True)
def _clear_gemini_tuning_environment(monkeypatch):
    monkeypatch.delenv("GEMINI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("GEMINI_ENABLE_MODEL_FALLBACKS", raising=False)


def test_gemini_selects_a_supplied_legal_move_and_returns_its_reason():
    models = _FakeModels()
    advisor = GeminiAgentAdvisor(client=SimpleNamespace(models=models), model="test-model")
    decision = advisor.choose_move(_context(), Move.STAY)
    assert decision.move is Move.EAST
    assert decision.rationale == "Closing on the strongest scent signal."
    assert decision.used_fallback is False
    assert models.calls[0]["model"] == "test-model"
    assert models.calls[0]["config"] == {
        "temperature": 0,
        "max_output_tokens": 24,
        "http_options": {
            "timeout": 8000,
            "retry_options": {"attempts": 1},
        },
    }


def test_timeout_env_is_converted_to_milliseconds_in_request_config(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "1.25")
    models = _FakeModels()
    advisor = GeminiAgentAdvisor(client=SimpleNamespace(models=models), model="test-model")
    advisor.choose_move(_context(), Move.STAY)
    assert models.calls[0]["config"]["http_options"]["timeout"] == 1250


def test_client_receives_the_bounded_http_timeout(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(models=_FakeModels())

    monkeypatch.setattr("google.genai.Client", fake_client)
    GeminiAgentAdvisor(api_key="test-key")
    assert captured["http_options"] == {
        "timeout": 8000,
        "retry_options": {"attempts": 1},
    }


def test_invalid_gemini_move_uses_the_validated_heuristic_fallback():
    models = _FakeModels("TELEPORT|Surprise!")
    advisor = GeminiAgentAdvisor(client=SimpleNamespace(models=models))
    decision = advisor.choose_move(_context(), Move.SOUTH)
    assert decision.move is Move.SOUTH
    assert decision.used_fallback is True


def test_provider_failure_uses_fallback_without_crashing_the_match():
    models = _FakeModels(error=TimeoutError("offline"))
    advisor = GeminiAgentAdvisor(client=SimpleNamespace(models=models))
    decision = advisor.choose_move(_context(), Move.STAY)
    assert decision.move is Move.STAY
    assert decision.used_fallback is True
    assert "TimeoutError" in decision.rationale
    assert "offline" in decision.rationale
    assert "after 1 models" in decision.rationale
    assert len(models.calls) == 1


def test_fallback_models_are_tried_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("GEMINI_ENABLE_MODEL_FALLBACKS", "true")
    models = _FakeModels(error=TimeoutError("offline"))
    advisor = GeminiAgentAdvisor(
        client=SimpleNamespace(models=models), model="configured-model",
    )
    decision = advisor.choose_move(_context(), Move.STAY)
    assert decision.used_fallback is True
    assert [call["model"] for call in models.calls] == [
        "configured-model",
        "gemini-flash-latest",
        "gemini-2.5-flash",
    ]
    assert "after 3 models" in decision.rationale


def test_provider_error_redacts_api_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")
    message = GeminiAgentAdvisor._safe_error(RuntimeError("bad super-secret-key"))
    assert "super-secret-key" not in message
    assert "<redacted>" in message


def test_prompt_contains_local_belief_but_not_an_opponent_true_position():
    prompt = GeminiAgentAdvisor._prompt(_context())
    assert "Belief-map peak: (0, 6)" in prompt
    assert "Legal moves: SOUTH, EAST, STAY" in prompt
    assert "true position" not in prompt.lower()
