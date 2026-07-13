"""Tests for benchmarks.metrics (pure-stdlib statistics helpers)."""

import pytest

from benchmarks.metrics import mean_std, median, percentile, wilson_ci


class TestWilsonCI:
    def test_empty_sample(self):
        assert wilson_ci(0, 0) == (0.0, 0.0)

    def test_half_hits_is_centered_and_bounded(self):
        lo, hi = wilson_ci(20, 40)
        assert 0.0 < lo < 0.5 < hi < 1.0
        assert lo == pytest.approx(0.352, abs=0.005)
        assert hi == pytest.approx(0.648, abs=0.005)

    def test_extremes_stay_in_unit_interval(self):
        lo_all, hi_all = wilson_ci(10, 10)
        lo_none, hi_none = wilson_ci(0, 10)
        assert 0.0 <= lo_none and hi_all <= 1.0
        assert hi_none > 0.0 and lo_all < 1.0

    def test_interval_narrows_with_n(self):
        lo_small, hi_small = wilson_ci(5, 10)
        lo_big, hi_big = wilson_ci(500, 1000)
        assert (hi_big - lo_big) < (hi_small - lo_small)


class TestMeanStd:
    def test_empty(self):
        assert mean_std([]) == (0.0, 0.0)

    def test_single_value_has_zero_std(self):
        assert mean_std([3.0]) == (3.0, 0.0)

    def test_known_sample(self):
        mean, std = mean_std([1.0, 2.0, 3.0, 4.0])
        assert mean == pytest.approx(2.5)
        assert std == pytest.approx(1.29099, abs=1e-4)


class TestPercentile:
    def test_empty(self):
        assert percentile([], 95.0) == 0.0

    def test_median_of_odd_and_even(self):
        assert median([3.0, 1.0, 2.0]) == 2.0
        assert median([1.0, 2.0, 3.0, 4.0]) == 2.5

    def test_p95_interpolates(self):
        xs = [float(i) for i in range(1, 101)]
        assert percentile(xs, 95.0) == pytest.approx(95.05)
