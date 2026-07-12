"""Tests for benchmarks.agreement: raw observation rows + aggregations."""

import pytest

from quantik_core import State
from quantik_core.move import generate_legal_moves_list

from benchmarks import reference
from benchmarks.adapters import MinimaxAdapter, RandomAdapter
from benchmarks.agreement import (
    aggregate_agreement,
    aggregate_cost,
    run_agreement,
    iter_agreement,
)
from benchmarks.checkpoint import observation_key

ANCHOR = ".ba./..CC/DcbD/cA.A"


@pytest.fixture(scope="module")
def payload():
    """One exactly-solved anchor position + one reference-less position."""
    bb = State.from_qfen(ANCHOR).bb
    solved = {
        "id": "p0000",
        "qfen": ANCHOR,
        "phase": "late_mid",
        "pieces": 8,
        "side_to_move": 1,
        "legal_moves": len(generate_legal_moves_list(bb)),
        "reference": reference.solve_position(bb, budget_s=30.0),
    }
    heuristic_qfen = "Ab../..../..../...."
    heuristic = {
        "id": "p0001",
        "qfen": heuristic_qfen,
        "phase": "opening",
        "pieces": 2,
        "side_to_move": 0,
        "legal_moves": len(
            generate_legal_moves_list(State.from_qfen(heuristic_qfen).bb)
        ),
        "reference": None,
    }
    return {"positions": [solved, heuristic]}


class TestRunAgreement:
    def test_row_counts_and_seed_scheduling(self, payload):
        rows = run_agreement(
            [MinimaxAdapter(max_depth=2), RandomAdapter()],
            payload,
            seeds=[0, 1, 2],
        )
        # 2 positions x (1 deterministic run + 3 stochastic runs) = 8 rows.
        assert len(rows) == 8
        random_seeds = sorted(
            r["seed"]
            for r in rows
            if r["engine"] == "random" and r["position_id"] == "p0000"
        )
        assert random_seeds == [0, 1, 2]

    def test_empty_seeds_rejected(self, payload):
        with pytest.raises(ValueError, match="seeds"):
            run_agreement([MinimaxAdapter(max_depth=2)], payload, seeds=[])

    def test_hit_semantics(self, payload):
        # time_limit_s caps the depth-16 search on the OPENING position.
        rows = run_agreement(
            [MinimaxAdapter(max_depth=16, time_limit_s=2.0)], payload, seeds=[0]
        )
        by_position = {r["position_id"]: r for r in rows}
        # Full-depth minimax must pick an optimal move on the solved anchor.
        assert by_position["p0000"]["hit"] is True
        # No exact reference => hit is None, not False.
        assert by_position["p0001"]["hit"] is None
        assert by_position["p0000"]["phase"] == "late_mid"

    def test_iter_agreement_skips_completed_keys(self, payload):
        adapters = [MinimaxAdapter(max_depth=16, time_limit_s=2.0), RandomAdapter()]
        baseline = run_agreement(adapters, payload, seeds=[0, 1])
        skip = {observation_key(baseline[0])}

        rows = list(iter_agreement(adapters, payload, seeds=[0, 1], skip_keys=skip))

        assert [observation_key(row) for row in rows] == [
            observation_key(row) for row in baseline if observation_key(row) not in skip
        ]
        assert observation_key(baseline[0]) not in [
            observation_key(row) for row in rows
        ]


class TestAggregations:
    def test_aggregate_agreement_excludes_unsolved(self, payload):
        rows = run_agreement(
            [MinimaxAdapter(max_depth=16, time_limit_s=2.0)], payload, seeds=[0]
        )
        agg = aggregate_agreement(rows)
        assert len(agg) == 1  # only the solved late_mid position counts
        entry = agg[0]
        assert (entry["engine"], entry["phase"]) == ("minimax", "late_mid")
        assert entry["n"] == 1 and entry["hits"] == 1
        assert entry["agreement"] == 1.0
        assert 0.0 <= entry["ci95_low"] <= entry["ci95_high"] <= 1.0

    def test_aggregate_cost_shapes(self, payload):
        rows = run_agreement(
            [MinimaxAdapter(max_depth=2), RandomAdapter()], payload, seeds=[0, 1]
        )
        agg = {entry["engine"]: entry for entry in aggregate_cost(rows)}
        assert agg["minimax"]["median_nodes"] is not None
        assert agg["minimax"]["median_time_s"] >= 0.0
        assert agg["minimax"]["p95_time_s"] >= agg["minimax"]["median_time_s"]
        # RandomAdapter reports no nodes; the aggregate must tolerate that.
        assert agg["random"]["median_nodes"] is None
