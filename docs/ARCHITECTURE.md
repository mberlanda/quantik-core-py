# Architecture

`quantik-core` is organized around a small stable core plus specialized analysis modules.

## Core State

- `quantik_core.core.State` owns immutable game-state serialization.
- `quantik_core.qfen` converts between QFEN and the internal bitboard tuple.
- `quantik_core.symmetry` computes canonical position keys.

## Game Rules

- `quantik_core.move` validates and applies individual moves.
- `quantik_core.board` provides a higher-level board with inventories and move history.
- `quantik_core.game_utils` contains shared rule helpers.
- `quantik_core.state_validator` validates static bitboard legality.

## Analysis and Storage

- `quantik_core.memory` contains compact in-memory representations.
- `quantik_core.storage` contains serialization and checkpoint-oriented helpers.
- `quantik_core.game_stats` contains game-tree statistics.
- `quantik_core.mcts` provides Monte Carlo Tree Search.
- `quantik_core.opening_book` provides SQLite-backed opening-book storage.
- `quantik_core.profiling` contains benchmark and memory measurement helpers.

## Public Surface

The stable public API is exported from `quantik_core`. Subpackages are available for advanced use, but top-level imports are the compatibility promise for 1.x.
