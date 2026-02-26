# Quantik Core

[![codecov](https://codecov.io/github/mberlanda/quantik-core-py/graph/badge.svg?token=CDLH126DO2)](https://codecov.io/github/mberlanda/quantik-core-py)

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
A b C d  ← Row with all 4 shapes = WIN!
. . . .
. . . .
. . . .
```

## QFEN Notation

Board states are represented using **QFEN** (Quantik FEN) notation - a human-readable format inspired by chess FEN.

### Format Structure

QFEN uses 4 slash-separated ranks representing rows from top to bottom:
```
rank1/rank2/rank3/rank4
```

### 4×4 Grid Layout
```
┌─────┬─────┬─────┬─────┐
│  0  │  1  │  2  │  3  │  ← Rank 1: positions 0-3
├─────┼─────┼─────┼─────┤
│  4  │  5  │  6  │  7  │  ← Rank 2: positions 4-7
├─────┼─────┼─────┼─────┤
│  8  │  9  │ 10  │ 11  │  ← Rank 3: positions 8-11
├─────┼─────┼─────┼─────┤
│ 12  │ 13  │ 14  │ 15  │  ← Rank 4: positions 12-15
└─────┴─────┴─────┴─────┘
```

### Notation Rules

- **A, B, C, D** = Player 0 pieces (uppercase) with shapes A, B, C, D
- **a, b, c, d** = Player 1 pieces (lowercase) with shapes A, B, C, D  
- **.** = Empty square
- **/** = Rank separator

### Visual Examples

#### 1. Empty Board
```
QFEN: "..../..../..../....."

┌─────┬─────┬─────┬─────┐
│  .  │  .  │  .  │  .  │
├─────┼─────┼─────┼─────┤
│  .  │  .  │  .  │  .  │
├─────┼─────┼─────┼─────┤
│  .  │  .  │  .  │  .  │
├─────┼─────┼─────┼─────┤
│  .  │  .  │  .  │  .  │
└─────┴─────┴─────┴─────┘
```

#### 2. Mixed Position
```
QFEN: "A.bC/..../d..B/...a"

┌─────┬─────┬─────┬─────┐
│  A  │  .  │  b  │  C  │ ← Player 0: A,C  Player 1: b
├─────┼─────┼─────┼─────┤
│  .  │  .  │  .  │  .  │
├─────┼─────┼─────┼─────┤
│  d  │  .  │  .  │  B  │ ← Player 0: B    Player 1: d
├─────┼─────┼─────┼─────┤
│  .  │  .  │  .  │  a  │ ← Player 1: a
└─────┴─────┴─────┴─────┘
```

#### 3. Winning Position (Complete Row)
```
QFEN: "AbCd/..../..../....."

┌─────┬─────┬─────┬─────┐
│  A  │  b  │  C  │  d  │ ← WIN! All 4 shapes in top row
├─────┼─────┼─────┼─────┤
│  .  │  .  │  .  │  .  │
├─────┼─────┼─────┼─────┤
│  .  │  .  │  .  │  .  │
├─────┼─────┼─────┼─────┤
│  .  │  .  │  .  │  .  │
└─────┴─────┴─────┴─────┘
```

#### 4. Complex Game State
```
QFEN: "Ab.C/d.BA/.cb./D.a."

┌─────┬─────┬─────┬─────┐
│  A  │  b  │  .  │  C  │ ← Player 0: A,C  Player 1: b
├─────┼─────┼─────┼─────┤
│  d  │  .  │  B  │  A  │ ← Player 0: B,A  Player 1: d  
├─────┼─────┼─────┼─────┤
│  .  │  c  │  b  │  .  │ ← Player 1: c,b
├─────┼─────┼─────┼─────┤
│  D  │  .  │  a  │  .  │ ← Player 0: D    Player 1: a
└─────┴─────┴─────┴─────┘
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
- **Move Generation**: Full legal move generation with placement validation
- **Game Logic**: Win detection, move validation, and game result checking
- **MCTS Engine**: Monte Carlo Tree Search with UCB1 selection
- **Opening Book**: SQLite-backed position database with canonical deduplication
- **Puzzle Generator**: Tactical puzzle generation with dropout-based search
- **Serialization**: Binary, QFEN, and CBOR formats
- **Canonicalization**: Symmetry-aware position normalization

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

### Basic State Manipulation

```python
from quantik_core import State, Move, generate_legal_moves, apply_move

# Create an empty game state
state = State.empty()
print(state.to_qfen())  # Output: ..../..../..../....

# Create positions using QFEN notation (see QFEN section for visual examples)
state = State.from_qfen("A.bC/..../d.B./...a")  # Mixed position
state = State.from_qfen("ABCD/..../..../.....")  # Player 0 wins with top row

# Convert to human-readable format
qfen = state.to_qfen()
print(f"Position: {qfen}")  # Output: ABCD/..../..../.....

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

### Monte Carlo Tree Search

```python
from quantik_core import State
from quantik_core.mcts import MCTSEngine, MCTSConfig

# Configure MCTS search
config = MCTSConfig(
    max_iterations=1000,
    exploration_weight=1.414,  # sqrt(2) for UCB1
    random_seed=42
)

# Create engine and search
engine = MCTSEngine(config)
state = State.from_qfen("..../..../..../....")

# Find best move
move, win_probability = engine.search(state)
print(f"Best move: {move}, Win probability: {win_probability:.2%}")
```

### Opening Book Database

```python
from quantik_core import State, Move
from quantik_core.opening_book import OpeningBookDatabase, OpeningBookConfig

# Create opening book
config = OpeningBookConfig(database_path="quantik_openings.db")
db = OpeningBookDatabase(config)

# Add positions
state = State.from_qfen("A.../..../..../....")
db.add_position(
    state=state,
    evaluation=0.5,
    visit_count=100,
    win_count_p0=60,
    win_count_p1=40,
    draw_count=0,
    best_moves=[Move(player=0, shape=1, position=5)],
    depth=1
)

# Query positions
entry = db.get_position(state)
if entry:
    print(f"Evaluation: {entry.evaluation}")
    print(f"Best moves: {entry.best_moves}")
```

## Performance

- **State Operations**: Bitboard-based representation enables fast position manipulation
- **Canonicalization**: <1µs per position with precomputed lookup tables
- **Memory Usage**: 16 bytes per game state + 1MB for transformation LUTs
- **Serialization**: 18-byte binary format, human-readable QFEN, or self-describing CBOR
- **MCTS**: 20,000+ iterations/second on modern hardware
- **Puzzle Generation**: 55,000+ positions/second with dropout optimization
- **Opening Book**: SQLite backend with canonical deduplication for space efficiency

## Use Cases

### Position Analysis and Canonicalization
```python
from quantik_core import State

# Create different equivalent positions
pos1 = State.from_qfen("A.../..../..../....") 
pos2 = State.from_qfen("..../..../..../.B..")  # Rotated + shape equivalence

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

## Documentation

- [MCTS Documentation](docs/MCTS.md) - Monte Carlo Tree Search implementation details
- [Opening Book Guide](docs/OPENING_BOOK.md) - Position database usage and API
- [Examples](examples/) - Complete working examples for all features

## Technical Details

- **Representation**: 8 disjoint 16-bit bitboards (one per color-shape combination)
- **Symmetries**: Dihedral group D4 (8 rotations/reflections) × color swap × shape permutations = 384 total
- **Serialization**: Versioned binary format with little-endian 16-bit words
- **Canonicalization**: Lexicographically minimal representation across symmetry orbit
- **MCTS Algorithm**: UCB1 with configurable exploration parameter
- **Opening Book**: Canonical key indexing for automatic deduplication

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
