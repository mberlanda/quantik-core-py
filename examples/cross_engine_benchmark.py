#!/usr/bin/env python3
"""Cross-engine benchmark: strength and move-agreement from shared mid-game
positions.

Samples random valid non-terminal mid-game positions, computes the exact
best move(s) with the minimax solver, and measures how often MCTS and beam
search agree with it. Also plays head-to-head games starting from mid-game
positions (more representative than always starting from the empty board).

Run: python examples/cross_engine_benchmark.py
"""

import os
import sys
import time

from quantik_core import State, apply_move
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine
from quantik_core.move import generate_legal_moves_list
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
    has_winning_line,
)

# `tuning/` lives at the repo root, a level above `examples/`. Running this
# file directly (`python examples/cross_engine_benchmark.py`) puts only
# `examples/` on sys.path[0], not the repo root, so `tuning` isn't
# importable without this -- add the repo root explicitly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tuning.build_dataset import sample_states  # noqa: E402


def optimal_moves(bb):
    """Every legal root move whose exact game value ties the best.

    All child values use the same fresh-root (ply-0) convention, so the
    argmax is comparable despite ply-adjusted mate scores shifting by a
    constant. `MinimaxEngine.solve`/`search` reject (or, worse, silently
    mis-score) a state with no legal moves for the side to move, so a
    child that is itself terminal -- an immediately winning move, either
    by completing a line or by leaving the opponent with no legal reply
    -- is scored directly as a win rather than solved; solving is only
    valid on a genuinely non-terminal child. Returns a list[Move]."""
    ref = {}
    # One reused engine, not one per child: MinimaxEngine.solve()/search()
    # reset all per-call state (_tt, _nodes, _pv_hint, _deadline) at the
    # start of every call, so reuse across independent states is safe and
    # avoids an engine allocation per legal move.
    engine = MinimaxEngine(MinimaxConfig(max_depth=16))
    for m in generate_legal_moves_list(bb):
        child_bb = apply_move(bb, m)
        if has_winning_line(child_bb) or not generate_legal_moves_list(child_bb):
            ref[m] = float("inf")
        else:
            ref[m] = -engine.solve(State(child_bb)).score
    best = max(ref.values())
    return [m for m, v in ref.items() if v == best]


def engine_move(name, bb, **cfg):
    state = State(bb)
    if name == "minimax":
        c = MinimaxConfig(
            max_depth=cfg.get("max_depth", 6), time_limit_s=cfg.get("time_limit_s", 0.2)
        )
        return MinimaxEngine(c).search(state).best_move
    if name == "mcts":
        c = MCTSConfig(
            max_iterations=cfg.get("max_iterations", 1500),
            random_seed=cfg.get("random_seed", 0),
        )
        return MCTSEngine(c).search(state)[0]
    if name == "beam":
        c = BeamSearchConfig(
            beam_width=cfg.get("beam_width", 64),
            max_depth=cfg.get("max_depth", 16),
            random_seed=cfg.get("random_seed", 0),
        )
        result = BeamSearchEngine(c).search(state)
        if result.best_leaf is not None and result.best_leaf.moves:
            return result.best_leaf.moves[0]
        return result.ranked_root_moves()[0].move
    raise ValueError(f"unknown engine {name}")


def move_agreement(n=40, seed=777):
    positions = sample_states(n, seed)
    hits = {"minimax": 0, "mcts": 0, "beam": 0}
    if not positions:
        return {name: 0.0 for name in hits}
    for bb in positions:
        opt = set(optimal_moves(bb))
        for name in hits:
            if engine_move(name, bb) in opt:
                hits[name] += 1
    return {name: h / len(positions) for name, h in hits.items()}


def play_from(bb, mover_name, other_name):
    """Play out a game from `bb`; returns True iff `mover_name` -- the side
    already to move at `bb` -- eventually wins.

    Sampled mid-game positions (8-12 plies) can have EITHER color to move,
    so `mover_name`/`other_name` bind to whichever color is actually to
    move right now, not a hard-coded P0/P1 -- a fixed assignment would
    silently swap which engine gets credited depending on the sample's
    parity. Both terminal conditions (a completed line, or no legal
    moves) mean the side whose turn it currently is has just lost -- the
    same convention `MinimaxEngine._negamax` uses.
    """
    p0, p1 = count_total_pieces(bb)
    turn = get_current_player_from_counts(p0, p1)
    mover_color = turn
    players = {turn: mover_name, 1 - turn: other_name}
    while True:
        if has_winning_line(bb):
            return (1 - turn) == mover_color
        moves = generate_legal_moves_list(bb)
        if not moves:
            return (1 - turn) == mover_color
        bb = apply_move(bb, engine_move(players[turn], bb))
        turn ^= 1


def main():
    start = time.time()
    print("[1] Move-agreement vs the exact solver (shared mid-game positions)")
    for name, frac in move_agreement().items():
        print(f"  {name:8s}: {frac:.3f}")

    print("\n[2] Head-to-head from mid-game positions (minimax as the side to move)")
    positions = sample_states(8, seed=99)
    wins = sum(1 for bb in positions if play_from(bb, "minimax", "mcts"))
    print(f"  minimax won {wins}/{len(positions)} (as the side to move)")
    print(f"\ntotal: {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
