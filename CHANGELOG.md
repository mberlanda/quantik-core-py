# Changelog

All notable changes to `quantik-core` are documented here.

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
