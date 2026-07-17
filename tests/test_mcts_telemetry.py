"""Telemetry tests for MCTSEngine."""

from quantik_core import State, apply_move, generate_legal_moves_list
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.search_telemetry import (
    UNPROVEN_VALUE_BOUND,
    EngineKind,
    PolicyMassKind,
)


def _empty() -> State:
    return State.empty()


def test_telemetry_none_before_search() -> None:
    engine = MCTSEngine(MCTSConfig(max_iterations=10, random_seed=1))
    assert engine.telemetry() is None


def test_telemetry_tt_off_empty_board_collapses_identity() -> None:
    # Symmetric first moves collapse to distinct canonical children even with
    # the transposition table off, so root identity is NOT preserved.
    engine = MCTSEngine(
        MCTSConfig(
            max_iterations=200, random_seed=20260716, use_transposition_table=False
        )
    )
    engine.search(_empty())
    t = engine.telemetry()
    assert t is not None
    assert t.engine_kind is EngineKind.MCTS
    assert t.policy_mass_kind is PolicyMassKind.VISITS
    assert t.root_identity_preserved is False


def test_telemetry_tt_on_empty_board_flags_identity_false() -> None:
    engine = MCTSEngine(
        MCTSConfig(max_iterations=200, random_seed=7, use_transposition_table=True)
    )
    engine.search(_empty())
    t = engine.telemetry()
    assert t is not None
    assert t.root_identity_preserved is False


def test_telemetry_identity_preserved_on_asymmetric_position() -> None:
    # A mid-game position whose legal first moves all reach distinct canonical
    # states preserves root identity (TT off).
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = MCTSEngine(
        MCTSConfig(
            max_iterations=200, random_seed=20260716, use_transposition_table=False
        )
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    if t.root_identity_preserved:
        legal = generate_legal_moves_list(state.bb)
        keys = {State(apply_move(state.bb, m)).canonical_key() for m in legal}
        assert len(keys) == len(legal)


def test_mcts_expanded_counted_once_per_expand_not_at_root_creation() -> None:
    # One iteration expands the root exactly once (its successor set is computed
    # in _expand) and constructs one successor state, so expanded == 1 and
    # generated == 1. Before the fix the root increment fired at node creation
    # (before any enumeration) AND again in _count_child_addition, giving 2.
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = MCTSEngine(
        MCTSConfig(
            max_iterations=1, random_seed=20260716, use_transposition_table=False
        )
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.counters.expanded_nodes == 1
    assert t.counters.generated_nodes == 1


def test_mcts_generated_counts_every_constructed_successor() -> None:
    # Two iterations both expand the root (K > 1 legal moves, so it is never
    # flagged fully expanded after one child). The second _expand re-derives
    # the already-visited child's state before constructing the new one, so
    # generated counts BOTH constructions: expanded == 2, generated == 3.
    # Before the fix, generated only counted retained children (== 2) and
    # expanded double-counted at creation + retention (== 3).
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = MCTSEngine(
        MCTSConfig(
            max_iterations=2, random_seed=20260716, use_transposition_table=False
        )
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.counters.expanded_nodes == 2
    assert t.counters.generated_nodes == 3


def test_telemetry_invariants_and_counters() -> None:
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = MCTSEngine(
        MCTSConfig(
            max_iterations=200, random_seed=20260716, use_transposition_table=False
        )
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.counters.expanded_nodes > 0
    assert t.counters.canonical_dedup_hits == 0  # structural for MCTS
    assert t.counters.tablebase_hits == 0
    assert t.counters.transposition_hits == 0  # TT off
    assert -1.0 <= t.root_value <= 1.0
    legal_mask = {
        m.shape * 16 + m.position for m in generate_legal_moves_list(state.bb)
    }
    for stat in t.root_moves:
        assert stat.action_index in legal_mask  # mass only on legal actions
        if stat.q_value is not None:
            assert -1.0 <= stat.q_value <= 1.0
    # PV starts from the root's best move and is non-empty when moves exist.
    assert t.principal_variation
    assert len(t.principal_variation) <= 16
    # Non-terminal sampled values never reach exact +/-1.0.
    for stat in t.root_moves:
        if stat.q_value is not None and abs(stat.q_value) != 1.0:
            assert abs(stat.q_value) <= UNPROVEN_VALUE_BOUND
