# Design: Classical alpha-beta search with handcrafted evaluation

**Date:** 2026-07-10
**Status:** Approved design — ready for implementation planning
**Branch:** feature branch off `main`, developed in an isolated git worktree

## 1. Goal & context

`quantik-core` already ships two search engines — `MCTSEngine` (UCB1, random
rollouts) and `BeamSearchEngine` — both built on `CompactGameTree`. It has **no
classical alpha-beta / minimax engine and no handcrafted static evaluation
function**. This work fills that gap: a deterministic, exact-on-a-small-tree
search with a reusable, tunable evaluation heuristic.

Quantik is a 4×4 game with at most 16 plies, a branching factor that shrinks
quickly, and a large symmetry group (D4 × S4 = 192). Those properties make
alpha-beta with iterative deepening, a transposition table, and move ordering a
natural fit — deep or even full search is feasible, and a full solve can serve
as an exact correctness anchor.

## 2. Non-goals (YAGNI)

- No wiring of the evaluation into MCTS rollouts (deferred; the eval is kept a
  pure function so this stays easy later).
- No neural networks, no search parallelism, no opening-book integration.

## 3. Architecture

Two new library modules plus benchmarks, tests, and docs. Follows the
established `*Config` dataclass + `*Engine` class pattern used by `mcts.py` and
`beam_search.py`.

```
src/quantik_core/
  evaluation.py   # EvalConfig + evaluate(bb, player, cfg) -> float   (pure, reusable)
  minimax.py      # MinimaxConfig + MinimaxEngine + MinimaxResult
examples/
  minimax_demo.py       # move selection, tactics, ID trace, mini-tournament
  minimax_benchmark.py  # the 3 benchmark categories (§7)
tests/
  test_evaluation.py
  test_minimax.py
docs/
  MINIMAX.md                                       # mirrors MCTS.md / BEAM_SEARCH.md
  research/2026-07-10-alpha-beta-eval-vs-mcts.md   # new dated paper (series preserved)
```

Public API additions exported from `quantik_core/__init__.py`:
`MinimaxEngine`, `MinimaxConfig`, `MinimaxResult`, `evaluate`, `EvalConfig`.

## 4. Evaluation function (`evaluation.py`)

`evaluate(bb, player, cfg) -> float` scores a **non-terminal** position from
`player`'s perspective (positive = good for `player`). The search layer owns
terminal scoring (§5); the eval is the depth-cutoff leaf heuristic.

### 4.1 Per-line analysis

Scan all 12 lines (`WIN_MASKS` = 4 rows + 4 columns + 4 zones). For each line
compute the **union of shapes present across both colors** (colors are
irrelevant to *winning*; a line wins when it holds all four distinct shapes):

- `present_shapes` = { s in 0..3 : (bb[s] | bb[s+4]) & mask != 0 }
- `occupied` = popcount of occupied cells on the line; `empty = 4 - occupied`

Classification:

| occupied | \|present\| | meaning |
|---|---|---|
| 4 | 4 | winning line — terminal, handled by search |
| any | < occupied | **dead** line (a shape is duplicated on it → can never hold 4 distinct) → contributes 0 |
| 3 | 3 | **live threat** — needs the one missing shape at the empty cell |
| 2 | 2 | building line (2 distinct) |
| 1 | 1 | 1 distinct |
| 0 | 0 | empty — neutral |

### 4.2 Threat terms (the directional signal, legality-aware)

For a live-threat line with missing shape `m` and empty cell `q`, a player `P`
can *legally* complete it iff **`P` still holds a copy of `m`** (count < 2) **and
placing `m` at `q` is legal for `P`** — i.e. the opponent does not already have
shape `m` on any line through `q`. (Reuse the existing move-legality logic:
`_is_move_legal_on_position` / a `WIN_MASKS`-through-`q` check.)

Scoring from `player`'s perspective, with `stm` = side to move:

- completable only by `player`  → `+cfg.threat_own`
- completable only by opponent  → `-cfg.threat_opp`
- completable by both           → `±cfg.threat_shared`, signed toward `stm` (tempo)
- completable by neither (dead threat) → 0

### 4.3 Tempo, mobility, and building potential

Colors matter in Quantik only through *legality*, so the durable directional
signal comes from threats plus tempo/mobility:

- **Mobility**: `cfg.mobility * (legal_moves(player) − legal_moves(opponent))`.
  Mobility matters because a player with no legal move loses.
- **Building potential**: small non-directional term for 2- and 1-distinct live
  lines, signed toward `stm`, weighted low (`cfg.build_two`, `cfg.build_one`) to
  break ties toward flexible development without overpowering threat terms.

`evaluate` returns the sum of §4.2 and §4.3.

### 4.4 `EvalConfig` defaults (all tunable)

```
win           = 10_000   # magnitude of a decided line (search assigns terminal ±)
threat_own    = 100
threat_opp    = 100
threat_shared = 20
mobility      = 3
build_two     = 2
build_one     = 0
```

### 4.5 Symmetry invariance (exact test anchor)

The board symmetry group is **D4 × S4 = 8 × 24 = 192, with no color/player
swap** (confirmed against the beam-search orbit counts). The eval treats every
line and every shape uniformly and reads side-to-move from piece counts (a
symmetry-invariant quantity), so **symmetric boards must score identically**.
This is asserted as a test: for random states, `evaluate` is constant across all
symmetric variants of the board. This invariance is also what makes the
transposition table (§5) sound.

## 5. Minimax engine (`minimax.py`)

### 5.1 Search

