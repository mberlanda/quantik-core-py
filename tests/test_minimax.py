import pytest
from quantik_core import State
from quantik_core.minimax import MinimaxEngine, MinimaxConfig


def cfg(**kw):
    return MinimaxConfig(**kw)


def test_finds_mate_in_one():
    # Row 0 = A b C . ; side to move can place D at pos 3 to complete 4 distinct
    e = MinimaxEngine(cfg(max_depth=2))
    r = e.search(State.from_qfen("AbC./..../..../...."))
    assert r.best_move.position == 3 and r.best_move.shape == 3  # D at pos 3
    assert r.score >= 9000  # near-win magnitude


def test_blocks_opponent_mate_in_one():
    # Row 0 = B c D . (P0: B@0, D@2; P1: c@1) is a live threat: missing shape A
    # at pos 3. P0 has used both of its A pieces elsewhere (A@10, A@14), so P0
    # cannot complete the line itself and must block pos 3 or hand P1 the win
    # next move. Of P0's remaining shapes, C is blocked (P1 owns c@1 on row 0)
    # and D is blocked (P1 owns d@15 on col 3), leaving B as the only legal
    # piece P0 may place at pos 3 -- a single, forced, verified-unique safe
    # move. See task-2-report.md for the full derivation and the script that
    # checked every non-blocking move loses immediately.
    qfen = "BcD./..../.cA./.dAd"
    state = State.from_qfen(qfen)

    # Ground truth: exhaustive solve (max_depth=16 guarantees a full-depth
    # solve since no Quantik game exceeds 16 plies, so this never hits the
    # eval cutoff -- every value is exact).
    solver = MinimaxEngine(cfg(max_depth=16))
    solved = solver.search(state)

    e = MinimaxEngine(cfg(max_depth=2))
    r = e.search(state)

    assert r.best_move == solved.best_move
    assert r.best_move.shape == 1 and r.best_move.position == 3  # B at pos 3
    assert solved.score > -9000


def test_alpha_beta_equals_plain_minimax():
    s = State.from_qfen("A.../..../..../....")
    v_ab = MinimaxEngine(
        cfg(max_depth=4, use_alpha_beta=True, use_transposition_table=False)
    ).search(s).score
    v_plain = MinimaxEngine(
        cfg(max_depth=4, use_alpha_beta=False, use_transposition_table=False)
    ).search(s).score
    assert v_ab == pytest.approx(v_plain)


def test_tt_equals_no_tt():
    s = State.from_qfen("A.../..../..../....")
    v_tt = MinimaxEngine(cfg(max_depth=6, use_transposition_table=True)).search(s).score
    v_no = MinimaxEngine(cfg(max_depth=6, use_transposition_table=False)).search(
        s
    ).score
    assert v_tt == pytest.approx(v_no)


def test_iterative_deepening_matches_fixed_depth():
    s = State.from_qfen("A.../..../..../....")
    # ID to depth 4 should agree in value with a direct depth-4 search
    v_id = MinimaxEngine(cfg(max_depth=4)).search(s).score
    assert v_id == pytest.approx(
        MinimaxEngine(
            cfg(max_depth=4, use_transposition_table=False, use_alpha_beta=False)
        )
        .search(s)
        .score
    )
