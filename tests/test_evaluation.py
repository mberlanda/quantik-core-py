import numpy as np
import pytest
from quantik_core import State
from quantik_core.evaluation import (
    EvalConfig,
    FEATURE_NAMES,
    features,
    evaluate,
    count_legal_moves,
)


def _bb(qfen):
    return State.from_qfen(qfen).bb


def test_feature_names_order():
    assert FEATURE_NAMES == [
        "threat_own",
        "threat_opp",
        "threat_shared",
        "mobility_diff",
        "build_two",
        "build_one",
    ]


def test_dead_line_scores_zero_threat():
    # Row 0 has shape A twice (A at 0, A-lower at 1) -> can never be 4-distinct
    f = features(_bb("Aa../..../..../...."), player=0)
    # no live 3-threats anywhere
    assert f[0] == 0 and f[1] == 0


def test_three_distinct_line_is_live_threat():
    # Row 0: A b C . -> 3 distinct shapes, missing D at pos 3
    f = features(_bb("AbC./..../..../...."), player=0)
    assert f[0] + f[1] + abs(f[2]) >= 1  # a threat is detected


def test_evaluate_is_dot_product():
    cfg = EvalConfig()
    bb = _bb("AbC./..../d..B/...a")
    assert evaluate(bb, 0, cfg) == pytest.approx(float(cfg.weights @ features(bb, 0)))


def _all_192_variants(bb):
    # VERIFIED API: D4 x S4 = 192, no color swap (canonical_key excludes color swap).
    from quantik_core.symmetry import SymmetryHandler as SH

    out = []
    for d4 in range(8):
        g = [SH.permute16(bb[i], d4) for i in range(8)]  # g[0:4]=P0 shapes, g[4:8]=P1
        for perm in SH.ALL_SHAPE_PERMS:
            out.append(tuple(g[c * 4 + perm[s]] for c in range(2) for s in range(4)))
    return out  # 192 boards (with duplicates for symmetric positions)


def test_symmetry_invariance():
    bb = _bb("AbC./..../d..B/...a")
    base = evaluate(bb, 0)
    for variant in _all_192_variants(bb):
        assert evaluate(variant, 0) == pytest.approx(base)


def test_perspective_relationship():
    # threat_own/opp swap and mobility negates when perspective flips
    bb = _bb("AbC./..../d..B/...a")
    f0, f1 = features(bb, 0), features(bb, 1)
    assert f0[0] == f1[1] and f0[1] == f1[0]
    assert f0[3] == -f1[3]
