# Parallelization Analysis: Endgame Puzzle Generator

## Executive Summary

The endgame puzzle generator is an excellent candidate for parallelization with potential speedups of **4-16x** on modern multi-core systems. The algorithm explores independent subtrees that can be processed in parallel with minimal coordination overhead.

**Performance Baseline:**
- Demo 1: 1,067,792 positions in 19.23s (55,513 pos/sec)
- Demo 2: 3,284,380 positions in 145.51s (22,572 pos/sec)

**Expected Parallel Performance (8 cores):**
- Best case: 145.51s → 18-20s (7-8x speedup)
- Realistic: 145.51s → 20-25s (6-7x speedup)

---

## Parallelization Strategy

### 1. Work Distribution Pattern

The puzzle generator uses depth-first search from the root position:

```
Root Position (depth 0)
├── Move 1 → Subtree A (independent)
├── Move 2 → Subtree B (independent)
├── Move 3 → Subtree C (independent)
└── Move N → Subtree N (independent)
```

**Key Insight:** Each first-level move creates an independent subtree that can be explored in parallel.

From the output data:
- Depth 1: 64 positions (typical for empty board)
- Each of these 64 branches is independent
- Can distribute across available CPU cores

### 2. Parallelization Approaches

#### Approach A: Process-Based Parallelization (Recommended)
**Method:** Python `multiprocessing.Pool`
**Advantages:**
- True parallelism (no GIL limitations)
- Mature, well-tested library
- Good performance characteristics
- Simple to implement

**Implementation:**
```python
from multiprocessing import Pool, cpu_count
from functools import partial

def explore_subtree_worker(args):
    """Worker function to explore a single subtree."""
    move, bb, config, seed_offset = args

    # Create separate generator with offset seed for this branch
    branch_config = PuzzleConfig(
        seed=config.seed + seed_offset,
        max_depth=config.max_depth - 1,  # Already at depth 1
        dropout_depth=config.dropout_depth - 1,
        dropout_rate=config.dropout_rate,
        min_puzzle_depth=config.min_puzzle_depth,
        max_puzzles=config.max_puzzles // 64,  # Distribute quota
    )

    generator = EndgamePuzzleGenerator(branch_config)
    new_bb = apply_move(bb, move)
    generator._explore_position(new_bb, depth=1, move_sequence=[move])

    return {
        'puzzles': generator.puzzles,
        'positions_explored': generator.positions_explored,
        'positions_by_depth': generator.positions_by_depth,
        'seen_positions': generator.seen_positions,
    }

class ParallelPuzzleGenerator(EndgamePuzzleGenerator):
    def generate_puzzles_parallel(self, starting_qfen="..../..../..../...."):
        """Generate puzzles using parallel exploration."""
        start_time = time.time()

        # Get first-level moves
        starting_state = State.from_qfen(starting_qfen)
        bb = starting_state.bb
        current_player, moves_by_shape = generate_legal_moves(bb)

        all_moves = []
        for shape_moves in moves_by_shape.values():
            all_moves.extend(shape_moves)

        # Prepare work items
        work_items = [
            (move, bb, self.config, idx)
            for idx, move in enumerate(all_moves)
        ]

        # Execute in parallel
        num_workers = min(cpu_count(), len(all_moves))
        with Pool(num_workers) as pool:
            results = pool.map(explore_subtree_worker, work_items)

        # Merge results
        self._merge_results(results)

        generation_time = time.time() - start_time
        return PuzzleStats(
            total_positions_explored=self.positions_explored,
            puzzles_found=len(self.puzzles),
            generation_time=generation_time,
            positions_by_depth=dict(self.positions_by_depth),
        )

    def _merge_results(self, results):
        """Merge results from parallel workers."""
        for result in results:
            self.puzzles.extend(result['puzzles'])
            self.positions_explored += result['positions_explored']

            for depth, count in result['positions_by_depth'].items():
                self.positions_by_depth[depth] += count

            self.seen_positions.update(result['seen_positions'])
```

