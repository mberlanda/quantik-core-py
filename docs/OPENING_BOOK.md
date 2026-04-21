# Opening Book Database

This document describes the opening book database implementation, which provides persistent storage for analyzed game positions with automatic canonical deduplication.

## Overview

The opening book database stores evaluated game positions using SQLite, with automatic deduplication of symmetric positions through canonical key indexing. This enables efficient storage and fast lookup of opening theory and analyzed positions.

### Key Features

- **Canonical Deduplication**: Symmetric positions automatically stored once
- **SQLite Backend**: Reliable, file-based storage
- **Fast Lookups**: Indexed by canonical state representation
- **Metadata Storage**: Store evaluations, visit counts, win statistics
- **Best Moves**: Track top moves for each position
- **Bulk Operations**: Efficient batch imports
- **Export Capability**: Human-readable exports

## Quick Start

```python
from quantik_core import State, Move
from quantik_core.opening_book import OpeningBookDatabase, OpeningBookConfig

# Create/open database
config = OpeningBookConfig(database_path="quantik_openings.db")
db = OpeningBookDatabase(config)

# Add a position
state = State.from_qfen("A.../..../..../....")
best_moves = [
    Move(player=0, shape=1, position=5),
    Move(player=0, shape=2, position=6)
]

db.add_position(
    state=state,
    evaluation=0.65,  # Position evaluation (-1 to 1)
    visit_count=1000,
    win_count_p0=650,
    win_count_p1=300,
    draw_count=50,
    best_moves=best_moves,
    depth=1
)

# Query position
entry = db.get_position(state)
if entry:
    print(f"Evaluation: {entry.evaluation}")
    print(f"Visit count: {entry.visit_count}")
    print(f"Best moves: {entry.best_moves}")

# Close database
db.close()
```

## Configuration

### OpeningBookConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database_path` | str | "quantik_opening_book.db" | Path to SQLite database file |
| `cache_size_mb` | int | 100 | SQLite cache size in MB |
| `enable_wal` | bool | True | Enable Write-Ahead Logging for performance |

### Configuration Examples

```python
# Default configuration
config = OpeningBookConfig()

# Custom database location
config = OpeningBookConfig(
    database_path="/data/openings/quantik.db",
    cache_size_mb=200,
    enable_wal=True
)

# Memory-only database (for testing)
config = OpeningBookConfig(database_path=":memory:")
```

## Database Schema

### Positions Table

Stores position data:

```sql
CREATE TABLE positions (
    canonical_key BLOB PRIMARY KEY,  -- 18-byte canonical state
    qfen TEXT NOT NULL,               -- Human-readable position
    depth INTEGER NOT NULL,           -- Ply depth from start
    evaluation REAL NOT NULL,         -- Position score (-1 to 1)
    visit_count INTEGER NOT NULL,     -- Number of visits
    win_count_p0 INTEGER NOT NULL,    -- Player 0 wins
    win_count_p1 INTEGER NOT NULL,    -- Player 1 wins
    draw_count INTEGER NOT NULL,      -- Draw count
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Best Moves Table

Stores ordered best moves for each position:

```sql
CREATE TABLE best_moves (
    canonical_key BLOB NOT NULL,
    move_rank INTEGER NOT NULL,  -- Move ranking (1-5)
    shape INTEGER NOT NULL,      -- Piece shape (0-3)
    position INTEGER NOT NULL,   -- Board position (0-15)
    PRIMARY KEY (canonical_key, move_rank),
    FOREIGN KEY (canonical_key) REFERENCES positions(canonical_key)
)
```

## Core Operations

### Adding Positions

```python
# Add single position
state = State.from_qfen("A.../..../..../....")
db.add_position(
    state=state,
    evaluation=0.5,
    visit_count=100,
    win_count_p0=50,
    win_count_p1=45,
    draw_count=5,
    best_moves=[Move(player=0, shape=1, position=5)],
    depth=1
)

# Update existing position (automatically replaces)
db.add_position(
    state=state,  # Same position
    evaluation=0.55,  # Updated evaluation
    visit_count=200,  # Increased visits
    win_count_p0=110,
    win_count_p1=85,
    draw_count=5,
    best_moves=[Move(player=0, shape=1, position=5)],
    depth=1
)
```

### Querying Positions

```python
# Query by state
state = State.from_qfen("A.../..../..../....")
entry = db.get_position(state)

