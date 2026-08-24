"""Loader for the shared, signed match config: config/game.json.

docs/tasks.md Sec. 3.1.2: all physical laws come from one pre-agreed file
both sides load identically -- board dimensions, starting positions, the
barrier set, and the scoring table -- as hard-coded values, never
renegotiated mid-match. Cryptographically locking this file so neither side
can silently diverge after Step-0 is Chapter 5/6's concern; this loader only
parses and validates structure/minimums for now.

Position arrays in the JSON are `[row, col]`, matching domain.board.Position's
field order -- an implementation choice, not a rulebook mandate (docs/tasks.md
Sec. 3.2.2 only requires both sides agree on origin corner and start index,
not on array ordering).
"""

from __future__ import annotations

from police_thief.shared.game_config_loader import config_fingerprint, load_match_parameters
from police_thief.shared.game_config_schema import (
    DEFAULT_NUM_GAMES,
    FIXED_DIVERSITY_REWARD,
    FIXED_MAX_GAMES_PER_TEAM,
    FIXED_MIN_GAMES_TO_PASS,
    FIXED_TIE_SCORE,
    MIN_CONCURRENT_REQUESTS,
    MIN_GRID_SIZE,
    MIN_MAX_BARRIERS,
    MIN_MAX_RETRIES,
    MIN_QUEUE_DEPTH,
    MIN_REQUESTS_PER_MINUTE,
    MIN_RETRY_BACKOFF_SEC,
    SUPPORTED_SCHEMA_VERSIONS,
    GameConfigError,
    MatchParameters,
    NetworkLeagueConfig,
    RateLimiterConfig,
    WorldConfig,
)

__all__ = [
    "DEFAULT_NUM_GAMES",
    "FIXED_DIVERSITY_REWARD",
    "FIXED_MAX_GAMES_PER_TEAM",
    "FIXED_MIN_GAMES_TO_PASS",
    "FIXED_TIE_SCORE",
    "MIN_CONCURRENT_REQUESTS",
    "MIN_GRID_SIZE",
    "MIN_MAX_BARRIERS",
    "MIN_MAX_RETRIES",
    "MIN_QUEUE_DEPTH",
    "MIN_REQUESTS_PER_MINUTE",
    "MIN_RETRY_BACKOFF_SEC",
    "SUPPORTED_SCHEMA_VERSIONS",
    "GameConfigError",
    "MatchParameters",
    "NetworkLeagueConfig",
    "RateLimiterConfig",
    "WorldConfig",
    "config_fingerprint",
    "load_match_parameters",
]
