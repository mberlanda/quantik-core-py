# Search Telemetry (Python)

This document describes the `search_telemetry` surface shared by the MCTS,
beam, and minimax engines in this package: what each event counter means, how
each engine maps its internal values onto a common `[-1, 1]` scale, when a
telemetry record's root-move identity is trustworthy, and how to export draft
JSONL rows for offline analysis.

## 1. Purpose

`search-summary.v1` is a proposed but not-yet-registered data contract for
search diagnostics (event counters, root-move statistics, principal
variation) emitted by any of this package's search engines. Registration
requires that the Rust and Python implementations expose the same observable
semantics before any artifact carries the finished contract label. This is
PR 2 of a three-part workstream: the Rust surface (PR 1, merged), this Python
mirror (PR 2), and contract registration (PR 3, which flips the draft label).

See also:
- Rust source doc: `quantik-core-rust/docs/search-telemetry.md` — the
  merged prose reference this document mirrors.
- Contract doc (sibling repo `quantik-core-contracts`):
  `docs/search-summary-v1.md` — the registration target this surface feeds.

## 2. Normative event semantics

The counters are defined by **search events**, not by whichever variables an
engine already happens to have. A definition names one event; every engine
increments the counter at exactly the code path where that event occurs.

| Counter | Event (same in every engine) |
| --- | --- |
| `expanded_nodes` | A state's successor set was computed by the search. |
| `generated_nodes` | A successor state was constructed. |
| `transposition_hits` | A cached **search result or subtree** was reused via state-keyed lookup instead of being searched again. |
| `canonical_dedup_hits` | A generated state was merged with, or skipped in favor of, an already-present duplicate — **without reusing any search result**. |
| `terminal_hits` | A state was determined terminal during tree search. Rollout outcomes are excluded in every engine. |
| `tablebase_hits` | A value/policy result was obtained from an external probe artifact instead of search. Always `0` until such an artifact exists. |

Counters are not mutually exclusive: a state whose enumeration finds zero legal
moves is both expanded and terminal. Identical semantics do not imply
comparable magnitudes — cross-engine workload comparison belongs to
`elapsed_ms` only.

## 3. Per-engine hook mapping (Python)

| Counter | MCTS | Beam | Minimax |
| --- | --- | --- | --- |
| `expanded_nodes` | +1 per `_expand`, right after `generate_legal_moves` computes the node's successor set (the no-legal-moves case included; a node already terminal by a winning line returns before enumeration and is not counted) | +1 per frontier entry processed in `_expand_frontier` (incl. the no-legal-moves case) | +1 per successor-set computation: once for the root moves in `search()`, then once right after `generate_legal_moves_list` in each `_negamax` node (the depth-0 leaf and the no-legal-moves node included; a `has_winning_line` node returns before enumeration and is not counted) |
| `generated_nodes` | +1 per candidate move whose successor state is constructed in the `_expand` loop (every `apply_move`/`State(...)`, including states re-derived for already-visited moves) | +1 per `apply_move` on a candidate move in `_expand_moves` | += `len(ordered)` at each `_children(...)` call (every move applied before dedup) |
| `transposition_hits` | +1 when `add_child_node` reuses an existing node (node count unchanged) **and** `use_transposition_table` | **0** — beam never reuses search results | +1 at each TT early-return in `_negamax`: the `Bound.EXACT` return and the narrowed `alpha >= beta` return |
| `canonical_dedup_hits` | **0** (structural — MCTS canonical merging is reflected in `root_identity_preserved`, not this counter) | +1 at the `if key in candidates` dedup-merge branch in `_expand_moves`; also bumps a private `root_dedup_hits` when `depth == 1` | += `len(ordered) - len(children)` (dedup skips) at each `_children(...)` call |
| `terminal_hits` | +1 when `_expand` determines a node terminal (winner, or no legal moves). Rollouts never instrumented | +1 per terminal child (winner branch) and per no-legal-moves frontier entry. Rollouts never instrumented | +1 at the `has_winning_line` return and the `not moves` return in `_negamax` |
| `tablebase_hits` | 0 | 0 | 0 |

`PolicyMassKind` per engine: MCTS = `Visits` (root visit counts), beam =
`Multiplicity` (leaf multiplicity grouped by first move), minimax = `None`
(`root_moves` carry exact `q_value`s from the per-move score vector,
`policy_mass = 0`).

Distinctions worth calling out explicitly:

- **Result reuse vs. duplicate merging.** `transposition_hits` requires that a
  previously computed result or subtree was reused. Beam canonical dedup and
  minimax child dedup merge duplicates but re-derive nothing, so they land in
  `canonical_dedup_hits`. Beam dedup must never masquerade as transposition
  reuse.
- **Rollout terminals are excluded from `terminal_hits` in EVERY engine.** MCTS
  `_simulate`/rollouts and beam `_rollout`/`_default_evaluate` are never
  instrumented.
