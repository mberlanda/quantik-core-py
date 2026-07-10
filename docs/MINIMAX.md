# Minimax (Alpha-Beta) Search

`quantik_core.minimax` provides a deterministic classical-search engine: negamax
with alpha-beta pruning, iterative deepening, and a transposition table. It
pairs with a *fitted* handcrafted evaluation (`quantik_core.evaluation`) used at
depth-limited leaves, and doubles as an exact solver at full depth.

Unlike the module-only MCTS and beam-search engines, `MinimaxEngine`,
`MinimaxConfig`, `MinimaxResult`, `evaluate`, and `EvalConfig` are exported at
the top level of `quantik_core`.

## Quick start

```python
from quantik_core import State, MinimaxEngine, MinimaxConfig, EvalConfig

# Depth/time-limited play with the fitted evaluation weights.
engine = MinimaxEngine(MinimaxConfig(max_depth=6, time_limit_s=1.0,
                                     eval_config=EvalConfig.load()))
result = engine.search(State.from_qfen("AbC./..../..../...."))

result.best_move     # the chosen Move
result.score         # negamax value from the side-to-move's perspective
result.depth_reached # deepest completed iteration
result.nodes         # nodes visited
result.pv            # principal variation (list[Move])
result.elapsed       # wall-clock seconds
```

## Configuration (`MinimaxConfig`)

| Field | Default | Meaning |
|-------|---------|---------|
| `max_depth` | `16` | Maximum iterative-deepening depth. 16 plies is the whole game, so `max_depth=16` never hits the eval cutoff — it solves exactly. |
| `time_limit_s` | `None` | Wall-clock budget; iterative deepening returns the deepest iteration that finished. |
| `use_alpha_beta` | `True` | Enable alpha-beta pruning. |
| `use_transposition_table` | `True` | Cache values by `canonical_key()`. |
| `dedup_children` | `True` | Collapse sibling moves that lead to the same canonical state. |
| `eval_config` | seeded `EvalConfig()` | Leaf evaluation weights. Pass `EvalConfig.load()` for the fitted weights. |
| `random_seed` | `None` | If set, breaks ties among equal-value root moves randomly; otherwise the lowest `(shape, position)` wins deterministically. |

## How it works

- **Negamax + alpha-beta.** Values are from the side-to-move's perspective; a
  child's value is negated into its parent.
- **Terminal detection uses `has_winning_line`.** A winning line means the
  *previous* mover completed it, so the side-to-move value is `-(win - ply)`.
  Depth-adjusting by `ply` makes faster mates score higher. "No legal moves"
  likewise loses. Using `has_winning_line` (rather than `check_game_winner`)
  sidesteps that helper's turn-balance edge case.
- **Iterative deepening** seeds each iteration's move order with the previous
  principal variation, and orders immediate winning replies first for the
  earliest possible cutoffs.
- **Transposition table.** Keyed by `State.canonical_key()`, which covers the
  D4 × S4 = 192 board symmetries **without** swapping colors. The negamax value
  is relative to the side to move (determined by piece counts, a
  symmetry-invariant quantity), so caching the value/bound by that key is sound.
  Only the value/bound is cached — never the move, which would be in the wrong
  orientation for a symmetric sibling.

## Evaluation (`quantik_core.evaluation`)

`evaluate(bb, player, cfg)` scores a non-terminal position as a dot product of a
weight vector and a 6-feature vector (`FEATURE_NAMES`):

`threat_own`, `threat_opp`, `threat_shared`, `mobility_diff`, `build_two`,
`build_one` — capturing live line threats (weighted by which side can *legally*
complete them), mobility, and partial line-building. The evaluation is
**symmetry-invariant** across all 192 board variants.

Weights are **fitted, not hand-guessed** (see `tuning/`, below). `EvalConfig()`
holds the seeded starting weights `[100, -100, 20, 3, 2, 0]`; `EvalConfig.load()`
reads the fitted weights from `tuning/weights.json` (falling back to seeded if
absent).

