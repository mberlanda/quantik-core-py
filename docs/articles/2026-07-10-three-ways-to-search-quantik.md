# Three Ways to Search a Game

### Minimax, Monte-Carlo Tree Search, and beam search, over the same 4×4 board my wife kept winning on

*Second in a series. The [first article](https://mauroberlanda.substack.com/p/the-game-my-wife-kept-winning-engineering)
turned Quantik into something a machine can represent without ambiguity. This
one asks the obvious next question: now that the machine can **name** a
position, can it **search** from one — and actually play well?*

---

In the first article I promised myself a rule: *before teaching a machine to
play a game, teach the machine what the game is.* So I spent that whole piece on
representation — eight 16-bit bitboards, a QFEN string like `AbCd/..../..../....`,
and a canonical key that folds the board's 192 symmetries (the dihedral group
D₄ times the 24 shape relabelings, |G| = 8 × 4!) into a single deterministic
name. No search. No AI. Just: *what is this position, unambiguously?*

That groundwork turns out to be the whole game. Everything in this article —
three different search engines, a learned evaluation function, a wall of
intractability, and a way around it — rests on that one 18-byte canonical key.
Naming positions was not the boring prelude to the interesting part. It **was**
the interesting part; the rest is consequences.

So let me spend the consequences.

## From naming positions to searching them

A search engine answers a different question than a canonical key does. The key
asks *what is this?* The engine asks *what should I play?* The bridge between
them is an old idea, and one I met long before software, back when I studied
Game Theory: **backward induction**. A position is winning for the player to
move if at least one legal move leads to a position that is losing for the
opponent. Unfold that recursively and you have the game's exact value — who
wins with perfect play, and how.

Quantik is unusually friendly to this. It is finite, deterministic, perfect
information, and — under Board Game Arena rules — has no draws: a player with no
legal move simply loses. The whole game is over in at most 16 plies, because
there are only 16 cells. A game that ends in sixteen moves and has no hidden
information *sounds* like it should be trivially solvable.

It is not. And the reason it is not is the single most important number in this
entire project.

## The wall, measured exactly

In the first article I counted the game tree. Here are the numbers that matter,
after canonical reduction:

| Ply | Distinct canonical positions | Reduction vs. raw histories |
|-----|------------------------------|-----------------------------|
| 1 | 3 | 21× |
| 4 | 10,946 | ~619× |
| 8 | 17,900,160 | over 100,000× |

Cumulatively, across the whole game, there are about **23.5 million** unique
canonical positions — squeezed down from roughly **2.2 trillion** raw move
sequences. The symmetry key is doing staggering work: at depth 8 it collapses a
number with twelve digits into one with eight.

And yet 23.5 million exact evaluations, each requiring me to compute a canonical
key that itself searches all 192 symmetries, is not something pure Python does
over a coffee. Measured on my laptop, an exact search from the *empty* board
plods along at a few hundred positions per second. I gave it a five-second
budget and it reached **depth three**. Three plies. Out of sixteen.

That is the wall. It is not hypothetical, and it is not a coding failure — it is
the shape of the problem. The open game is astronomically wide (from the empty
board, the first player has 64 raw placements; the tree fans out from there),
and the canonical key that makes the space *countable* is also expensive enough
to make exhaustively *walking* it slow.

Here is the twist that makes the rest of the article work: **the wall is only at
the opening.** The branching factor shrinks fast — every piece placed removes a
cell and constrains the next move — so once a handful of pieces are down, the
remaining tree is small enough to solve *exactly, to the end of the game, in
well under a second.* Quantik is intractable in its first few plies and trivial
in its last dozen. Any engine that wants to play the whole game has to cope with
both regimes. That single fact is why one search strategy is not enough, and why
I ended up building three.

## Way one — Minimax with alpha-beta: exact, deterministic, and stubborn

The classical answer is **minimax**: assume both players play perfectly, score
each position from the mover's perspective, and pick the move that maximizes
your worst case. I wrote it in the negamax form, where a child's value is simply
the negation of the parent's, and bolted on the two optimizations every chess
engine has used since the 1970s.

