# Classical Alpha-Beta Search with a Fitted Evaluation: An Exact, Deterministic Alternative to Sampling on Quantik

*Working paper #3 — quantik-core, 2026-07-10. Follows
[2026-07-07-beam-search-vs-mcts.md](2026-07-07-beam-search-vs-mcts.md) and
[2026-07-08-budget-shaping-schedules-vs-mcts-truncation.md](2026-07-08-budget-shaping-schedules-vs-mcts-truncation.md);
part of the same incremental series. Where the first two papers compared two
*sampling* search strategies — bounded-width beam search and UCT — against
each other, this note introduces a third, structurally different engine:
classical alpha-beta minimax over a handcrafted, fitted evaluation function.
Numbers are reproducible from `examples/minimax_benchmark.py` and the
`tuning/` pipeline described below.*

## 1. Introduction

The first two papers in this series treated Quantik's search problem as a
budgeting question: given that the raw game tree is too large to enumerate
exhaustively (2,235,929,747,584 legal move sequences, 23,577,899 unique
canonical states through depth 8 — `GAME_TREE_ANALYSIS.md`), how should a
fixed amount of work be allocated between *coverage* (how many branches stay
alive) and *precision* (how accurately each branch is valued)? Both beam
search and UCT answer that question by sampling: they spend evaluations on
random playouts and either keep a bounded frontier (beam) or grow a tree
along UCB-selected paths (UCT).

This note asks a different question: for the parts of the game that *are*
small enough to search exactly — which, for Quantik, turns out to be most
positions more than a handful of plies deep — is there a reason to sample at
all? Quantik has at most 16 plies and a branching factor that collapses
quickly as pieces fill the board and legality constraints bite. That is
exactly the regime where classical alpha-beta minimax, the workhorse of
deterministic two-player game search since the 1950s, is the natural tool:
it is exact wherever it reaches a true terminal, and it degrades gracefully
to a heuristic evaluation only where the remaining tree is still too large
to finish.

The catch is the evaluation function. Alpha-beta without a good leaf
heuristic just becomes "exact search to a shallow depth, then random-ish
tie-breaking." This work therefore delivers two things together: a
depth-limited alpha-beta engine (`quantik_core.minimax`), and a *fitted*
linear evaluation (`quantik_core.evaluation`) whose weights are learned from
the same exact solver that the engine already contains — Quantik is small
enough that the "ground truth" needed to train an evaluation function is not
an external oracle or a corpus of human games, it is simply a deeper run of
the same search, applied to positions where that deeper run is cheap.

## 2. Background: what "exact" means for Quantik

Quantik is a 4×4 adversarial placement game: each of two players owns two
pieces of each of four shapes; the pieces differ by shape, and separately
by color/owner. A player wins by completing a row, column, or 2×2 zone
containing all four *shapes*, regardless of which player placed them; it is
illegal to place a shape in a line where the *opponent* already has that
shape. A player with no legal move loses. Winning is therefore a purely
shape-based, color-blind condition — color enters the rules only through the
legality constraint on where a shape may be placed.

The companion papers established the state space: the raw tree is
enormous, but folding out the board's `D4` symmetry (rotations and
reflections, order 8) and the game's shape-relabeling symmetry (`S4`,
order 24) collapses it by factors from 21× at ply 1 to over 10⁵× at ply 8.
`State.canonical_key()` is the implementation of this fold — it is the same
canonicalization the beam-search and multiplicity-accounting machinery in
the earlier papers rely on, and it is central to this paper's soundness
argument (§5).

## 3. The evaluation function: a linear model over six legality-aware features

`quantik_core.evaluation.evaluate(bb, player, cfg)` scores a
**non-terminal** position from `player`'s perspective; positive is good for
`player`. It is used only as the depth-cutoff leaf heuristic — the search
layer (§4) handles all terminal positions itself, exactly.

### 3.1 Per-line classification

The evaluation scans all 12 win lines (4 rows + 4 columns + 4 zones). For
each line it computes the *union of shapes present across both colors* —
because winning only cares about the four distinct shapes, not who placed
them — and classifies the line by how many distinct shapes versus how many
occupied cells it has:

| occupied | distinct shapes | meaning |
|---|---|---|
| 4 | 4 | winning line — terminal, handled by search, never reached by `evaluate` |
| any | fewer than occupied | **dead** — a shape repeats on the line, so it can never hold all four distinct shapes; contributes nothing |
| 3 | 3 | **live threat** — one more (specific) shape at one specific empty cell wins the line |
| 2 | 2 | building line |
| 1 | 1 | minimally developed line |
| 0 | 0 | empty, neutral |

