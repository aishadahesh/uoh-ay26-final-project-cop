"""Environment tuning and token-usage accounting for the Gemini advisor.

Split out of gemini_agent.py. The mixin keeps `usage_snapshot`,
`_record_usage` and `_safe_error` on GeminiAgentAdvisor itself.
"""


from __future__ import annotations

import os
from typing import Any


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _usage_value(metadata: Any, *names: str) -> int:
    for name in names:
        value = metadata.get(name) if isinstance(metadata, dict) else getattr(metadata, name, None)
        if isinstance(value, int) and value >= 0:
            return value
    return 0


class _GeminiUsageMixin:
    """Token accounting and error shaping for the advisor."""

    def usage_snapshot(self) -> tuple[int, int]:
        """Cumulative successfully reported Gemini input/output tokens."""
        return self._input_tokens, self._output_tokens

    def _record_usage(self, response: Any) -> None:
        metadata = getattr(response, "usage_metadata", None)
        if metadata is None:
            return
        self._input_tokens += _usage_value(
            metadata, "prompt_token_count", "input_token_count"
        )
        self._output_tokens += _usage_value(
            metadata, "candidates_token_count", "output_token_count"
        )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = " ".join(str(exc).split())
        for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            secret = os.getenv(variable)
            if secret:
                message = message.replace(secret, "<redacted>")
        concise = message[:120].rstrip()
        return f"{type(exc).__name__} - {concise}" if concise else type(exc).__name__
