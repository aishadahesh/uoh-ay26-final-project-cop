"""League scoring: Diversity Incentive, the one-counted-game rule, the tie
rule, and game-count declarations (Chapter 9, Sec. 9.2).

docs/tasks.md Sec. 9.2.1-9.2.9: the league score is not simply the sum of
every match played -- it rewards facing new opponents (the Diversity
Incentive) rather than farming one easy rival repeatedly, and only ONE game
per opponent ever counts toward scoring (warm-up games are unlimited but
never counted). Because only one counted game per opponent ever exists, "a
victory against an opponent not already beaten" (Sec. 9.2.1) and "a win on
your one counted game against this opponent" (Sec. 9.2.2) are the same
condition -- so the Diversity Incentive is simply awarded on a win, exactly
once per opponent, by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class LeagueRuleError(ValueError):
    """Raised when an action would violate a MUST-level league rule."""


@dataclass
class LeagueRecord:
    """One team's running tally across the league season."""

    min_games_to_pass: int
    max_games_per_team: int
    diversity_reward: int
    _counted_opponents: set[str] = field(default_factory=set)
    _total_score: int = 0

    @property
    def games_played(self) -> int:
        return len(self._counted_opponents)

    @property
    def has_passed_minimum(self) -> bool:
        return self.games_played >= self.min_games_to_pass

    @property
    def total_score(self) -> int:
        return self._total_score

    def can_count_another_game(self) -> bool:
        return self.games_played < self.max_games_per_team

    def is_new_opponent(self, opponent_id: str) -> bool:
        return opponent_id not in self._counted_opponents

    def record_counted_game(self, opponent_id: str, own_score: int, won: bool) -> int:
        """Record one COUNTED (not warm-up) game and return the score
        actually awarded, including the Diversity Incentive if won.

        Sec. 9.2.2: only one counted game per opponent, ever -- a second
        counted game against an already-counted opponent is a rule
        violation, not something to silently ignore (a rematch is only
        legitimate as an uncounted warm-up game).
        """
        if opponent_id in self._counted_opponents:
            raise LeagueRuleError(
                f"opponent {opponent_id!r} already has a counted game; "
                "only warm-up (uncounted) games are permitted now"
            )
        if not self.can_count_another_game():
            raise LeagueRuleError(
                f"already at the max_games_per_team cap ({self.max_games_per_team}); "
                "cannot count another game"
            )
        awarded = own_score + (self.diversity_reward if won else 0)
        self._counted_opponents.add(opponent_id)
        self._total_score += awarded
        return awarded


def verify_game_count_declaration(declared_games_played: int, actual: LeagueRecord) -> bool:
    """Sec. 9.2.4-9.2.5: a declaration is auditable, not a matter of trust --
    a mismatch discovered at any point disqualifies the declaring team."""
    return declared_games_played == actual.games_played


def apply_tie_rule(own_total: int, opponent_total: int, tie_score: int) -> tuple[int, int]:
    """Sec. 9.2.8-9.2.9 / Appendix F Table 17 row 5: when the cumulative
    score of all sub-games against one rival ends in an exact tie, each side
    receives the tie score as a credit ON TOP of its cumulative subtotal
    (e.g. 75-75 becomes 77-77) -- no rematch is needed or permitted."""
    if own_total == opponent_total:
        return own_total + tie_score, opponent_total + tie_score
    return own_total, opponent_total
