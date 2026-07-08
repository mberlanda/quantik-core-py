# Budget Shaping in Quantik Search: Per-Depth Schedules versus Simulation Truncation

*Working paper #2 — quantik-core, 2026-07-08. Follows
[2026-07-07-beam-search-vs-mcts.md](2026-07-07-beam-search-vs-mcts.md);
part of an incremental series preserving the design conversation. This note
motivates and specifies the per-depth rollout schedule, contrasts it with
the UCT engine's simulation-truncation parameter, and explains how the two
engines' budget-shaping knobs compose.*

## 1. The problem: one budget, two competing uses

A search budget buys two different goods:

- **Coverage** — how many distinct scenarios (canonical branches) are kept
  alive per ply;
- **Precision** — how accurately each kept scenario is valued.

For the default rollout evaluator, total cost decomposes per level:

> cost ≈ Σ_d  evaluations(*d*) × rollouts(*d*) × cost_per_playout,
> with evaluations(*d*) ≈ min( width(*d−1*) × branching, unique(*d*) ).

The companion paper established the coverage side: Quantik's canonical
space is tiny through ply 3 (3 / 51 / 726 states) and explodes afterwards,
so `beam_schedule` buys *exhaustive* shallow coverage cheaply — e.g.
`[3, 51, 726] + [64]` at roughly 20–30 s with 2-rollout evaluations
(~10⁴ ply-4 candidate evaluations dominating), and `[3, 51, 726, 10946] +
[64]` in minutes (~10⁵ ply-5 evaluations). Exhaustive ply 5 (105,632
states) marks the practical pure-Python ceiling, on the order of an hour.

