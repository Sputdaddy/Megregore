import pytest
from megregore.decay import compute_half_life, decay_activation, boost_activation


class TestComputeHalfLife:
    def test_importance_1_gives_24h(self):
        assert compute_half_life(1) == pytest.approx(24.0, rel=0.01)

    def test_importance_10_gives_about_478h(self):
        result = compute_half_life(10)
        assert 470 < result < 490

    def test_higher_importance_longer_halflife(self):
        for i in range(1, 10):
            assert compute_half_life(i) < compute_half_life(i + 1)


class TestDecayActivation:
    def test_no_time_elapsed(self):
        result = decay_activation(1.0, 5, "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00")
        assert result == 1.0

    def test_half_life_halves_activation(self):
        from datetime import datetime, timedelta, timezone
        half_life_hours = compute_half_life(5)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(hours=half_life_hours)
        result = decay_activation(1.0, 5, start.isoformat(), end.isoformat())
        assert result == pytest.approx(0.5, abs=0.02)

    def test_low_importance_decays_fast(self):
        result = decay_activation(1.0, 1, "2024-01-01T00:00:00+00:00", "2024-01-15T00:00:00+00:00")
        assert result < 0.1

    def test_high_importance_decays_slow(self):
        result = decay_activation(1.0, 10, "2024-01-01T00:00:00+00:00", "2024-01-15T00:00:00+00:00")
        assert result > 0.3

    def test_minimum_clamp(self):
        result = decay_activation(1.0, 1, "2024-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00")
        assert result == 0.01


class TestBoostActivation:
    def test_normal_boost(self):
        assert boost_activation(0.5) == 0.8

    def test_clamp_at_max(self):
        assert boost_activation(0.9) == 1.0

    def test_already_at_max(self):
        assert boost_activation(1.0) == 1.0

    def test_custom_boost_amount(self):
        assert boost_activation(0.5, 0.1) == 0.6

    def test_boost_from_minimum(self):
        assert boost_activation(0.01) == 0.31
