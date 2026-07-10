# Cross-Engine Follow-up 1: Mid-Game Strength & Move-Agreement Benchmark

> **For agentic workers:** Execute this plan task-by-task with TDD. Steps use `- [ ]` checkboxes. This is a standalone follow-up; it depends only on already-merged code (`quantik_core.minimax`, `quantik_core.mcts`, `quantik_core.beam_search`, `tuning.build_dataset`). Read `docs/MINIMAX.md` for context.

**Goal:** Measure the three search engines (minimax, MCTS/UCT, beam search) from a *shared set of random valid non-terminal mid-game positions*, and report a **move-agreement** metric — how often each stochastic engine picks the exact-solver's move.

**Architecture:** A new example script `examples/cross_engine_benchmark.py` that (a) samples shared mid-game positions, (b) for each, computes the exact best move(s) via the minimax solver, and (c) queries each engine for its move and tallies agreement. Also a light head-to-head strength section starting games from mid-game positions instead of the empty board.

**Tech Stack:** Python 3.12+, numpy only. No new dependencies. No library changes — this is an example + a smoke test.

## Global Constraints
- Python `>=3.12`, numpy only. No new runtime deps.
- `./auto-lint.sh` before every commit. Do NOT run the full `./dev-check.sh` coverage gate (examples are not coverage-measured).
- Commit trailer:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Heavy work guarded under `if __name__ == "__main__":`. The smoke test only imports + calls pure helpers.
- Reuse, don't duplicate: `from tuning.build_dataset import sample_states` returns a list of non-terminal bitboards (8-tuples), deduped by canonical key, sampled 8–12 plies in. Signature: `sample_states(n: int, seed: int) -> list[tuple[int,...]]`.

## Verified existing APIs (use exactly)
- `from quantik_core import State, Move, apply_move`
- `from quantik_core.minimax import MinimaxEngine, MinimaxConfig` — `MinimaxEngine(MinimaxConfig(max_depth=16)).solve(State(bb))` → `MinimaxResult(best_move, score, ...)`. `score>0` = side-to-move wins.
- `from quantik_core.mcts import MCTSEngine, MCTSConfig` — `MCTSEngine(MCTSConfig(max_iterations=N, random_seed=S)).search(State(bb))` → `(Move, float)`.
- `from quantik_core.beam_search import BeamSearchEngine, BeamSearchConfig` — `BeamSearchEngine(BeamSearchConfig(beam_width=W, max_depth=D, random_seed=S)).search(State(bb))` → `BeamSearchResult`; the chosen first move is `result.best_leaf.moves[0]` (guard `best_leaf is None` → fall back to `result.ranked_root_moves()[0].move`).
- `from quantik_core.move import generate_legal_moves_list` → flat `list[Move]` for the side to move.
- `from quantik_core.game_utils import has_winning_line, check_game_winner, WinStatus`

---

## Task 1: Optimal-move set helper + move-agreement over shared positions

**Files:**
- Create: `examples/cross_engine_benchmark.py`
- Test: `tests/test_examples_demos.py` (append; reuse its `_load_demo_module` loader)

**Interfaces produced:**
- `optimal_moves(bb) -> list[Move]` — every root move whose exact value equals the solver's best. Computed by solving each child and taking the argmax (consistent ply convention, see code).
- `engine_move(engine_name, bb, **cfg) -> Move` for `engine_name in {"minimax","mcts","beam"}`.
- `move_agreement(n, seed) -> dict[str, float]` — fraction of sampled positions where each engine's move is in `optimal_moves`.

- [x] **Step 1: Write the failing smoke test** (append to `tests/test_examples_demos.py`):

```python
@pytest.fixture(scope="module")
def cross_engine_benchmark():
    return _load_demo_module("cross_engine_benchmark.py")


class TestCrossEngineBenchmark:
    def test_optimal_moves_finds_the_mate(self, cross_engine_benchmark):
        from quantik_core import State
        # Row 0 = A b C . ; side to move can complete with D at pos 3.
        bb = State.from_qfen("AbC./..../..../....").bb
        opt = cross_engine_benchmark.optimal_moves(bb)
        assert any(m.shape == 3 and m.position == 3 for m in opt)

    def test_engine_move_returns_legal(self, cross_engine_benchmark):
        from quantik_core import State
        from quantik_core.move import generate_legal_moves_list
        bb = State.from_qfen("AbC./..../..../....").bb
        legal = generate_legal_moves_list(bb)
        for name in ("minimax", "mcts", "beam"):
            assert cross_engine_benchmark.engine_move(name, bb) in legal
```

- [x] **Step 2: Run, verify fail** — `.venv/bin/pytest tests/test_examples_demos.py -k CrossEngine -x --no-cov` → import error.

- [x] **Step 3: Implement `examples/cross_engine_benchmark.py`.** Full content:

