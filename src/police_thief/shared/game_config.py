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

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from police_thief.domain.board import BoardConfig, Position
from police_thief.domain.scent import ScentConfig
from police_thief.domain.scoring import ScoringTable
from police_thief.services.commit_reveal import canonical_json
from police_thief.shared.config import ConfigError

MIN_MAX_BARRIERS = 14
MIN_GRID_SIZE = 7
MIN_REQUESTS_PER_MINUTE = 30
MIN_CONCURRENT_REQUESTS = 2
MIN_RETRY_BACKOFF_SEC = 5
MIN_MAX_RETRIES = 3
MIN_QUEUE_DEPTH = 100
DEFAULT_NUM_GAMES = 1
FIXED_DIVERSITY_REWARD = 10
FIXED_MIN_GAMES_TO_PASS = 2
FIXED_MAX_GAMES_PER_TEAM = 10
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.00"})
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


def config_fingerprint(path: Path) -> str:
    """SHA-256 over the canonically-serialized shared config (Sec. 4.2.6/5.5).

    "Cryptographically locking" the physics/scent parameters before match
    start means: this fingerprint goes into the signed Step-0 declaration
    (services/step0.py), so any later divergence -- including a change to
    the otherwise-fixed scent parameters -- is detectable by comparing
    fingerprints, without needing a bespoke locking mechanism per section.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(canonical_json(data)).hexdigest()


def load_match_parameters(path: Path) -> MatchParameters:
    """Parse config/game.json into board, scoring, and start-position data."""
    if not path.is_file():
        raise GameConfigError(f"missing shared match config: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        schema_version = str(data["schema_version"])
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise GameConfigError(
                f"unsupported schema_version {schema_version!r} at {path}; "
                f"supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )
        board_section = data["board_and_agents"]
        movement_section = data["movement_and_barriers"]
        scoring_section = data["scoring"]
        pheromones_section = data["pheromones"]
        world_section = data["world"]
        network_league_section = data["network_and_league"]
        rate_limiter_section = data["rate_limiter_gatekeeper"]

        grid_size = int(board_section["grid_size"])
        max_barriers = int(movement_section["max_barriers"])
        if grid_size < MIN_GRID_SIZE:
            raise GameConfigError(
                f"grid_size {grid_size} is below the mandatory floor {MIN_GRID_SIZE}"
            )
        if max_barriers < MIN_MAX_BARRIERS:
            raise GameConfigError(
                f"max_barriers {max_barriers} is below the mandatory floor {MIN_MAX_BARRIERS}"
            )

        board = BoardConfig(
            grid_size=grid_size,
            axis_origin_corner=str(board_section["axis_origin_corner"]),
            axis_start_index=int(board_section["axis_start_index"]),
            max_barriers=max_barriers,
        )
        scoring = ScoringTable(
            capture_cop=int(scoring_section["capture_cop"]),
            capture_thief=int(scoring_section["capture_thief"]),
            survival_cop=int(scoring_section["survival_cop"]),
            survival_thief=int(scoring_section["survival_thief"]),
            tie_score=int(scoring_section["tie_score"]),
            technical_loss=int(scoring_section["technical_loss"]),
        )
        scent = ScentConfig(
            center_intensity=float(pheromones_section["pheromone_center_intensity"]),
            min_center_intensity=float(pheromones_section["pheromone_min_center_intensity"]),
            decay_rate=float(pheromones_section["pheromone_decay"]),
            field_size=int(pheromones_section["pheromone_grid_size"]),
        )
        _validate_fixed_scent_config(scent, path)

        world = WorldConfig(
            map_area=str(world_section["map_area"]),
            hint_max_words=int(world_section["hint_max_words"]),
        )
        network_league = NetworkLeagueConfig(
            response_timeout_sec=float(network_league_section["response_timeout_sec"]),
            watchdog_timeout_sec=float(network_league_section["watchdog_timeout_sec"]),
            num_games=int(network_league_section["num_games"]),
            diversity_reward=int(network_league_section["diversity_reward"]),
            min_games_to_pass=int(network_league_section["min_games_to_pass"]),
            max_games_per_team=int(network_league_section["max_games_per_team"]),
            token_budget_per_series=int(network_league_section["token_budget_per_series"]),
        )
        _validate_fixed_network_league_config(network_league, path)
        rate_limiter = RateLimiterConfig(
            requests_per_minute=int(rate_limiter_section["requests_per_minute"]),
            concurrent_requests=int(rate_limiter_section["concurrent_requests"]),
            retry_backoff_sec=float(rate_limiter_section["retry_backoff_sec"]),
            max_retries=int(rate_limiter_section["max_retries"]),
            queue_depth=int(rate_limiter_section["queue_depth"]),
        )
        _validate_rate_limiter_floors(rate_limiter, path)

        thief_start = Position(*board_section["thief_start"])
        cop_start = Position(*board_section["cop_start"])
        for label, pos in (("thief_start", thief_start), ("cop_start", cop_start)):
            if not (0 <= pos.row < grid_size and 0 <= pos.col < grid_size):
                raise GameConfigError(f"{label} {pos} is outside the {grid_size}x{grid_size} board")
        if thief_start == cop_start:
            raise GameConfigError(
                f"thief_start and cop_start are both {cop_start} -- a match cannot start with "
                "both agents on the same cell (docs/tasks.md TODO T0775)"
            )

        return MatchParameters(
            board=board,
            scoring=scoring,
            scent=scent,
            thief_start=thief_start,
            cop_start=cop_start,
            max_moves=int(movement_section["max_moves"]),
            survival_threshold=int(movement_section["survival_threshold"]),
            world=world,
            network_league=network_league,
            rate_limiter=rate_limiter,
        )
    except GameConfigError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise GameConfigError(f"malformed shared config at {path}: {exc}") from exc