What a width schedule alone *cannot* express is the precision side of the
trade. With a flat `rollouts_per_candidate`, every level pays the same
per-candidate evaluation price — but the wide, exhaustive levels do not
need precise values at all (nothing is pruned there: when width ≥ canonical
count, the evaluator's ranking is irrelevant to survival), while the narrow
tail, where pruning actually bites, benefits from every additional rollout
(per-candidate noise σ ≈ 1/√n for ±1 playout outcomes).

## 2. `rollout_schedule`: wide-and-cheap early, narrow-and-precise late

We therefore add the precision twin of `beam_schedule`:

```python
BeamSearchConfig(
    beam_schedule=[3, 51, 726, 64],   # exhaustive plies 1–3, width-64 tail
    rollout_schedule=[1, 1, 1, 8],    # 1 playout on exhaustive levels,
)                                     # 8 on the pruned tail (last extends)
```

Semantics mirror `beam_schedule`: entry *i* applies at depth *i + 1*; the
last entry extends to all deeper levels; `None` falls back to the flat
`rollouts_per_candidate`. The schedule affects only the built-in rollout
evaluator — a custom `evaluator: State → [-1, 1]` owns its own cost model
and ignores it. A `stats["rollouts"]` counter exposes the exact number of
playouts performed, which both makes the budget observable and admits an
exact regression test: with `beam_schedule=[3, 51]`, `max_depth=2`,
`rollout_schedule=[1, 5]`, exactly 3×1 + 51×5 = 258 playouts must occur —
any depth-indexing error produces a different integer.

Cost illustration for the exhaustive-ply-3 recipe (measured ~0.5 ms per
single playout): flat 8 rollouts ≈ (3 + 51 + 726 + ~10⁴ + tail) × 8
playouts, dominated by ~8×10⁴ playouts at ply 4; scheduled `[1, 1, 1, 8]`
pays ~10⁴ playouts at ply 4 — the same exhaustive coverage and the same
tail precision for roughly an eighth of the dominant term. The general
recipe: **spend width wherever unique(*d*) is affordable, spend rollouts
only where pruning decisions are made.**

## 3. The UCT engine's "drop-out": `MCTSConfig.max_depth`

The existing UCT engine has the truncation parameter the reader may recall:
`MCTSConfig.max_depth` (default 16). Its `_simulate` plays uniformly random
moves from the selected node and stops early when the *absolute* ply count
reaches `max_depth`, returning 0.0 — a neutral, draw-like value — for
unresolved playouts.

Three properties are worth spelling out:

1. **At the default 16 it never triggers.** Quantik games end by ply 16
   at the latest (blocked player loses; a full board blocks the mover), so
   `max_depth=16` means playouts always reach a true terminal — same as the
   beam engine's evaluator, which needs no cutoff at all.
2. **Below 16 it is a simulation drop-out, and it biases.** Truncated
   playouts inject 0.0 into the visit-averaged values, pulling estimates
   toward "balanced" in exactly the deep regions where truncation fires
   most. The bias is silent: nothing in the result distinguishes "genuinely
   contested" from "unresolved because we stopped simulating."
3. **The beam analogue is explicit, not silent.** The beam's `max_depth`
   bounds *frontier advancement*, and unresolved lines are returned as
   first-class `frontier_leaves` with their evaluated values and full move
   sequences — the caller sees precisely which scenarios were left open.
   (`reached_terminal` summarizes it.) This observability difference, not
   the cutoff itself, is the substantive contrast.

(One housekeeping note for completeness: `MCTSConfig.use_transposition_table`
is declared but not consulted by the current engine implementation; the
transposition behavior actually in effect is the storage-level merge in
`CompactGameTree.add_child_node`.)

## 4. How the knobs line up

| Concern | Beam engine | UCT engine |
|---|---|---|
| Breadth per ply | `beam_schedule` / `beam_width` (hard, deterministic) | emergent from UCB visit allocation (soft) |
| Evaluation precision | `rollout_schedule` / `rollouts_per_candidate` per *candidate* | one playout per iteration; precision accrues at *visited* nodes over iterations |
| Horizon | `max_depth` bounds the frontier; leftovers reported explicitly | `max_depth` truncates playouts; leftovers folded into values as 0.0 |
| Budget unit | playouts, exactly countable ex ante (`stats["rollouts"]`) | iterations, anytime-interruptible |
| Where noise hurts | misranking at pruned levels (irrevocable) | under-visited subtrees (recoverable with more iterations) |

The deeper duality: UCT *adapts* its breadth/precision split online via UCB
— which is optimal when the budget must be spent at a single decision point
— while the beam fixes the split *structurally* via schedules — which is
what you want when the goal is reproducible, quantified coverage of the
scenario space (exhaustive prefixes, exact multiplicity mass, materialized
terminal lines).

## 5. Fitting the two approaches together

Empirically (companion paper, §5.4): at matched budgets from the empty
board, UCT concentrates ~2×10³–2×10⁴ nodes within plies ≤ 6–7 and
materializes essentially no terminals (first ones appear around 25k
iterations, ~150 s), while the beam resolves the full game in seconds but
with a noisier root preference. That suggests composition patterns rather
than a choice:

1. **Beam-seeded UCT (shared tree).** Run a scheduled beam pass first —
   exhaustive prefix, multiplicity-weighted statistics, terminal flags —
   into the shared `CompactGameTree`; then let UCT refine the root decision
   over a structure that already knows where the terminals are. (Current
   restriction: the shared tree assumes a player-0-to-move root.)
2. **UCT as the beam's evaluator.** The `evaluator` hook accepts any
   `State → [-1, 1]`; a small fixed-iteration UCT probe per candidate
   trades the rollout schedule for adaptive per-candidate precision.
   Costly, but expressible today without engine changes.
3. **Beam for the book, UCT for the move.** Offline: scheduled beam passes
   generate opening-book entries (canonical key, weighted values,
   multiplicities, PV edges). Online: UCT plays from book exits.

## 6. Status and pending validation

`beam_schedule` is implemented and tested (flat-equivalence, last-entry
extension, exhaustive-prefix zero-pruning, off-by-one mutation tests);
`rollout_schedule` is specified as above and being implemented with the
same test discipline, including the exact 258-playout anchor. A scheduled
vs. flat benchmark (recipe of §2 against flat width/rollouts at equal
wall-clock) will be appended to this series once both knobs are merged.

## References

- Companion: [2026-07-07-beam-search-vs-mcts.md](2026-07-07-beam-search-vs-mcts.md)
  (design, flat-width benchmarks, UCT comparison, multiplicity accounting).
- `docs/BEAM_SEARCH.md` (user-facing configuration reference),
  `docs/MCTS.md`, `GAME_TREE_ANALYSIS.md` (exact enumeration).
- L. Kocsis, C. Szepesvári. *Bandit based Monte-Carlo Planning.* ECML 2006.
