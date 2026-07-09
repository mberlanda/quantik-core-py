# Bounded-Memory Beam Search over Canonical Game Trees: Design and an Empirical Comparison with UCT on Quantik

*Working paper — quantik-core, July 2026. Prepared as ground material for a
forthcoming article; numbers are reproducible from the scripts in the
appendix.*

## Abstract

We describe the design, implementation, and empirical evaluation of a
parametrizable beam search engine for Quantik, a 4×4 adversarial placement
game whose raw game tree contains ≈2.24 × 10¹² legal move sequences. The
engine combines three ideas: (i) a symmetry-reduced *canonical* state
representation that collapses rotations, reflections, and piece
substitutions (reduction factors of 21× to 1.2 × 10⁵× per ply); (ii) a
level-synchronous beam frontier with a per-depth width schedule, which makes
*exhaustive* enumeration of the shallow game affordable while sampling the
deep game under a fixed budget; and (iii) *path-multiplicity accounting*,
which restores the raw-line mass hidden by canonicalization so that branch
statistics weight each canonical line by the number of concrete games it
represents. We compare against the existing UCT (Monte Carlo Tree Search)
engine sharing the same 64-byte compact node storage. On commodity hardware
the beam engine resolves the full game (terminal frontier at every line) from
the empty board in ~1–15 s using under 0.4 MB of tree memory, while UCT at
matched wall-clock budgets concentrates its tree asymmetrically and does not
guarantee a terminal frontier. We derive a practical cost model
(evaluations at level *d+1* ∝ width(*d*) × branching × rollouts), give
tuning recipes, and validate the multiplicity accounting against exact
combinatorial ground truth from an independent full-tree enumeration.

## 1. Introduction

Quantik is a two-player, perfect-information, zero-sum placement game: each
player owns two pieces of each of four shapes and places them on a 4×4
board; a player wins by completing a row, column, or 2×2 zone containing
all four *shapes* (regardless of owner); it is illegal to place a shape in a
row/column/zone where the *opponent* already placed that shape. A player
with no legal move loses. Games therefore last at most 16 plies.

Despite the small board, the raw tree is large: an exact depth-wise
enumeration (see `GAME_TREE_ANALYSIS.md` in this repository) counts
2,235,929,747,584 legal move sequences, of which only 23,577,899 distinct
*canonical* states remain after symmetry reduction through depth 8.

The repository's existing search engine is a UCT-style Monte Carlo Tree
Search (`quantik_core.mcts.MCTSEngine`). UCT is a strong anytime algorithm,
but for two of our goals it is an awkward fit:

1. **Reaching the end of the game.** UCT grows its tree one node per
   iteration along the UCB-selected path. Coverage of terminal positions in
   the *persistent tree* is incidental — playouts do reach terminals, but
   their outcomes are aggregated into noisy value estimates rather than
   materialized as explicit end-of-game lines with reconstructible move
   sequences.
2. **Predictable, bounded resource use.** The shape of a UCT tree depends on
   the stochastic playouts; neither its depth profile nor its node count at
   a given depth is controlled directly.

Beam search inverts these trade-offs: it advances a whole frontier one ply
at a time, prunes to a configured width with an evaluation function, and
therefore reaches depth *D* (here, the true terminal frontier at *D* ≤ 16)
with *O*(width × *D*) memory and a fully deterministic budget, at the price
of irrevocable pruning (no backtracking past a level) and dependence on the
evaluator's quality.

This paper documents the implementation in `quantik_core.beam_search`,
its parametrization, the symmetry-multiplicity statistics, and a controlled
comparison with the UCT engine.

## 2. Background

### 2.1 State space and symmetry

The canonical representation collapses three group actions:

1. **Board symmetries** — the dihedral group of the square (rotations and
   reflections, |D₄| = 8);
2. **Shape substitution** — any permutation of the four shapes (|S₄| = 24),
   since the rules are shape-agnostic;
3. **(Implementation-defined) canonical ordering** — `State.canonical_key()`
   selects a unique representative of each orbit.

Depth-wise effect (excerpt from the exact enumeration):