if entry:
    print(f"QFEN: {entry.qfen}")
    print(f"Depth: {entry.depth}")
    print(f"Evaluation: {entry.evaluation}")
    print(f"Visits: {entry.visit_count}")
    print(f"Win rate (P0): {entry.win_count_p0 / entry.visit_count:.1%}")

    # Access best moves
    for rank, (shape, position) in enumerate(entry.best_moves, 1):
        print(f"{rank}. Shape {shape} at position {position}")
else:
    print("Position not in opening book")
```

### Query by Depth

```python
# Get most-visited positions at depth 2
entries = db.query_by_depth(depth=2, limit=10)

for entry in entries:
    win_rate = entry.win_count_p0 / entry.visit_count
    print(f"{entry.qfen}: {win_rate:.1%} ({entry.visit_count} visits)")
```

## Canonical Deduplication

The opening book automatically deduplicates symmetric positions:

```python
# These are equivalent positions (rotations/reflections)
state1 = State.from_qfen("A.../..../..../....")  # Top-left
state2 = State.from_qfen("...A/..../..../....")  # Top-right (rotated)

# Both map to same canonical form
key1 = state1.canonical_key()
key2 = state2.canonical_key()

# Add both - only one entry created
db.add_position(state1, evaluation=0.5, visit_count=100,
                win_count_p0=50, win_count_p1=50, draw_count=0,
                best_moves=[], depth=1)

db.add_position(state2, evaluation=0.55, visit_count=150,
                win_count_p0=80, win_count_p1=60, draw_count=10,
                best_moves=[], depth=1)

# Last write wins - only one position stored
stats = db.get_statistics()
print(f"Positions: {stats['total_positions']}")  # Output: 1

# Retrieving either state returns the same entry
entry1 = db.get_position(state1)
entry2 = db.get_position(state2)
assert entry1.canonical_key == entry2.canonical_key
```

## Building from Game Tree

Build an opening book by exploring the game tree:

```python
from quantik_core import State, generate_legal_moves, apply_move
from quantik_core.game_utils import check_game_winner, WinStatus

def build_opening_book(db, max_depth=5):
    """Build opening book by exploring game tree."""
    positions = {}

    def explore(bb, depth):
        if depth > max_depth:
            return

        state = State(bb)
        canonical_key = state.canonical_key()

        # Check if already visited
        if (canonical_key, depth) in positions:
            positions[(canonical_key, depth)]['visit_count'] += 1
            return

        # Check for terminal position
        winner = check_game_winner(bb)
        if winner != WinStatus.NO_WIN:
            eval_score = 1.0 if winner == WinStatus.PLAYER_0_WINS else -1.0
            positions[(canonical_key, depth)] = {
                'state': state,
                'evaluation': eval_score,
                'visit_count': 1,
                'win_count_p0': 1 if winner == WinStatus.PLAYER_0_WINS else 0,
                'win_count_p1': 1 if winner == WinStatus.PLAYER_1_WINS else 0,
                'draw_count': 0,
                'best_moves': [],
                'depth': depth
            }
            return

        # Generate and explore moves
        current_player, moves_by_shape = generate_legal_moves(bb)
        all_moves = []
        for shape_moves in moves_by_shape.values():
            all_moves.extend(shape_moves)

        if not all_moves:
            return

        # Store position
        positions[(canonical_key, depth)] = {
            'state': state,
            'evaluation': 0.0,
            'visit_count': 1,
            'win_count_p0': 0,
            'win_count_p1': 0,
            'draw_count': 0,
            'best_moves': all_moves[:3],
            'depth': depth
        }

        # Explore children
        for move in all_moves:
            new_bb = apply_move(bb, move)
            explore(new_bb, depth + 1)

    # Start exploration
    initial_bb = State.from_qfen("..../..../..../....")bb
    explore(initial_bb, 0)

    # Populate database
    for (canonical_key, depth), data in positions.items():
        db.add_position(
            state=data['state'],
            evaluation=data['evaluation'],
            visit_count=data['visit_count'],
            win_count_p0=data['win_count_p0'],
            win_count_p1=data['win_count_p1'],
            draw_count=data['draw_count'],
            best_moves=data['best_moves'],
            depth=depth
        )

    return len(positions)
```

## Statistics and Analytics

### Database Statistics

```python
stats = db.get_statistics()

print(f"Total positions: {stats['total_positions']:,}")
print(f"Unique depths: {stats['unique_depths']}")
print(f"Total visits: {stats['total_visits']:,}")
print(f"Max depth: {stats['max_depth']}")
print(f"Database size: {stats['file_size_bytes']:,} bytes")
print(f"Size (MB): {stats['file_size_bytes'] / 1024 / 1024:.1f}")
```

### Positions by Depth

```python
depth_counts = db.get_positions_by_depth()

