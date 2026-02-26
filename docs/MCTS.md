# Monte Carlo Tree Search (MCTS) Implementation

This document describes the MCTS implementation in Quantik Core, including algorithm details, configuration options, and usage examples.

## Overview

The MCTS engine implements the UCT (Upper Confidence Bounds for Trees) algorithm, which balances exploration and exploitation to find strong moves in complex game positions.

### Algorithm Phases

1. **Selection**: Traverse tree using UCB1 formula to select most promising nodes
2. **Expansion**: Add one new child node to expand the search tree
3. **Simulation**: Play out random game from expanded position
4. **Backpropagation**: Update statistics along path back to root

## Quick Start

```python
from quantik_core import State
from quantik_core.mcts import MCTSEngine, MCTSConfig

# Create configuration
config = MCTSConfig(
    max_iterations=1000,
    exploration_weight=1.414,  # sqrt(2) - standard UCB1
    random_seed=42  # For reproducibility
)

# Create engine and search
engine = MCTSEngine(config)
state = State.from_qfen("..../..../..../....")

# Find best move
move, win_probability = engine.search(state)
print(f"Best move: {move}")
print(f"Win probability (Player 0): {win_probability:.2%}")

# Get detailed statistics
stats = engine.get_statistics()
print(f"Nodes created: {stats['nodes_created']}")
print(f"Memory usage: {stats['memory_usage']} bytes")
```

## Configuration Options

### MCTSConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `exploration_weight` | float | 1.414 | UCB1 exploration constant (√2 for theory-optimal) |
| `max_iterations` | int | 10,000 | Maximum number of MCTS iterations |
| `max_depth` | int | 16 | Maximum simulation depth |
| `random_seed` | int\|None | None | Seed for reproducible results |
| `use_transposition_table` | bool | True | Use existing tree nodes for transpositions |

### Exploration Weight Tuning

The `exploration_weight` parameter controls the exploration-exploitation tradeoff:

- **Lower values (0.5-1.0)**: More exploitation (favor best-known moves)
  - Use for: Strong opponents, time-critical decisions
  - Risk: May miss better alternatives

- **Standard (1.414)**: Balanced UCB1
  - Use for: General gameplay, research
  - Theoretical optimum for regret minimization

- **Higher values (2.0-3.0)**: More exploration (try diverse moves)
  - Use for: Discovering new strategies, opening preparation
  - Risk: Slower convergence to best move

## UCB1 Formula

The algorithm uses the Upper Confidence Bound formula:

```
UCB1(node) = win_rate + c × sqrt(ln(parent_visits) / node_visits)
              ︸︷︷︸                 ︸︷︷︸︷︷︸
           exploitation          exploration
```

Where:
- `win_rate`: Proportion of wins from this position
- `c`: Exploration weight (default: √2)
- `parent_visits`: Number of times parent was visited
- `node_visits`: Number of times this node was visited

## Integration with Compact Tree

The MCTS engine integrates with Quantik Core's compact game tree structure:

```python
# Access the underlying tree
tree = engine.tree
root = tree.get_node(engine.root_id)

print(f"Root visits: {root.visit_count}")
print(f"Root evaluation: {root.best_value}")
print(f"P0 wins: {root.win_count_p0}, P1 wins: {root.win_count_p1}")

# Get child nodes
children = tree.get_children(engine.root_id)
for child_id in children:
    child = tree.get_node(child_id)
    state = tree.get_state(child_id)
    print(f"Child: {state.to_qfen()}, Visits: {child.visit_count}")
```

## Performance Characteristics

### Iteration Speed

Typical performance on modern hardware:

- **Empty board**: 20,000-25,000 iterations/second
- **Midgame**: 15,000-20,000 iterations/second
- **Endgame**: 25,000-30,000 iterations/second

### Memory Usage

- **Per node**: 64 bytes (fits in CPU cache line)
- **1,000 iterations**: ~50-100 KB
- **10,000 iterations**: ~500 KB - 1 MB
- **100,000 iterations**: ~5-10 MB

### Convergence

Iterations needed for strong play:

- **Simple positions**: 100-500 iterations
- **Complex middlegame**: 1,000-5,000 iterations
- **Critical tactical positions**: 5,000-20,000 iterations

## Advanced Usage

### Progressive Search

Implement time management with progressive search:

```python
from quantik_core.mcts import MCTSEngine, MCTSConfig

def search_with_time_limit(state, time_limit_seconds):
    """Search with increasing iterations until time limit."""
    import time

    start_time = time.time()
    best_move = None
    best_prob = 0

    for iterations in [100, 500, 1000, 5000, 10000]:
        if time.time() - start_time > time_limit_seconds:
            break

        config = MCTSConfig(max_iterations=iterations, random_seed=42)
        engine = MCTSEngine(config)
        move, prob = engine.search(state)

        best_move = move
        best_prob = prob

        print(f"{iterations} iterations: {prob:.2%} confidence")

    return best_move, best_prob
```

### Move Analysis

Analyze all candidate moves:

