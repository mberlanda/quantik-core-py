"""
High-volume performance benchmark with 1M+ test cases and 5K+ distinct states.

This benchmark generates a large-scale test suite to thoroughly evaluate
the performance characteristics of different optimization strategies under
realistic load conditions.
"""

import time
import tracemalloc
import random
from typing import List, Dict, Set
from collections import defaultdict

from quantik_core.core import State
from quantik_core.state_validator_comparison import (
    validate_game_state,
    clear_all_caches,
    get_cache_stats,
    _validate_game_state_single_pass,
    _validate_game_state_optimized,
    _validate_game_state_ultra,
    validate_game_state_original,
)


class StateGenerator:
    """Generate diverse game states for comprehensive testing."""

    def __init__(self, seed: int = 42):
        """Initialize with random seed for reproducible results."""
        random.seed(seed)
        self.shapes = ["A", "B", "C", "D"]
        self.positions = list(range(16))  # 4x4 board positions

    def generate_empty_states(self, count: int) -> List[str]:
        """Generate empty board variations."""
        return ["..../..../..../...."] * count

    def generate_single_piece_states(self, count: int) -> List[str]:
        """Generate states with single pieces in different positions."""
        states = []
        for _ in range(count):
            qfen = ["....", "....", "....", "...."]
            pos = random.randint(0, 15)
            row, col = pos // 4, pos % 4
            shape = random.choice(self.shapes)
            player = random.choice([shape.upper(), shape.lower()])

            qfen_list = list(qfen[row])
            qfen_list[col] = player
            qfen[row] = "".join(qfen_list)

            states.append("/".join(qfen))
        return states

    def generate_sparse_states(
        self, count: int, piece_count_range: tuple = (2, 6)
    ) -> List[str]:
        """Generate states with few pieces scattered across the board."""
        states = []
        for _ in range(count):
            qfen = ["....", "....", "....", "...."]
            piece_count = random.randint(*piece_count_range)
            used_positions = set()

            for _ in range(piece_count):
                # Avoid overlaps
                available_positions = [
                    p for p in self.positions if p not in used_positions
                ]
                if not available_positions:
                    break

                pos = random.choice(available_positions)
                used_positions.add(pos)
                row, col = pos // 4, pos % 4
                shape = random.choice(self.shapes)
                player = random.choice([shape.upper(), shape.lower()])

                qfen_list = list(qfen[row])
                qfen_list[col] = player
                qfen[row] = "".join(qfen_list)

            states.append("/".join(qfen))
        return states

    def generate_dense_states(
        self, count: int, piece_count_range: tuple = (8, 14)
    ) -> List[str]:
        """Generate states with many pieces (typical mid-to-late game)."""
        states = []
        for _ in range(count):
            qfen = ["....", "....", "....", "...."]
            piece_count = random.randint(*piece_count_range)
            used_positions = set()

            # Ensure reasonable balance between players
            player0_pieces = piece_count // 2
            player1_pieces = piece_count - player0_pieces

            # Place player 0 pieces
            for _ in range(player0_pieces):
                available_positions = [
                    p for p in self.positions if p not in used_positions
                ]
                if not available_positions:
                    break

                pos = random.choice(available_positions)
                used_positions.add(pos)
                row, col = pos // 4, pos % 4
                shape = random.choice(self.shapes)

                qfen_list = list(qfen[row])
                qfen_list[col] = shape.upper()
                qfen[row] = "".join(qfen_list)

            # Place player 1 pieces
            for _ in range(player1_pieces):
                available_positions = [
                    p for p in self.positions if p not in used_positions
                ]
                if not available_positions:
                    break

                pos = random.choice(available_positions)
                used_positions.add(pos)
                row, col = pos // 4, pos % 4
                shape = random.choice(self.shapes)

                qfen_list = list(qfen[row])
                qfen_list[col] = shape.lower()
                qfen[row] = "".join(qfen_list)

            states.append("/".join(qfen))
        return states

    def generate_pattern_states(self, count: int) -> List[str]:
        """Generate states with specific patterns (lines, clusters, etc.)."""
        states = []
        patterns = [
            # Row patterns
            lambda: ["ABCD", "....", "....", "...."],
            lambda: ["....", "abcd", "....", "...."],
            lambda: ["AB..", "CD..", "....", "...."],
            # Column patterns
            lambda: ["A...", "B...", "C...", "D..."],
            lambda: [".a..", ".b..", ".c..", ".d.."],
            # Diagonal patterns
            lambda: ["A...", ".B..", "..C.", "...D"],
            lambda: ["...a", "..b.", ".c..", "d..."],
            # Mixed patterns
            lambda: (
                ["AB..", ".ab.", "..AB", "...ab"]
                if random.random() > 0.5
                else ["A.B.", "a.b.", "C.D.", "c.d."]
            ),
        ]

        for _ in range(count):
            pattern_func = random.choice(patterns)
            qfen = pattern_func()
            states.append("/".join(qfen))
        return states

    def generate_invalid_states(self, count: int) -> List[str]:
        """Generate various invalid states for comprehensive testing."""
        states = []
        for _ in range(count):
            qfen = ["....", "....", "....", "...."]

            # Different types of invalid states
            invalid_type = random.choice(
                [
                    "too_many_pieces",  # Exceed MAX_PIECES_PER_SHAPE
                    "turn_imbalance",  # Wrong turn balance
                    "overlaps",  # Multiple pieces on same position (handled by generator)
                    "illegal_placement",  # Same shape on same line for both players
                ]
            )

            if invalid_type == "too_many_pieces":
                # Place too many pieces of the same shape
                shape = random.choice(self.shapes)
                positions = random.sample(
                    self.positions, 5
                )  # More than MAX_PIECES_PER_SHAPE (4)
                for pos in positions:
                    row, col = pos // 4, pos % 4
                    qfen_list = list(qfen[row])
                    qfen_list[col] = shape.upper()
                    qfen[row] = "".join(qfen_list)

            elif invalid_type == "turn_imbalance":
                # Create significant turn imbalance
                player0_count = random.randint(5, 8)
                player1_count = random.randint(0, 2)

                positions = random.sample(self.positions, player0_count + player1_count)

                for i, pos in enumerate(positions):
                    row, col = pos // 4, pos % 4
                    shape = random.choice(self.shapes)
                    if i < player0_count:
                        player_shape = shape.upper()
                    else:
                        player_shape = shape.lower()

                    qfen_list = list(qfen[row])
                    qfen_list[col] = player_shape
                    qfen[row] = "".join(qfen_list)

            elif invalid_type == "illegal_placement":
                # Place same shape on same line for both players
                shape = random.choice(self.shapes)
                # Pick a row and place both players' pieces
                row = random.randint(0, 3)
                col1, col2 = random.sample(range(4), 2)

                qfen_list = list(qfen[row])
                qfen_list[col1] = shape.upper()
                qfen_list[col2] = shape.lower()
                qfen[row] = "".join(qfen_list)

            states.append("/".join(qfen))
        return states

    def generate_comprehensive_test_suite(
        self, total_target: int = 1000000, distinct_target: int = 5000
    ) -> List[str]:
        """Generate comprehensive test suite with specified targets."""
        print(
            f"🎯 Generating test suite: {total_target:,} total cases, {distinct_target:,} distinct states"
        )

        # Calculate distribution
        distinct_per_category = distinct_target // 6  # 6 categories

        print(f"📊 Generating distinct states...")
        distinct_states = []

        # Generate distinct states across categories
        distinct_states.extend(self.generate_empty_states(50))
        distinct_states.extend(self.generate_single_piece_states(distinct_per_category))
        distinct_states.extend(self.generate_sparse_states(distinct_per_category * 2))
        distinct_states.extend(self.generate_dense_states(distinct_per_category))
        distinct_states.extend(self.generate_pattern_states(distinct_per_category))
        distinct_states.extend(self.generate_invalid_states(distinct_per_category))

        # Remove duplicates and ensure we have enough distinct states
        unique_states = list(set(distinct_states))

        while len(unique_states) < distinct_target:
            # Generate more states to reach target
            additional = self.generate_sparse_states(
                distinct_target - len(unique_states)
            )
            unique_states.extend(additional)
            unique_states = list(set(unique_states))

        unique_states = unique_states[:distinct_target]

        print(f"✅ Generated {len(unique_states):,} distinct states")

        # Create test suite by repeating states to reach total target
        print(f"📈 Expanding to {total_target:,} total test cases...")

        test_suite = []
        repeats_per_state = total_target // len(unique_states)
        remainder = total_target % len(unique_states)

        for i, state in enumerate(unique_states):
            repeats = repeats_per_state + (1 if i < remainder else 0)
            test_suite.extend([state] * repeats)

        # Shuffle to distribute repeated states throughout the test suite
        random.shuffle(test_suite)

        print(f"✅ Generated {len(test_suite):,} total test cases")
        return test_suite


