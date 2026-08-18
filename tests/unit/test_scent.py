"""Unit tests for pheromone emission and decay (Chapter 4)."""

import pytest

from police_thief.domain.board import Position
from police_thief.domain.scent import ScentConfig, ScentField


@pytest.fixture
def field() -> ScentField:
    return ScentField(grid_size=7, config=ScentConfig())


def test_default_config_matches_mandatory_parameters_table():
    config = ScentConfig()
    assert config.center_intensity == 0.9
    assert config.decay_rate == 0.10
    assert config.field_size == 5


def test_untouched_cell_has_zero_intensity(field):
    assert field.intensity_at(Position(3, 3)) == 0.0


def test_emit_sets_center_intensity_exactly(field):
    field.emit(Position(3, 3))
    assert field.intensity_at(Position(3, 3)) == pytest.approx(0.9)


def test_emit_falls_off_radially_and_hits_zero_past_the_field_radius(field):
    field.emit(Position(3, 3))
    assert field.intensity_at(Position(3, 4)) == pytest.approx(0.6)  # distance 1
    assert field.intensity_at(Position(3, 5)) == pytest.approx(0.3)  # distance 2
    assert field.intensity_at(Position(4, 4)) == pytest.approx(0.6)  # Chebyshev distance 1
    assert field.intensity_at(Position(5, 5)) == pytest.approx(0.3)  # Chebyshev distance 2
    assert field.intensity_at(Position(3, 6)) == 0.0  # distance 3, outside 5x5 field


def test_emit_never_touches_a_cell_outside_the_board(field):
    field.emit(Position(0, 0))  # corner: much of the 5x5 window is off-board
    assert field.intensity_at(Position(-1, 0)) == 0.0  # would be off-board if it existed


def test_decay_matches_the_rulebooks_own_worked_example_number():
    """docs/tasks.md Sec. 4.3.4: 0.9 emitted, then ~0.81 after one decay step
    with no re-emission -- this is the exact number the rulebook's own
    lie-detection illustration uses.
    """
    field = ScentField(grid_size=7, config=ScentConfig())
    p = Position(5, 5)
    field.emit(p)
    field.decay()
    assert field.intensity_at(p) == pytest.approx(0.81)


def test_decay_only_cell_follows_the_exact_geometric_curve_over_n_turns(field):
    """No re-emission at this cell after the initial one: tau(n) = 0.9 * (1-rho)^n."""
    p = Position(3, 3)
    field.emit(p)
    rho = field.config.decay_rate
    for n in range(1, 6):
        field.decay()
        assert field.intensity_at(p) == pytest.approx(0.9 * (1 - rho) ** n)


def test_reemission_while_present_keeps_intensity_at_or_above_pure_decay(field):
    """Sec. 4.2.3: an agent that stays keeps re-emitting every turn, so its
    own cell's intensity never drops as low as a cell that was only ever
    emitted at once and left to decay on its own.
    """
    p = Position(3, 3)
    q = Position(0, 0)  # emitted once, then abandoned
    field.emit(p)
    field.emit(q)
    for _ in range(3):
        field.decay()
        field.emit(p)  # agent "stays" at p every turn
    assert field.intensity_at(p) >= field.intensity_at(q)


def test_mandatory_update_equation_combines_decay_and_fresh_emission(field):
    """tau(t+1) = max(0, (1-rho)*tau(t) + delta_tau) -- both terms in one turn."""
    p = Position(3, 3)
    field.emit(p)  # tau(0) = 0.9
    field.decay()  # tau(1) = 0.9 * 0.9 = 0.81
    field.emit(p)  # tau(1) += 0.9 -> 1.71 (re-emission, NOT capped at center_intensity)
    assert field.intensity_at(p) == pytest.approx(0.81 + 0.9)


def test_repeated_decay_with_no_emission_approaches_zero_asymptotically(field):
    """Geometric decay ((1-rho)^n) never hits exact 0.0 in finite realistic
    time -- it approaches zero asymptotically. This is correct, mandated
    behavior (Sec. 4.2.4's formula), not a bug: "silence is no information,
    never negative information," decaying arbitrarily close to but not
    below zero.
    """
    field.emit(Position(3, 3))
    for _ in range(200):
        field.decay()
    assert 0.0 < field.intensity_at(Position(3, 3)) < 1e-6


def test_full_decay_rate_forgets_a_cell_entirely_in_one_step():
    """ScentField itself doesn't enforce the loader's "must be exactly 0.10"
    business rule (game_config.py does) -- at the class level, decay_rate=1.0
    (total forgetting) is valid input and should fully clear a cell.
    """
    field = ScentField(grid_size=7, config=ScentConfig(decay_rate=1.0))
    p = Position(3, 3)
    field.emit(p)
    field.decay()
    assert field.intensity_at(p) == 0.0


def test_decay_never_produces_a_negative_value(field):
    field.emit(Position(3, 3))
    field.decay()
    assert field.intensity_at(Position(3, 3)) >= 0.0


def test_sustained_presence_can_exceed_the_bare_center_intensity(field):
    """Documented interpretation choice (docs/tasks.md Sec. 0.4, academic
    freedom on contradiction): the rulebook's own table describes tau_ij(t)
    as "a continuous value in [0, 0.9]", but its MANDATORY formula
    tau(t+1) = max(0, (1-rho)*tau(t) + delta_tau) adds a fresh 0.9 every
    turn an agent is present, which mathematically exceeds 0.9 after just
    two consecutive turns in the same cell (0.9 -> 0.81 + 0.9 = 1.71).
    This implementation follows the mandatory formula literally rather than
    silently capping it to match the descriptive text, since the formula is
    explicitly labeled MANDATORY while the range is only descriptive prose.
    """
    p = Position(3, 3)
    field.emit(p)
    field.decay()
    field.emit(p)
    assert field.intensity_at(p) > field.config.center_intensity


def test_scent_is_symmetric_two_independent_fields_do_not_share_state():
    """Sec. 4.1.3/4.3.3: each side's scent is its own -- never shared memory."""
    cop_scent = ScentField(grid_size=7, config=ScentConfig())
    thief_scent = ScentField(grid_size=7, config=ScentConfig())
    cop_scent.emit(Position(1, 1))
    assert thief_scent.intensity_at(Position(1, 1)) == 0.0