```python
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
from quantik_core.game_utils import check_game_winner, has_winning_line, WinStatus

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tuning.build_dataset import sample_states  # noqa: E402  (repo root on path)


def optimal_moves(bb):
    """Every legal root move whose exact game value ties the best.

    All child values use the same fresh-root (ply-0) convention, so the
    argmax is comparable despite ply-adjusted mate scores shifting by a
    constant. Returns a list[Move]."""
    ref = {}
    for m in generate_legal_moves_list(bb):
        child = State(apply_move(bb, m))
        ref[m] = -MinimaxEngine(MinimaxConfig(max_depth=16)).solve(child).score
    best = max(ref.values())
    return [m for m, v in ref.items() if v == best]


def engine_move(name, bb, **cfg):
    state = State(bb)
    if name == "minimax":
        c = MinimaxConfig(max_depth=cfg.get("max_depth", 6),
                          time_limit_s=cfg.get("time_limit_s", 0.2))
        return MinimaxEngine(c).search(state).best_move
    if name == "mcts":
        c = MCTSConfig(max_iterations=cfg.get("max_iterations", 1500),
                       random_seed=cfg.get("random_seed", 0))
        return MCTSEngine(c).search(state)[0]
    if name == "beam":
        c = BeamSearchConfig(beam_width=cfg.get("beam_width", 64),
                             max_depth=cfg.get("max_depth", 16),
                             random_seed=cfg.get("random_seed", 0))
        result = BeamSearchEngine(c).search(state)
        if result.best_leaf is not None and result.best_leaf.moves:
            return result.best_leaf.moves[0]
        return result.ranked_root_moves()[0].move
    raise ValueError(f"unknown engine {name}")


def move_agreement(n=40, seed=777):
    positions = sample_states(n, seed)
    hits = {"minimax": 0, "mcts": 0, "beam": 0}
    for bb in positions:
        opt = set(optimal_moves(bb))
        for name in hits:
            if engine_move(name, bb) in opt:
                hits[name] += 1
    return {name: h / len(positions) for name, h in hits.items()}


def play_from(bb, p0_name, p1_name):
    players = {0: p0_name, 1: p1_name}
    turn = 0
    while True:
        if has_winning_line(bb):
            return check_game_winner(bb)
        moves = generate_legal_moves_list(bb)
        if not moves:
            return WinStatus.PLAYER_1_WINS if turn == 0 else WinStatus.PLAYER_0_WINS
        bb = apply_move(bb, engine_move(players[turn], bb))
        turn ^= 1


def main():
    start = time.time()
    print("[1] Move-agreement vs the exact solver (shared mid-game positions)")
    for name, frac in move_agreement().items():
        print(f"  {name:8s}: {frac:.3f}")

    print("\n[2] Head-to-head from mid-game positions (minimax P0 vs MCTS P1)")
    positions = sample_states(8, seed=99)
    wins = sum(1 for bb in positions
               if play_from(bb, "minimax", "mcts") == WinStatus.PLAYER_0_WINS)
    print(f"  minimax won {wins}/{len(positions)} (as the side to move)")
    print(f"\ntotal: {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run the smoke test, verify pass** — `.venv/bin/pytest tests/test_examples_demos.py -k CrossEngine -v --no-cov`.

- [x] **Step 5: Run the script once** — `.venv/bin/python examples/cross_engine_benchmark.py`. Capture the numbers (they belong in a future research-note update). Expected shape: minimax agreement ~1.0 (it *is* a shallow-search proxy for the solver), MCTS/beam lower. If a run exceeds ~4 minutes, reduce `move_agreement(n=...)` default.

- [x] **Step 6: Lint + commit** — `./auto-lint.sh`; `git add examples/cross_engine_benchmark.py tests/test_examples_demos.py`; commit `feat(examples): cross-engine move-agreement + mid-game benchmark`.

---

## Self-review checklist
- Does `optimal_moves` account for the ply-shift correctly? (All children solved fresh at ply 0 → argmax comparable. Yes.)
- Is the smoke test cheap? (It solves a near-terminal position and runs one shallow search per engine — a few seconds. Acceptable.)
- No new runtime dependencies; heavy work under `__main__`.

## Post-implementation notes (two defects found and fixed during execution)

1. **`optimal_moves` must not call `.solve()`/`.search()` on a terminal
   child.** A legal move that immediately wins (completes a line, or leaves
   the opponent with zero legal replies) produces a child that `MinimaxEngine`
   explicitly rejects/mis-scores as a search root (`search()` requires a
   non-empty `generate_legal_moves_list`, and even when the child still has
   moves, `_negamax` never re-checks whether `bb` itself is already
   terminal). Sampled 8–12-ply positions frequently have an immediate winning
   move, so this affected `move_agreement()` broadly, not just the smoke
   test. Fixed by scoring such children directly (`float("inf")`) instead of
   solving them.
2. **The `sys.path` insert and the smoke-test anchor were both intractable
   as written.** `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`
   adds `examples/` (already `sys.path[0]` by default), not the repo root
   where `tuning/` lives — running the script directly raised
   `ModuleNotFoundError`. Separately, the plan's own smoke-test anchor
   (`"AbC./..../..../...."`, 3 pieces placed) makes `optimal_moves` solve
   ~40 non-winning branches from a near-empty position — measured **>170s
   for a single such solve**. Fixed the path insert to the repo root and
   replaced the anchor with a mid-game position (8 plies in); the full smoke
   test now runs in well under a second.

Actual run (`examples/cross_engine_benchmark.py`, 69.4s): move-agreement
minimax=1.000, beam=0.975, mcts=0.500. Head-to-head from mid-game starts
(minimax P0 vs MCTS P1): minimax won 4/8 — see the research note's
"Future work" section (item 1) for the full writeup.