| Depth | Raw move sequences | Unique canonical | Reduction |
|------:|-------------------:|-----------------:|----------:|
| 1 | 64 | 3 | 21.3× |
| 2 | 3,392 | 51 | 66.5× |
| 3 | 167,552 | 726 | 230.8× |
| 4 | 6,776,960 | 10,946 | 619.1× |
| 5 | 231,883,776 | 105,632 | 2,195× |
| 6 | 6,241,600,512 | 901,916 | 6,920× |
| 7 | 1.32 × 10¹¹ | 4,658,465 | 28,422× |
| 8 | 2.10 × 10¹² | 17,900,160 | 117,153× |

Two consequences drive the design. First, the shallow game is *tiny* in
canonical space — exhaustive search through ply 3 needs only 726 frontier
states. Second, canonical classes have *unequal orbit sizes* (already at
ply 1: the three classes — corner, edge, and center placements — represent
16, 32, and 16 raw moves respectively), so statistics computed over
canonical representatives are biased unless re-weighted (§3.4).

### 2.2 Compact storage

Both engines share `CompactGameTree`: nodes are packed into 64-byte rows of
a contiguous NumPy array (18-byte packed state, tree topology, win/visit
counters, a 32-bit `multiplicity` field, flags, and values), with a
transposition dictionary keyed on the literal 18-byte packed state at a
given depth. Note the storage's transposition key is *not* symmetry-reduced;
symmetry reduction happens in the search layers that feed it. States
themselves serialize to 18 bytes (`State.pack()`), so a million-node tree
occupies ~64 MB of node storage before dictionary overhead.

## 3. Method

### 3.1 Algorithm

Search proceeds level-synchronously from a validated non-terminal root
(frontier = {root}, multiplicity 1). For each depth *d* = 1…`max_depth`:

```
for each frontier entry (state, moves, multiplicity):
    if the mover has no legal move:            # blocked-player-loses rule
        record terminal leaf (value ±1)         # opponent of mover wins
        continue
    for each legal move m:
        child = apply(state, m)
        if child is terminal (four shapes in a line/zone):
            record terminal leaf; insert into tree with terminal flags
        else:
            k = canonical_key(child)
            if k unseen this level: candidates[k] = (child, moves+m, mult)
            else:                   candidates[k].multiplicity += mult
score each candidate with the evaluator (value in [-1,1], P0 perspective)
rank from the perspective of the player who just moved
keep the top width(d) candidates; insert ONLY survivors into the tree
survivors become the next frontier
```

Termination: frontier empty (every line resolved to a terminal) or
`max_depth` reached; remaining frontier entries are reported as
non-terminal leaves. Every leaf carries its full move sequence from the
root, so principal variations are replayable without storing edge moves in
the 64-byte nodes.

Three details matter for correctness:

- **Terminals bypass the beam.** Every terminal child of the frontier is
  recorded regardless of width — the beam bounds only the *live* frontier.
- **Mover-relative pruning.** Candidates at one level all share the same
  mover (Quantik has strict alternation); ranking negates the P0-perspective
  value when the mover is P1. This keeps the frontier adversarially
  sensible: each level keeps the replies its own mover prefers. Final
  results are then re-oriented to the *root* player's perspective. Both sign
  conventions are pinned by mutation-verified regression tests (§5.3).
- **Evaluate-then-insert.** Candidates are scored *before* tree insertion;
  pruned candidates never allocate a node. This is what makes the memory
  bound structural rather than aspirational.

### 3.2 Parametrization and the width schedule

`BeamSearchConfig` exposes: `beam_width` (flat width), `beam_schedule`
(per-depth widths, last entry extending to deeper levels), `max_depth`
(≤ 16), `rollouts_per_candidate`, `random_seed` (private RNG; the engine
never touches global random state), and a pluggable
`evaluator: State → [-1, 1]` (default: mean of seeded uniform random
playouts, which in Quantik always reach a true terminal within 16 plies —
no truncation heuristic is needed).

The cost model is dominated by evaluation:

> evaluations at level *d+1* ≈ min( width(*d*) × branching(*d*),
> unique(*d+1*) )   with branching ≈ 40–60 in the early midgame,

