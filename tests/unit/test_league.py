"""Unit tests for league scoring: Diversity Incentive, tie rule, and
game-count caps (Chapter 9, Sec. 9.2)."""

import pytest

from police_thief.domain.league import (
    LeagueRecord,
    LeagueRuleError,
    apply_tie_rule,
    verify_game_count_declaration,
)


def test_a_new_league_record_starts_with_zero_games_and_below_minimum():
    record = LeagueRecord(min_games_to_pass=2, max_games_per_team=10, diversity_reward=10)
    assert record.games_played == 0
    assert record.has_passed_minimum is False


def test_a_win_against_a_new_opponent_awards_the_full_diversity_reward():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=10, diversity_reward=10)
    awarded = record.record_counted_game("TeamB", own_score=20, won=True)
    assert awarded == 30  # 20 base + 10 diversity


def test_a_loss_against_a_new_opponent_awards_no_diversity_reward():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=10, diversity_reward=10)
    awarded = record.record_counted_game("TeamB", own_score=5, won=False)
    assert awarded == 5


def test_games_played_and_minimum_threshold_track_correctly():
    record = LeagueRecord(min_games_to_pass=2, max_games_per_team=10, diversity_reward=10)
    record.record_counted_game("TeamB", own_score=20, won=True)
    assert record.has_passed_minimum is False
    record.record_counted_game("TeamC", own_score=5, won=False)
    assert record.games_played == 2
    assert record.has_passed_minimum is True


def test_total_score_accumulates_across_multiple_counted_games():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=10, diversity_reward=10)
    record.record_counted_game("TeamB", own_score=20, won=True)
    record.record_counted_game("TeamC", own_score=5, won=False)
    assert record.total_score == 35


def test_a_second_counted_game_against_the_same_opponent_is_rejected():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=10, diversity_reward=10)
    record.record_counted_game("TeamB", own_score=20, won=True)
    with pytest.raises(LeagueRuleError):
        record.record_counted_game("TeamB", own_score=20, won=True)


def test_a_counted_game_beyond_the_max_games_per_team_cap_is_rejected():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=1, diversity_reward=10)
    record.record_counted_game("TeamB", own_score=20, won=True)
    with pytest.raises(LeagueRuleError):
        record.record_counted_game("TeamC", own_score=5, won=False)


def test_can_count_another_game_reflects_the_cap():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=1, diversity_reward=10)
    assert record.can_count_another_game() is True
    record.record_counted_game("TeamB", own_score=20, won=True)
    assert record.can_count_another_game() is False


def test_is_new_opponent_reflects_the_counted_set():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=10, diversity_reward=10)
    assert record.is_new_opponent("TeamB") is True
    record.record_counted_game("TeamB", own_score=20, won=True)
    assert record.is_new_opponent("TeamB") is False


def test_verify_game_count_declaration_true_when_honest():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=10, diversity_reward=10)
    record.record_counted_game("TeamB", own_score=20, won=True)
    assert verify_game_count_declaration(1, record) is True


def test_verify_game_count_declaration_false_on_a_false_declaration():
    record = LeagueRecord(min_games_to_pass=1, max_games_per_team=10, diversity_reward=10)
    record.record_counted_game("TeamB", own_score=20, won=True)
    assert verify_game_count_declaration(5, record) is False


def test_apply_tie_rule_credits_tie_score_on_top_of_each_tied_subtotal():
    assert apply_tie_rule(10, 10, tie_score=2) == (12, 12)


def test_apply_tie_rule_turns_a_75_75_series_into_77_77():
    # The exact all-captures six-game series from the reviewed G001 match:
    # 3 x capture_cop (20) + 3 x capture_thief (5) = 75 for each side.
    assert apply_tie_rule(75, 75, tie_score=2) == (77, 77)


def test_apply_tie_rule_leaves_scores_unchanged_when_not_tied():
    assert apply_tie_rule(20, 5, tie_score=2) == (20, 5)
