"""The four mandatory match-lifecycle JSON reports (Chapter 9, Sec. 9.3.16-9.3.22).

docs/tasks.md Sec. 9.3.19-9.3.20: a match's full lifecycle is covered by four
separate, namespaced JSON files -- never one blob, so files never mix across
different matches or sub-games:

    declaration_<game_id>.json        -- pre-game fixed match data
    config_<game_id>_g<NN>.json       -- the agreed, cryptographically-locked config snapshot
    log_<game_id>_g<NN>.json          -- the full commit/reveal move log (Chapter 5/7's format, reused as-is)
    result_<game_id>.json             -- final score, sign-off, and all four repo cross-links

Each builder is a thin dataclass + canonical-JSON writer; no bespoke crypto
is invented here -- SHA-256 hashing reuses Chapter 5's canonical_json, and
the log file itself reuses Chapter 7's save_log/load_log exactly (Sec. 9.3.19
explicitly calls the log file "for cryptographic audit in a replay
simulator" -- the same file Chapter 7's Replay Viewer already consumes).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from police_thief.services.commit_reveal import LogEntry
from police_thief.services.match_report_declaration import (
    MatchConfigSnapshot,
    MatchDeclaration,
    TeamInfo,
    build_config_snapshot,
    build_declaration,
    load_config_snapshot_dict,
    load_declaration_dict,
    save_config_snapshot,
    save_declaration,
)
from police_thief.services.match_report_files import (
    MatchReportError,
    _read_json,
    _write_json,
    config_filename,
    declaration_filename,
    log_filename,
    result_filename,
    sha256_of_log,
)
from police_thief.services.step0 import TokenUsage

__all__ = [
    "MatchConfigSnapshot",
    "MatchDeclaration",
    "MatchReportError",
    "MatchResult",
    "RepoCrossLinks",
    "ResultTeamIdentity",
    "TeamInfo",
    "_read_json",
    "_write_json",
    "build_config_snapshot",
    "build_declaration",
    "build_match_result",
    "config_filename",
    "declaration_filename",
    "load_config_snapshot_dict",
    "load_declaration_dict",
    "load_match_result_dict",
    "log_filename",
    "result_filename",
    "results_agree",
    "save_config_snapshot",
    "save_declaration",
    "save_match_result",
    "save_series_result",
    "sha256_of_log",
]



@dataclass(frozen=True)
class RepoCrossLinks:
    """Sec. 9.4.3: the results JSON must include all four repo links, both teams."""

    team_a_cop_repo: str
    team_a_thief_repo: str
    team_b_cop_repo: str
    team_b_thief_repo: str


@dataclass(frozen=True)
class ResultTeamIdentity:
    """Team name and members recorded alongside the mandatory repo links."""

    team_name: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class MatchResult:
    """Sec. 9.3.19's `[results file]`: final outcome, for league score weighting."""

    game_id: str
    sub_game_number: int
    cop_score: int
    thief_score: int
    outcome: str
    mutual_sign_off: bool
    log_sha256: str
    total_tokens_used: int
    repo_links: RepoCrossLinks
    team_a: ResultTeamIdentity | None = None
    team_b: ResultTeamIdentity | None = None
    participants: dict | None = None
    token_usage_by_group: dict[str, int] | None = None
    audit: dict | None = None


def build_match_result(
    game_id: str,
    sub_game_number: int,
    cop_score: int,
    thief_score: int,
    outcome: str,
    mutual_sign_off: bool,
    log_entries: list[LogEntry],
    token_usage: TokenUsage,
    repo_links: RepoCrossLinks,
    team_a: ResultTeamIdentity | None = None,
    team_b: ResultTeamIdentity | None = None,
    participants: dict | None = None,
    token_usage_by_group: dict[str, int] | None = None,
    audit: dict | None = None,
) -> MatchResult:
    return MatchResult(
        game_id=game_id,
        sub_game_number=sub_game_number,
        cop_score=cop_score,
        thief_score=thief_score,
        outcome=outcome,
        mutual_sign_off=mutual_sign_off,
        log_sha256=sha256_of_log(log_entries),
        total_tokens_used=token_usage.total,
        repo_links=repo_links,
        team_a=team_a,
        team_b=team_b,
        participants=participants,
        token_usage_by_group=token_usage_by_group,
        audit=audit,
    )


def save_match_result(
    result: MatchResult, directory: Path, *, include_sub_game: bool = False,
) -> Path:
    sub_game = result.sub_game_number if include_sub_game else None
    path = directory / result_filename(result.game_id, sub_game)
    _write_json(asdict(result), path)
    return path


def save_series_result(result: dict, directory: Path, game_id: str) -> Path:
    """Write the aggregate result after every subgame has been verified."""
    path = directory / result_filename(game_id)
    _write_json(result, path)
    return path


def load_match_result_dict(directory: Path, game_id: str) -> dict:
    return _read_json(directory / result_filename(game_id))


def results_agree(own: MatchResult, opponent: MatchResult) -> bool:
    """Sec. 9.3.18: mutual sign-off is a precondition, not a formality.

    A single-sided report is worthless per the rulebook's own words -- so
    this must be checked *before* either side sends, not discovered after.
    """
    return (
        own.game_id == opponent.game_id
        and own.sub_game_number == opponent.sub_game_number
        and own.cop_score == opponent.cop_score
        and own.thief_score == opponent.thief_score
        and own.outcome == opponent.outcome
        and own.log_sha256 == opponent.log_sha256
    )