and each default evaluation costs `rollouts_per_candidate` playouts. A flat
width therefore *cannot* express the natural strategy for Quantik —
"enumerate the small shallow game exhaustively, then sample" — because the
width needed for exhaustiveness at ply 3 (726) would multiply the cost of
every deeper level by an order of magnitude. The schedule expresses it
directly, e.g. with the exported `UNIQUE_CANONICAL_STATES_PER_DEPTH`
constant:

```python
schedule = [3, 51, 726] + [64]   # exhaustive through ply 3, width-64 tail
```

By construction, levels whose width meets or exceeds the canonical count
prune nothing; the search below an exhaustive prefix is a *complete* summary
of the game to that depth.

### 3.3 Result statistics: from optimistic leaves to ranked options

`search()` returns every terminal leaf discovered plus the surviving
frontier, each with value, depth, and move sequence. Two derived views:

- **`best_leaf`** — the single leaf with the best root-perspective value.
  This is deliberately *optimistic*: it answers "what is the best confirmed
  end-of-game line found?", assuming the opponent follows that line. In
  our experiments it is almost always a fastest-possible win (ply 5 from
  the empty board), because the beam records every terminal it passes.
- **`ranked_root_moves(top_k)`** — aggregates all leaves by their first
  move, reporting per option the best and mean leaf value (root
  perspective), a win-probability rescaling of the mean, support counts,
  and whether a confirmed terminal win exists via that move. These are
  beam-sampled statistics, not minimax-proven values, and are documented as
  such.

### 3.4 Symmetry multiplicity: putting the orbits back

Canonical deduplication is essential for coverage but distorts statistics:
a canonical line "one corner A, then …" stands for 16 raw openings while
"one edge A, then …" stands for 32. Counting leaves equally over-weights
small orbits.

We restore the mass by *path-count accumulation*: the root carries weight 1;
every raw legal move contributes its parent's weight to its canonical child;
merges during per-level dedup *add* weights instead of discarding the
duplicate. A leaf's `multiplicity` is then exactly the number of raw move
sequences it represents, and `ranked_root_moves` weights its means by it.
The tree's per-node `multiplicity` field receives the same quantities.

Multiplicity is exact wherever the schedule is exhaustive and a lower bound
below pruned levels (pruned branches' mass is invisible — an inherent
property of any beam). Pruning itself remains value-based and unweighted;
multiplicity is a *statistics* channel, not a search heuristic.

This accounting admits unusually strong tests, because an independent exact
enumeration of the game exists: with an exhaustive schedule and a constant
evaluator, the summed frontier multiplicities must reproduce the raw
sequence counts of §2.1 *exactly* — [16, 16, 32] at ply 1 (Σ = 64), 3,392 at
ply 2, 167,552 at ply 3, and exactly 6,912 P1-winning sequences among ply-4
terminals. The unit-test suite asserts these equalities.

## 4. Relationship to prior work

The ingredients are classical: beam search as breadth-limited best-first
search; UCT as the reference MCTS variant (Kocsis & Szepesvári, 2006);
symmetry reduction via canonical forms is standard in combinatorial game
analysis; progressive widening and beam-MCTS hybrids address related
budget-shaping concerns inside MCTS itself. The contribution here is an
engineering synthesis and measurement on a concrete, exactly-enumerable
domain: a beam whose width schedule aligns with known canonical-space sizes,
whose statistics are made orbit-correct by path multiplicity, and which
shares its node store with a UCT engine for direct comparison — plus
mutation-verified tests anchored to exact combinatorial ground truth.

## 5. Experimental evaluation

### 5.1 Setup

- Hardware/software: Apple Silicon (macOS, arm64), CPython 3.14, pure-Python
  engines (NumPy used for node storage, not for search logic).
- Root: empty board; `max_depth = 16`; seeds {0, 1, 2} per configuration.
- Beam grid: width ∈ {4, 16, 64} × rollouts ∈ {2, 8}, flat widths (the
  schedule feature is evaluated separately in §5.4).