The first is **alpha-beta pruning** — once a move is proven good enough to
refute the opponent's alternative, you stop examining that alternative. It never
changes the answer, only the work. On one mid-game position, searching to depth
four, the unpruned tree visited **33,194** nodes in 10.7 seconds; with
alpha-beta and its friends, **1,787** nodes in 1.0 second. Same value,
roughly an eighteenth of the effort.

The second is a **transposition table** — a cache of positions already
evaluated, so that the many move orders converging on the same board (the
*transpositions* from article one) are scored once. And this is where the
canonical key pays off in a way I find genuinely satisfying: I key the cache by
`canonical_key()`. Two boards that are rotations, reflections, or shape
relabelings of each other are the *same entry*. The symmetry reduction I built
for storage turns out to also be a search accelerator.

There is a subtlety I want to be honest about, because getting it wrong is a
silent bug. The canonical key deliberately does **not** swap colors — it folds
the 192 geometric-and-shape symmetries but keeps track of whose turn it is.
That matters, because a minimax value is *relative to the player to move*. If
the key collapsed color-swapped positions, two boards with opposite values would
share a cache entry and quietly poison each other. Because it doesn't — and
because whose turn it is follows deterministically from the piece counts, itself
symmetry-invariant — caching the value by canonical key is sound. I cache the
value; I never cache the *move*, since the same canonical entry can be reached
in different orientations and the move would point the wrong way. (A whole-branch
review caught exactly one place where I'd let a fail-soft bound leak into a
tie-break and pick a worse move; the fix was to search the root at full width.
I mention it because "exact search" is a promise you have to actually keep.)

When I let this engine run to full depth — all sixteen plies — it stops being a
heuristic player and becomes an **exact solver**. It never guesses, because it
always reaches true terminals. A forced win scores `10000 − (plies to the end)`,
so the number encodes not just *that* you win but *how fast*: a position scored
9997 is a forced win in three plies; −9996 is a forced loss in four. Those exact
values are the anchors my tests are built on, and — as we'll see — they are also
the teacher for the evaluation function.

## When you must stop early, you have to guess — well

Exact-to-the-end only works where the tree is small. Everywhere else, the engine
searches as deep as its time budget allows and then, at the frontier, has to
**estimate** the value of a non-terminal position. That estimator is the
*evaluation function*, and it is where a search engine's personality lives.

Mine is deliberately simple: a weighted sum of six features of the position, all
computed from the mover's perspective. The features count things that matter in
Quantik — how many lines are one legal placement away from completing (weighted
by which side can *legally* place that missing shape, since colors matter only
through the placement rule), how much more mobile you are than your opponent, how
much half-built structure is on the board. A line "wins" when it holds all four
distinct shapes regardless of color, so the features are colorblind about
winning but sharp about legality.

The obvious question is: *what weights?* My first instinct was to hand-pick them
— threats are worth a lot, mobility a little, and so on. But hand-picked weights
are just prejudices with decimal points. I wanted something better, and the game
handed me the answer: **I already own an exact oracle.** The full-depth solver
*is* the ground truth. So I don't guess the weights — I fit them.

## Three depths, and the one place sampling sneaks in

This is the point I most want to be clear about, because it confused even me
until I drew the table. There are three different "depths" in play and they are
independent:

- **Runtime search depth.** When the engine searches to depth `d`, the top `d`
  plies are covered *exhaustively*. Nothing is sampled; alpha-beta only skips
  lines it can prove don't matter. Only the leaves at depth `d` get the
  evaluation estimate.
- **Solve depth.** Full depth (16) reaches true terminals — *fully exact, no
  evaluation used at all* — but only where the remaining tree is small enough.
- **Training-sample depth.** To fit the evaluation weights I need positions
  labeled with their true value, and the only way to get a true label is to
  *solve* the position. Solving is only fast a few plies in. So I sample
  positions **eight to twelve plies into the game**, solve each exactly, and use
  the solver's verdict as the label.

The one place randomness enters this entire pipeline is that third row — *which
positions to label*. It is a property of how I generate training data, not of
how the engine plays. At the board, the engine still exhaustively covers its top
`d` plies from whatever position you hand it. The mid-game sampling bias is a
feature, not a leak: the leaves a depth-limited search actually evaluates are
themselves several plies into the game, so training on mid-game positions trains
on the right distribution.

