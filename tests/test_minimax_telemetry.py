"""Telemetry tests for MinimaxEngine."""

from quantik_core import State
from quantik_core.core import State as CoreState
from quantik_core.minimax import (
    MinimaxConfig,
    MinimaxEngine,
    minimax_q_from_score,
)
from quantik_core.move import generate_legal_moves_list
from quantik_core.search_telemetry import (
    EngineKind,
    PolicyMassKind,
    SearchEventCounters,
)


def test_minimax_q_from_score_proven_and_squash() -> None:
    win = 10_000.0
    assert minimax_q_from_score(win - 1.0, win) == 1.0  # mate: proven win
    assert minimax_q_from_score(-(win - 1.0), win) == -1.0  # proven loss
    # heuristic scores squash strictly inside (-1, 1), sign-preserving
    assert minimax_q_from_score(0.0, win) == 0.0
    assert 0.0 < minimax_q_from_score(3.0, win) < 1.0
    assert -1.0 < minimax_q_from_score(-3.0, win) < 0.0


def test_telemetry_none_before_search() -> None:
    engine = MinimaxEngine(MinimaxConfig(max_depth=2, dedup_children=False))
    assert engine.telemetry() is None


def test_minimax_telemetry_shape_and_counters() -> None:
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=4, dedup_children=False, random_seed=20260716)
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.engine_kind is EngineKind.MINIMAX
    assert t.policy_mass_kind is PolicyMassKind.NONE
    assert t.root_identity_preserved is True  # dedup off
    assert t.counters.expanded_nodes > 0
    assert t.counters.generated_nodes > 0
    assert t.counters.tablebase_hits == 0
    assert t.depth_reached == 4
    assert -1.0 <= t.root_value <= 1.0
    for stat in t.root_moves:
        assert stat.policy_mass == 0
        assert stat.q_value is not None
        assert -1.0 <= stat.q_value <= 1.0
    assert t.principal_variation
    assert t.principal_variation[0] in {s.mv for s in t.root_moves}


def test_minimax_dedup_on_flags_identity_false() -> None:
    state = State.empty()
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=2, dedup_children=True, random_seed=1)
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.root_identity_preserved is False


def test_minimax_expanded_counted_at_move_generation() -> None:
    # `expanded_nodes` is the "successor set was computed" event, so it fires
    # once per `generate_legal_moves_list` call: once for the root moves, and
    # once for every negamax node -- INCLUDING the depth-0 leaf children, which
    # compute their successor set before the leaf evaluation short-circuits.
    # A depth-1 search over K non-terminal root moves therefore yields
    # expanded_nodes == K + 1 and generated_nodes == K (the root's K children
    # are constructed once; the leaves construct nothing). Before the fix,
    # expanded was counted at the `_children(...)` sites, so the depth-0 leaves
    # were never counted and expanded_nodes was just 1.
    state = State.empty()
    k = len(generate_legal_moves_list(state.bb))
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=1, dedup_children=False, use_transposition_table=False)
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.counters.expanded_nodes == k + 1
    assert t.counters.generated_nodes == k


def test_minimax_no_legal_moves_node_is_expanded_and_terminal() -> None:
    # A no-legal-moves node computed its (empty) successor set before being
    # ruled terminal, so it must be BOTH expanded and terminal (per the
    # normative counter semantics). A full single-shape board has no winning
    # line and no legal moves; negamax on it must bump both counters.
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=2, dedup_children=False, use_transposition_table=False)
    )
    engine._counters = SearchEventCounters()
    engine._nodes = 0
    engine._deadline = None
    no_moves_bb = CoreState((0xFFFF, 0, 0, 0, 0, 0, 0, 0)).bb
    assert generate_legal_moves_list(no_moves_bb) == []
    engine._negamax(no_moves_bb, 1, float("-inf"), float("inf"), 0, [], None)
    assert engine._counters.terminal_hits == 1
    assert engine._counters.expanded_nodes == 1


def test_minimax_transposition_hits_with_tt_on() -> None:
    # A position reachable by two move orders yields TT reuse when the TT is on.
    state = State.from_qfen("Ab../..c./...D/....")
    engine = MinimaxEngine(
        MinimaxConfig(
            max_depth=6,
            dedup_children=False,
            use_transposition_table=True,
            random_seed=1,
        )
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.counters.transposition_hits > 0  # TT must be reused on this fixture