- UCT: iterations ∈ {2,000, 10,000, 25,000}, default exploration weight
  √2, same seeds; wall-clock budgets bracket the beam runs.
- Metrics: wall time, evaluator calls, candidates generated/deduped/pruned,
  tree nodes inserted, allocated tree memory, terminal leaves discovered,
  frontier resolution (did every line reach a terminal?), and best-root-move
  agreement across seeds.

### 5.2 Beam search results (flat widths)

Median over 3 seeds; "term. leaves" is the count of distinct terminal lines
materialized with full PVs.

| width | rollouts | time (s) | evaluations | term. leaves | nodes | memory (MB) | resolved |
|------:|---------:|---------:|------------:|-------------:|------:|------------:|:--------:|
| 4 | 2 | 1.2 | ~670 | 28–62 | ~90 | 0.25 | 3/3 |
| 4 | 8 | 4.3 | ~665 | 14–45 | ~70 | 0.25 | 3/3 |
| 16 | 2 | 5.6 | ~2,540 | 186–231 | ~390 | 0.26 | 3/3 |
| 16 | 8 | 17.2 | ~2,740 | 117–179 | ~335 | 0.26 | 3/3 |
| 64 | 2 | 15.3 | ~9,920 | 667–774 | ~1,450 | 0.30 | 3/3 |
| 64 | 8 | 57.5 | ~9,860 | 403–566 | ~1,250 | 0.30 | 2/3 |

Observations:

1. **Full-game reachability is routine.** Even width 4 resolves every line
   to a true terminal from the empty board in ~1 s. (The single unresolved
   width-64/rollouts-8 run had a live frontier remaining exactly at ply 16.)
2. **Memory is not the constraint.** All configurations stay near the
   initial 0.25 MB allocation; node counts (~10²–10³) are dwarfed by the
   capacity. Time — almost entirely evaluator playouts — is the budget.
   Wall time scales ≈ linearly in width × rollouts, at ~0.9–1.1 ms per
   2-rollout evaluation.
3. **Terminal yield scales ~linearly with width** (≈ 60 → 200 → 720 lines
   at rollouts = 2).
4. **`best_leaf` saturates.** Every run finds a value-+1.0 terminal at ply
   5 — the earliest ply at which first-player wins exist (§2.1). Selecting
   *among* root moves by `best_leaf` is therefore noise-driven; ranked,
   multiplicity-weighted means are the appropriate signal (§3.3–3.4).
5. **More rollouts did not stabilize the root choice at these scales**
   (seed agreement did not improve from rollouts 2 → 8) — consistent with
   the root of Quantik being far from decided, and with variance reduction
   (σ ≈ 1/√n per candidate) being spent where value gaps are smaller than
   the remaining noise. Given time ∝ width × rollouts, width (coverage)
   is the better marginal purchase for scenario exploration; rollouts
   matter when *ranking* survivors of a narrowed decision.

### 5.3 Verification methodology

Beyond conventional unit tests (35 at the time of the flat-width benchmark;
grown since with the schedule and multiplicity suites), correctness-critical
properties are *mutation-verified*: the reviewer or implementer flips the
specific sign or drops the specific term (mover-relative pruning sign;
root-perspective negation in ranked statistics; weighted vs. unweighted
means; schedule depth indexing) and confirms that exactly the pinning test
fails, then restores. The multiplicity suite is additionally anchored to
exact enumeration ground truth (§3.4). The full gate (446+ tests, ≥90%
coverage, mypy, flake8, packaging) runs per commit.

### 5.4 UCT comparison

Same root, same node storage, default UCT parameters, seeds {0, 1, 2}.

Ranges over 3 seeds; "used" memory is node_count × 64 B (the engine
pre-allocates a 100,000-node capacity, ≈6.4 MB, reported separately).

| iterations | time (s) | nodes | max tree depth | terminal nodes in tree | memory used / alloc (MB) | best-move agreement |
|-----------:|---------:|------:|---------------:|-----------------------:|------------:|:-------------------:|
| 2,000 | 9.4–10.3 | ~1,770 | 5–6 | 0 | 0.11 / 6.3 | 3/3 |
| 10,000 | 58–61 | ~8,590 | 6 | 0 | 0.55 / 6.6 | 3/3 |
| 25,000 | 152–164 | ~21,370 | 7 | 0–4 | 1.37 / 7.1 | 3/3 |

