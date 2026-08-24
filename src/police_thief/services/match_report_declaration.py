"""The pre-game declaration and the agreed-config snapshot.

Split out of match_reports.py, which re-exports these names."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from police_thief.services.match_report_files import (
    _read_json,
    _write_json,
    config_filename,
    declaration_filename,
)
from police_thief.services.step0 import SignedStep0


@dataclass(frozen=True)
class TeamInfo:
    """Sec. 9.3.17/9.4.1-9.4.3: identity + the mandatory sibling-repo cross-link."""

    team_name: str
    members: tuple[str, ...]
    cop_repo_url: str
    thief_repo_url: str


@dataclass(frozen=True)
class MatchDeclaration:
    """Sec. 9.3.19's `[declaration file]`: everything fixed before the first move."""

    game_id: str
    sub_game_number: int
    team: TeamInfo
    step0: SignedStep0
    token_budget_per_series: int


def build_declaration(
    game_id: str,
    sub_game_number: int,
    team: TeamInfo,
    step0: SignedStep0,
    token_budget_per_series: int,
) -> MatchDeclaration:
    return MatchDeclaration(
        game_id=game_id,
        sub_game_number=sub_game_number,
        team=team,
        step0=step0,
        token_budget_per_series=token_budget_per_series,
    )


def save_declaration(declaration: MatchDeclaration, directory: Path) -> Path:
    path = directory / declaration_filename(declaration.game_id)
    _write_json(asdict(declaration), path)
    return path


def load_declaration_dict(directory: Path, game_id: str) -> dict:
    return _read_json(directory / declaration_filename(game_id))


@dataclass(frozen=True)
class MatchConfigSnapshot:
    """Sec. 9.3.19's `[config file]`: the agreed, locked match parameters."""

    game_id: str
    sub_game_number: int
    config: dict
    config_sha256: str


def build_config_snapshot(
    game_id: str, sub_game_number: int, config: dict, config_sha256: str
) -> MatchConfigSnapshot:
    return MatchConfigSnapshot(
        game_id=game_id,
        sub_game_number=sub_game_number,
        config=config,
        config_sha256=config_sha256,
    )


def save_config_snapshot(snapshot: MatchConfigSnapshot, directory: Path) -> Path:
    path = directory / config_filename(snapshot.game_id, snapshot.sub_game_number)
    _write_json(asdict(snapshot), path)
    return path


def load_config_snapshot_dict(directory: Path, game_id: str, sub_game_number: int) -> dict:
    return _read_json(directory / config_filename(game_id, sub_game_number))