print("Positions per depth:")
for depth in sorted(depth_counts.keys()):
    count = depth_counts[depth]
    print(f"  Depth {depth}: {count:,} positions")
```

### Coverage Analysis

```python
def analyze_coverage(db):
    """Analyze opening book coverage."""
    stats = db.get_statistics()
    depth_counts = db.get_positions_by_depth()

    print(f"Opening Book Coverage Analysis")
    print(f"=" * 50)

    total_theoretical = 0
    total_stored = 0

    for depth in sorted(depth_counts.keys()):
        stored = depth_counts[depth]
        # Rough estimate: 64 choices for first move, ~30 avg per subsequent
        theoretical = 64 * (30 ** depth) if depth > 0 else 1

        total_theoretical += theoretical
        total_stored += stored
        coverage = (stored / theoretical) * 100

        print(f"Depth {depth}:")
        print(f"  Stored: {stored:,}")
        print(f"  Theoretical: {theoretical:,}")
        print(f"  Coverage: {coverage:.2f}%")

    overall_coverage = (total_stored / total_theoretical) * 100
    print(f"\nOverall coverage: {overall_coverage:.4f}%")
```

## Export and Import

### Export to Text File

```python
# Export all positions
db.export_to_file("opening_book_export.txt")

# Export with depth limit
db.export_to_file("opening_book_first_3_plies.txt", depth_limit=3)

# File format:
# QFEN | Depth | Eval | Visits | P0Wins | P1Wins | Draws
# A.../..../..../.../1/0.500/100/50/45/5
```

### Import from Another Database

```python
def merge_databases(source_db, target_db):
    """Merge positions from source into target database."""
    stats = source_db.get_statistics()
    max_depth = stats['max_depth']

    for depth in range(max_depth + 1):
        entries = source_db.query_by_depth(depth, limit=100000)

        for entry in entries:
            # Reconstruct state from QFEN
            state = State.from_qfen(entry.qfen)

            # Convert move tuples back to Move objects
            best_moves = [
                Move(player=0, shape=shape, position=pos)
                for shape, pos in entry.best_moves
            ]

            target_db.add_position(
                state=state,
                evaluation=entry.evaluation,
                visit_count=entry.visit_count,
                win_count_p0=entry.win_count_p0,
                win_count_p1=entry.win_count_p1,
                draw_count=entry.draw_count,
                best_moves=best_moves,
                depth=entry.depth
            )

    print(f"Merged {stats['total_positions']} positions")
```

## Best Practices

### 1. Context Manager Usage

Always use context manager for automatic cleanup:

```python
# Recommended
with OpeningBookDatabase(config) as db:
    entry = db.get_position(state)
    # Database automatically closed

# Manual (if needed)
db = OpeningBookDatabase(config)
try:
    entry = db.get_position(state)
finally:
    db.close()
```

### 2. Batch Operations

For bulk inserts, wrap in transaction:

```python
import sqlite3

db = OpeningBookDatabase(config)
db.conn.execute("BEGIN TRANSACTION")

try:
    for state, data in positions.items():
        db.add_position(state, **data)

    db.conn.execute("COMMIT")
except Exception as e:
    db.conn.execute("ROLLBACK")
    raise
```

### 3. Regular Maintenance

```python
def optimize_database(db):
    """Optimize database after large imports."""
    db.conn.execute("ANALYZE")
    db.conn.execute("VACUUM")
    db.conn.commit()
```

### 4. Separate Databases by Strength

```python
# Organize by analysis depth/quality
master_db = OpeningBookDatabase(
    OpeningBookConfig(database_path="master_openings.db")
)