Observed throughput was ~150–210 iterations/s from the empty board (each
iteration includes a full random playout). Three findings:

1. **Terminal coverage is negligible.** UCT's persistent tree reaches at
   most ply 7 after 25,000 iterations (~2.5 min) and materializes 0–4
   terminal nodes; the width-4 beam materializes dozens of complete
   terminal lines in ~1 s, the width-64 beam ~700 in ~15 s. For scenario
   enumeration and endgame reachability, the beam is the right tool by
   orders of magnitude.
2. **Root-move choice is UCT's strength.** All nine UCT runs agree on the
   same opening move with a tight value estimate (win probability
   0.46–0.50), across a 12× budget range — *more* stable than the beam's
   seed-sensitive root preference (§5.2, obs. 5). UCB's adaptive
   reallocation is doing exactly what it is designed for.
3. **Value calibration differs.** UCT's root estimate hovers near 0.49 —
   a visit-weighted average acknowledging the root is far from decided —
   while the beam's `best_leaf` saturates at +1.0 (best-case line). The
   beam's multiplicity-weighted mean statistics (§3.4) are the comparable
   quantity, not `best_leaf`.

Structural comparison:

| Property | Beam (this work) | UCT (`MCTSEngine`) |
|---|---|---|
| Depth profile | uniform frontier per ply, guaranteed to `max_depth`/terminals | asymmetric; deep only where UCB concentrates |
| Terminal lines | materialized with replayable PVs, all encountered terminals kept | implicit in playout statistics; tree terminals incidental |
| Memory | *O*(width × depth) structural bound, evaluate-then-insert | one node per iteration along selected path |
| Budget shape | deterministic per level (width × branching × rollouts) | anytime; stop whenever |
| Value estimates | evaluator applied once per surviving candidate | visit-averaged, improves with iterations at visited nodes |
| Symmetry usage | canonical dedup per level + exact multiplicity weights | canonical dedup among siblings at expansion |
| Failure mode | evaluator misranks → good line pruned irrevocably | insufficient iterations → shallow, high-variance tree |
| Best use | coverage: scenario enumeration, endgame reachability, book building | move choice at a single position under a time budget |

The engines compose rather than compete: they share `CompactGameTree`, so a
beam pass can seed the transposition structure (terminal flags, values,
multiplicities) that a subsequent UCT run exploits — with the caveat, noted
in the code, that the current tree hard-codes a player-0-to-move root.

### 5.5 Coverage: what does a width "buy"?

Fraction of unique canonical states a width-*W* level can retain:

| W \ depth | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|
| 4 | 1.00 | 0.08 | 0.006 | 0.0004 | — |
| 16 | 1.00 | 0.31 | 0.022 | 0.0015 | — |
| 64 | 1.00 | **1.00** | 0.088 | 0.006 | 0.0006 |
| 256 | 1.00 | 1.00 | 0.35 | 0.023 | 0.002 |
| 1,024 | 1.00 | 1.00 | **1.00** | 0.094 | 0.010 |

Practical schedule recipes (measured ~1 ms per 2-rollout evaluation):

- `[3, 51, 726] + [64]` — exhaustive through ply 3, sampled tail:
  the expensive step is evaluating ≈10⁴ ply-4 candidates; ~20–30 s total.
- `[3, 51, 726, 10946] + [64]` — exhaustive through ply 4: ~10⁵
  evaluations at ply 5; minutes. Suitable for offline analysis and book
  generation. Node storage at ply 4 is 10,946 × 64 B ≈ 0.7 MB — memory
  remains a non-issue.
- Exhaustive ply 5 (105,632 states) is the practical ceiling for the
  pure-Python rollout evaluator (~hour); beyond it, replace the evaluator
  (cheap heuristic, or rollouts = 1 on wide levels and more only on the
  final level) rather than shrinking the prefix.

## 6. Limitations and threats to validity

