# Quantik Core

A high-performance Python library for manipulating Quantik game states, optimized for Monte Carlo simulations, game analysis, and AI engines.

## What is Quantik?

Quantik is an elegant 4×4 abstract strategy game where players compete to complete lines with all four unique shapes.

### Game Rules

- **Board**: 4×4 grid (16 squares)
- **Pieces**: 4 different shapes (A, B, C, D) in 2 colors (one per player)
- **Objective**: Be the first to complete a **row**, **column**, or **2×2 zone** containing all four different shapes
- **Gameplay**: 
  - Players alternate placing one of their remaining pieces on an empty square
  - A piece cannot be placed if the opponent already has the same shape in the target square's row, column, or 2×2 zone
  - Colors don't matter for winning - only the presence of all four shapes in a line

### Example Victory

```
A B C D  ← Row with all 4 shapes = WIN!
. . . .
. . . .
. . . .
```

## Features

This library provides the core foundation for building:

- **Monte Carlo Tree Search (MCTS)** engines
- **Game analysis** and position evaluation systems  
- **AI training** and recommendation engines
- **Opening book** generation and endgame databases
- **Statistical analysis** of game patterns
- **Game engines** and tournament systems
- **Research tools** for combinatorial game theory

**Current Implementation:**
- **State Representation**: Complete bitboard-based game state management
- **Serialization**: Binary, QFEN, and CBOR formats
- **Canonicalization**: Symmetry-aware position normalization
- **Move Generation**: Coming in next release
- **Game Logic**: Win detection and move validation (planned)

## Core Capabilities

- **Blazing Fast Operations**: Bitboard-based representation enables O(1) move generation and win detection
- **Compact Memory Footprint**: Game states fit in just 16 bytes with optional 18-byte canonical serialization
- **Symmetry Normalization**: Automatic canonicalization under rotations, reflections, color swaps, and shape relabeling
- **Cross-Language Compatibility**: Binary format designed for interoperability with Go, Rust, and other engines
- **Human-Readable Format**: QFEN (Quantik FEN) notation for debugging and documentation
- **Self-Describing Serialization**: CBOR-based format for robust data exchange

## Installation

```bash
pip install quantik-core
```

## Quick Start

```python
from quantik_core import State

# Create an empty game state
state = State.empty()

# Create a position using QFEN notation
state = State.from_qfen("A.../..b./.c../...D")

# Convert to human-readable format
qfen = state.to_qfen()
print(f"Position: {qfen}")  # Output: A.../..b./.c../...D

# Get canonical representation for symmetry analysis
canonical_key = state.canonical_key()
print(f"Canonical key: {canonical_key.hex()}")

# Serialize to binary format (18 bytes)
binary_data = state.pack()
restored_state = State.unpack(binary_data)

# Serialize to CBOR for cross-language compatibility
cbor_data = state.to_cbor(canon=True, meta={"game_id": 123})
restored_from_cbor = State.from_cbor(cbor_data)
```

## Performance

- **State Operations**: Bitboard-based representation enables fast position manipulation
- **Canonicalization**: <1µs per position with precomputed lookup tables
- **Memory Usage**: 16 bytes per game state + 1MB for transformation LUTs
- **Serialization**: 18-byte binary format, human-readable QFEN, or self-describing CBOR

## Use Cases

### Position Analysis and Canonicalization
```python
from quantik_core import State

# Create different equivalent positions
pos1 = State.from_qfen("A.../..../..../....") 
pos2 = State.from_qfen("..../..../..../.a..")  # Rotated + color swapped

# Both have the same canonical representation
assert pos1.canonical_key() == pos2.canonical_key()
```

### Database Storage and Retrieval
```python
# Use canonical keys as database indices
positions_db = {}
canonical_key = state.canonical_key()
positions_db[canonical_key] = {"eval": 0.75, "visits": 1000}
```

### Cross-Language Data Exchange
```python
# Save position with metadata for other engines
data = state.to_cbor(
    canon=True,
    mc=5000,  # Monte Carlo simulations
    meta={"depth": 12, "engine": "quantik-py-v1"}
)

# Binary format for high-performance applications
binary = state.pack()  # Just 18 bytes
```

## Technical Details

- **Representation**: 8 disjoint 16-bit bitboards (one per color-shape combination)
- **Symmetries**: Dihedral group D4 (8 rotations/reflections) × color swap × shape permutations = 384 total
- **Serialization**: Versioned binary format with little-endian 16-bit words
- **Canonicalization**: Lexicographically minimal representation across symmetry orbit

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Citation

If you use this library in research, please cite:
```bibtex
@software{quantik_core,
  title={Quantik Core: High-Performance Game State Manipulation},
  author={Mauro Berlanda},
  year={2025},
  url={https://github.com/mberlanda/quantik-core-py}
}
```