blitz_db = OpeningBookDatabase(
    OpeningBookConfig(database_path="blitz_openings.db")
)
```

## Performance Considerations

### Lookup Speed

- **Canonical key lookup**: O(1) with index
- **Depth query**: O(log n) with index
- **Cold start**: ~1ms (database open)
- **Warm cache**: <0.1ms per lookup

### Storage Efficiency

Typical storage requirements:

| Depth | Positions | Size |
|-------|-----------|------|
| 0-2 | ~100 | 10 KB |
| 0-4 | ~10,000 | 500 KB |
| 0-6 | ~500,000 | 20 MB |
| 0-8 | ~10,000,000 | 400 MB |

With canonical deduplication:
- ~30-50% space savings from symmetry reduction
- SQLite compression provides additional ~20% savings

### Optimization Tips

1. **Enable WAL mode**: Better concurrent access
2. **Increase cache size**: Faster queries
3. **Use indexed queries**: Query by depth, not full scans
4. **Batch inserts**: Much faster than individual adds
5. **Regular VACUUM**: Reclaim deleted space

## Integration Examples

### With MCTS

```python
def mcts_with_opening_book(state, book_db, mcts_config):
    """Use opening book if available, otherwise MCTS."""
    # Check opening book first
    entry = book_db.get_position(state)

    if entry and entry.visit_count > 100:  # Sufficient data
        # Use opening book move
        if entry.best_moves:
            shape, position = entry.best_moves[0]
            move = Move(player=0, shape=shape, position=position)
            win_prob = entry.win_count_p0 / entry.visit_count
            return move, win_prob, "book"

    # Fall back to MCTS
    from quantik_core.mcts import MCTSEngine
    engine = MCTSEngine(mcts_config)
    move, win_prob = engine.search(state)
    return move, win_prob, "mcts"
```

### Building from Analysis

```python
def analyze_and_store(state, db, depth):
    """Analyze position and store in opening book."""
    from quantik_core.mcts import MCTSEngine, MCTSConfig

    # Run MCTS analysis
    config = MCTSConfig(max_iterations=10000)
    engine = MCTSEngine(config)
    best_move, win_prob = engine.search(state)

    # Extract statistics
    root = engine.tree.get_node(engine.root_id)
    children = engine.tree.get_children(engine.root_id)

    # Get best moves
    move_stats = []
    for child_id in children:
        child = engine.tree.get_node(child_id)
        child_state = engine.tree.get_state(child_id)
        if child.visit_count > 0:
            move_stats.append((child.visit_count, child_state))

    move_stats.sort(reverse=True)
    best_moves = [s.to_qfen() for _, s in move_stats[:3]]

    # Store in opening book
    db.add_position(
        state=state,
        evaluation=win_prob * 2 - 1,  # Convert to [-1, 1]
        visit_count=root.visit_count,
        win_count_p0=root.win_count_p0,
        win_count_p1=root.win_count_p1,
        draw_count=0,
        best_moves=[],  # Could extract from children
        depth=depth
    )
```

## Examples

See `examples/opening_book_demo.py` for complete working examples:

- Building opening book from game tree
- Querying positions
- Canonical deduplication demonstration
- Export functionality
- Best move lookup during gameplay

## API Reference

### OpeningBookDatabase

```python
class OpeningBookDatabase:
    def __init__(self, config: OpeningBookConfig)
    def add_position(self, state: State, evaluation: float, ...)
    def get_position(self, state: State) -> Optional[OpeningBookEntry]
    def query_by_depth(self, depth: int, limit: int) -> List[OpeningBookEntry]
    def get_statistics(self) -> Dict[str, int]
    def get_positions_by_depth(self) -> Dict[int, int]
    def export_to_file(self, output_path: str, depth_limit: Optional[int])
    def close(self)
```

### OpeningBookEntry

```python
@dataclass
class OpeningBookEntry:
    canonical_key: bytes
    qfen: str
    depth: int
    evaluation: float
    visit_count: int
    best_moves: List[Tuple[int, int]]
    win_count_p0: int
    win_count_p1: int
    draw_count: int
```

## Troubleshooting

### Database Locked Errors

```python
# Enable WAL mode for concurrent access
config = OpeningBookConfig(enable_wal=True)

# Or increase timeout
db.conn.execute("PRAGMA busy_timeout = 5000")
```

### Large Database Size

```python
# Run VACUUM to reclaim space
db.conn.execute("VACUUM")
db.conn.commit()

# Check actual vs allocated size
stats = db.get_statistics()
print(f"Database size: {stats['file_size_bytes'] / 1024 / 1024:.1f} MB")
```

### Slow Queries

```python
# Rebuild indices
db.conn.execute("REINDEX")

# Analyze query plan
cursor = db.conn.execute("""
    EXPLAIN QUERY PLAN
    SELECT * FROM positions WHERE depth = 3
""")
print(cursor.fetchall())
```

## Further Reading

- [SQLite Performance Tuning](https://www.sqlite.org/performance.html)
- [Opening Book Theory](https://www.chessprogramming.org/Opening_Book)
- Quantik Core: [Canonical Key Documentation](../src/quantik_core/README.md)
