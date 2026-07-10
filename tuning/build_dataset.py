"""Build a solver-labeled dataset for fitting the evaluation weights.

Each sample is a reachable, non-terminal Quantik position labeled with the
exact game-theoretic outcome for the side to move (+1 win / -1 loss / 0
draw), obtained from the full-depth `MinimaxEngine` solver.

Sampling bias (intentional and documented): a full solve from the *open*
game is intractable in pure Python -- `canonical_key()` scans all 192
symmetries, so the early game runs at only a few hundred nodes/s. Positions
that are already ~8-12 plies in have a small remaining tree and solve in
well under a second, so we sample there. This biases the dataset toward
mid/late-game positions, which is acceptable: the leaves a depth-limited
search actually evaluates are themselves several plies into the game.

Run: `python tuning/build_dataset.py` -> writes `tuning/dataset.npz`
(arrays `X` of shape (N, 6) and `y` of shape (N,)).
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import List, Tuple

import numpy as np

from quantik_core import State, apply_move
from quantik_core.evaluation import features
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
    has_winning_line,
)
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import generate_legal_moves_list

_DATASET_PATH = Path(__file__).resolve().parent / "dataset.npz"

# Ply range to sample. Kept deep enough that every exact solve is fast
# (measured max ~1.1s, mean ~0.25s at >=8 plies) so a few hundred samples
# build in ~1-2 minutes.
_MIN_PLIES = 8
_MAX_PLIES = 12


def _random_nonterminal_position(rng: random.Random) -> Tuple[int, ...] | None:
    """Play a random legal game for a random number of plies in the sampling
    range, returning a non-terminal bitboard (or None if the line ended early).
    """
    plies = rng.randint(_MIN_PLIES, _MAX_PLIES)
    bb: Tuple[int, ...] = State.empty().bb
    for _ in range(plies):
        moves = generate_legal_moves_list(bb)
        if not moves:
            return None
        move = rng.choice(moves)
        nxt = apply_move(bb, move)
        if has_winning_line(nxt):
            return None  # terminal reached before target depth; resample
        bb = nxt  # type: ignore[assignment]
    if not generate_legal_moves_list(bb):
        return None  # no legal moves: terminal
    return bb


def sample_states(n: int, seed: int) -> List[Tuple[int, ...]]:
    """Sample `n` distinct non-terminal bitboards, deduped by canonical key."""
    rng = random.Random(seed)
    seen: set[bytes] = set()
    out: List[Tuple[int, ...]] = []
    attempts = 0
    while len(out) < n and attempts < n * 200:
        attempts += 1
        bb = _random_nonterminal_position(rng)
        if bb is None:
            continue
        key = State(bb).canonical_key()
        if key in seen:
            continue
        seen.add(key)
        out.append(bb)
    return out


def label_state(bb: Tuple[int, ...]) -> int:
    """Exact outcome for the side to move: +1 win, -1 loss, 0 draw."""
    result = MinimaxEngine(MinimaxConfig(max_depth=16)).solve(State(bb))
    if result.score > 0:
        return 1
    if result.score < 0:
        return -1
    return 0


def build(n: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """Sample, solve-label, and featurize `n` positions -> (X, y)."""
    states = sample_states(n, seed)
    rows: List[np.ndarray] = []
    labels: List[int] = []
    for bb in states:
        p0, p1 = count_total_pieces(bb)
        stm = get_current_player_from_counts(p0, p1)
        rows.append(features(bb, stm))
        labels.append(label_state(bb))
    X = np.asarray(rows, dtype=np.float64)
    y = np.asarray(labels, dtype=np.int64)
    return X, y


def main(n: int = 500, seed: int = 20260710) -> None:
    import time

    start = time.time()
    X, y = build(n, seed)
    np.savez(_DATASET_PATH, X=X, y=y)
    wins = int((y == 1).sum())
    losses = int((y == -1).sum())
    draws = int((y == 0).sum())
    print(
        f"dataset: {len(y)} positions in {time.time() - start:.1f}s "
        f"(wins={wins} losses={losses} draws={draws}) -> {_DATASET_PATH}"
    )


if __name__ == "__main__":
    main()