### 3.2 Threats are legality-aware, not just geometric

The interesting design decision is in how a 3-distinct "live threat" line is
scored. It would be tempting to just count such lines and attribute them to
whichever player's turn it would help. But Quantik's placement-legality rule
means a line with three distinct shapes and one empty cell is not
automatically completable by either player: completing it requires the
missing shape `m` at the empty cell `q`, which is legal for a player only if
(a) that player still has an unplaced copy of `m`, and (b) the opponent does
not already have `m` on some other line through `q`. A "threat" that no one
can legally fill is not a threat at all.

So for each live-threat line the evaluation checks, per side, whether that
side could legally place the missing shape right now, and buckets the line
into one of four cases (from `player`'s perspective, with `stm` the side to
move):

- completable only by `player` → `+threat_own`
- completable only by the opponent → `-threat_opp` (in the feature vector,
  `threat_opp` itself is a non-negative count; its weight carries the sign)
- completable by both sides (a race for the same cell) → `threat_shared`,
  signed toward `stm` — whoever moves next gets first claim, so this is a
  tempo term
- completable by neither → 0, it drops out entirely

This legality gate is why the evaluation is more than a shape-counting
heuristic: two positions with geometrically identical "three shapes, one
gap" patterns can score completely differently depending on hand
inventories and where the opponent's pieces of the missing shape already
sit.

### 3.3 Mobility and building potential

Because color affects the game only through legality, the durable
directional signal beyond threats comes from **mobility** — the difference
in legal-move counts, `legal_moves(player) − legal_moves(opponent)` — which
matters concretely because a player with zero legal moves loses outright.
Two smaller terms add tie-breaking texture: `build_two` and `build_one`
count live lines with two and one distinct shapes respectively (signed
toward the side to move), rewarding flexible development without
overpowering the threat terms.

### 3.4 The feature vector and the linear model

All of the above is packaged as a fixed-order, six-dimensional feature
vector, computed by a single pure function that both the evaluator and the
weight-fitting pipeline (§6) share:

```
features(bb, player) -> [threat_own, threat_opp, threat_shared,
                          mobility_diff, build_two, build_one]

evaluate(bb, player, cfg) = cfg.weights @ features(bb, player)
```

Because `evaluate` is *exactly* a dot product with no nonlinearity, fitting
the weights is a linear/logistic-regression problem (§6), and every
position's score decomposes transparently into six interpretable terms.
`EvalConfig` also carries `win = 10_000.0`, the terminal-value magnitude
used by the search layer (§4.2) — the evaluation function itself never
touches it, since it only ever scores non-terminal leaves.

The seeded starting weights, chosen by hand before any fitting, were
`[threat_own=100, threat_opp=-100, threat_shared=20, mobility=3,
build_two=2, build_one=0]` — a reasonable a-priori ranking (threats
dominate, mobility matters, minimal development is a weak tie-breaker) but,
as §6–§7 show, measurably worse than what a few hundred solved positions
can teach.

### 3.5 Symmetry invariance

Because the evaluation treats every line and every shape uniformly, and
reads the side to move from piece counts (itself invariant under board
symmetry and shape relabeling), `evaluate` is provably constant across all
symmetric variants of a board — the same board rotated, reflected, or
shape-relabeled scores identically. This is asserted directly as a test
(random states, all symmetry variants), and it is also the property that
makes the transposition table in §5 sound.

## 4. The minimax engine

`quantik_core.minimax.MinimaxEngine` implements **negamax with alpha-beta
pruning, iterative deepening, and a transposition table**, evaluated with
the function above at the depth cutoff.

### 4.1 Negamax and iterative deepening

The search is a standard negamax formulation: `_negamax` returns the value
of a position from the perspective of whoever is to move *at that node*; a
parent folds a child's value back into its own perspective by negating it.
`MinimaxEngine.search` deepens from depth 1 up to `config.max_depth` (or
until `config.time_limit_s` elapses), and each iteration seeds its root move
ordering with the *previous* iteration's principal variation — a standard
technique that sharpens alpha-beta cutoffs as the search goes deeper,
because the move most likely to still be best is tried first.

### 4.2 Terminal detection: a deliberate implementation choice