def convert_qfens_to_states(qfens: List[str]) -> List[State]:
    """Convert QFEN strings to State objects, filtering out invalid ones."""
    states = []
    failed_count = 0

    print("🔄 Converting QFENs to State objects...")

    for i, qfen in enumerate(qfens):
        if i % 100000 == 0:
            print(f"  Progress: {i:,}/{len(qfens):,} ({i/len(qfens)*100:.1f}%)")

        try:
            state = State.from_qfen(qfen, validate=False)
            states.append(state)
        except Exception:
            failed_count += 1
            continue

    print(f"✅ Converted {len(states):,} states ({failed_count:,} failed)")
    return states


def benchmark_optimization_strategy(
    states: List[State], strategy_name: str, validation_func, iterations: int = 1
) -> Dict:
    """Benchmark a specific optimization strategy."""
    print(f"🔬 Testing {strategy_name}...")

    clear_all_caches()

    # Memory tracking
    tracemalloc.start()

    # Performance timing
    start_time = time.perf_counter()

    validation_count = 0
    for iteration in range(iterations):
        if iterations > 1 and iteration % (iterations // 10) == 0:
            print(f"  Iteration {iteration + 1}/{iterations}")

        for state in states:
            try:
                validation_func(state.bb)
                validation_count += 1
            except Exception:
                continue

    end_time = time.perf_counter()

    # Get memory usage
    current_memory, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Get cache statistics
    cache_stats = get_cache_stats()

    # Calculate metrics
    total_time = end_time - start_time
    validations_per_second = validation_count / total_time if total_time > 0 else 0
    avg_time_per_validation = (
        (total_time / validation_count * 1000000) if validation_count > 0 else 0
    )  # microseconds

    # Cache metrics
    total_hits = sum(stats["hits"] for stats in cache_stats.values())
    total_misses = sum(stats["misses"] for stats in cache_stats.values())
    total_calls = total_hits + total_misses
    hit_rate = (total_hits / total_calls * 100) if total_calls > 0 else 0
    cache_size = sum(stats["currsize"] for stats in cache_stats.values())

    return {
        "strategy": strategy_name,
        "total_time_sec": total_time,
        "validations_count": validation_count,
        "validations_per_second": validations_per_second,
        "avg_time_per_validation_us": avg_time_per_validation,
        "peak_memory_mb": peak_memory / (1024 * 1024),
        "current_memory_mb": current_memory / (1024 * 1024),
        "cache_hit_rate": hit_rate,
        "cache_size": cache_size,
        "total_cache_calls": total_calls,
    }


def run_high_volume_benchmark():
    """Run high-volume benchmark with 1M+ test cases."""
    print("🚀 High-Volume State Validator Performance Benchmark")
    print("=" * 70)

    # Generate comprehensive test suite
    generator = StateGenerator()
    qfens = generator.generate_comprehensive_test_suite(
        total_target=10000000, distinct_target=10000
    )

    # Convert to State objects
    states = convert_qfens_to_states(qfens)

    if len(states) == 0:
        print("❌ No valid states generated. Exiting.")
        return

    print(f"\n📋 Test Configuration:")
    print(f"  Total test cases: {len(states):,}")
    print(
        f"  Distinct states: {len(set(state.to_qfen() for state in states[:5000])):,} (estimated)"
    )
    print(f"  Test repetitions: 1 (focus on raw performance)")

    # Define optimization strategies to test
    strategies = [
        ("Original", lambda bb: validate_game_state_original(State(bb))),
        ("V1 Optimized", _validate_game_state_optimized),
        ("V2 Ultra", _validate_game_state_ultra),
        ("V3 Single-Pass", _validate_game_state_single_pass),
    ]

    # Run benchmarks
    results = []

    print(f"\n🏃‍♂️ Running benchmarks...")

    for strategy_name, validation_func in strategies:
        result = benchmark_optimization_strategy(states, strategy_name, validation_func)
        results.append(result)

        print(
            f"  ✅ {strategy_name}: {result['validations_per_second']:,.0f} validations/sec"
        )

    # Analysis
    print(f"\n📊 Performance Analysis Results")
    print("=" * 80)

    # Sort by performance
    results_sorted = sorted(
        results, key=lambda x: x["validations_per_second"], reverse=True
    )

    print(
        f"{'Strategy':<15} {'Val/Sec':<12} {'Avg (μs)':<10} {'Speedup':<8} {'Hit Rate':<9} {'Memory (MB)':<12}"
    )
    print("-" * 80)

    baseline_vps = results_sorted[-1]["validations_per_second"]  # Slowest as baseline

    for result in results_sorted:
        speedup = result["validations_per_second"] / baseline_vps

        print(
            f"{result['strategy']:<15} "
            f"{result['validations_per_second']:>11,.0f} "
            f"{result['avg_time_per_validation_us']:>9.2f} "
            f"{speedup:>7.1f}x "
            f"{result['cache_hit_rate']:>8.1f}% "
            f"{result['peak_memory_mb']:>11.2f}"
        )

    # Detailed insights
    print(f"\n🔍 Detailed Performance Insights")
    print("=" * 50)

    fastest = results_sorted[0]
    print(f"🏆 Fastest Strategy: {fastest['strategy']}")
    print(
        f"   Performance: {fastest['validations_per_second']:,.0f} validations/second"
    )
    print(
        f"   Average time: {fastest['avg_time_per_validation_us']:.2f} microseconds per validation"
    )
    print(f"   Memory usage: {fastest['peak_memory_mb']:.2f} MB peak")
    print(f"   Cache efficiency: {fastest['cache_hit_rate']:.1f}% hit rate")

    # Single-pass analysis
    single_pass_result = next(
        (r for r in results if "Single-Pass" in r["strategy"]), None
    )
    if single_pass_result:
        print(f"\n🎯 Single-Pass Validation Analysis:")
        print(
            f"   Throughput: {single_pass_result['validations_per_second']:,.0f} validations/sec"
        )
        print(
            f"   Linear O(8) efficiency: {single_pass_result['avg_time_per_validation_us']:.2f} μs average"
        )

        # Compare to other strategies
        for result in results:
            if result["strategy"] != single_pass_result["strategy"]:
                ratio = (
                    single_pass_result["validations_per_second"]
                    / result["validations_per_second"]
                )
                print(
                    f"   vs {result['strategy']}: {ratio:.2f}x {'faster' if ratio > 1 else 'slower'}"
                )

    # Memory analysis
    print(f"\n💾 Memory Usage Analysis:")
    for result in results_sorted:
        print(
            f"   {result['strategy']}: {result['peak_memory_mb']:.2f} MB peak, "
            f"{result['cache_size']} cache items"
        )

    # Cache efficiency analysis
    print(f"\n📈 Cache Efficiency Analysis:")
    for result in results_sorted:
        if result["total_cache_calls"] > 0:
            print(
                f"   {result['strategy']}: {result['cache_hit_rate']:.1f}% hit rate "
                f"({result['total_cache_calls']:,} total calls)"
            )

    # Final recommendations
    print(f"\n💡 Performance Recommendations")
    print("=" * 40)

    if fastest["strategy"] == "V3 Single-Pass":
        print(f"✨ Single-pass validation achieves optimal performance!")
        print(
            f"   🚀 Best throughput: {fastest['validations_per_second']:,.0f} validations/sec"
        )
        print(f"   ⚡ Linear O(8) complexity with all validations combined")
        print(f"   🎯 Recommended for high-performance game engines")
    else:
        print(f"🏆 Optimal strategy: {fastest['strategy']}")
        print(
            f"   📊 Achieves {fastest['validations_per_second']:,.0f} validations/sec"
        )

        if single_pass_result:
            ratio = (
                fastest["validations_per_second"]
                / single_pass_result["validations_per_second"]
            )
            print(
                f"   📈 Single-pass is {ratio:.2f}x {'slower' if ratio > 1 else 'faster'} than optimal"
            )

    print(f"\n🎯 Use Case Guidelines:")
    print(f"   🔥 Ultra-high performance: {fastest['strategy']}")
    most_efficient_memory = min(results, key=lambda x: x["peak_memory_mb"])
    print(
        f"   💾 Memory constrained: {most_efficient_memory['strategy']} ({most_efficient_memory['peak_memory_mb']:.1f} MB)"
    )
    best_cache = max(results, key=lambda x: x["cache_hit_rate"])
    print(
        f"   📊 Cache optimization: {best_cache['strategy']} ({best_cache['cache_hit_rate']:.1f}% hit rate)"
    )


if __name__ == "__main__":
    run_high_volume_benchmark()
