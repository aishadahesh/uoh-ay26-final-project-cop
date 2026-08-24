"""Inspecting a peer's public repository for the declared commit.

Split out of pregame_validation.py so `pregame_peer_check` can call it
without importing back into the facade module.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from police_thief.services.pregame_game_json import validate_shared_game
from police_thief.services.pregame_schema import (
    _GITHUB_RE,
    _PROTECTED,
    ValidationIssue,
    _at,
    _issue,
)


def inspect_public_repository(repo_url: Any, commit_hash: str, expected_game: Any) -> tuple[list[ValidationIssue], list[dict[str, Any]]]:
    """Inspect only public rule artifacts; never fetch private strategy files."""
    issues: list[ValidationIssue] = []
    checks: list[dict[str, Any]] = []
    match = _GITHUB_RE.match(repo_url) if isinstance(repo_url, str) else None
    if not match:
        return [_issue("opponent", "repository", "url", "invalid_value", "public GitHub repository URL", repo_url)], checks
    owner, repo = match.groups()
    base = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_hash}"

    def fetch(path: str, *, body: bool) -> bytes | None:
        request = urllib.request.Request(f"{base}/{path}", method="GET" if body else "HEAD", headers={"User-Agent": "police-thief-pregame-validator/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                checks.append({"file": path, "status": "verified", "http_status": response.status})
                return response.read() if body else b""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            checks.append({"file": path, "status": "failed", "error": str(exc)})
            return None

    raw = fetch("config/game.json", body=True)
    if raw is None:
        issues.append(_issue("opponent", "repository/config/game.json", "$", "missing_or_unreachable", "file at declared commit", "unavailable"))
    else:
        try:
            repository_game = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            issues.append(_issue("opponent", "repository/config/game.json", "$", "invalid_json", "valid JSON", str(exc)))
        else:
            issues.extend(validate_shared_game(repository_game, scope="opponent_repository"))
            # By-agreement values (for example response timeouts) may differ
            # between a repository default and the signed match instance.  The
            # immutable repository must still carry the exact protected rules.
            for field in sorted(_PROTECTED):
                expected = _at(expected_game, field) if isinstance(expected_game, dict) else None
                received = _at(repository_game, field)
                if expected != received:
                    issues.append(_issue("opponent", "repository/config/game.json", field, "protected_repository_mismatch", expected, received))
    # Existence only: the TOML body may contain legitimate private settings.
    if fetch("config/game.toml", body=False) is None:
        issues.append(_issue("opponent", "repository/config/game.toml", "$", "missing_or_unreachable", "file at declared commit", "unavailable"))
    required_groups = (("README.md",), ("docs/PRD.md", "PRD.md"), ("docs/PLAN.md", "PLAN.md"), ("docs/TODO.md", "TODO.md"))
    for candidates in required_groups:
        if not any(fetch(path, body=False) is not None for path in candidates):
            issues.append(_issue("opponent", "repository", "required_file", "missing_required_file", " or ".join(candidates), "missing"))
    return issues, checks