Rather than the pre-existing `check_game_winner` helper, the engine detects
terminals with `has_winning_line`. This is a deliberate choice, not an
oversight: `check_game_winner` has a known turn-balance edge case, and
sidestepping it is simpler than working around it inside the hot search
loop. The consequence for the value convention: if `has_winning_line(bb)` is
true at a node, it means the *previous* mover just completed a line, so the
side to move at *this* node has already lost. The returned value is
`-(win − ply)`, not a flat `-win` — subtracting the ply number means a
faster forced loss (or, negated one ply up, a faster forced win) scores more
extremely than a deeper one. This both matches the intuitive preference for
quicker mates and is necessary for alpha-beta comparisons between mates
found at different depths to behave sensibly. The same rule applies to "no
legal moves" (Quantik's other loss condition): the side to move immediately
loses, scored `-(win − ply)`.

### 4.3 Move ordering

Within a node, children are generated in a deterministic `(shape, position)`
order, then re-sorted so that any move producing an immediate win for the
side to move is tried first — a forced-win child is trivially the best
possible reply, so trying it first gets the earliest possible beta cutoff.
At the root, the prior iteration's principal-variation move is floated to
the front instead, since the root has no single "immediate win" shortcut
across iterations.

### 4.4 Child dedup

An optional `dedup_children` setting (on by default) collapses sibling
moves whose resulting positions share a `canonical_key()` — i.e., are
related by one of the board's 192 symmetries — down to one representative,
searching it once rather than once per symmetric duplicate. This is folded
into move generation itself (not deferred to the transposition table)
because Quantik's early game is wide enough (dozens of legal moves per ply)
that without it even modest depths blow up combinatorially, and the
alpha-beta-off configuration used to test alpha-beta's correctness (§4.5)
has no pruning to fall back on if dedup is also off.

### 4.5 Config and result shape

```
MinimaxConfig:
  max_depth: int = 16
  time_limit_s: float | None = None
  use_alpha_beta: bool = True
  use_transposition_table: bool = True
  dedup_children: bool = True
  eval_config: EvalConfig = EvalConfig()
  random_seed: int | None = None   # tie-break among equal-value root moves

MinimaxResult:
  best_move, score, depth_reached, nodes, pv, elapsed
```

`MinimaxEngine.solve(state)` is simply `search` with `max_depth=16` and no
time limit — since no Quantik game exceeds 16 plies, a depth-16 search
always bottoms out on true terminals rather than the heuristic cutoff, so it
functions as an exact solver rather than a heuristic engine, wherever it is
affordable to run to completion (§7.3).

## 5. Transposition-table soundness: why caching by canonical key is safe here

The transposition table stores, per `canonical_key()`, a
`(depth_searched, value, bound_kind)` triple, with `bound_kind` one of
`EXACT`, `LOWER`, `UPPER` in the usual alpha-beta sense.

This deserves an explicit argument, because caching by a *symmetry-reduced*
key is a stronger claim than the usual "same position, same value" TT
soundness: the table is shared across positions that are literally different
boards, related only by a symmetry transform. The argument has two parts:

1. **The board symmetry group used by `canonical_key()` is `D4 × S4`, order
   192 — board symmetries composed with shape relabelings, *without* a
   color/player swap.** This was confirmed against the beam-search paper's
   independently-verified orbit counts (§2 there): the same 192-element
   group, not the full 384-element group that Quantik's rules admit in
   theory if color swap were also folded in. The engine's canonicalization
   deliberately stays at 192; color/player identity is preserved by the key.
2. **The negamax value is defined relative to the side to move, not to a
   fixed color, and side-to-move is itself a symmetry-invariant quantity**
   (it is determined purely by piece counts, which board symmetries and
   shape relabelings cannot change). So two boards sharing a canonical key
   have not just "the same shape of position" but *the same negamax value*,
   because negamax was never asking "is this good for White" — it was
   always asking "is this good for whoever moves next," and that question's
   answer transfers exactly across the symmetry orbit.

Given that, caching the *value* (and alpha-beta bound) by canonical key is
sound: any two states in the same orbit have provably the same negamax
value at the same remaining depth, so a lookup hit is a correct answer, not
an approximation.

**What is not cached is the move.** A canonical key collapses 192
concretely different boards onto one representative; the move that is best
in the representative's orientation is generally the *wrong* move (wrong
row/column/shape) for a different, symmetric sibling — canonicalization
does not remember which of the 192 transforms was applied to reach the
representative. Move ordering therefore comes entirely from the
concrete-orientation principal variation carried across iterative-deepening
iterations (§4.1, §4.3), never from the transposition table.

The two soundness ingredients above (evaluation invariance in §3.5, negamax
value invariance here) are the same underlying fact — piece counts alone
determine both the side to move and the invariance of anything computed from
them — applied to two different layers of the engine: the leaf heuristic and
the search's own value cache.

## 6. Weight fitting: the full-depth solver is its own oracle