## Three "depths" — what is exact, and where sampling enters

These are independent and easy to conflate:

| Depth | What it means | Exact? | Estimate / sampling |
|-------|---------------|--------|---------------------|
| **Runtime search depth** (`search(max_depth=d)`) | The top `d` plies from the search root are explored exhaustively (alpha-beta only prunes provably-irrelevant lines). | Top `d` plies: yes. | Depth-`d` leaves use the fitted **evaluation** estimate. |
| **Solve depth** (`solve()` = `max_depth=16`) | The whole remaining game, down to true terminals. | **Fully exact** — no evaluation ever used. | None — but only *tractable* when few plies remain. |
| **Training-sample depth** (dataset generation) | The ply at which positions are sampled to be labeled by the solver. | The label is exact (via `solve`). | **This is the only place random sampling enters.** Positions are sampled 8–12 plies in, because that is where `solve` is fast. |

The last row is the subtle one: sampling at plies 8–12 is a property of **how
training labels are produced**, not of how the engine searches at runtime. At
runtime the engine exhaustively covers its top `d` plies from whatever position
it is given.

## Cross-engine cooperation (shared representation)

Because every engine in this library keys off the same `canonical_key()`, they
share a state identity and can help each other. The `OpeningBookDatabase`
(`quantik_core.opening_book`) is keyed by `canonical_key` and stores
`best_moves` / `evaluation` / terminal status — it is **engine-agnostic**, so
MCTS, beam search, and minimax all read and write the same book. In particular
the minimax **exact solver** can produce authoritative entries (exact value and
best moves) that upgrade another engine's statistical estimates wherever a
position is tractable to solve. See the research note for the planned
cooperation directions (a hybrid opening→endgame player, an exact-solver book
filler, eval-guided MCTS rollouts, and cross-engine move-agreement metrics).

## Tuning the weights (`tuning/`)

A full solve from the empty board is intractable in pure Python (~23.5M unique
canonical states cumulatively; `canonical_key()` scans all 192 symmetries, so
the open game runs at only a few hundred nodes/s — see `GAME_TREE_ANALYSIS.md`).
The tuner therefore samples positions that are already 8–12 plies in — where the
remaining tree is small and each exact solve is fast — and fits the weights to
the solver's verdict:

```bash
python tuning/build_dataset.py   # solver-labeled positions -> tuning/dataset.npz
python tuning/fit_weights.py     # logistic regression -> tuning/weights.json
```

The fit is deterministic (fixed seed + frozen sampling). Validation uses two
metrics, also reported by the benchmark: **sign-accuracy** (does `sign(evaluate)`
match the solver's win/loss verdict?) and **move-agreement** (does a shallow
eval-guided search pick the solver's move?). On the reference run the fit lifts
sign-accuracy from ~0.77 (seeded) to ~0.92 (fitted).

## Solving

`MinimaxEngine(MinimaxConfig(max_depth=16)).solve(state)` returns the exact
game-theoretic result for `state`. Because no Quantik game exceeds 16 plies,
every value is exact and every principal-variation leaf is a true terminal. A
forced win/loss scores `±(10_000 - plies_to_end)`, so the score encodes both the
outcome and its distance:

```python
from quantik_core import State, MinimaxEngine, MinimaxConfig

r = MinimaxEngine(MinimaxConfig(max_depth=16)).solve(
    State.from_qfen(".B.C/a.../.Ca./..d."))
assert r.score == 10_000 - 3   # side to move forces a win in 3 plies
```

Solving is fast only a few plies in; from the open game it is intractable in
pure Python (use the time-bounded `search` for directional evidence there).

## Benchmarks

`python examples/minimax_benchmark.py` reports four sections: playing strength
(vs random and MCTS), search performance (nodes/sec and alpha-beta/TT prune
ratios), solve correctness (exact anchors), and evaluation quality (seeded vs
fitted). See `examples/minimax_demo.py` for an annotated walkthrough.
