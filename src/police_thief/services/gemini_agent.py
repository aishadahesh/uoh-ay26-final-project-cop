"""Validated Gemini tactical move selection with one corrective retry."""

from __future__ import annotations

from police_thief.services.gemini_prompting import _GeminiPromptMixin
from police_thief.services.gemini_types import (
    _FALLBACK_MODELS,
    DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_TIMEOUT_SECONDS,
    MAX_ACTION_ATTEMPTS,
    MIN_GEMINI_HTTP_TIMEOUT_SECONDS,
    GeminiConfigurationError,
    GeminiDecision,
    TacticalContext,
)
from police_thief.services.gemini_usage import (
    _float_env,
    _GeminiUsageMixin,
    _truthy_env,
)

__all__ = [
    "DEFAULT_GEMINI_MAX_OUTPUT_TOKENS",
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_GEMINI_TIMEOUT_SECONDS",
    "MAX_ACTION_ATTEMPTS",
    "MIN_GEMINI_HTTP_TIMEOUT_SECONDS",
    "GeminiAgentAdvisor",
    "GeminiConfigurationError",
    "GeminiDecision",
    "TacticalContext",
]

import os
from typing import Any

from police_thief.domain.board import Move


class GeminiAgentAdvisor(_GeminiPromptMixin, _GeminiUsageMixin):
    """Ask Gemini for a move, repair bad output, and execute only legal actions."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        allow_fallback_models: bool | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _float_env("GEMINI_TIMEOUT_SECONDS", DEFAULT_GEMINI_TIMEOUT_SECONDS)
        )
        self.http_timeout_seconds = max(self.timeout_seconds, MIN_GEMINI_HTTP_TIMEOUT_SECONDS)
        self.allow_fallback_models = (
            allow_fallback_models
            if allow_fallback_models is not None
            else _truthy_env("GEMINI_ENABLE_MODEL_FALLBACKS")
        )
        self._input_tokens = 0
        self._output_tokens = 0
        if client is not None:
            self._client = client
            return
        key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise GeminiConfigurationError(
                "Agent modes require GEMINI_API_KEY in .env or the process environment."
            )
        from google import genai

        self._client = genai.Client(
            api_key=key,
            http_options={
                "timeout": int(self.http_timeout_seconds * 1000),
                "retry_options": {"attempts": 1},
            },
        )

    def choose_move(self, context: TacticalContext, fallback: Move) -> GeminiDecision:
        legal = tuple(dict.fromkeys(context.legal_moves))
        if not legal:
            raise ValueError(
                "Gemini cannot choose an action because no legal actions were supplied"
            )
        safe_fallback = (
            fallback if fallback in legal else (Move.STAY if Move.STAY in legal else legal[0])
        )
        models = tuple(
            dict.fromkeys(
                (self.model, *_FALLBACK_MODELS) if self.allow_fallback_models else (self.model,)
            )
        )
        rejected: list[str] = []
        last_error: Exception | None = None
        total_attempts = 0
        for model in models:
            prompt = self._prompt(context)
            for attempt in range(1, MAX_ACTION_ATTEMPTS + 1):
                total_attempts += 1
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config={
                            "temperature": 0,
                            "max_output_tokens": DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
                            "http_options": {
                                "timeout": int(self.http_timeout_seconds * 1000),
                                "retry_options": {"attempts": 1},
                            },
                        },
                    )
                    self._record_usage(response)
                    text = response.text or ""
                    parsed, rejection = self._parse_response(text, legal)
                    if parsed is not None:
                        move, reason = parsed
                        return GeminiDecision(
                            move,
                            reason,
                            attempts=total_attempts,
                            rejected=tuple(rejected),
                        )
                    rejected.append(rejection)
                    if attempt < MAX_ACTION_ATTEMPTS:
                        prompt = self._repair_prompt(context, text, rejection)
                except Exception as exc:  # provider/model failure; another model may recover
                    last_error = exc
                    break
        if rejected:
            cause = rejected[-1]
        elif last_error is not None:
            cause = f"provider unavailable: {self._safe_error(last_error)}"
        else:
            cause = "Gemini returned no usable response"
        return GeminiDecision(
            safe_fallback,
            f"Fallback activated after {total_attempts} Gemini attempt(s): {cause}. Selected {safe_fallback.name} ({safe_fallback.value}).",
            used_fallback=True,
            attempts=total_attempts,
            rejected=tuple(rejected),
        )
















