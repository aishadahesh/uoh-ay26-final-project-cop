"""Validation of the values the rulebook fixes or floors.

Split out of game_config.py; called by load_match_parameters."""

from __future__ import annotations

import math
from pathlib import Path

from police_thief.domain.scent import ScentConfig
from police_thief.shared.game_config_schema import (
    _FIXED_SCENT_CONFIG,
    FIXED_DIVERSITY_REWARD,
    FIXED_MAX_GAMES_PER_TEAM,
    FIXED_MIN_GAMES_TO_PASS,
    MIN_CONCURRENT_REQUESTS,
    MIN_MAX_RETRIES,
    MIN_QUEUE_DEPTH,
    MIN_REQUESTS_PER_MINUTE,
    MIN_RETRY_BACKOFF_SEC,
    GameConfigError,
    NetworkLeagueConfig,
    RateLimiterConfig,
)


def _validate_fixed_scent_config(scent: ScentConfig, path: Path) -> None:
    """Sec. 4.2: scent parameters are FIXED, not team-negotiable minimums."""
    fixed = _FIXED_SCENT_CONFIG
    if not math.isclose(scent.center_intensity, fixed.center_intensity):
        raise GameConfigError(
            f"pheromone_center_intensity must be exactly {fixed.center_intensity} at {path}"
        )
    if not math.isclose(scent.min_center_intensity, fixed.min_center_intensity):
        raise GameConfigError(
            "pheromone_min_center_intensity must be exactly "
            f"{fixed.min_center_intensity} at {path}"
        )
    if not math.isclose(scent.decay_rate, fixed.decay_rate):
        raise GameConfigError(f"pheromone_decay must be exactly {fixed.decay_rate} at {path}")
    if scent.field_size != fixed.field_size:
        raise GameConfigError(f"pheromone_grid_size must be exactly {fixed.field_size} at {path}")


def _validate_fixed_network_league_config(network_league: NetworkLeagueConfig, path: Path) -> None:
    """Validate the negotiated series size and the fixed league constants."""
    if not 1 <= network_league.num_games <= network_league.max_games_per_team:
        raise GameConfigError(
            "num_games must be between 1 and max_games_per_team "
            f"({network_league.max_games_per_team}) at {path}"
        )
    if network_league.diversity_reward != FIXED_DIVERSITY_REWARD:
        raise GameConfigError(
            f"diversity_reward must be exactly {FIXED_DIVERSITY_REWARD} at {path}"
        )
    if network_league.min_games_to_pass != FIXED_MIN_GAMES_TO_PASS:
        raise GameConfigError(
            f"min_games_to_pass must be exactly {FIXED_MIN_GAMES_TO_PASS} at {path}"
        )
    if network_league.max_games_per_team != FIXED_MAX_GAMES_PER_TEAM:
        raise GameConfigError(
            f"max_games_per_team must be exactly {FIXED_MAX_GAMES_PER_TEAM} at {path}"
        )


def _validate_rate_limiter_floors(rate_limiter: RateLimiterConfig, path: Path) -> None:
    """App. F, Table 19: every field here is a MINIMUM -- teams may raise, never lower."""
    if rate_limiter.requests_per_minute < MIN_REQUESTS_PER_MINUTE:
        raise GameConfigError(
            f"requests_per_minute below the mandatory floor {MIN_REQUESTS_PER_MINUTE} at {path}"
        )
    if rate_limiter.concurrent_requests < MIN_CONCURRENT_REQUESTS:
        raise GameConfigError(
            f"concurrent_requests below the mandatory floor {MIN_CONCURRENT_REQUESTS} at {path}"
        )
    if rate_limiter.retry_backoff_sec < MIN_RETRY_BACKOFF_SEC:
        raise GameConfigError(
            f"retry_backoff_sec below the mandatory floor {MIN_RETRY_BACKOFF_SEC} at {path}"
        )
    if rate_limiter.max_retries < MIN_MAX_RETRIES:
        raise GameConfigError(f"max_retries below the mandatory floor {MIN_MAX_RETRIES} at {path}")
    if rate_limiter.queue_depth < MIN_QUEUE_DEPTH:
        raise GameConfigError(f"queue_depth below the mandatory floor {MIN_QUEUE_DEPTH} at {path}")