The fit itself is unglamorous and deliberately dependency-free: 500 solved
positions (428 won, 72 lost for the side to move), a logistic regression in a
few lines of NumPy, done. The interesting part is that it *worked*, and where.
On the training set, the fitted weights lifted overall sign accuracy from 0.826
to 0.884 — but the honest number is the **balanced** one, because the sample is
win-heavy. There, accuracy went from 0.760 to 0.926, driven almost entirely by
the model getting much better at recognizing **losing** positions: loss-recall
climbed from 0.67 to 0.99. On an independent held-out sample, sign accuracy went
from 0.77 to 0.92. The hand-picked weights weren't terrible; they were just
systematically blind to defeat, and the solver taught them to see it.

## Way two and three — sampling and frontiers

Minimax is not the only way to search this tree, and the earlier papers in this
project built the other two. I'll be brief, because they deserve their own
telling, but the contrast is the point.

**Monte-Carlo Tree Search (UCT)** doesn't try to be exact. It samples: play many
random-ish games from the current position, keep statistics on which first moves
tend to win, and spend more simulations on the moves that look promising
(balancing exploration and exploitation with the UCB1 formula). It never hits an
intractability wall, because it never tries to be exhaustive — it just gets a
noisier answer the less time you give it. It is the natural choice exactly where
minimax is helpless: the wide-open early game.

**Beam search** keeps a bounded *frontier* — the best `k` positions at each ply
— and marches level by level toward the terminals, pruning the rest. It trades
minimax's completeness for a fixed memory budget, and it shines when you want
broad, shallow coverage of the reachable terminal states rather than a deep
principal variation.

Three engines, one canonical representation, three different bargains with the
same intractability:

| Engine | Bargain | Strongest where |
|--------|---------|-----------------|
| Minimax + fitted eval | Exact when it can be, learned guess when it can't | Mid-to-late game; anywhere the tree is small |
| MCTS / UCT | Never exact, never stuck; noisy but always answers | The wide-open early game |
| Beam search | Bounded-memory exhaustive frontier | Broad shallow coverage of terminals |

## Does it actually play?

I'll close the loop with the only test that matters to my wife: does it win? I
played the fitted-evaluation minimax engine against a random mover and against a
1,500-iteration UCT engine, from both sides. It won every game — 8 out of 8 in
each matchup.

I want to be honest about what that does and doesn't prove. Beating a random
mover is table stakes. The 1,500-iteration UCT baseline is a *weak* opponent —
a stronger MCTS budget would be a real fight, and I haven't run that yet.
"8 out of 8" is encouraging, not a coronation. The result I actually trust is
the boring one: on positions the solver can adjudicate, the fitted evaluation
agrees with ground truth far more often than the hand-picked one did, and the
exact solver is, by construction, never wrong where it runs to the end.

## The part I'm most interested in next

Here is what I didn't expect to find, and what I'll build next. Because all three
engines key off the *same* canonical name, they are not really three separate
programs — they are three lenses on one shared state space, and they can help
each other:

- The exact solver can **fill a shared opening book** — the position database is
  keyed by canonical key and is engine-agnostic, so a batch of exact solves
  becomes ground truth that MCTS and beam search read for free.
- A **hybrid player** could let UCT handle the intractable opening and hand off
  to the exact solver the moment few enough cells remain — each engine used only
  in the regime where it is strong, and the wall sidestepped entirely.
- The fitted evaluation could replace MCTS's random rollouts with a *guided*
  one.

That last thread — engines teaching each other, an exact oracle correcting a
statistical one — is really the same question I ended the first article on, in
disguise. I asked then whether an AI could become not only a strong opponent but
a useful *teacher*. It turns out the first thing these engines can teach is one
another.

So, a question for you before the next installment: when you get beaten at a
game the way I kept getting beaten at this one, do you reach for calculation, or
for the pattern your opponent clearly sees and you don't? Because I built the
calculator — and I'm increasingly convinced the interesting part was never the
calculation.

*The library is open source: `mberlanda/quantik-core-py` (on PyPI as
`quantik-core`). The engine, the evaluation, and the weight-fitting pipeline
described here live in `quantik_core.minimax`, `quantik_core.evaluation`, and
`tuning/`; the numbers come from `examples/minimax_benchmark.py`. Subscribe to
follow the series.*
