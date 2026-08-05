from types import SimpleNamespace

import pytest

from police_thief.domain.board import Move, Position
from police_thief.services.gemini_agent import GeminiAgentAdvisor, TacticalContext
from police_thief.shared.constants import AgentRole


class _FakeModels:
    def __init__(self, text: str = "EAST|Closing on the strongest scent signal.", error=None, usage=None):
        self.text = text
        self.error = error
        self.usage = usage
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text, usage_metadata=self.usage)


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
            "max_output_tokens": 128,
        "http_options": {
            # 8s per-turn budget floored up to the 10s minimum HTTP timeout
            # (MIN_GEMINI_HTTP_TIMEOUT_SECONDS) so a tight turn deadline
            # can't cut off a call the provider would otherwise complete.
            "timeout": 10000,
            "retry_options": {"attempts": 1},
        },
    }


def test_gemini_records_provider_token_usage():
    usage = SimpleNamespace(prompt_token_count=41, candidates_token_count=7)
    advisor = GeminiAgentAdvisor(
        client=SimpleNamespace(models=_FakeModels(usage=usage)), model="test-model"
    )
    advisor.choose_move(_context(), Move.STAY)
    assert advisor.usage_snapshot() == (41, 7)


def test_timeout_env_is_converted_to_milliseconds_in_request_config(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "12")
    models = _FakeModels()
    advisor = GeminiAgentAdvisor(client=SimpleNamespace(models=models), model="test-model")
    advisor.choose_move(_context(), Move.STAY)
    assert models.calls[0]["config"]["http_options"]["timeout"] == 12000


def test_timeout_below_the_http_floor_is_bounded_up_to_the_floor(monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "1.25")
    models = _FakeModels()
    advisor = GeminiAgentAdvisor(client=SimpleNamespace(models=models), model="test-model")
    advisor.choose_move(_context(), Move.STAY)
    assert models.calls[0]["config"]["http_options"]["timeout"] == 10000


def test_client_receives_the_bounded_http_timeout(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(models=_FakeModels())

    monkeypatch.setattr("google.genai.Client", fake_client)
    GeminiAgentAdvisor(api_key="test-key")
    assert captured["http_options"] == {
        "timeout": 10000,
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
    assert "after 1 Gemini attempt(s)" in decision.rationale
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
    assert "after 3 Gemini attempt(s)" in decision.rationale


def test_provider_error_redacts_api_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")
    message = GeminiAgentAdvisor._safe_error(RuntimeError("bad super-secret-key"))
    assert "super-secret-key" not in message
    assert "<redacted>" in message


def test_prompt_contains_local_belief_but_not_an_opponent_true_position():
    prompt = GeminiAgentAdvisor._prompt(_context())
    assert "BELIEVED_OPPONENT=(0,6)" in prompt
    assert "ALLOWED_ACTIONS=SOUTH [S]; EAST [E]; STAY [STAY]" in prompt
    assert "true position" not in prompt.lower()


def test_parse_response_accepts_a_move_code_and_a_move_prefix():
    """Real-world Gemini output isn't always the exact move.name -- accept
    the short wire code too, and a "MOVE:"/"MOVE="-style prefix some models
    add despite the prompt's instructions."""
    parsed, rejection = GeminiAgentAdvisor._parse_response(
        "MOVE: E|Closing the gap", (Move.SOUTH, Move.EAST, Move.STAY),
    )
    assert rejection == ""
    assert parsed is not None
    assert parsed[0] is Move.EAST
