"""Unit tests for the search_telemetry data types and helpers."""

from quantik_core.move import Move
from quantik_core.search_telemetry import (
    UNPROVEN_VALUE_BOUND,
    EngineKind,
    PolicyMassKind,
    RootMoveStat,
    SearchEventCounters,
    SearchTelemetry,
    clamp_unproven,
)


def test_unproven_bound_value() -> None:
    assert UNPROVEN_VALUE_BOUND == 1.0 - 1e-6


def test_clamp_unproven_never_reaches_exact_one() -> None:
    assert clamp_unproven(1.0) == UNPROVEN_VALUE_BOUND
    assert clamp_unproven(-1.0) == -UNPROVEN_VALUE_BOUND
    assert clamp_unproven(2.5) == UNPROVEN_VALUE_BOUND
    assert clamp_unproven(-2.5) == -UNPROVEN_VALUE_BOUND
    assert clamp_unproven(0.3) == 0.3


def test_engine_kind_strings_match_bench_conventions() -> None:
    assert EngineKind.MCTS.as_str() == "mcts"
    assert EngineKind.BEAM.as_str() == "beam"
    assert EngineKind.MINIMAX.as_str() == "minimax"


def test_policy_mass_kind_strings() -> None:
    assert PolicyMassKind.VISITS.as_str() == "visits"
    assert PolicyMassKind.MULTIPLICITY.as_str() == "multiplicity"
    assert PolicyMassKind.NONE.as_str() == "none"


def test_root_move_stat_computes_action_index() -> None:
    stat = RootMoveStat.from_move(Move(0, 2, 5), 7, 0.25)
    assert stat.action_index == 2 * 16 + 5
    assert stat.policy_mass == 7
    assert stat.q_value == 0.25


def test_event_counters_default_to_zero() -> None:
    c = SearchEventCounters()
    assert (
        c.expanded_nodes,
        c.generated_nodes,
        c.transposition_hits,
        c.canonical_dedup_hits,
        c.terminal_hits,
        c.tablebase_hits,
    ) == (0, 0, 0, 0, 0, 0)


def test_search_telemetry_holds_fields() -> None:
    t = SearchTelemetry(
        engine_kind=EngineKind.MCTS,
        root_value=0.5,
        policy_mass_kind=PolicyMassKind.VISITS,
        root_moves=[RootMoveStat.from_move(Move(0, 0, 0), 3, 0.5)],
        root_identity_preserved=True,
        principal_variation=[Move(0, 0, 0)],
        counters=SearchEventCounters(expanded_nodes=1),
        elapsed_ms=2,
        depth_reached=1,
        seed=42,
    )
    assert t.engine_kind is EngineKind.MCTS
    assert t.counters.expanded_nodes == 1
    assert t.seed == 42