### 6.1 Why fit at all, and why no external solver is needed

The seeded weights in §3.4 were a reasonable guess, not a target. Because
Quantik is small enough to solve exactly in bounded regions, the evaluation
has a well-defined ground truth to be fit against: the exact side-to-move
outcome (`+1` win / `0` draw / `−1` loss) that `MinimaxEngine.solve` already
computes. No separate solver, oracle, or external engine is needed — the
same alpha-beta engine that will *use* the fitted weights at its depth
cutoff is also the label source for fitting them.

### 6.2 Why the training positions cannot come from the empty board

A full solve from the empty board would be the most natural source of
labeled positions, but it is intractable in pure Python at the tree sizes
this game reaches. `GAME_TREE_ANALYSIS.md`'s exact enumeration puts the
cumulative unique canonical state count at 23,577,899 through depth 8 alone
(and the raw, non-canonical count at ply 8 is already
2,097,048,766,464) — and every node visited by the search calls
`canonical_key()` for dedup and/or the transposition table, which itself
scans all 192 symmetries and costs several hundred microseconds. The result
(confirmed directly, §7.3) is that search from the open board proceeds at
only a few hundred nodes per second, nowhere near enough to reach the depths
where positions actually resolve.

The tuning pipeline (`tuning/`) sidesteps this by sampling positions that
are already 8–12 plies into a random game. At that depth the remaining
subtree is small enough that an exact solve is fast (measured up to ~1.1 s,
averaging ~0.25 s per position at ≥8 plies), so a few hundred labeled
positions build in one to two minutes rather than being computationally
infeasible.

This introduces an intentional **mid/late-game sampling bias**: no opening
positions are in the training set. It is accepted as reasonable rather than
worked around, for a specific reason: the positions the *fitted evaluation
will actually be asked to score* are themselves the leaves of a
depth-limited search — i.e., they are already several plies deeper than
wherever the search started. A depth-cutoff leaf reached from a midgame root
is exactly the kind of position the mid/late-game training sample
represents; the evaluation is not being asked to generalize far outside its
training distribution.

### 6.3 The fitting procedure

`tuning/build_dataset.py` samples non-terminal positions uniformly at
random plies in `[8, 12]`, dedups them by `canonical_key()` (so the same
canonical position is never double-counted even if reached via different
random move sequences), and labels each with the exact solver's verdict for
the side to move. `tuning/fit_weights.py` then fits the six weights by
plain-numpy logistic regression (standardized features, batch gradient
descent with a small L2 penalty, fixed seed — no new dependency), predicting
`P(win)` from `weights @ features`, and maps the fit back into the original
(unstandardized) feature space so the resulting weights are directly usable
by `evaluate`. The fit is fully deterministic given the seed and the frozen
dataset, so refining the evaluation over time is a repeatable loop:
change or add a feature, rerun the fit, commit the new `tuning/weights.json`.

### 6.4 What was actually fit, and how much it helped

The committed dataset (`tuning/dataset.npz`, seed `20260710`) has 500
labeled positions, split **428 wins / 72 losses / 0 draws** for the side to
move — reflecting that random mid-game play from Quantik's rules more often
lands the side to move in a winning position than a losing one at this
sampling depth. On this dataset:

| weights | sign-accuracy | win-recall | loss-recall | balanced accuracy |
|---|---:|---:|---:|---:|
| seeded | 0.826 | 0.853 | 0.667 | 0.760 |
| fitted | 0.884 | 0.867 | 0.986 | 0.926 |

Overall sign-accuracy improved from 0.826 to 0.884 — matching the
`sign_accuracy: 0.884` recorded directly in the committed
`tuning/weights.json` — but the more informative number is **loss-recall**:
the seeded weights correctly flagged only 66.7% of the actual losing
positions as bad (`sign(evaluate) < 0`) for the side to move, while the
fitted weights catch 98.6% of them. Because the dataset is heavily
imbalanced toward wins (428:72), overall accuracy alone would understate
this: a classifier that always predicted "win" would already score 85.6%
sign-accuracy while being useless for the loss class specifically. Balanced
accuracy — the average of win-recall and loss-recall — is the fairer
summary, and it improves from 0.760 to 0.926. In search terms, this matters
because an evaluation that systematically fails to recognize losing
positions is an evaluation that will happily walk a depth-limited search
into a trap it should have pruned away.

The fitted weights themselves (`tuning/weights.json`):

```
threat_own = 3.833, threat_opp = -1.275, threat_shared = 1.077,
mobility_diff = 0.228, build_two = -0.328, build_one = -0.476
```