- **MCTS counts events, not distinct nodes.** `_expand` recomputes a node's
  successor set and re-derives already-visited children's states on every pass,
  so a node revisited across iterations contributes an `expanded_nodes` event
  each time and its siblings' constructions recur in `generated_nodes`. This is
  faithful to the event definitions but means the Python MCTS magnitudes are
  higher than Rust's, whose `expand` generates a node's moves once at creation
  and constructs exactly one successor per call via `untried_moves`. Per the
  Section 2 note, only `elapsed_ms` is meant for workload comparison.

### Structural zeros called out explicitly

- **MCTS `canonical_dedup_hits` is always 0.** MCTS collapse is a root-identity
  concern (reported via `root_identity_preserved`), not a counter.
- **Beam `transposition_hits` is always 0.** Beam never reuses a search result.
- **`tablebase_hits` is always 0** in all three engines.

## 4. Value semantics

Every `root_value` and every `RootMoveStat.q_value` lies in `[-1.0, 1.0]`,
positive is good for the **root player**, and `|v| == 1.0` is reserved for
**proven** results (terminal nodes, mates). Every unproven (sampled or
heuristic) estimate is clamped to `[-UNPROVEN_VALUE_BOUND,
UNPROVEN_VALUE_BOUND]` where `UNPROVEN_VALUE_BOUND = 1.0 - 1e-6`, via
`clamp_unproven`, so a sampled/heuristic value can never be mistaken for a
proven `±1.0`.

Per-engine value mapping:

- **MCTS**: win probability `p` for the root player maps to `2p - 1`. A
  terminal child (and a terminal best child's `root_value`) is PROVEN: value
  derived from the node's `terminal_value` (P0-perspective, negated when the
  root mover is player 1) and reported as exact `±1.0`. Every non-terminal
  child's rollout-sampled `2p - 1` goes through `clamp_unproven`.
- **Beam**: a ranked root move's `q_value` is exact `1.0` only when
  `RankedRootMove.has_terminal_win` is set **and** `best_value >= 1.0` (a
  proven root-player win). `RankedRootMove` carries no flag for a proven
  *loss*: once a terminal loss and a sampled loss both collapse to
  `best_value == -1.0` they are indistinguishable, so every other case
  (**including a proven loss**) goes through `clamp_unproven` → a proven loss
  is conservatively reported as `-UNPROVEN_VALUE_BOUND`, not exactly `-1.0`.
  `root_value` follows the same rule at `best_leaf`: exact `±1.0` when
  `best_leaf.is_terminal`, `clamp_unproven` otherwise.
- **Minimax**: `minimax_q_from_score(score, win)`. Mate scores are `±(win -
  ply)` with `ply <= 16`, so a proven result satisfies `|score| >= win - 16.0`
  and maps to exactly `±1.0`; everything else is squashed with the smooth,
  monotonic, sign-preserving `score / (1.0 + abs(score))`, strictly inside
  `(-1, 1)`. `score` is already in **root-player perspective** (`_search_root`
  negates each child's negamax value).

## 5. Root identity

`root_identity_preserved` is `false` whenever canonical/transposition merging
may have collapsed distinct root moves onto shared statistics. The Python
rules differ from Rust's because Python's MCTS `_expand` canonical-dedups
children unconditionally (its `existing_states` guard keys on
`State.canonical_key()`), so symmetric root moves collapse **even with the
transposition table off**:

- **MCTS**: `root_identity_preserved = (not use_transposition_table) and (the
  legal root moves all produce distinct child canonical keys)`. The empty
  board's symmetric first moves therefore make it `false` regardless of the
  transposition-table setting; TT on always makes it `false` too. This is
  stricter than Rust, whose rule is preserved iff the transposition table is
  off — consequently, the empty-board MCTS row that Rust's exporter emits is
  skipped in the Python exporter.
- **Minimax**: preserved iff `dedup_children` is `false`.
- **Beam**: best-effort — preserved iff no depth-1 canonical dedup occurred
  (`root_dedup_hits == 0`). Symmetric positions may skip even with a default
  config; the empty board's beam row is skipped for this reason (depth-1
  dedup occurs there too).

The exporter **skips** (returns `None`, a legitimate skip — not an error) any
row whose telemetry has `root_identity_preserved == false`. It **raises**
`ValueError` for an `action_index` outside `[0, 64)` (matching Rust's `Err`).
Rust checks only `>= 64` because its `action_index` is an unsigned `u8`;
Python's is a signed `int`, so the exporter also rejects negative indices,
which would otherwise silently index the dense policy/value arrays from the
end.

For telemetry-quality export runs: MCTS `use_transposition_table=False`,
minimax `dedup_children=False`, and treat beam skips as expected.

## 6. Exporter usage

Run the draft exporter example against a small fixed position set (the empty
board plus two mid-game positions), across all three engines:

```sh
python examples/search_summary_export.py --out <path>
```

This writes one JSON line per completed root search whose root identity was
preserved, using the schema label `search-summary.v1-draft`
(`SEARCH_SUMMARY_DRAFT_SCHEMA` in `quantik_core.search_summary`). Rows that are
skipped for an unpreserved root identity are logged to stderr, not written.

**`search-summary.v1` (the non-draft label) must not be emitted anywhere
until the contract is registered in `quantik-core-contracts`.** The draft
label exists specifically so downstream consumers can distinguish
work-in-progress rows from a finished, versioned contract.
