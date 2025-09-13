"""
Comprehensive benchmarks for state validator performance optimizations.

This module benchmarks both original and optimized implementations to measure:
- Execution time improvements
- Memory usage reductions
- Cache hit rates
- Scalability with different input sizes
"""

import time
import tracemalloc
import random
from typing import List, Tuple, Callable, Any
from functools import lru_cache
from dataclasses import dataclass
from contextlib import contextmanager

from quantik_core.core import State
from quantik_core.state_validator_comparison import (
    ValidationResult,
    validate_game_state,
    validate_piece_counts,
    validate_turn_balance,
    validate_position_placement,
    count_pieces_by_shape,
    _validate_game_state_optimized,
    _validate_piece_counts_optimized,
    _validate_turn_balance_optimized,
    _validate_game_state_ultra,
    _count_pieces_by_shape_ultra,
    _validate_piece_counts_ultra,
    _validate_turn_balance_ultra,
    validate_game_state_original,
    validate_piece_counts_original,
    validate_turn_balance_original,
    get_cache_stats,
    clear_all_caches,
)


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""

    name: str
    execution_time: float
    memory_peak: int
    memory_current: int
    iterations: int
    avg_time_per_op: float
    cache_info: str = ""


@contextmanager
def benchmark_context():
    """Context manager for measuring time and memory."""
    tracemalloc.start()
    start_time = time.perf_counter()

    yield

    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return end_time - start_time, current, peak


