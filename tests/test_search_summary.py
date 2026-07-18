"""Tests for the search-summary.v1 exporter."""

import json

import pytest

from quantik_core import State
from quantik_core.contracts import SUPPORTED_CONTRACTS
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import Move
from quantik_core.search_summary import (
    SEARCH_SUMMARY_CONTRACT_VERSION,
    SEARCH_SUMMARY_SCHEMA,
    SearchSummaryRunConfig,
    search_summary_row,
)
from quantik_core.search_telemetry import (
    EngineKind,
    PolicyMassKind,
    RootMoveStat,
    SearchEventCounters,
    SearchTelemetry,
)


def _run_config() -> SearchSummaryRunConfig:
    return SearchSummaryRunConfig(config_label="test", search_depth=4)


def test_schema_label_is_registered() -> None:
    assert SEARCH_SUMMARY_SCHEMA == "search-summary.v1"
    # The registered label is listed in the supported-contracts manifest.
    assert SUPPORTED_CONTRACTS["search_summary"] == "search-summary.v1"


def test_row_shape_and_mask_consistency() -> None:
    qfen = "..../..../..../...."
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=4, dedup_children=False, random_seed=7)
    )
    engine.search(State.from_qfen(qfen))
    t = engine.telemetry()
    assert t is not None
    row = search_summary_row(0, "run-test", qfen, t, _run_config())
    assert row is not None
    assert row["schema"] == SEARCH_SUMMARY_SCHEMA
    assert row["contract_version"] == SEARCH_SUMMARY_CONTRACT_VERSION
    assert row["engine_kind"] == "minimax"
    assert len(row["policy_visits"]) == 64
    assert len(row["root_q_values"]) == 64
    # mass only on legal actions
    mask = row["legal_action_mask"]
    for i, v in enumerate(row["policy_visits"]):
        if v > 0:
            assert (mask >> i) & 1
    # row is JSON-serializable (None -> null)
    json.dumps(row)


def test_skips_unpreserved_identity() -> None:
    t = SearchTelemetry(
        engine_kind=EngineKind.MCTS,
        root_value=0.0,
        policy_mass_kind=PolicyMassKind.VISITS,
        root_moves=[],
        root_identity_preserved=False,
        principal_variation=[],
        counters=SearchEventCounters(),
    )
    assert search_summary_row(0, "r", "..../..../..../....", t, _run_config()) is None


def test_out_of_range_action_index_raises() -> None:
    bad = RootMoveStat(mv=Move(0, 0, 0), action_index=64, policy_mass=1, q_value=0.0)
    t = SearchTelemetry(
        engine_kind=EngineKind.MCTS,
        root_value=0.0,
        policy_mass_kind=PolicyMassKind.VISITS,
        root_moves=[bad],
        root_identity_preserved=True,
        principal_variation=[],
        counters=SearchEventCounters(),
    )
    with pytest.raises(ValueError):
        search_summary_row(0, "r", "..../..../..../....", t, _run_config())


def test_negative_action_index_raises() -> None:
    # A negative action_index would otherwise silently index policy_visits /
    # root_q_values from the end and corrupt the row; it must raise instead.
    bad = RootMoveStat(mv=Move(0, 0, 0), action_index=-1, policy_mass=1, q_value=0.0)
    t = SearchTelemetry(
        engine_kind=EngineKind.MCTS,
        root_value=0.0,
        policy_mass_kind=PolicyMassKind.VISITS,
        root_moves=[bad],
        root_identity_preserved=True,
        principal_variation=[],
        counters=SearchEventCounters(),
    )
    with pytest.raises(ValueError):
        search_summary_row(0, "r", "..../..../..../....", t, _run_config())


def test_mcts_row_populates_policy_visits() -> None:
    # An asymmetric position preserves identity -> a row is emitted.
    qfen = "A.bC/..../d..B/...a"
    engine = MCTSEngine(
        MCTSConfig(
            max_iterations=200, random_seed=20260716, use_transposition_table=False
        )
    )
    engine.search(State.from_qfen(qfen))
    t = engine.telemetry()
    assert t is not None
    # This position's legal moves reach 24 distinct canonical children, so
    # root identity preservation is a structural property of the qfen (not
    # RNG-dependent): the row is deterministically emitted here.
    assert t.root_identity_preserved is True
    row = search_summary_row(
        0,
        "run-test",
        qfen,
        t,
        SearchSummaryRunConfig(config_label="mcts", rollouts=200),
    )
    assert row is not None
    assert row["policy_mass_kind"] == "visits"
    assert sum(row["policy_visits"]) > 0