- **Negamax with alpha-beta pruning.** Value is from the side-to-move's
  perspective.
- **Iterative deepening** to `max_depth` (bounded by ≤16 plies) or until
  `time_limit_s` elapses; each iteration seeds move ordering with the previous
  iteration's principal variation and records the new PV.
- **Terminal detection uses `has_winning_line`, not `check_game_winner`.** A
  winning line at a node means the *previous* mover completed it, so the
  side-to-move value is `-(win − ply)` — depth-adjusted so faster wins score
  higher. Using `has_winning_line` deliberately sidesteps the known
  `check_game_winner` turn-balance edge case. "No legal moves" ⇒ side-to-move
  loses ⇒ `-(win − ply)`.
- **Depth cutoff** ⇒ `evaluate(bb, side_to_move, eval_config)`.

### 5.2 Transposition table

Keyed by `state.canonical_key()`, storing `(depth, value, bound_flag)` where
`bound_flag ∈ {EXACT, LOWER, UPPER}`. Sound because (a) the value is
symmetry-invariant (§4.5) and (b) side-to-move is determined by piece counts,
also invariant. **The TT caches value/bound only — not a best move**: a stored
move would be in the wrong orientation for a symmetric sibling. Move ordering
comes from the concrete-orientation PV instead. Toggled by
`use_transposition_table`.

### 5.3 Move ordering & child dedup

Ordering: PV move first → immediate winning moves → shallow heuristic (e.g.
threat count of the resulting state). Optional `dedup_children`: collapse
sibling moves that lead to the same `canonical_key()` (search one representative;
at the root keep a concrete move to return), shrinking the effective branching
factor.

### 5.4 Config & result

```
MinimaxConfig:
  max_depth: int = 16
  time_limit_s: float | None = None
  use_alpha_beta: bool = True
  use_transposition_table: bool = True
  dedup_children: bool = True
  eval_config: EvalConfig = EvalConfig()
  random_seed: int | None = None   # deterministic tie-break among equal-value moves

MinimaxResult:
  best_move: Move
  score: float
  depth_reached: int
  nodes: int          # nodes visited
  pv: list[Move]      # principal variation
  elapsed: float
```

## 6. Public API

Add the five names in §3 to `quantik_core/__init__.py` `__all__`, mirroring how
`mcts` / `beam_search` symbols are surfaced (engine classes are imported from
their module; `MCTSEngine` today is imported via `quantik_core.mcts`, so match
whatever the repo's current convention is for engines vs. top-level exports).

## 7. Benchmarks (`examples/minimax_benchmark.py`)

Three categories, all three requested:

1. **Playing strength** — head-to-head win rates over N games: minimax vs a
   random mover, and minimax vs `MCTSEngine`, each as player 0 and player 1.
   Output a win table.
2. **Search performance** — nodes/sec; node counts and prune ratio with
   alpha-beta on/off and TT on/off; depth reached under a time budget;
   time-to-move by ply.
3. **Solve correctness** — full-depth alpha-beta from the empty board;
   confirm Quantik's first-player-win result; report nodes, time, and the
   perfect-play PV.

Recorded numbers land in the research paper (§9).

## 8. Testing strategy (TDD, exact anchors)

- **Evaluation**: dead-line (duplicated shape) scores 0; 3-distinct line is
  detected as a live threat with correct completable-by attribution; threat
  legality respects opponent-blocking and pieces-in-hand; perspective sign-flip
  (`evaluate(bb, p)` == `-evaluate(bb, 1-p)` up to the tempo term's definition —
  pin the exact identity during implementation); **symmetry invariance** across
  all 192 variants for random states.
- **Minimax**: finds mate-in-1 on crafted QFEN positions; blocks an opponent
  mate-in-1; **alpha-beta value ≡ plain-minimax value** on fixed positions;
  **TT-on value ≡ TT-off value**; iterative deepening to depth `d` ≡ fixed-depth
  `d`; partial/full solve matches known results, anchored to
  `GAME_TREE_ANALYSIS.md` counts where applicable.
- Quality gates: `./auto-lint.sh`, `./dev-check.sh`, ≥90% coverage.

## 9. Documentation deliverables

- `docs/MINIMAX.md` — usage/reference mirroring `docs/MCTS.md` and
  `docs/BEAM_SEARCH.md`; update `docs/EXAMPLES.md` and the README examples table.
- `docs/research/2026-07-10-alpha-beta-eval-vs-mcts.md` — a **new** dated paper
  in the incremental research series (never rewrite an earlier paper). A
  self-contained design note explaining the evaluation heuristic, the
  alpha-beta/TT/ID machinery, the symmetry-soundness argument, and the measured
  benchmarks (§7) — written to be clearly explanatory as standalone material.

## 10. Execution / orchestration model

Per repo convention (`AGENTS.md`): opus orchestrates and reviews; sonnet
implements.

- **Implementation subagent(s) (sonnet)** — build `evaluation.py`, `minimax.py`,
  tests, examples, and library docs under TDD, running the quality gates.
- **Review subagent (opus)** — empirical review: verify the alpha-beta≡minimax
  and TT≡no-TT equivalences, the symmetry-invariance anchor, and the solve
  result actually hold; scrutinize sign/indexing-critical logic.
- **Documentation subagent** — collect the concrete design decisions, the
  soundness arguments, and the measured benchmark numbers into
  `docs/research/2026-07-10-alpha-beta-eval-vs-mcts.md` as a clear, standalone
  design note.

All work occurs on a feature branch in an isolated git worktree; final PR to
`main`.