```python
def analyze_moves(state, iterations=1000):
    """Analyze all moves from current position."""
    config = MCTSConfig(max_iterations=iterations, random_seed=42)
    engine = MCTSEngine(config)
    engine.search(state)

    # Get move statistics
    root_id = engine.root_id
    children = engine.tree.get_children(root_id)

    move_stats = []
    for child_id in children:
        child = engine.tree.get_node(child_id)
        child_state = engine.tree.get_state(child_id)

        if child.visit_count > 0:
            win_rate = child.win_count_p0 / child.visit_count
            move_stats.append({
                'position': child_state.to_qfen(),
                'visits': child.visit_count,
                'win_rate': win_rate,
                'evaluation': child.best_value
            })

    # Sort by visits (robust child selection)
    move_stats.sort(key=lambda x: x['visits'], reverse=True)
    return move_stats
```

### Parallel Search

For multi-core systems, run multiple searches in parallel:

```python
from multiprocessing import Pool
from functools import partial

def parallel_mcts_search(state, num_workers=4, iterations_per_worker=2500):
    """Run MCTS in parallel and merge results."""

    def worker_search(seed, state_qfen):
        config = MCTSConfig(
            max_iterations=iterations_per_worker,
            random_seed=seed
        )
        engine = MCTSEngine(config)
        state = State.from_qfen(state_qfen)
        return engine.search(state)

    # Launch parallel searches
    qfen = state.to_qfen()
    with Pool(num_workers) as pool:
        results = pool.starmap(
            worker_search,
            [(seed, qfen) for seed in range(num_workers)]
        )

    # Aggregate results (vote by win probability)
    from collections import Counter
    move_votes = Counter()
    for move, prob in results:
        move_votes[move] += prob

    best_move = move_votes.most_common(1)[0][0]
    avg_prob = sum(p for m, p in results if m == best_move) / num_workers

    return best_move, avg_prob
```

## Comparison with Other Approaches

### MCTS vs. Minimax

| Aspect | MCTS | Minimax |
|--------|------|---------|
| **Evaluation** | Statistical sampling | Heuristic function |
| **Strength** | Scales with time | Depends on depth |
| **Uncertainty** | Handles well | Requires pruning |
| **Anytime** | Yes | No |
| **Parallelization** | Easy | Moderate |

### When to Use MCTS

**MCTS is ideal for:**
- Complex positions with many candidate moves
- Games without good evaluation functions
- Time-flexible search (anytime algorithm)
- Learning and discovering strategies

**Consider alternatives for:**
- Endgame tablebases (use database lookup)
- Simple tactical positions (pattern matching)
- Time-critical moves (opening book)

## Best Practices

### 1. Iteration Count Selection

```python
# Adaptive iteration count based on position
def get_iteration_count(state):
    """Determine iterations based on game phase."""
    move_count = count_pieces(state)

    if move_count < 4:  # Opening
        return 500  # Use opening book instead
    elif move_count < 10:  # Middlegame
        return 5000  # Complex positions
    else:  # Endgame
        return 2000  # Simpler with fewer options
```

### 2. Seed Management

```python
# Reproducible for testing, random for production
if testing:
    config = MCTSConfig(random_seed=42)
else:
    config = MCTSConfig(random_seed=None)  # Random
```

### 3. Memory Management

```python
# Create new engine for each search to avoid memory growth
for position in positions:
    engine = MCTSEngine(config)  # Fresh tree
    move, prob = engine.search(position)
    # Tree is garbage collected after this
```

## Troubleshooting

### Low Win Probabilities

If win probabilities are consistently near 50%:
- Increase `max_iterations`
- Check if position is truly balanced
- Verify game state is correct

### Inconsistent Results

If results vary significantly between runs:
- Set `random_seed` for reproducibility
- Increase `max_iterations` for stability
- Check for insufficient exploration

### Slow Performance

If iterations/second is low:
- Profile simulation depth (reduce `max_depth`)
- Check for memory issues
- Ensure compact tree is being used

## Examples

See `examples/mcts_demo.py` for complete working examples:

- Basic MCTS search
- Tactical position analysis
- Exploration parameter tuning
- Performance benchmarking
- Full game playout
- Tree statistics

## API Reference

### MCTSEngine

```python
class MCTSEngine:
    def __init__(self, config: MCTSConfig)
    def search(self, initial_state: State) -> Tuple[Move, float]
    def get_statistics(self) -> dict
```

### MCTSConfig

```python
@dataclass
class MCTSConfig:
    exploration_weight: float = 1.414
    max_iterations: int = 10000
    max_depth: int = 16
    random_seed: Optional[int] = None
    use_transposition_table: bool = True
```

## Further Reading

- [Wikipedia: Monte Carlo tree search](https://en.wikipedia.org/wiki/Monte_Carlo_tree_search)
- Browne et al. (2012): "A Survey of Monte Carlo Tree Search Methods"
- Coulom (2006): "Efficient Selectivity and Backup Operators in Monte-Carlo Tree Search"
