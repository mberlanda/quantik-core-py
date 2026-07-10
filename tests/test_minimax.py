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


# A non-trivial mid-game anchor: not decided in one ply (a genuine positional
# value, not an instant mate), yet small enough that even unpruned plain
# minimax stays fast. Alpha-beta demonstrably prunes here (plain explores ~4k
# nodes at depth 3, alpha-beta ~1.5k), so the equivalence checks exercise the
# pruning/TT machinery rather than a trivial subtree.
_ANCHOR = ".D.a/..../..d./.BBd"


def test_alpha_beta_equals_plain_minimax():
    # Alpha-beta must not change the value it computes -- only the node count.
    s = State.from_qfen(_ANCHOR)
    v_ab = (
        MinimaxEngine(
            cfg(max_depth=3, use_alpha_beta=True, use_transposition_table=False)
        )
        .search(s)
        .score
    )
    v_plain = (
        MinimaxEngine(
            cfg(max_depth=3, use_alpha_beta=False, use_transposition_table=False)
        )
        .search(s)
        .score
    )
    assert v_ab == pytest.approx(v_plain)


def test_tt_equals_no_tt():
    # The transposition table must not change the computed value.
    s = State.from_qfen(_ANCHOR)
    v_tt = MinimaxEngine(cfg(max_depth=4, use_transposition_table=True)).search(s).score
    v_no = (
        MinimaxEngine(cfg(max_depth=4, use_transposition_table=False)).search(s).score
    )
    assert v_tt == pytest.approx(v_no)


def test_iterative_deepening_matches_fixed_depth():
    # ID to depth 3 (full config) agrees in value with an unpruned depth-3
    # search -- deepening changes move ordering/speed, never the value.
    s = State.from_qfen(_ANCHOR)
    v_id = MinimaxEngine(cfg(max_depth=3)).search(s).score
    assert v_id == pytest.approx(
        MinimaxEngine(
            cfg(max_depth=3, use_transposition_table=False, use_alpha_beta=False)
        )
        .search(s)
        .score
    )


def test_tt_matches_no_tt_across_sampled_positions():
    # Regression for a TT-bound-classification bug: a TT hit narrows this
    # node's alpha/beta before searching, but the final EXACT/LOWER/UPPER
    # classification must compare `best_value` against the ORIGINAL window
    # (pre-narrowing), not the narrowed one -- else a cutoff only reachable
    # because of an unrelated entry's tighter window gets misrecorded as a
    # bound proven against the caller's actual window, corrupting later
    # reuse of that entry. The single fixed `_ANCHOR` position never
    # exercised this path; sampling several positions with real transposing
    # sibling lines (mid-game, more legal moves) does.
    from tuning.build_dataset import sample_states

    positions = sample_states(10, seed=4242)
    for bb in positions:
        s = State(bb)
        v_tt = (
            MinimaxEngine(cfg(max_depth=6, use_transposition_table=True))
            .search(s)
            .score
        )
        v_no_tt = (
            MinimaxEngine(cfg(max_depth=6, use_transposition_table=False))
            .search(s)
            .score
        )
        assert v_tt == pytest.approx(v_no_tt), f"mismatch at {s.to_qfen()!r}"


# ----- exact-solve correctness anchors -------------------------------------
# A full solve from the EMPTY board is intractable in pure Python (~23.5M
# unique canonical states cumulatively; canonical_key scans all 192
# symmetries, so the engine runs at only a few hundred nodes/s from the open
# game -- see GAME_TREE_ANALYSIS.md and docs/MINIMAX.md). Instead we anchor
# solver correctness on positions a few plies in, where the remaining tree is
# small enough to solve exactly and the game-theoretic value is a precise,
# ply-adjusted number: score == +/-(win - plies_to_end). max_depth=16 never
# hits the eval cutoff (no Quantik game exceeds 16 plies), so every value is
# exact and every leaf on the PV is a true terminal.


def test_solve_exact_forced_win_in_three():
    # From this position P0 (side to move) can force a win in exactly 3 plies.
    r = MinimaxEngine(cfg(max_depth=16)).solve(State.from_qfen(".B.C/a.../.Ca./..d."))
    assert r.score == pytest.approx(10_000 - 3)  # win - ply, ply == 3
    assert r.depth_reached == 16
    assert len(r.pv) == 3


def test_solve_exact_forced_loss_in_four():
    # Here every P0 reply loses; the opponent forces mate in 4 plies, so the
    # side-to-move value is -(win - 4). Exercises the losing side of the sign.
    r = MinimaxEngine(cfg(max_depth=16)).solve(State.from_qfen(".D.a/D..c/..d./.BBd"))
    assert r.score == pytest.approx(-(10_000 - 4))
    assert r.depth_reached == 16


def test_random_tiebreak_never_returns_suboptimal_move():
    # Regression: narrowing alpha across root siblings once let an inferior
    # move's fail-soft upper bound tie best_value and be picked by the random
    # tie-break. From this position one root move forces a win while others
    # lose badly; every seed must still return an optimal move.
    from quantik_core import apply_move
    from quantik_core.move import generate_legal_moves_list

    pos = State.from_qfen("D.../.A.d/D.A./.bc.")
    # Reference value of every legal root move, all computed with the SAME
    # (fresh-root, ply-0) convention so the argmax is comparable even though
    # ply-adjusted mate scores shift by a constant vs. the in-search ply.
    ref = {}
    for m in generate_legal_moves_list(pos.bb):
        child = State(apply_move(pos.bb, m))
        ref[m] = -MinimaxEngine(cfg(max_depth=2)).search(child).score
    best_ref = max(ref.values())
    optimal = {m for m, v in ref.items() if v == pytest.approx(best_ref)}

    for seed in range(8):
        r = MinimaxEngine(cfg(max_depth=3, random_seed=seed)).search(pos)
        assert r.best_move in optimal, f"seed={seed} picked a suboptimal move"


def test_solve_pv_ends_in_terminal():
    # The principal variation of an exact solve must end on a real terminal:
    # replaying it reaches a winning line (or a no-legal-move loss).
    from quantik_core import apply_move
    from quantik_core.game_utils import has_winning_line
    from quantik_core.move import generate_legal_moves_list

    s = State.from_qfen(".B.C/a.../.Ca./..d.")
    r = MinimaxEngine(cfg(max_depth=16)).solve(s)
    bb = s.bb
    for mv in r.pv:
        bb = apply_move(bb, mv)
    assert has_winning_line(bb) or not generate_legal_moves_list(bb)
