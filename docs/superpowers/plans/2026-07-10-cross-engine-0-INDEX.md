# Cross-Engine Cooperation Follow-ups — Index

Four independent follow-up plans that build on the merged minimax + fitted-eval
work (PR #17). Each is self-contained, TDD, and executable on a fresh context by
a less-powerful model. Do them in **any order** — they don't depend on each
other — though the suggested order below front-loads the cheapest wins.

| # | Plan | Scope | Coverage gate? | Rough size | Status |
|---|------|-------|----------------|-----------|--------|
| 1 | `...cross-engine-1-midgame-benchmark.md` | Example + smoke test only (`examples/cross_engine_benchmark.py`) | No (examples not measured) | Small | ✅ Done (branch `feat/cross-engine-midgame-benchmark`) |
| 2 | `...cross-engine-2-opening-book-filler.md` | Tool + tests (`tuning/fill_opening_book.py`) | No | Small–medium | Not started |
| 3 | `...cross-engine-3-eval-guided-mcts.md` | **Library change** (`src/quantik_core/mcts.py`) | **Yes — ./dev-check.sh, ≥90%** | Medium | Not started |
| 4 | `...cross-engine-4-hybrid-player.md` | **New library module** (`src/quantik_core/hybrid.py`) | **Yes — ./dev-check.sh, ≥90%** | Medium | Not started |

## Shared conventions (all four)
- Work in an isolated worktree/branch; open a PR per plan (or bundle 1+2 and 3+4 if you prefer fewer PRs — they don't conflict).
- Local env per `AGENTS.md`: create `.venv`, `pip install -e ".[dev,cbor]"`.
- `./auto-lint.sh` before every commit. Plans 3 and 4 additionally require `./dev-check.sh` (full suite + black + flake8 + coverage ≥ 90%) before their final commit; plans 1 and 2 only need their own test files green.
- Commit trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Reuse `tuning.build_dataset.sample_states(n, seed)` for mid-game position sampling (plans 1 & 2). It returns non-terminal 8-tuples deduped by canonical key, sampled 8–12 plies in — the range where exact solves are fast.

## Why these exist (context)
The three engines (minimax, MCTS/UCT, beam) key off the same `canonical_key()`,
so they share a state identity and can help each other. These plans turn that
into working code: measure them against the exact solver (1), feed the solver's
ground truth into the shared opening book (2), let the fitted eval guide MCTS
rollouts (3), and combine sampling-in-the-opening with exact-solve-in-the-endgame
(4). Background: `docs/MINIMAX.md` (three-depths and cooperation sections) and
`docs/research/2026-07-10-alpha-beta-eval-vs-mcts.md` (Future Work section).