**Challenges:**
- Seed management for reproducibility
- Merging `seen_positions` across workers (some duplicate work acceptable)
- Inter-process communication overhead for large result sets

#### Approach B: Task-Based Agent Parallelism
**Method:** Claude Code Task agents
**Advantages:**
- Can leverage multiple Claude agents
- Good for exploratory analysis
- Flexible coordination

**Implementation:**
```python
# Launch multiple agents to explore different subtree ranges
# Agent 1: Explore moves 0-15
# Agent 2: Explore moves 16-31
# Agent 3: Explore moves 32-47
# Agent 4: Explore moves 48-63
```

**Challenges:**
- Agent coordination overhead
- Less suitable for production code
- Better for one-off analysis

#### Approach C: Distributed Computing
**Method:** Ray, Dask, or Celery
**Advantages:**
- Scales beyond single machine
- Professional-grade tools
- Good for very deep searches

**Challenges:**
- Significant complexity overhead
- Overkill for current problem size
- Requires additional infrastructure

---

## Detailed Performance Analysis

### Current Performance Characteristics

From the test output:

```
DEMO 1: Basic Puzzle Generation
- Total positions: 1,067,792
- Time: 19.23 seconds
- Rate: 55,513 pos/sec
- Depth distribution:
  - Depth 0-3: 2,738 positions (0.26%)
  - Depth 4: 29,547 positions (2.77%)
  - Depth 5: 144,028 positions (13.49%)
  - Depth 6: 891,479 positions (83.48%)

DEMO 2: Deep Search with High Dropout
- Total positions: 3,284,380
- Time: 145.51 seconds
- Rate: 22,572 pos/sec
- Depth distribution:
  - Depth 0-4: 32,285 positions (0.98%)
  - Depth 5: 67,940 positions (2.07%)
  - Depth 6: 254,169 positions (7.74%)
  - Depth 7: 849,842 positions (25.88%)
  - Depth 8: 2,080,144 positions (63.33%)
```

**Key Observation:** Most work happens at deepest levels (80-85% of positions).

### Parallelization Overhead Analysis

**Overhead Sources:**
1. **Process creation**: ~10-50ms per process (one-time)
2. **IPC serialization**: Depends on result size
   - Small results (<1MB): ~1-5ms
   - Medium results (1-10MB): ~10-50ms
   - Large results (>10MB): 50-200ms
3. **Merge operations**: O(n) where n = total puzzles/positions

**Estimated overhead for 8-core parallelization:**
- Process creation: 50ms
- Serialization (64 results): 64 × 10ms = 640ms
- Merge: 100ms
- Total: ~800ms (~0.5% overhead for 145s job)

### Expected Speedup

