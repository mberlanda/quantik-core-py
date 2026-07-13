"""Tests for benchmarks.stability.

Uses synthetic rows so the arithmetic is verified exactly, without running
any engine.
"""

import pytest

from benchmarks.stability import aggregate_stability


def _row(engine, position_id, seed, move, hit):
    return {
        "engine": engine,
        "config_label": engine,
        "position_id": position_id,
        "seed": seed,
        "move": move,
        "hit": hit,
    }


class TestAggregateStability:
    def test_known_arithmetic(self):
        rows = [
            # position p1: modal move chosen by 2 of 3 seeds
            _row("fake", "p1", 0, "1:0:0", True),
            _row("fake", "p1", 1, "1:0:0", True),
            _row("fake", "p1", 2, "1:0:1", False),
            # position p2: perfectly consistent, always optimal
            _row("fake", "p2", 0, "1:2:3", True),
            _row("fake", "p2", 1, "1:2:3", True),
            _row("fake", "p2", 2, "1:2:3", True),
        ]
        (entry,) = aggregate_stability(rows)
        assert entry["engine"] == "fake"
        assert entry["seeds"] == 3
        # mean of (2/3, 3/3)
        assert entry["move_consistency"] == pytest.approx(5 / 6)
        # per-seed agreement: 1.0, 1.0, 0.5
        assert entry["agreement_mean"] == pytest.approx(5 / 6)
        assert entry["agreement_std"] == pytest.approx(0.28868, abs=1e-4)

    def test_unsolved_positions_do_not_count_toward_agreement(self):
        rows = [
            _row("fake", "p1", 0, "1:0:0", None),
            _row("fake", "p1", 1, "1:0:0", None),
        ]
        (entry,) = aggregate_stability(rows)
        assert entry["move_consistency"] == 1.0
        assert entry["agreement_mean"] == 0.0  # no solved positions at all
        assert entry["agreement_std"] == 0.0

    def test_deterministic_engine_single_seed(self):
        rows = [_row("minimax", "p1", 0, "1:0:0", True)]
        (entry,) = aggregate_stability(rows)
        assert entry["seeds"] == 1
        assert entry["move_consistency"] == 1.0
        assert entry["agreement_std"] == 0.0