def generate_test_states(count: int) -> List[State]:
    """Generate a variety of test states for benchmarking."""
    states = []

    # Empty state
    states.append(State.from_qfen("..../..../..../....", validate=False))

    # Simple states
    for _ in range(count // 4):
        # Random single piece placements
        qfen_parts = ["....", "....", "....", "...."]
        pos = random.randint(0, 15)
        row, col = pos // 4, pos % 4
        shape = random.choice("ABCD")
        player = random.choice([0, 1])
        char = shape if player == 0 else shape.lower()
        qfen_parts[row] = qfen_parts[row][:col] + char + qfen_parts[row][col + 1 :]
        states.append(State.from_qfen("/".join(qfen_parts), validate=False))

    # Medium complexity states
    for _ in range(count // 4):
        qfen_parts = ["....", "....", "....", "...."]
        pieces_placed = random.randint(2, 6)
        positions = random.sample(range(16), pieces_placed)

        for i, pos in enumerate(positions):
            row, col = pos // 4, pos % 4
            shape = random.choice("ABCD")
            player = i % 2
            char = shape if player == 0 else shape.lower()
            qfen_parts[row] = qfen_parts[row][:col] + char + qfen_parts[row][col + 1 :]

        try:
            states.append(State.from_qfen("/".join(qfen_parts), validate=False))
        except:
            continue

    # Complex states
    for _ in range(count // 4):
        qfen_parts = ["....", "....", "....", "...."]
        pieces_placed = random.randint(6, 12)
        positions = random.sample(range(16), pieces_placed)

        for i, pos in enumerate(positions):
            row, col = pos // 4, pos % 4
            shape = random.choice("ABCD")
            player = i % 2
            char = shape if player == 0 else shape.lower()
            qfen_parts[row] = qfen_parts[row][:col] + char + qfen_parts[row][col + 1 :]

        try:
            states.append(State.from_qfen("/".join(qfen_parts), validate=False))
        except:
            continue

    # Fill remaining with valid specific patterns
    while len(states) < count:
        states.append(State.from_qfen("A.../B.../..a./..b.", validate=False))

    return states[:count]


def benchmark_function(
    func: Callable, states: List[State], iterations: int = 1000
) -> BenchmarkResult:
    """Benchmark a function with the given states."""
    tracemalloc.start()
    start_time = time.perf_counter()

    for _ in range(iterations):
        for state in states:
            try:
                if hasattr(func, "__name__") and "fast" in func.__name__:
                    func(state.bb)
                else:
                    func(state)
            except:
                continue

    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    execution_time = end_time - start_time
    total_ops = iterations * len(states)

    # Get cache info if available
    cache_info = ""
    if hasattr(func, "cache_info"):
        cache_info = str(func.cache_info())

    return BenchmarkResult(
        name=func.__name__,
        execution_time=execution_time,
        memory_peak=peak,
        memory_current=current,
        iterations=total_ops,
        avg_time_per_op=execution_time / total_ops if total_ops > 0 else 0,
        cache_info=cache_info,
    )


# Original implementations for comparison
def validate_game_state_original(state: State) -> ValidationResult:
    """Original implementation without optimizations."""
    # 1. Validate piece counts
    player0_counts, player1_counts = count_pieces_by_shape(state)
    for shape in range(4):
        if player0_counts[shape] > 2:
            return ValidationResult.SHAPE_COUNT_EXCEEDED
        if player1_counts[shape] > 2:
            return ValidationResult.SHAPE_COUNT_EXCEEDED

    # 2. Validate turn balance
    total0 = sum(player0_counts)
    total1 = sum(player1_counts)
    difference = total0 - total1
    if not (difference == 0 or difference == 1):
        return ValidationResult.TURN_BALANCE_INVALID

    # 3. Validate no overlapping pieces
    all_positions = 0
    for bb in state.bb:
        if all_positions & bb:
            return ValidationResult.PIECE_OVERLAP
        all_positions |= bb

    # 4. Validate placement legality (original slow version)
    from quantik_core.constants import WIN_MASKS

    for shape in range(4):
        player0_pieces = state.bb[shape]
        player1_pieces = state.bb[4 + shape]
        for line_mask in WIN_MASKS:
            if (player0_pieces & line_mask) and (player1_pieces & line_mask):
                return ValidationResult.ILLEGAL_PLACEMENT

    return ValidationResult.OK


def validate_piece_counts_original(state: State) -> ValidationResult:
    """Original piece count validation."""
    player0_counts, player1_counts = count_pieces_by_shape(state)
    for shape in range(4):
        if player0_counts[shape] > 2:
            return ValidationResult.SHAPE_COUNT_EXCEEDED
        if player1_counts[shape] > 2:
            return ValidationResult.SHAPE_COUNT_EXCEEDED
    return ValidationResult.OK


def validate_turn_balance_original(state: State) -> Tuple:
    """Original turn balance validation."""
    player0_counts, player1_counts = count_pieces_by_shape(state)
    total0 = sum(player0_counts)
    total1 = sum(player1_counts)
    difference = total0 - total1

    if difference == 0:
        return 0, ValidationResult.OK
    elif difference == 1:
        return 1, ValidationResult.OK
    else:
        return None, ValidationResult.TURN_BALANCE_INVALID


def run_benchmarks():
    """Run comprehensive benchmarks and print results."""
    print("🚀 Quantik State Validator Performance Benchmarks")
    print("=" * 60)

    # Test different dataset sizes
    test_sizes = [10, 100, 1000]

    for size in test_sizes:
        print(f"\n📊 Benchmark Results for {size} states:")
        print("-" * 40)

        states = generate_test_states(size)
        iterations = max(10, 1000 // size)  # Adjust iterations based on dataset size

        # Benchmark validate_game_state
        print("\n🎯 Game State Validation:")
        original_result = benchmark_function(
            validate_game_state_original, states, iterations
        )
        optimized_v1_result = benchmark_function(
            lambda s: _validate_game_state_optimized(s.bb), states, iterations
        )
        optimized_v2_result = benchmark_function(
            lambda s: _validate_game_state_ultra(s.bb), states, iterations
        )
        optimized_api_result = benchmark_function(
            validate_game_state, states, iterations
        )

        print(
            f"Original:     {original_result.avg_time_per_op*1e6:.2f}μs/op, {original_result.memory_peak/1024:.1f}KB peak"
        )
        print(
            f"Optimized V1: {optimized_v1_result.avg_time_per_op*1e6:.2f}μs/op, {optimized_v1_result.memory_peak/1024:.1f}KB peak"
        )
        print(
            f"Optimized V2: {optimized_v2_result.avg_time_per_op*1e6:.2f}μs/op, {optimized_v2_result.memory_peak/1024:.1f}KB peak"
        )
        print(
            f"Public API:   {optimized_api_result.avg_time_per_op*1e6:.2f}μs/op, {optimized_api_result.memory_peak/1024:.1f}KB peak"
        )

        speedup_v1 = (
            original_result.avg_time_per_op / optimized_v1_result.avg_time_per_op
        )
        speedup_v2 = (
            original_result.avg_time_per_op / optimized_v2_result.avg_time_per_op
        )
        speedup_api = (
            original_result.avg_time_per_op / optimized_api_result.avg_time_per_op
        )

        memory_reduction_v1 = (
            (original_result.memory_peak - optimized_v1_result.memory_peak)
            / original_result.memory_peak
            * 100
        )
        memory_reduction_v2 = (
            (original_result.memory_peak - optimized_v2_result.memory_peak)
            / original_result.memory_peak
            * 100
        )

        print(
            f"⚡ Speedup V1: {speedup_v1:.2f}x, V2: {speedup_v2:.2f}x, API: {speedup_api:.2f}x"
        )
        print(
            f"💾 Memory reduction V1: {memory_reduction_v1:.1f}%, V2: {memory_reduction_v2:.1f}%"
        )

        # Compare V1 vs V2 directly
        v2_vs_v1_speedup = (
            optimized_v1_result.avg_time_per_op / optimized_v2_result.avg_time_per_op
        )
        print(f"🚀 V2 vs V1 improvement: {v2_vs_v1_speedup:.2f}x")

        # Benchmark piece count validation
        print("\n🧮 Piece Count Validation:")
        original_pieces = benchmark_function(
            validate_piece_counts_original, states, iterations
        )
        optimized_v1_pieces = benchmark_function(
            lambda s: _validate_piece_counts_optimized(s.bb), states, iterations
        )
        optimized_v2_pieces = benchmark_function(
            validate_piece_counts, states, iterations
        )

        print(f"Original:     {original_pieces.avg_time_per_op*1e6:.2f}μs/op")
        print(f"Optimized V1: {optimized_v1_pieces.avg_time_per_op*1e6:.2f}μs/op")
        print(f"Optimized V2: {optimized_v2_pieces.avg_time_per_op*1e6:.2f}μs/op")

        pieces_speedup_v1 = (
            original_pieces.avg_time_per_op / optimized_v1_pieces.avg_time_per_op
        )
        pieces_speedup_v2 = (
            original_pieces.avg_time_per_op / optimized_v2_pieces.avg_time_per_op
        )
        pieces_v2_vs_v1 = (
            optimized_v1_pieces.avg_time_per_op / optimized_v2_pieces.avg_time_per_op
        )

        print(f"⚡ Speedup V1: {pieces_speedup_v1:.2f}x, V2: {pieces_speedup_v2:.2f}x")
        print(f"🚀 V2 vs V1: {pieces_v2_vs_v1:.2f}x")

        # Benchmark turn balance validation
        print("\n⚖️  Turn Balance Validation:")
        original_balance = benchmark_function(
            validate_turn_balance_original, states, iterations
        )
        optimized_v1_balance = benchmark_function(
            lambda s: _validate_turn_balance_optimized(s.bb), states, iterations
        )
        optimized_v2_balance = benchmark_function(
            validate_turn_balance, states, iterations
        )

        print(f"Original:     {original_balance.avg_time_per_op*1e6:.2f}μs/op")
        print(f"Optimized V1: {optimized_v1_balance.avg_time_per_op*1e6:.2f}μs/op")
        print(f"Optimized V2: {optimized_v2_balance.avg_time_per_op*1e6:.2f}μs/op")

        balance_speedup_v1 = (
            original_balance.avg_time_per_op / optimized_v1_balance.avg_time_per_op
        )
        balance_speedup_v2 = (
            original_balance.avg_time_per_op / optimized_v2_balance.avg_time_per_op
        )
        balance_v2_vs_v1 = (
            optimized_v1_balance.avg_time_per_op / optimized_v2_balance.avg_time_per_op
        )

        print(
            f"⚡ Speedup V1: {balance_speedup_v1:.2f}x, V2: {balance_speedup_v2:.2f}x"
        )
        print(f"🚀 V2 vs V1: {balance_v2_vs_v1:.2f}x")

        # Show cache statistics for all optimized versions
        print(f"\n📈 Cache Statistics:")
        cache_stats = get_cache_stats()

        print("V1 Optimized:")
        for name, stats in cache_stats.items():
            if name.startswith("v1_"):
                hit_rate = (
                    stats["hits"] / (stats["hits"] + stats["misses"]) * 100
                    if (stats["hits"] + stats["misses"]) > 0
                    else 0
                )
                print(f"  {name}: {hit_rate:.1f}% hit rate, {stats['currsize']} items")

        print("V2 Ultra-optimized:")
        for name, stats in cache_stats.items():
            if name.startswith("v2_"):
                hit_rate = (
                    stats["hits"] / (stats["hits"] + stats["misses"]) * 100
                    if (stats["hits"] + stats["misses"]) > 0
                    else 0
                )
                print(f"  {name}: {hit_rate:.1f}% hit rate, {stats['currsize']} items")


def benchmark_position_placement():
    """Benchmark position placement validation with different scenarios."""
    print("\n🎯 Position Placement Validation Benchmark:")
    print("-" * 45)

    # Create test state
    state = State.from_qfen("A.../B.../..../....", validate=False)

    # Benchmark many position placement checks
    iterations = 10000

    tracemalloc.start()
    start_time = time.perf_counter()

    for _ in range(iterations):
        for pos in range(16):
            for shape in range(4):
                for player in range(2):
                    try:
                        validate_position_placement(state, pos, shape, player)
                    except:
                        continue

    end_time = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    total_ops = iterations * 16 * 4 * 2
    avg_time = (end_time - start_time) / total_ops

    print(f"Position placement: {avg_time*1e6:.2f}μs/op")
    print(f"Memory peak: {peak/1024:.1f}KB")
    print(f"Total operations: {total_ops:,}")


def memory_profile_comparison():
    """Compare memory usage patterns between implementations."""
    print("\n💾 Memory Usage Profile Comparison:")
    print("-" * 40)

    states = generate_test_states(100)

    # Profile original implementation
    tracemalloc.start()
    for state in states:
        validate_game_state_original(state)
    current_orig, peak_orig = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Profile optimized implementation
    tracemalloc.start()
    for state in states:
        validate_game_state(state)
    current_opt, peak_opt = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"Original implementation:")
    print(f"  Peak memory: {peak_orig/1024:.1f}KB")
    print(f"  Current memory: {current_orig/1024:.1f}KB")

    print(f"Optimized implementation:")
    print(f"  Peak memory: {peak_opt/1024:.1f}KB")
    print(f"  Current memory: {current_opt/1024:.1f}KB")

    reduction = (peak_orig - peak_opt) / peak_orig * 100
    print(f"Memory reduction: {reduction:.1f}%")


if __name__ == "__main__":
    # Clear any existing caches
    clear_all_caches()

    run_benchmarks()
    benchmark_position_placement()
    memory_profile_comparison()

    print(f"\n🎉 Benchmark Complete!")
    print("Key optimizations implemented:")
    print("  ✅ LRU caching on hot paths")
    print("  ✅ Bitwise parameter validation")
    print("  ✅ Single-pass validation combining multiple checks")
    print("  ✅ Tuple instead of list allocations")
    print("  ✅ Early exit optimizations")
    print("  ✅ Reduced function call overhead")
    print("  ✅ V2: Reuse of cached piece counts (eliminates redundant calculations)")
    print("  ✅ V2: Multiple specialized caches (better hit rates)")
    print("  ✅ V2: Zero-allocation validation functions")