**Theoretical maximum (Amdahl's Law):**
- Serial fraction (s): 0.02 (overhead + merge)
- Parallel fraction (p): 0.98
- Speedup(N) = 1 / (s + p/N)

```
Cores  | Speedup | Time (145s baseline)
-------|---------|--------------------
2      | 1.96x   | 74s
4      | 3.85x   | 38s
8      | 7.21x   | 20s
16     | 12.25x  | 12s
```

**Realistic speedup (accounting for work imbalance):**
- Work distribution across 64 first-level moves is not perfectly balanced
- Some subtrees much larger than others
- Load imbalance factor: ~0.85

```
Cores  | Realistic Speedup | Time
-------|-------------------|------
2      | 1.66x            | 87s
4      | 3.27x            | 44s
8      | 6.13x            | 24s
16     | 10.41x           | 14s
```

---

## Implementation Complexity

### Option 1: Simple Multiprocessing (Low Complexity)
**Effort:** 2-3 hours
**Files to modify:**
- `examples/endgame_puzzle_generator.py`: Add `ParallelPuzzleGenerator` class
- Create new example: `examples/parallel_puzzle_generation.py`

**Changes required:**
- Extract worker function
- Add result merging logic
- Handle seed distribution
- Add parallel demo

### Option 2: Advanced Parallelization (Medium Complexity)
**Effort:** 4-6 hours
**Additional features:**
- Dynamic work stealing for load balancing
- Shared memory for position deduplication (using `multiprocessing.Manager`)
- Progress monitoring across workers
- Graceful interruption handling

### Option 3: Production-Grade Solution (High Complexity)
**Effort:** 8-12 hours
**Additional features:**
- Ray or Dask integration
- Distributed caching
- Checkpointing and resume
- Advanced scheduling strategies

---

## Recommended Implementation Path

### Phase 1: Proof of Concept (Recommended First)
**Time:** 2-3 hours

1. Create `examples/parallel_puzzle_generation.py`
2. Implement simple `multiprocessing.Pool`-based parallelization
3. Benchmark against serial version
4. Validate puzzle reproducibility

**Success criteria:**
- 5-7x speedup on 8-core machine
- Identical or similar puzzle output (order may differ)
- Clean, maintainable code

### Phase 2: Integration (Optional)
**Time:** 1-2 hours

1. Add `ParallelPuzzleGenerator` class to main generator file
2. Add command-line flag: `--parallel`
3. Update documentation

### Phase 3: Advanced Features (Optional)
**Time:** 4-6 hours

1. Add progress monitoring
2. Implement work stealing
3. Add checkpointing
4. Create benchmarking suite

---

## Code Example: Minimal Parallel Implementation

```python
#!/usr/bin/env python3
"""
Parallel Puzzle Generation Example

Demonstrates 5-8x speedup using multiprocessing.
"""

import time
from multiprocessing import Pool, cpu_count
from typing import List, Tuple

from quantik_core import State, Move, generate_legal_moves, apply_move
from examples.endgame_puzzle_generator import (
    EndgamePuzzleGenerator,
    PuzzleConfig,
    PuzzleStats,
)


def explore_branch_worker(
    args: Tuple[Move, tuple, PuzzleConfig, int]
) -> dict:
    """
    Worker function to explore a single branch from root.

    Args:
        args: Tuple of (move, bb, config, seed_offset)

    Returns:
        Dict with puzzles, statistics, and visited positions
    """
    move, bb, config, seed_offset = args

    # Create generator with branch-specific seed
    branch_config = PuzzleConfig(
        seed=config.seed + seed_offset,
        max_depth=config.max_depth - 1,
        dropout_depth=max(0, config.dropout_depth - 1),
        dropout_rate=config.dropout_rate,
        min_puzzle_depth=config.min_puzzle_depth,
        max_puzzles=max(1, config.max_puzzles // 64),
    )

    generator = EndgamePuzzleGenerator(branch_config)
    new_bb = apply_move(bb, move)
    generator._explore_position(new_bb, depth=1, move_sequence=[move])

    return {
        'puzzles': generator.puzzles,
        'positions_explored': generator.positions_explored,
        'positions_by_depth': dict(generator.positions_by_depth),
    }


def generate_puzzles_parallel(
    config: PuzzleConfig,
    starting_qfen: str = "..../..../..../....",
    num_workers: int = None,
) -> Tuple[List, PuzzleStats]:
    """
    Generate puzzles using parallel tree exploration.

    Args:
        config: Puzzle generation configuration
        starting_qfen: Starting position
        num_workers: Number of parallel workers (default: cpu_count())

    Returns:
        Tuple of (puzzles, stats)
    """
    if num_workers is None:
        num_workers = cpu_count()

    start_time = time.time()

    # Get first-level moves
    starting_state = State.from_qfen(starting_qfen)
    bb = starting_state.bb
    _, moves_by_shape = generate_legal_moves(bb)

    all_moves = []
    for shape_moves in moves_by_shape.values():
        all_moves.extend(shape_moves)

    print(f"Distributing {len(all_moves)} branches across {num_workers} workers")

    # Prepare work items
    work_items = [
        (move, bb, config, idx)
        for idx, move in enumerate(all_moves)
    ]

    # Execute in parallel
    with Pool(num_workers) as pool:
        results = pool.map(explore_branch_worker, work_items)

    # Merge results
    all_puzzles = []
    total_positions = 1  # Root position
    merged_depth_counts = {0: 1}

    for result in results:
        all_puzzles.extend(result['puzzles'])
        total_positions += result['positions_explored']

        for depth, count in result['positions_by_depth'].items():
            merged_depth_counts[depth] = (
                merged_depth_counts.get(depth, 0) + count
            )

    generation_time = time.time() - start_time

    stats = PuzzleStats(
        total_positions_explored=total_positions,
        puzzles_found=len(all_puzzles),
        generation_time=generation_time,
        positions_by_depth=merged_depth_counts,
    )

    return all_puzzles, stats


def benchmark_serial_vs_parallel():
    """Compare serial and parallel performance."""
    config = PuzzleConfig(
        seed=123,
        max_depth=8,
        dropout_depth=4,
        dropout_rate=0.8,
        min_puzzle_depth=4,
        max_puzzles=10000,
    )

    print("=" * 80)
    print("PARALLEL VS SERIAL BENCHMARK")
    print("=" * 80)

    # Serial version
    print("\nSerial execution:")
    generator_serial = EndgamePuzzleGenerator(config)
    stats_serial = generator_serial.generate_puzzles()

    print(f"Time: {stats_serial.generation_time:.2f}s")
    print(f"Positions: {stats_serial.total_positions_explored:,}")
    print(f"Puzzles: {stats_serial.puzzles_found}")

    # Parallel version
    print("\nParallel execution:")
    puzzles_parallel, stats_parallel = generate_puzzles_parallel(config)

    print(f"Time: {stats_parallel.generation_time:.2f}s")
    print(f"Positions: {stats_parallel.total_positions_explored:,}")
    print(f"Puzzles: {stats_parallel.puzzles_found}")

    # Calculate speedup
    speedup = stats_serial.generation_time / stats_parallel.generation_time
    print(f"\nSpeedup: {speedup:.2f}x")
    print(f"Efficiency: {speedup / cpu_count() * 100:.1f}%")


if __name__ == "__main__":
    benchmark_serial_vs_parallel()
```

---

## Trade-offs and Considerations

### Advantages of Parallelization
✅ Significant speedup (5-8x on 8 cores)
✅ Enables deeper searches in reasonable time
✅ Better utilization of modern hardware
✅ Relatively simple implementation
✅ Minimal code changes

### Disadvantages of Parallelization
❌ Slight increase in memory usage (N × worker memory)
❌ Non-deterministic puzzle ordering (positions still deterministic with seeds)
❌ Some duplicate work across workers (position deduplication less effective)
❌ Additional complexity for debugging
❌ Process overhead for very small searches

### When to Use Parallel vs Serial

**Use Parallel when:**
- max_depth ≥ 7
- Expected positions > 500,000
- Available CPU cores ≥ 4
- Wall-clock time is critical

**Use Serial when:**
- max_depth ≤ 5
- Expected positions < 100,000
- Single-core environment
- Reproducible puzzle order required
- Memory constrained

---

## Alternative: Incremental Parallelization

For users who want gradual adoption:

### Level 1: Parallel Demo Script (Current recommendation)
- Keep existing serial generator unchanged
- Add new parallel example file
- Let users choose based on needs

### Level 2: Parallel Flag
- Add `--parallel` flag to existing generator
- Default to serial for backwards compatibility

### Level 3: Auto-detection
- Automatically choose serial/parallel based on:
  - Number of available cores
  - Estimated problem size
  - Memory constraints

---

## Conclusion

**Recommendation:** Implement Approach A (Process-Based Parallelization) as a separate example file.

**Rationale:**
- **High impact:** 5-8x speedup on typical workloads
- **Low risk:** No changes to existing code
- **Low complexity:** 2-3 hours implementation
- **Backwards compatible:** Serial version still available
- **Production ready:** multiprocessing is stable and well-tested

**Next Steps:**
1. Create `examples/parallel_puzzle_generation.py` with minimal implementation
2. Run benchmark on representative workload
3. Document performance characteristics
4. Consider integration into main generator if successful

**Expected Outcome:**
Demo 2 workload (145s) → 20-25s on 8-core machine (6-7x speedup)
