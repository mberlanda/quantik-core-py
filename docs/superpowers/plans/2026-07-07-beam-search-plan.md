# Implementation Plan — Beam Search for Quantik MCTS

Spec: `docs/superpowers/specs/2026-07-07-beam-search-design.md` (read it first; it is the contract).

Working directory: this worktree. Python: `.venv/bin/python` (already provisioned with `pip install -e ".[dev,cbor]"`).

## Task 1 — Tests first (TDD)

Create `tests/test_beam_search.py` covering the 10 scenarios in the spec's Testing
section. Model structure and fixtures on `tests/test_mcts.py` (QFEN strings, seeded
configs, small iteration/beam budgets so the suite stays fast — target < 20s for the
file). Run them: they must fail with `ModuleNotFoundError` / assertion errors, not
collection errors.

## Task 2 — Implementation

Create `src/quantik_core/beam_search.py` implementing `BeamSearchConfig`,
`BeamLeaf`, `BeamSearchResult`, `BeamSearchEngine` exactly per spec. Reuse:

- `quantik_core`: `State`, `Move`, `generate_legal_moves`, `apply_move`
- `quantik_core.game_utils`: `check_game_winner`, `WinStatus`
- `quantik_core.memory.compact_tree`: `CompactGameTree`, `NODE_FLAG_*`

Match the style of `src/quantik_core/mcts.py` (docstrings, typing, numpy scalar
handling when writing node fields). Private `random.Random(config.random_seed)`
— do NOT seed the global RNG.

## Task 3 — Quality gates

1. `./auto-lint.sh`
2. `./dev-check.sh` (runs full suite; 90% total coverage gate, mypy, flake8 must pass)
3. Commit in two commits: tests, then implementation (or one commit if the runner
   requires green; then squash message `feat: parametrizable beam search engine`).

## Guardrails

- Do not modify `mcts.py`, `compact_tree.py`, `__init__.py`, or any existing test.
- No new dependencies.
- All commands prefixed with `rtk` where applicable (see CLAUDE.md).
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