- **Evaluator quality bounds line quality.** With few random rollouts the
  frontier wanders; reported values are noisy estimates, and `best_leaf` is
  best-case, not minimax. No claim of playing strength is made — no
  engine-vs-engine matches were run (future work).
- **Pruning loses mass.** Below the exhaustive prefix, multiplicities are
  lower bounds and rankings are conditional on beam visibility.
- **Single machine, wall-clock timing, pure Python.** Absolute times are
  indicative; the *ratios* (time ∝ width × rollouts; memory flat) are the
  robust findings.
- **Root-position bias.** The empty board maximizes symmetry collapse;
  midgame roots have smaller orbits and larger effective branching per
  canonical state.
- **Draw handling.** Quantik as modeled has no draws (a blocked player
  loses); the value scale conflates "unknown" (0 from mixed rollouts) with
  genuinely balanced.

## 7. Applications: toward opening books

The repository ships an SQLite-backed `OpeningBookDatabase` keyed by
canonical states, with per-position win statistics and parent/child edges.
Beam search with an exhaustive prefix is a natural book *generator*:

1. Run with schedule `[3, 51, 726, 10946]` (exhaustive plies 1–4, exact
   multiplicities) and a meaningful rollout budget on the tail.
2. Export each frontier/terminal node: canonical key, depth, value
   statistics, multiplicity, and the PV edges → `add_position`/`add_edges`.
3. Defence lines fall out of the same data: because pruning is
   mover-relative, the surviving replies at odd/even levels are precisely
   the strongest options *for the side to move*; `ranked_root_moves` at any
   book position yields graded recommendations with support counts.

Persistence of the beam tree itself is deliberately out of scope: the
`CompactGameTree` is an in-memory working set (contiguous NumPy rows —
trivially dumpable, but without stable semantics across runs), while the
opening book is the durable, queryable artifact. The 18-byte packed state
and the multiplicity field are the bridge between the two.

## 8. Future work

Engine-vs-engine strength evaluation (beam-seeded UCT vs. plain UCT);
learned or handcrafted evaluators to push exhaustive-equivalent quality
past ply 5; beam-tree → opening-book exporter (§7); multiplicity-aware
*pruning* (e.g., width in raw-mass rather than canonical count);
draw/uncertainty separation in the value scale; removing the
player-0-root restriction from the shared tree.

## References

- L. Kocsis, C. Szepesvári. *Bandit based Monte-Carlo Planning.* ECML 2006
  (UCT).
- C. Browne et al. *A Survey of Monte Carlo Tree Search Methods.* IEEE
  TCIAIG 4(1), 2012.
- R. Coulom. *Efficient Selectivity and Backup Operators in Monte-Carlo Tree
  Search.* CG 2006.
- P. S. Ow, T. E. Morton. *Filtered beam search in scheduling.* IJPR 26(1),
  1988 (beam search formalization).
- This repository: `GAME_TREE_ANALYSIS.md` (exact enumeration),
  `SYMMETRY_REDUCTION_DEMONSTRATION.md`, `docs/MCTS.md`,
  `docs/BEAM_SEARCH.md`, design spec
  `docs/superpowers/specs/2026-07-07-beam-search-design.md`.

## Appendix: reproducibility

- Engines: `quantik_core.beam_search.BeamSearchEngine`,
  `quantik_core.mcts.MCTSEngine` (this branch: `feat/mcts-beam-search`).
- Beam sweep: widths {4, 16, 64} × rollouts {2, 8} × seeds {0, 1, 2},
  `max_depth=16`, root `..../..../..../....`; metrics from
  `BeamSearchResult.stats` and `get_statistics()`.
- UCT sweep: iterations {2,000, 10,000, 25,000} × seeds {0, 1, 2}; tree
  depth/terminal profiles scanned from `CompactGameTreeStorage.node_data`
  (depth at bytes 22–24, flags at byte 25).
- Exact anchors: unit tests in `tests/test_beam_search.py` (multiplicity
  sums vs. enumeration; mutation-verified sign/weighting properties).
- Demo: `examples/beam_search_demo.py`.
