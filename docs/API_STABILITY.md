# API Stability

`quantik_core` top-level imports are the stable 1.x API:

- `State`
- `Move`
- `validate_move`
- `apply_move`
- `generate_legal_moves`
- `generate_legal_moves_list`
- `QuantikBoard`
- `PlayerInventory`
- `GameResult`
- `MoveRecord`
- `SymmetryHandler`
- `SymmetryTransform`
- `bb_to_qfen`
- `bb_from_qfen`
- `ValidationResult`
- `Bitboard`
- `PlayerId`
- `VERSION`
- `FLAG_CANON`

Specialized modules are importable directly, but may evolve in minor releases until their contracts are promoted here:

- `quantik_core.memory`
- `quantik_core.storage`
- `quantik_core.profiling`
- `quantik_core.mcts`
- `quantik_core.opening_book`

## Winner Attribution

`has_winning_line()` answers whether a completed Quantik line exists. Static winner attribution without move history is count-based today; board-level APIs should be preferred when move history matters.

## Checkpoint Trust Boundary

`GameTree.load_checkpoint()` reads pickle data. Only load checkpoints created by trusted local code.
