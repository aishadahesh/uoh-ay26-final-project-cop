"""Reading config/game.json into MatchParameters, and fingerprinting it.

Split out of game_config.py, which now re-exports this module."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from police_thief.domain.board import BoardConfig, Position
from police_thief.domain.scent import ScentConfig
from police_thief.domain.scoring import ScoringTable
from police_thief.services.commit_reveal import canonical_json
from police_thief.shared.game_config_schema import (
    MIN_GRID_SIZE,
    MIN_MAX_BARRIERS,
    SUPPORTED_SCHEMA_VERSIONS,
    GameConfigError,
    MatchParameters,
    NetworkLeagueConfig,
    RateLimiterConfig,
    WorldConfig,
)
from police_thief.shared.game_config_validate import (
    _validate_fixed_network_league_config,
    _validate_fixed_scent_config,
    _validate_rate_limiter_floors,
)


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