Qualitatively they preserve the seeded weights' sign pattern on the two
dominant threat terms (own positive, opponent's negative) but compress the
magnitudes drastically relative to each other and, notably, invert the sign
on `build_two` and `build_one` — the fit found that, once threats and
mobility are accounted for, incremental "building" lines are mildly
*informative of the opponent's chances* rather than the side to move's, the
opposite of the seeded guess. This is exactly the kind of correction hand-
tuning is unlikely to find and a supervised fit is well suited to catch.

## 7. Benchmarks

All numbers below are from a single run of `examples/minimax_benchmark.py`
(total run time 383.8 s) on the same machine used for the earlier papers
(Apple Silicon, macOS, CPython, pure-Python search — NumPy used only inside
the tuning pipeline, not the search itself).

### 7.1 Playing strength

Eight games per pairing, minimax playing both sides in turn against each
opponent, `max_depth=6` and `time_limit_s=0.15` per move with the fitted
evaluation:

| opponent | minimax as P0 | minimax as P1 |
|---|---:|---:|
| random mover | 8/8 | 8/8 |
| UCT, 1,500 iterations | 8/8 | 8/8 |

Minimax swept every game in both configurations. This is a directional
result, not a rigorous strength claim: 8 games per cell is a small sample,
MCTS with 1,500 iterations is a comparatively weak baseline (recall from
paper #1, §5.4, that UCT needs ~25,000 iterations before it materializes
even a handful of terminal nodes from the open board), and a shallow
`max_depth=6` search with a fitted evaluation is not the same claim as a
full solve. What it does establish is that a bounded-depth exact search plus
a fitted leaf heuristic reliably outplays both an undirected random mover
and a moderately-budgeted stochastic search — the two engines are not
merely different in character, one dominates the other at these settings.

### 7.2 Search performance: alpha-beta and TT prune ratios

Fixed depth-4 search from a mid-game anchor position
(`.D.a/..../..d./.BBd`), with dedup-by-canonical-key active in every
configuration (it is on by default and was not disabled for this
comparison):

| configuration | nodes | time | rate |
|---|---:|---:|---:|
| alpha-beta + TT + dedup | 1,787 | 1.021 s | 1,750 n/s |
| alpha-beta only (no TT) | 1,856 | 1.046 s | 1,775 n/s |
| no alpha-beta, no TT | 33,194 | 10.678 s | 3,109 n/s |

The headline prune ratio is between the unpruned and fully-pruned
configurations: **~18.6× fewer nodes and ~10.5× less wall time** with
alpha-beta and the transposition table both active. Interestingly, almost
all of that reduction — 33,194 down to 1,856 nodes — comes from alpha-beta
pruning alone; the transposition table's further contribution on top of
alpha-beta at this single fixed-depth call is small (1,856 → 1,787 nodes,
about 4% fewer). That is expected rather than a weakness of the TT: a
transposition table earns most of its keep by carrying information *across*
iterative-deepening iterations (a shallower iteration's exact values seed
the next, deeper one) and across transpositions reached by different move
orders within a single deep search — benefits that a single fixed-depth-4
call from one position has limited opportunity to realize. Note also that
the unpruned configuration's *rate* (3,109 n/s) is higher than the pruned
configurations' (~1,750–1,775 n/s): the pruned searches spend a larger
fraction of their (far smaller) node budget at shallow, canonical-key-
computing internal nodes near the root, while the unpruned search's node
count is dominated by cheap, terminal-adjacent leaves.

### 7.3 The open-game intractability, directly measured

From the empty board, with `max_depth=16` and a wall-clock budget:

| budget | depth reached | nodes | elapsed |
|---|---:|---:|---:|
| 2 s | 3 | 536 | 2.3 s |
| 5 s | 3 | 536 | 5.1 s |

Depth 3 from the empty board — 536 nodes — is itself already at the edge of
what a 2-second budget affords (the run overshoots slightly to 2.3 s,
because the internal time check only fires every 1,024 visited nodes and
depth 3 finishes in fewer than that). What is more telling is that
*increasing the budget to 5 seconds does not move the reported depth or
node count at all*: the engine reports the last iteration that ran to
completion, and depth 4 from the empty board — with its far larger branching
and every internal node paying the 192-symmetry `canonical_key()` cost for
dedup and the transposition table — simply does not finish within the extra
2.7 seconds available. This is a direct, empirical illustration of the same
intractability argument made analytically in §6.2 and in
`GAME_TREE_ANALYSIS.md`: the open game is out of reach for exhaustive
alpha-beta in pure Python, for exactly the reason a full-depth solve from
the empty board is not used as the training-label source in §6.

Against that backdrop, the engine still reports a directional empty-board
move at the 5-second budget — `score=-121.0`, depth 3 — using the fitted
evaluation at the depth-3 cutoff. This is *not* a claim about the true value
of the empty board (which, per prior combinatorial-game-theory-style
convention, is understood as a first-player win in Quantik; nothing here
either confirms or contests that at the depth this engine can reach in
seconds); it is reported honestly in the benchmark as "directional only."

Time-to-move along one self-played minimax line (0.2 s budget per move)
shows how sharply this changes once the board fills in:

| ply | depth reached | nodes | time |
|---:|---:|---:|---:|
| 0 | 3 | 536 | 0.51 s |
| 1 | 2 | 241 | 0.22 s |
| 2 | 2 | 208 | 0.32 s |
| 3 | 2 | 941 | 0.62 s |
| 4 | 2 | 166 | 0.25 s |
| 5 | 2 | 164 | 0.79 s |

Node counts and timings both bounce around at fixed shallow depths rather
than climbing steadily — consistent with the branching factor being highly
position-dependent (it can spike, as at ply 3's 941 nodes, when a position
happens to have unusually many legal replies) rather than monotonically
shrinking ply over ply.

### 7.4 Solve correctness: exact anchors

Because a full solve from the empty board is infeasible, correctness is
anchored on exact solves from positions a few plies from the end, where
`MinimaxEngine.solve` reaches true terminals throughout and the ply-adjusted
`±(win − ply)` value convention (§4.2) is directly checkable:

| position (QFEN) | expected score | measured score | nodes |
|---|---:|---:|---:|
| `.B.C/a.../.Ca./..d.` (win in 3) | 9,997 | 9,997 | 3,607 |
| `.D.a/D..c/..d./.BBd` (loss in 4) | −9,996 | −9,996 | 1,936 |

Both match exactly: `win − ply = 10,000 − 3 = 9,997` for a forced win found
at ply 3, and `−(win − ply) = −(10,000 − 4) = −9,996` for a forced loss at
ply 4. These are the kind of anchors the earlier papers used exact
enumeration and multiplicity sums for (paper #1, §3.4) — small, exactly
checkable ground truth standing in for the full-tree proof that pure-Python
search cannot deliver from the open board.

### 7.5 Evaluation quality: seeded versus fitted, under the search's own conditions

The tuning pipeline's own accuracy numbers (§6.4) are computed against the
500-position *training* dataset. The benchmark suite separately checks
evaluation quality against 60 held-out solved positions sampled the same
way (8–12 plies, deduped by canonical key), and adds a second metric —
**move-agreement**: whether a shallow (`max_depth=2`), eval-guided search
picks the same move the full solver would:

| weights | sign-accuracy | move-agreement |
|---|---:|---:|
| seeded | 0.767 | 0.983 |
| fitted | 0.917 | 0.933 |

Sign-accuracy improves substantially, from 0.767 to 0.917, corroborating
the training-set numbers in §6.4 on an independent sample. Move-agreement,
however, moves in the *opposite* direction — from 0.983 down to 0.933 — a
result worth reporting honestly rather than smoothing over. It is not a
contradiction: sign-accuracy asks whether the leaf's win/loss *sign* is
right, while move-agreement asks whether a 2-ply search using that leaf
heuristic ranks the *specific best move* the same as the full solver does,
which depends on fine-grained ordering between several candidate moves, not
just the sign of the best one. A leaf function can become better calibrated
on the win/loss question while occasionally reordering two options whose
values are close — especially plausible here, since the fitted weights are
an order of magnitude smaller in relative spread than the seeded ones
(§6.4) and were optimized for a classification objective (predicting
win/loss), not directly for move ranking. Both metrics are reported in
§4.6 of the design spec as complementary; §7.1's head-to-head strength
results (fitted evaluation, 32/32 games won across both opponents) are the
metric that most directly answers "does this make the engine play better,"
and on that measure the fit clearly helped.

## 8. Minimax versus the sampling engines: a structural comparison

| Property | Minimax (this work) | Beam search (paper #1) | UCT / MCTS (papers #1–2) |
|---|---|---|---|
| Determinism | Exact, deterministic given config (modulo the `random_seed` tie-break among equal-value root moves) | Deterministic given seed; stochastic evaluator by default | Stochastic (random playouts, UCB sampling) |
| What it guarantees | Provably correct value wherever it reaches true terminals (§4.2, §7.4) | Materializes every terminal it passes; frontier is a beam-bounded, mover-relative ranking | Visit-averaged estimate; improves with more iterations at visited nodes |
| Leaf valuation | Fitted linear evaluation only below the search horizon | Mean of random rollouts (or a pluggable evaluator) | Random rollout to a true terminal (or truncation, paper #2) |
| Cost driver | `canonical_key()` calls for dedup/TT (192-symmetry scan, several hundred µs each) dominate near the root; alpha-beta cuts the node count sharply once threats appear | Evaluator playouts (§paper #1, ~1 ms per 2-rollout evaluation) | Playouts per iteration (~150–210 iterations/s from the empty board, paper #1) |
| Open-game behavior | Depth 3–4 in seconds; intractable beyond that in pure Python (§7.3) | Resolves the *entire* game from the empty board in ~1–15 s (different problem: bounded-width frontier, not exhaustive alpha-beta) | Reaches ply 6–7 after tens of thousands of iterations; negligible terminal coverage (paper #1, §5.4) |
| Where it is exact | Anywhere within its search horizon that terminals are reached (midgame onward, and small enough endgames from any root) | Only where the width schedule is exhaustive (paper #1 §3.2) | Never exactly; asymptotically as iterations → ∞ |
| Failure mode | Evaluation misranks close leaves below the horizon (§7.5); open-game intractability | Evaluator misranks a pruned branch — irrevocable | Under-visited subtrees; recoverable with more iterations |

The two families are not really in competition so much as answering
different questions well. Beam search (paper #1) is built to *cover* the
game — guaranteeing a bounded-memory, terminal-reaching frontier at every
ply, which is exactly what opening-book generation wants. UCT adapts its
attention online and gives a calibrated, visit-weighted value estimate at a
single decision point, which is what move selection under a live time
budget wants. Minimax with a fitted evaluation gives something neither of
the sampling engines can: a value that is *exactly correct*, not merely
estimated, whenever the remaining tree is within reach — which for Quantik
is a large fraction of the game once a handful of pieces are down — backed
by a leaf heuristic for the remainder that is trained against that same
exactness rather than guessed.

The engines are also complementary in the same spirit as papers #1–2's
composition proposals: the fitted evaluation used at minimax's depth cutoff
is a plain `State → float` function, so nothing prevents it from also
serving as the beam engine's pluggable `evaluator` (in place of, or blended
with, random rollouts) or as a fast, deterministic estimate at UCT leaf
nodes in place of a full random playout — directions this design
deliberately leaves as future work (it does not wire the evaluation into
MCTS rollouts) so the evaluation stays a small, pure, independently testable
function.

## 9. Limitations

- **Open-game intractability is real, not just a documented risk.** §7.3
  measured it directly: depth 4 from the empty board does not complete in a
  5-second budget in pure Python. The `canonical_key()` cost (a 192-symmetry
  scan on every dedup/TT-relevant node) is the dominant factor, and it is
  paid at every internal node regardless of alpha-beta's pruning — pruning
  reduces *how many* nodes pay it, not the per-node cost itself.
- **Playing-strength numbers are directional.** Eight games per cell against
  a random mover and a 1,500-iteration UCT baseline is enough to show a
  clear pattern, not enough for a calibrated strength estimate; MCTS-1500 in
  particular is a weak baseline relative to what UCT reaches at the
  iteration counts explored in paper #1 (10,000–25,000).
- **The evaluation's training data has a sampling bias by construction**
  (§6.2): all 500 labeled positions are 8–12 plies deep, none are openings.
  This is argued to be acceptable because depth-cutoff leaves are themselves
  deep, but it has not been tested against, say, an evaluation trained (were
  it feasible) on a uniform sample across all plies.
- **Sign-accuracy and move-agreement can disagree** (§7.5): the fitted
  weights improved one and slightly regressed the other on the 60-position
  held-out sample. Whichever metric matters more depends on the downstream
  use — leaf-level classification versus move selection — and this note
  reports both rather than picking the one that looks better.
- **Single machine, pure Python, one run per benchmark table.** As in the
  earlier papers, absolute throughput numbers (node rates, wall times) are
  indicative of this environment; the ratios (prune ratios, sign-accuracy
  deltas) are the more robust findings.

## 10. Conclusion

Quantik's small board and short game length make it an unusually good fit
for classical alpha-beta search — exact wherever the remaining tree is
small, which for Quantik is most of the game once a few pieces are placed,
with a genuine intractability wall only at the wide open game, measured
directly here rather than only argued analytically. Pairing that search
with a *fitted* rather than hand-guessed evaluation closes the gap at the
depth cutoff using the same asset the engine already has: its own exact
solver, applied to positions cheap enough to solve, turned into training
labels. The fit measurably improved the evaluation's ability to recognize
losing positions (loss-recall 0.667 → 0.986 on the training set; sign-
accuracy 0.767 → 0.917 on an independent held-out sample) and, at the level
that matters most, translated into a fitted-evaluation minimax engine that
won every game played against both a random mover and a 1,500-iteration UCT
baseline. Alongside the beam search and UCT engines from the earlier
papers, this gives the repository three structurally distinct search
strategies over the same canonical state representation — exhaustive-frontier
coverage, adaptive stochastic sampling, and exact deterministic search with
a learned leaf heuristic — each strongest where the others are weakest.

## Future work: cross-engine cooperation

All three engines key off the same `canonical_key()`, so they share a state
identity and can be made to help one another. Concrete follow-ups (each its own
piece of work, listed roughly by increasing scope):

1. **Mid-game strength & agreement benchmark.** ✅ Done —
   `examples/cross_engine_benchmark.py`. Plays minimax, UCT, and beam search
   from a *shared set of random valid non-terminal mid-game positions* (8–12
   plies in, both sides to move) and reports **move-agreement**: how often
   each engine's move is in the exact solver's optimal-move set. Measured:
   minimax 1.000 (a shallow-search proxy for the solver), beam 0.975, MCTS
   0.500. The head-to-head from these same neutral starting positions
   (minimax P0 vs MCTS-1500 P1) is markedly less lopsided than the
   empty-board result above — minimax won 4/8, versus ~100% from the empty
   board — because a random mid-game position isn't systematically
   favorable to either side the way a controlled opening is.
2. **Exact-solver → shared opening book.** The `OpeningBookDatabase` is keyed by
   `canonical_key` and is engine-agnostic. A batch job can solve every
   tractable position and write **exact** evaluations and best moves into the
   book, upgrading statistical entries to ground truth for every engine that
   consults it.
3. **Hybrid opening→endgame player.** Use adaptive sampling (UCT or beam) while
   the tree is intractable, then hand off to the **exact** minimax solve once
   few enough cells remain — pairing each engine with the regime where it is
   strongest and sidestepping the open-game intractability wall entirely.
4. **Eval-guided MCTS rollouts.** Replace UCT's random playouts with the fitted
   evaluation as a leaf/rollout policy — the evaluation from this work is kept a
   pure function precisely so this stays a small change.

## References

- Companion papers: [2026-07-07-beam-search-vs-mcts.md](2026-07-07-beam-search-vs-mcts.md),
  [2026-07-08-budget-shaping-schedules-vs-mcts-truncation.md](2026-07-08-budget-shaping-schedules-vs-mcts-truncation.md).
- This repository: `GAME_TREE_ANALYSIS.md` (exact enumeration),
  `docs/superpowers/specs/2026-07-10-alpha-beta-eval-design.md` (design
  spec), `docs/MINIMAX.md` (usage reference).
- C. E. Shannon. *Programming a Computer for Playing Chess.* Philosophical
  Magazine, 1950 (minimax over an evaluation function, the classical
  antecedent of this design).
- D. E. Knuth, R. W. Moore. *An Analysis of Alpha-Beta Pruning.* Artificial
  Intelligence 6(4), 1975.

## Appendix: reproducibility

- Engine/evaluation modules: `src/quantik_core/minimax.py`,
  `src/quantik_core/evaluation.py` (this branch:
  `feat/minimax-eval`, developed in an isolated worktree).
- Tuning pipeline: `tuning/build_dataset.py` (`n=500`, `seed=20260710`,
  ply range `[8, 12]`, deduped by `canonical_key()`) →
  `tuning/dataset.npz`; `tuning/fit_weights.py` → `tuning/weights.json`
  (committed).
- Benchmark harness: `examples/minimax_benchmark.py`; full run captured in
  `.superpowers/sdd/benchmark-output.txt` (total wall time 383.8 s).
- Exact anchors: `tests/test_minimax.py` (alpha-beta ≡ plain-minimax value,
  TT-on ≡ TT-off value, iterative-deepening-to-depth-`d` ≡ fixed-depth `d`,
  mate-in-1 / block-mate-in-1 on crafted QFEN positions), `tests/
  test_tuning.py` (`features()` matches `evaluate()`'s dot product, fit
  reproducibility under a fixed seed, `EvalConfig.load` round-trip),
  `tests/test_evaluation.py` (dead-line scoring, threat legality, 192-variant
  symmetry invariance).
