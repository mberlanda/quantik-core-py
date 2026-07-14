# Changelog

All notable changes to `quantik-core` are documented here.

## Unreleased

## 1.1.0 - 2026-07-14

### Added

- Added `quantik_core.opening_book_summary`, a lightweight SQLite consumer that
  exports `opening-book-summary.v1` JSON for Rust/Python depth-book consistency
  checks.
- Added a GitHub Actions opening-book consistency job that uses
  `mberlanda/quantik-core-contracts/actions/opening-book-consistency@v1.1.0`
  to compare the Python summary against a Rust-generated depth-4 opening book.
- Added `BeamSearchEngine`, a parametrizable, memory-bounded beam search that guarantees reaching true terminal Quantik states (win/loss by blocked player) by deduplicating candidates per depth via `State.canonical_key()`, ranking them mover-relative, and pruning to a configurable `beam_width` while sharing the `CompactGameTree` structure used by MCTS.
- Added `BeamSearchResult.root_player` and `BeamSearchResult.frontier_leaves` (the live, non-terminal leaves remaining at `max_depth_reached`).
- Added `BeamSearchConfig.rollout_schedule` for a depth-dependent playout budget in the built-in evaluator (pairing with `beam_schedule` to be wide-and-cheap on exhaustive levels and precise on the pruned tail), plus a `stats["rollouts"]` counter exposing the exact playout spend.
- Added `BeamSearchResult.ranked_root_moves()`, aggregating every collected leaf by its first move from the root into `RankedRootMove` entries (`best_value`, `mean_value`, `win_probability`, `leaf_count`, `has_terminal_win`) for ranking multiple midgame options.
- Added `examples/beam_search_demo.py` showcasing full-depth terminal reachability, tactical win detection with the full winning principal variation, a beam-width memory sweep, a pluggable custom evaluator, and ranked root move statistics from a midgame position.
- Added `docs/BEAM_SEARCH.md` documenting the algorithm, configuration, result fields, ranked root moves, memory model, and the caveats of sharing a `CompactGameTree` with `MCTSEngine`.
- Added `BeamSearchConfig.beam_schedule`, a depth-dependent beam width (last entry extends to deeper levels) so a search can keep an exhaustive shallow prefix and switch to guided sampling once the canonical state space grows too large, plus the `UNIQUE_CANONICAL_STATES_PER_DEPTH` constant for building such schedules.
- Added symmetry-multiplicity accounting: `BeamLeaf.multiplicity` and `RankedRootMove.total_multiplicity` track how many raw (pre-canonicalization) move sequences a leaf represents via path-count accumulation, `RankedRootMove.mean_value` is now multiplicity-weighted, and survivor/terminal tree nodes are inserted with their accumulated multiplicity instead of the previous implicit default of 1.
- Added the cross-engine benchmark harness for GH issue #24: shared checksummed position datasets with exact references in `benchmarks/`, a `dataset`/`run`/`report` CLI in `examples/cross_engine_benchmark.py`, fixed-resource and algorithm-native benchmark families, correctness preflight, seed-stability aggregation, paired head-to-head reporting, reproducible result bundles, and generated Markdown reports documented in `docs/BENCHMARKS.md`.
- Added optional wall-clock `time_limit_s` budgets to `MCTSConfig` and `BeamSearchConfig` for fixed-resource benchmark runs.

### Changed

- Bumped the package and supported contracts release to `1.1.0`, including
  fixture contract versions and the contracts validation action.

### Fixed

- Fixed `examples/beam_search_demo.py`'s move formatting to reflect the actual mover (QFEN convention: uppercase = player 0, lowercase = player 1) instead of always rendering shapes uppercase.
- Fixed `examples/mcts_demo.py`'s move formatting with the same player-aware convention (it had the identical uppercase-only bug).
- Fixed `CompactGameTree.create_root_node` to derive `player_turn` from the root state's own piece-count parity instead of hardcoding player 0, so a tree can be correctly rooted at any mid-game (player-1-to-move) state.
- Fixed `MCTSConfig.use_transposition_table`, which was declared but never consulted: `MCTSEngine._expand` now forwards it to `CompactGameTree.add_child_node`, and passing `False` skips the transposition merge so revisited canonical states always allocate a fresh node.
- Fixed `auto-lint.sh` failing on a fresh environment by adding the missing `autopep8` dependency to the `dev` extra.
- Corrected the MCTS throughput claims in `README.md` and `docs/MCTS.md` (previously an unverified 20,000+ iterations/second) to the measured ~150-210 iterations/second for the current pure-Python engine from the empty board.

## 1.0.0 - 2026-06-22

### Added

- Added validated `Move` objects, move validation, move application, and legal move generation.
- Added `QuantikBoard` with inventory tracking, move history, undo, legal moves, win detection, and stalemate handling.
- Added QFEN parsing and serialization helpers in a dedicated `qfen` module.
- Added symmetry handling and canonical keys for rotations, reflections, color swaps, and shape permutations.
- Added game statistics utilities and win-probability analysis examples.
- Added compact bitboard, compact state, and compact tree storage for memory-efficient analysis.
- Added binary and optional CBOR serialization helpers for state exchange.
- Added memory profiling and benchmark utilities.
- Added MCTS search, an SQLite-backed opening book, and puzzle-generation examples.

### Changed

- Reworked package structure under `src/quantik_core`.
- Integrated `CompactBitboard` as the internal `State` storage while preserving the tuple `bb` property.
- Consolidated duplicated constants, validation helpers, bitboard index calculations, piece counting, and endgame detection.
- Dropped Python 3.9 support and set the supported range to Python 3.10 through 3.13.
- Stabilized top-level public exports for the 1.x API.
- Made memory package exports and symmetry lookup tables lazy to reduce import-time coupling.

### Fixed

- Fixed malformed QFEN fixtures and added fixture validation tests.
- Fixed validation of bitboard values outside the 4x4 board.
- Fixed explicit `player=0` handling in board legal-move queries.
- Fixed package version mismatch between runtime imports and package metadata.
- Fixed stale PyPI and README links that pointed to `mauroberlanda/quantik-core-py` instead of `mberlanda/quantik-core-py`.
- Fixed invalid five-dot QFEN examples in README and docstrings.

### Security

- Documented checkpoint loading as trusted-only release surface because it uses pickle internally.

### Migration Notes

- `quantik_core` top-level imports now expose only the documented stable API.
- Memory, storage, profiling, MCTS, and opening-book APIs remain available from their subpackages and are documented as specialized APIs.
