#!/usr/bin/env python3
"""
Benchmark harness for the Quantik alpha-beta minimax engine.

Four sections:
1. Playing strength  -- win rates vs a random mover and vs MCTS (both sides).
2. Search performance -- nodes/sec, alpha-beta and transposition-table prune
   ratios, depth reached under a time budget, and time-to-move by ply.
3. Solve correctness  -- exact anchors (win-in-3, loss-in-4) plus a
   time-bounded search from the empty board as directional evidence for the
   known first-player-win result (a full empty-board solve is intractable in
   pure Python; see docs/MINIMAX.md).
4. Evaluation quality -- seeded vs fitted weights on sign-accuracy and
   move-agreement against the exact solver.

Run: python examples/minimax_benchmark.py
Defaults are modest so the whole run finishes in a few minutes (~6 min on a
laptop); scale the constants up for sharper estimates or down for a quick
smoke.
"""

from quantik_core.game_utils import WinStatus
from quantik_core.move import generate_legal_moves_list
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
    has_winning_line,
)
from quantik_core.evaluation import EvalConfig, evaluate
from quantik_core import State, apply_move
import os
import random
import sys
import time

# Ensure sibling example modules import both as a direct script (examples/ is
# already sys.path[0]) and when this file is loaded by path elsewhere.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import minimax_demo as _md  # noqa: E402

minimax_player = _md.minimax_player
mcts_player = _md.mcts_player
play_game = _md.play_game
random_player = _md.random_player


def _sample_solved(n, seed, min_plies=8, max_plies=12):
    """Sample `n` distinct positions solvable fast, with (state, exact_move,
    label) where label is +1/-1 for the side to move."""
    rng = random.Random(seed)
    seen, out = set(), []
    while len(out) < n and len(seen) < n * 50:
        plies = rng.randint(min_plies, max_plies)
        bb = State.empty().bb
        ok = True
        for _ in range(plies):
            moves = generate_legal_moves_list(bb)
            if not moves:
                ok = False
                break
            bb = apply_move(bb, rng.choice(moves))
            if has_winning_line(bb):
                ok = False
                break
        if not ok or not generate_legal_moves_list(bb):
            continue
        key = State(bb).canonical_key()
        if key in seen:
            continue
        seen.add(key)
        r = MinimaxEngine(MinimaxConfig(max_depth=16)).solve(State(bb))
        label = 1 if r.score > 0 else -1 if r.score < 0 else 0
        if label != 0:
            out.append((bb, r.best_move, label))
    return out


def bench_strength(games=8):
    print("\n[1] Playing strength")
    mm = dict(max_depth=6, time_limit_s=0.15, eval_config=EvalConfig.load())

    def rate(results, mm_win):
        return sum(1 for r in results if r == mm_win)

    r = [play_game(minimax_player(**mm), random_player(seed=g)) for g in range(games)]
    print(f"  vs random  (minimax P0): {rate(r, WinStatus.PLAYER_0_WINS)}/{games}")
    r = [play_game(random_player(seed=g), minimax_player(**mm)) for g in range(games)]
    print(f"  vs random  (minimax P1): {rate(r, WinStatus.PLAYER_1_WINS)}/{games}")

    mcts = dict(max_iterations=1500, random_seed=0)
    r = [play_game(minimax_player(**mm), mcts_player(**mcts)) for _ in range(games)]
    print(f"  vs MCTS1500(minimax P0): {rate(r, WinStatus.PLAYER_0_WINS)}/{games}")
    r = [play_game(mcts_player(**mcts), minimax_player(**mm)) for _ in range(games)]
    print(f"  vs MCTS1500(minimax P1): {rate(r, WinStatus.PLAYER_1_WINS)}/{games}")


def bench_search():
    print("\n[2] Search performance")
    pos = State.from_qfen(".D.a/..../..d./.BBd")  # fast mid-game anchor
    depth = 4
    for label, kw in (
        ("full (ab+tt+dedup)", {}),
        ("ab only (no tt)", dict(use_transposition_table=False)),
        ("no ab, no tt", dict(use_alpha_beta=False, use_transposition_table=False)),
    ):
        t = time.time()
        r = MinimaxEngine(MinimaxConfig(max_depth=depth, **kw)).search(pos)
        dt = time.time() - t
        rate = r.nodes / dt if dt else 0
        print(
            f"  d{depth} {label:22s}: nodes={r.nodes:7d}  {dt:6.3f}s  {rate:8.0f} n/s"
        )

    # depth reached from the empty board under a time budget
    for budget in (2.0, 5.0):
        t = time.time()
        r = MinimaxEngine(MinimaxConfig(max_depth=16, time_limit_s=budget)).search(
            State.empty()
        )
        print(
            f"  empty board, {budget:.0f}s budget: depth={r.depth_reached} "
            f"nodes={r.nodes} ({time.time() - t:.1f}s)"
        )

    # time-to-move by ply along one self-played minimax line
    print("  time-to-move by ply (minimax, 0.2s budget/move):")
    bb = State.empty().bb
    for ply in range(6):
        if has_winning_line(bb) or not generate_legal_moves_list(bb):
            break
        t = time.time()
        r = MinimaxEngine(MinimaxConfig(max_depth=16, time_limit_s=0.2)).search(
            State(bb)
        )
        print(
            f"    ply {ply}: depth={r.depth_reached} nodes={r.nodes} {time.time() - t:.2f}s"
        )
        bb = apply_move(bb, r.best_move)


def bench_solve():
    print("\n[3] Solve correctness")
    for qfen, expect in ((".B.C/a.../.Ca./..d.", 9997), (".D.a/D..c/..d./.BBd", -9996)):
        r = MinimaxEngine(MinimaxConfig(max_depth=16)).solve(State.from_qfen(qfen))
        ok = abs(r.score - expect) < 1e-6
        print(
            f"  {qfen}: score={r.score:.0f} (expect {expect}) {'OK' if ok else 'FAIL'}"
            f"  nodes={r.nodes}"
        )
    t = time.time()
    r = MinimaxEngine(MinimaxConfig(max_depth=16, time_limit_s=5.0)).search(
        State.empty()
    )
    p0, p1 = count_total_pieces(apply_move(State.empty().bb, r.best_move))
    print(
        f"  empty (5s budget): best={r.best_move} score={r.score:.1f} "
        f"depth={r.depth_reached} ({time.time() - t:.1f}s) -- directional only"
    )


def bench_eval_quality(n=60):
    print(f"\n[4] Evaluation quality (n={n} solved positions)")
    samples = _sample_solved(n, seed=12345)
    for label, cfg in (("seeded", EvalConfig()), ("fitted", EvalConfig.load())):
        sign_hits = agree = 0
        for bb, exact_move, y in samples:
            p0, p1 = count_total_pieces(bb)
            stm = get_current_player_from_counts(p0, p1)
            score = evaluate(bb, stm, cfg)
            if (score > 0) == (y > 0):
                sign_hits += 1
            shallow = MinimaxEngine(MinimaxConfig(max_depth=2, eval_config=cfg)).search(
                State(bb)
            )
            if shallow.best_move == exact_move:
                agree += 1
        n_s = len(samples)
        print(
            f"  {label}: sign-accuracy={sign_hits / n_s:.3f}  "
            f"move-agreement={agree / n_s:.3f}"
        )


def main():
    start = time.time()
    bench_strength()
    bench_search()
    bench_solve()
    bench_eval_quality()
    print(f"\ntotal benchmark time: {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
