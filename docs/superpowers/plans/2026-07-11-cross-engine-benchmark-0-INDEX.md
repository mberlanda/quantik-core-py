# Cross-Engine Benchmark (GH issue #24) — Index

Five sequential plans that build a methodologically consistent, reproducible
cross-engine benchmark for `MinimaxEngine`, `MCTSEngine`, and
`BeamSearchEngine` (plus a random-mover baseline). They implement GH issue
#24 **and** the "Cross-engine benchmark consistency requirements" brief:
shared versioned position dataset, exact reference solutions, separate
fixed-resource vs algorithm-native families, effective-work metrics,
multi-seed stochastic evaluation, side-balanced head-to-head, correctness
preflight, reproducible result bundles, and auto-generated Markdown tables.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans. Execute the parts **in order** — each part's
> "Consumes" interfaces come from the previous parts.

| # | Plan | Scope | Coverage gate? | Rough size |
|---|------|-------|----------------|-----------|
| 1 | `...benchmark-1-engine-time-limits.md` | **Library change**: optional `time_limit_s` on `MCTSConfig` and `BeamSearchConfig` | **Yes — ./dev-check.sh, ≥90%** | Small |
| 2 | `...benchmark-2-dataset-reference.md` | New `benchmarks/` package: phase-bucketed dataset + exact reference solver | No (benchmarks/ not in coverage scope, tests still required) | Medium |
| 3 | `...benchmark-3-adapters-preflight.md` | Engine adapters with uniform metrics, stats helpers, correctness preflight | No | Medium |
| 4 | `...benchmark-4-runners.md` | Agreement, head-to-head, and stability runners + aggregations | No | Medium |
| 5 | `...benchmark-5-cli-report-docs.md` | Result bundle + Markdown report, CLI rewrite of `examples/cross_engine_benchmark.py`, docs, committed dataset artifact | **Yes — ./dev-check.sh** (final gate) | Medium–large |

## Progress ledger (2026-07-11)

Committed on branch `worktree-cross-engine-benchmark-24`:

- Part 1: engine `time_limit_s` support for MCTS and beam search, plus review
  fixes for finite validation and MCTS positional-argument compatibility.
- Part 2: `benchmarks.dataset` and `benchmarks.reference`.
- Part 3: metrics helpers, engine adapters, and correctness preflight.
- Part 4: agreement/cost, head-to-head, and stability runners.
- Part 5 started: result bundles, Markdown reports, and the
  `examples/cross_engine_benchmark.py` `dataset`/`run`/`report` CLI.

Fresh local verification:

- `tests/test_benchmark_*.py` module set: 73 passed in 99 seconds with
  `--no-cov`.
- `tests/test_examples_demos.py`: 18 passed with `--no-cov`.

Remaining before handoff/merge:

- Commit documentation updates and this progress ledger.
- Generate and commit `benchmarks/positions-v1.json`.
- Smoke-run the real artifact and inspect the generated Markdown report.
- Run `./dev-check.sh`.
- Push, request fresh Copilot review on PR #28, then address any new comments.

## Shared conventions (all five)

- Work on one feature branch (suggested: `feat/cross-engine-benchmark-24`),
  one commit per task, PR at the end referencing issue #24.
- Local env per `AGENTS.md`:
  ```bash
  if [ ! -d ".venv" ]; then
      python -m venv .venv
      .venv/bin/python -m pip install -e ".[dev,cbor]"
  fi
  PYTHON=".venv/bin/python"
  ```
- Format before every commit: `.venv/bin/python -m black src tests examples benchmarks`
  (benchmarks/ is not in dev-check's black target list, but flake8 runs on `.`,
  so keep it clean anyway).
- Commit trailer on every commit: your standard Claude co-author trailer,
  e.g. `Co-Authored-By: Claude <noreply@anthropic.com>`.
- Every new test must be FAST (each new test file < ~60s): tiny MCTS
  iteration counts (≤200), small beam widths (≤8), near-endgame anchor
  positions. The canonical fast anchor is QFEN `.ba./..CC/DcbD/cA.A`
  (8 pieces placed, P1 to move, three immediately winning moves — one
  completes a line at shape=3/pos=5, the other two leave P0 with no legal
  reply; exact-solves in well under a second).
- Never regenerate the dataset per engine; all runners consume one loaded,
  checksum-verified dataset payload.

## Key facts about this codebase (read once, they matter everywhere)

- A Quantik game NEVER draws and never exceeds 16 plies: a completed line
  wins for the mover; a side with no legal moves loses. So "remaining
  plies" from a position with `p` pieces placed is `16 - p`, and a
  completed iterative-deepening search of depth ≥ `16 - p` saw only true
  terminal leaves — i.e. it is **exact** (no heuristic cutoff).
- One ply == one piece placed, so "pieces placed" and "plies from empty"
  are the same number. Phase buckets: opening 0–4 pieces, early_mid 5–7,
  late_mid 8–11, endgame 12–16.
- `MinimaxEngine(MinimaxConfig(max_depth=16)).solve(state)` is the exact
  solver, but it rejects (raises on) states with no legal moves, and a
  child that is itself terminal must be scored directly as a win for the
  mover instead of solved (see `benchmarks/reference.py` in part 2).
- `MCTSEngine.__init__` calls the **global** `random.seed(config.random_seed)`.
  Determinism therefore requires constructing a FRESH engine per move
  selection — never reuse an `MCTSEngine` across measured calls.
- `State.canonical_key()` collapses the 192 board symmetries; the dataset
  dedups positions by it. `State.to_qfen()` / `State.from_qfen()` (module
  `quantik_core.core`) serialize positions.
- Exact-solve cost cliff: positions ≥ 8 plies solve in ≲1.1s; 5–7 plies can
  take much longer; the open game is intractable in pure Python. Hence the
  per-position solve budget and the opening bucket being heuristic-only.

## Deliberate scope decisions (do not "fix" these while executing)

- **HybridPlayer is excluded from v1.** Issue #24 scopes the three base
  engines + a random baseline. The adapter layer (part 3) makes adding a
  hybrid adapter a small follow-up; don't add it now (YAGNI).
- **Transposition-table hit/miss counts and duplicate-state counts are
  not recorded.** The brief lists them, but `MinimaxResult` and the engine
  stats don't expose them; recording them would require library changes
  beyond part 1's scope. Note as future work in the PR, don't extend the
  engines.
- **Beam search's `time_limit_s` is level-granular** (checked between
  depth levels), so it can overshoot the fixed-family budget. The harness
  reports MEASURED wall time per move, which keeps comparisons honest;
  docs and report call this out explicitly.
- **The opening bucket never gets exact references** — it is the separate
  heuristic benchmark the brief requires, not a gap.

## Why this exists (context)

PR #22 fixed two MCTS bugs that had made it non-functional; all older MCTS
numbers are stale. The two existing scripts
(`examples/cross_engine_benchmark.py`, `examples/minimax_benchmark.py`)
hardcode every parameter and mix methodologically different measurements.
Issue #24 asks for one CLI-configurable harness covering all three engines;
the consistency brief (reproduced in `docs/BENCHMARKS.md` by part 5) defines
what "methodologically sound" means. Background: `docs/MINIMAX.md`,
`docs/MCTS.md`, `docs/BEAM_SEARCH.md`,
`docs/research/2026-07-10-alpha-beta-eval-vs-mcts.md`.
