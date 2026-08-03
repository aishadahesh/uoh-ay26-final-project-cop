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

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from police_thief.services.commit_reveal import LogEntry, canonical_json
from police_thief.services.step0 import SignedStep0, TokenUsage


class MatchReportError(ValueError):
    """Raised when a report file is missing, malformed, or schema-invalid."""


def declaration_filename(game_id: str) -> str:
    return f"declaration_{game_id}.json"


def config_filename(game_id: str, sub_game_number: int) -> str:
    return f"config_{game_id}_g{sub_game_number:02d}.json"


def log_filename(game_id: str, sub_game_number: int) -> str:
    return f"log_{game_id}_g{sub_game_number:02d}.json"


def result_filename(game_id: str, sub_game_number: int | None = None) -> str:
    suffix = "" if sub_game_number is None else f"_g{sub_game_number:02d}"
    return f"result_{game_id}{suffix}.json"


def _write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise MatchReportError(f"missing report file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MatchReportError(f"malformed JSON report at {path}: {exc}") from exc


def sha256_of_log(entries: list[LogEntry]) -> str:
    """SHA-256 over the canonically-serialized log (Sec. 9.3.17's "SHA-256 of the match log")."""
    payload = canonical_json([asdict(entry) for entry in entries])
    return hashlib.sha256(payload).hexdigest()


# --- declaration_<game_id>.json --------------------------------------------


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


# --- config_<game_id>_g<NN>.json --------------------------------------------


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


# --- log_<game_id>_g<NN>.json ------------------------------------------------
# Deliberately not re-implemented here: Chapter 7's domain.replay.save_log/
# load_log already write/read exactly this file's content (a JSON array of
# LogEntry records). Callers should pass `log_filename(game_id, sub_game_number)`
# as the path's name when calling those functions, e.g.:
#     save_log(entries, directory / log_filename(game_id, sub_game_number))


# --- result_<game_id>.json ---------------------------------------------------


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
