# Hybrid Opening→Endgame Player

`quantik_core.hybrid.HybridPlayer` combines an adaptive sampling engine
(MCTS or beam search) for the open game with the **exact** minimax solver
for the endgame — pairing each engine with the regime where it is
strongest.

## Why a handoff

A full solve from the empty board is intractable in pure Python (see
`docs/MINIMAX.md`'s "three depths" section: `canonical_key()` scans all 192
symmetries per call, so the open game runs at only a few hundred nodes/s).
But Quantik's branching shrinks sharply as pieces are placed — a position
with few empty cells has a small remaining tree that `MinimaxEngine.solve`
resolves exactly and fast. `HybridPlayer` samples (MCTS or beam) while the
tree is still wide, then switches to the exact solver once few enough
empty cells remain, sidestepping the open-game intractability wall
entirely instead of trying to search through it.

## Quick start

```python
from quantik_core import State
from quantik_core.hybrid import HybridPlayer, HybridConfig

move = HybridPlayer(HybridConfig()).select_move(
    State.from_qfen("A.b./..../..../....")
)
```

`search()` returns the fuller `HybridResult` (which engine was used, and
whether the move is exact) instead of just the move:

```python
result = HybridPlayer(HybridConfig()).search(state)
print(result.engine_used, result.exact, result.best_move)
```

## Configuration (`HybridConfig`)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `handoff_empty_cells` | int | 8 | At or below this many empty cells, use the exact solver; above it, use `opening_engine`. |
| `opening_engine` | str | `"mcts"` | `"mcts"` or `"beam"` — which engine drives play above the handoff threshold. |
| `mcts_config` | `MCTSConfig` | defaults | Used when `opening_engine="mcts"`. |
| `beam_config` | `BeamSearchConfig` | defaults | Used when `opening_engine="beam"`. |
| `minimax_config` | `MinimaxConfig` | `max_depth=16` | Used for the endgame handoff via `MinimaxEngine.solve()`. **`max_depth` and `time_limit_s` are ignored**: `solve()` unconditionally overrides both to guarantee an exact result (see `docs/MINIMAX.md`). `eval_config` is also never consulted there, since `solve()` never reaches the heuristic depth-cutoff. Only `use_alpha_beta`/`use_transposition_table`/`dedup_children`/`random_seed` actually affect the endgame handoff. |

### Tuning `handoff_empty_cells`

The default of **8** (i.e. handoff once 8+ pieces are placed) was chosen
because exact solves from that depth complete quickly — this repo's
measurements across several 8-empty-cell positions range from ~0.25s to
~1.3s. Raising the threshold hands off earlier (more exact play, since
minimax never misjudges a position the way a sampling engine's heuristic
can) but risks slower per-move latency as you approach the open game's
intractability wall; lowering it defers to the sampling engine longer
(faster moves, but no longer provably optimal near the boundary). The
handoff itself is a hard cutover by empty-cell count, not a smooth
blend — at or below the threshold, the exact solver decides every move.

### Choosing `opening_engine`

- **`"beam"`** (`BeamSearchEngine`) is deterministic given a seed, and any
  candidate that *survives* beam pruning is always followed all the way to
  a true terminal state (unlike MCTS's rollouts, which can stop at
  `max_depth` without resolving). This is not a guarantee of finding the
  objectively best line, though: `beam_width` pruning can discard a
  promising branch before it's explored deeply enough to reveal where it
  leads. See `docs/BEAM_SEARCH.md`.
- **`"mcts"`** (`MCTSEngine`) samples stochastically via UCB1. **Known
  limitation:** `CompactGameTree.create_root_node` currently marks the
  root node as fully expanded at creation instead of only once every
  legal move has a child, which can leave MCTS's root with a single
  explored child regardless of `max_iterations` — see `docs/MCTS.md`'s
  "Known limitation" note. When that happens, the opening move MCTS
  contributes is decided by move-generation order, not search quality.
  `opening_engine="beam"` does not share this limitation.

## API

```python
from quantik_core.hybrid import HybridPlayer, HybridConfig, HybridResult
```

- `HybridConfig` — see the table above.
- `HybridResult`: `best_move: Move`, `engine_used: "minimax" | "mcts" | "beam"`, `exact: bool`.
- `HybridPlayer(config)`:
  - `.select_move(state) -> Move`
  - `.search(state) -> HybridResult`

Module-only, matching `quantik_core.mcts` / `quantik_core.beam_search` —
import from `quantik_core.hybrid`, not the top-level `quantik_core` package.
