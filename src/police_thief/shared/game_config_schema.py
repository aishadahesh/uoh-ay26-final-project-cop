"""Mandatory floors, fixed league values, and the parsed configuration
dataclasses.

Split out of game_config.py so the vocabulary the whole codebase imports is
separate from the validation rules and the loader that enforce it."""

from __future__ import annotations

from dataclasses import dataclass, field

from police_thief.domain.board import BoardConfig, Position
from police_thief.domain.scent import ScentConfig
from police_thief.domain.scoring import ScoringTable
from police_thief.shared.config import ConfigError

MIN_MAX_BARRIERS = 14

MIN_GRID_SIZE = 7

MIN_REQUESTS_PER_MINUTE = 30

MIN_CONCURRENT_REQUESTS = 2

MIN_RETRY_BACKOFF_SEC = 5

MIN_MAX_RETRIES = 3

MIN_QUEUE_DEPTH = 100

DEFAULT_NUM_GAMES = 6

FIXED_DIVERSITY_REWARD = 10

FIXED_MIN_GAMES_TO_PASS = 2

FIXED_MAX_GAMES_PER_TEAM = 10

FIXED_TIE_SCORE = 2  # Appendix F Table 17 row 5: fixed, credited to each side on a tied series

SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.00", "1.2"})

_FIXED_SCENT_CONFIG = ScentConfig()  # docs/tasks.md Sec. 4.2: fixed, not a minimum floor


class GameConfigError(ConfigError):
    """Raised when the shared match config is missing, malformed, or below floor."""


@dataclass(frozen=True)
class WorldConfig:
    """docs/tasks.md App. F, Table 14: the hint arena theme and word cap.

    Defaults are the mandatory baseline, so board-physics-only callers (the
    integration tests predating this section, `run_local_match`) can
    construct a `MatchParameters` without caring about hint theming.
    """

    map_area: str = ""
    hint_max_words: int = 15


@dataclass(frozen=True)
class NetworkLeagueConfig:
    """docs/tasks.md App. F, Table 18. Defaults are the mandatory/example baseline."""

    response_timeout_sec: float = 30.0
    watchdog_timeout_sec: float = 60.0
    num_games: int = DEFAULT_NUM_GAMES
    diversity_reward: int = FIXED_DIVERSITY_REWARD
    min_games_to_pass: int = FIXED_MIN_GAMES_TO_PASS
    max_games_per_team: int = FIXED_MAX_GAMES_PER_TEAM
    token_budget_per_series: int = 200_000


@dataclass(frozen=True)
class RateLimiterConfig:
    """docs/tasks.md App. F, Table 19 -- the Gatekeeper's tunable minimums.
    Defaults are exactly the mandatory floors.
    """

    requests_per_minute: int = MIN_REQUESTS_PER_MINUTE
    concurrent_requests: int = MIN_CONCURRENT_REQUESTS
    retry_backoff_sec: float = MIN_RETRY_BACKOFF_SEC
    max_retries: int = MIN_MAX_RETRIES
    queue_depth: int = MIN_QUEUE_DEPTH


@dataclass(frozen=True)
class MatchParameters:
    """Everything Chapters 3/4/8/9's logic needs for one match."""

    board: BoardConfig
    scoring: ScoringTable
    scent: ScentConfig
    thief_start: Position
    cop_start: Position
    max_moves: int
    survival_threshold: int
    world: WorldConfig = field(default_factory=WorldConfig)
    network_league: NetworkLeagueConfig = field(default_factory=NetworkLeagueConfig)
    rate_limiter: RateLimiterConfig = field(default_factory=RateLimiterConfig)
