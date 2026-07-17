"""Telemetry tests for BeamSearchEngine."""

from quantik_core import State
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine
from quantik_core.search_telemetry import (
    UNPROVEN_VALUE_BOUND,
    EngineKind,
    PolicyMassKind,
)


def test_beam_telemetry_shape_and_counters() -> None:
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = BeamSearchEngine(BeamSearchConfig(random_seed=20260716))
    result = engine.search(state)
    t = engine.telemetry(result)
    assert t.engine_kind is EngineKind.BEAM
    assert t.policy_mass_kind is PolicyMassKind.MULTIPLICITY
    assert t.counters.transposition_hits == 0
    assert t.counters.tablebase_hits == 0
    assert t.counters.expanded_nodes > 0
    assert t.counters.generated_nodes > 0
    assert t.depth_reached == result.max_depth_reached
    assert -1.0 <= t.root_value <= 1.0
    for stat in t.root_moves:
        assert stat.policy_mass >= 1  # total_multiplicity
        assert stat.q_value is not None
        assert -1.0 <= stat.q_value <= 1.0


def test_beam_root_identity_tracks_depth1_dedup() -> None:
    # Empty board: the 64 legal first moves collapse onto canonical
    # representatives, so depth-1 dedup MUST occur and identity MUST be
    # reported as not preserved. This is deterministic (canonical keys do
    # not depend on the seed).
    engine = BeamSearchEngine(BeamSearchConfig(random_seed=20260716))
    result = engine.search(State.empty())
    t = engine.telemetry(result)
    assert t.counters.canonical_dedup_hits > 0
    assert t.root_identity_preserved is False


def test_beam_non_terminal_values_stay_within_unproven_bound() -> None:
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = BeamSearchEngine(BeamSearchConfig(random_seed=20260716))
    result = engine.search(state)
    t = engine.telemetry(result)
    for stat in t.root_moves:
        if stat.q_value is not None and abs(stat.q_value) != 1.0:
            assert abs(stat.q_value) <= UNPROVEN_VALUE_BOUND
