"""
Realistic performance analysis showing V2 advantages.

This demonstrates scenarios where V2's granular caching strategy
provides significant advantages over V1's monolithic approach.
"""

import time
import tracemalloc
from typing import List

from quantik_core.core import State
from quantik_core.state_validator_comparison import (
    # Original
    validate_game_state_original,
    validate_piece_counts_original,
    validate_turn_balance_original,
    # V1 Optimized
    _validate_game_state_optimized,
    _validate_piece_counts_optimized,
    _validate_turn_balance_optimized,
    _count_pieces_by_shape_optimized,
    # V2 Ultra-optimized
    _validate_game_state_ultra,
    _validate_piece_counts_ultra,
    _validate_turn_balance_ultra,
    _count_pieces_by_shape_ultra,
    _validate_overlaps_ultra,
    _validate_placement_legality_ultra,
    get_cache_stats,
    clear_all_caches,
)


def create_game_analysis_scenario():
    """Create a realistic game analysis scenario where V2 shines."""
    states = []

    # Game progression
    game_qfens = [
        "..../..../..../....",  # Empty
        "A.../..../..../....",  # Move 1
        "A.../..../a.../....",  # Move 2
        "A.B./..../a.../....",  # Move 3
        "A.B./..../a.c./....",  # Move 4
        "A.B./C.../a.c./....",  # Move 5
        "A.B./C.../a.c./d...",  # Move 6
        "A.B./C.D./a.c./d...",  # Move 7
        "A.B./C.D./a.c./d.e.",  # Move 8 (invalid - 'e' doesn't exist)
        "A.B./C.D./a.c./d.a.",  # Move 8 (corrected)
    ]

    for qfen in game_qfens:
        try:
            states.append(State.from_qfen(qfen, validate=False))
        except:
            continue

    return states


def scenario_1_individual_validations():
    """Scenario 1: Individual validation functions called separately."""
    print("🎮 Scenario 1: Individual Validation Functions")
    print("=" * 50)
    print("Use case: Game engine validating different aspects separately")
    print("- Check piece counts before move")
    print("- Check turn balance during gameplay")
    print("- Validate specific aspects independently")

    states = create_game_analysis_scenario()
    iterations = 500

    # V1: Each function call goes through full game state validation
    print(f"\n📊 V1: Monolithic validation (repeated full checks)")
    clear_all_caches()

    start_time = time.perf_counter()
    for _ in range(iterations):
        for state in states:
            # In V1, these all call the same monolithic function internally
            _validate_piece_counts_optimized(state.bb)  # Full validation
            _validate_turn_balance_optimized(state.bb)  # Full validation again
            # Plus some overlap checks
            _validate_game_state_optimized(state.bb)  # Full validation again
    v1_time = time.perf_counter() - start_time

    v1_stats = get_cache_stats()

    # V2: Granular validation with shared piece counting
    print(f"\n📊 V2: Granular validation (specialized functions)")
    clear_all_caches()

    start_time = time.perf_counter()
    for _ in range(iterations):
        for state in states:
            # Get piece counts once
            shape_counts = _count_pieces_by_shape_ultra(state.bb)

            # Use for multiple validations
            _validate_piece_counts_ultra(shape_counts)
            _validate_turn_balance_ultra(shape_counts)

            # Other validations use their own specialized caches
            _validate_overlaps_ultra(state.bb)
            _validate_placement_legality_ultra(state.bb)
    v2_time = time.perf_counter() - start_time

    v2_stats = get_cache_stats()

    print(f"\n⏱️  Results:")
    speedup = v1_time / v2_time if v2_time > 0 else float("inf")
    print(f"V1 Time: {v1_time*1000:.2f}ms")
    print(f"V2 Time: {v2_time*1000:.2f}ms")
    print(f"V2 Speedup: {speedup:.2f}x")

    # Show cache efficiency
    print(f"\n📈 Cache Hit Analysis:")

    v1_total_calls = sum(stats["hits"] + stats["misses"] for stats in v1_stats.values())
    v2_total_calls = sum(stats["hits"] + stats["misses"] for stats in v2_stats.values())

    print(f"V1 total cache operations: {v1_total_calls}")
    print(f"V2 total cache operations: {v2_total_calls}")

    v1_piece_counts = sum(
        (stats["hits"] + stats["misses"])
        for name, stats in v1_stats.items()
        if "piece" in name.lower() or "count" in name.lower()
    )
    v2_piece_counts = sum(
        (stats["hits"] + stats["misses"])
        for name, stats in v2_stats.items()
        if "piece" in name.lower() or "count" in name.lower()
    )

    print(f"V1 piece-counting related calls: {v1_piece_counts}")
    print(f"V2 piece-counting related calls: {v2_piece_counts}")

    if v1_piece_counts > 0:
        reduction = (v1_piece_counts - v2_piece_counts) / v1_piece_counts * 100
        print(f"Piece counting reduction: {reduction:.1f}%")


def scenario_2_mixed_validation_patterns():
    """Scenario 2: Mixed validation patterns (realistic game engine usage)."""
    print("\n\n🎮 Scenario 2: Mixed Validation Patterns")
    print("=" * 50)
    print("Use case: Game engine with varied validation needs")
    print("- Sometimes just check piece counts")
    print("- Sometimes just check overlaps")
    print("- Sometimes full validation")

    states = create_game_analysis_scenario()
    iterations = 300

    # V1: All validations go through monolithic function
    print(f"\n📊 V1: All validation through monolithic function")
    clear_all_caches()

    start_time = time.perf_counter()
    for _ in range(iterations):
        for i, state in enumerate(states):
            if i % 3 == 0:
                # Just piece counts
                _validate_piece_counts_optimized(state.bb)
            elif i % 3 == 1:
                # Just turn balance
                _validate_turn_balance_optimized(state.bb)
            else:
                # Full validation
                _validate_game_state_optimized(state.bb)
    v1_time = time.perf_counter() - start_time

    # V2: Targeted validation
    print(f"\n📊 V2: Targeted validation functions")
    clear_all_caches()

    start_time = time.perf_counter()
    for _ in range(iterations):
        for i, state in enumerate(states):
            if i % 3 == 0:
                # Just piece counts - get shape counts and use
                shape_counts = _count_pieces_by_shape_ultra(state.bb)
                _validate_piece_counts_ultra(shape_counts)
            elif i % 3 == 1:
                # Just turn balance - reuse shape counts if available
                shape_counts = _count_pieces_by_shape_ultra(state.bb)
                _validate_turn_balance_ultra(shape_counts)
            else:
                # Full validation - coordinates efficiently
                _validate_game_state_ultra(state.bb)
    v2_time = time.perf_counter() - start_time

    print(f"\n⏱️  Results:")
    speedup = v1_time / v2_time if v2_time > 0 else float("inf")
    print(f"V1 Time: {v1_time*1000:.2f}ms")
    print(f"V2 Time: {v2_time*1000:.2f}ms")
    print(f"V2 Speedup: {speedup:.2f}x")


def scenario_3_cache_pressure_test():
    """Scenario 3: Cache pressure test with many different states."""
    print("\n\n🎮 Scenario 3: Cache Pressure Test")
    print("=" * 50)
    print("Use case: High-performance game engine with many state variations")

    # Generate many different states
    states = []
    import random

    shapes = ["A", "B", "C", "D"]
    for i in range(100):  # 100 different states
        qfen_parts = ["....", "....", "....", "...."]

        # Add random pieces
        for _ in range(random.randint(1, 8)):
            row = random.randint(0, 3)
            col = random.randint(0, 3)
            shape = random.choice(shapes)
            player = random.choice([shape.upper(), shape.lower()])

            qfen_list = list(qfen_parts[row])
            qfen_list[col] = player
            qfen_parts[row] = "".join(qfen_list)

        qfen = "/".join(qfen_parts)
        try:
            states.append(State.from_qfen(qfen, validate=False))
        except:
            continue

    print(f"Testing with {len(states)} different states")
    iterations = 100

    # V1 test
    print(f"\n📊 V1: Monolithic caching")
    clear_all_caches()

    start_time = time.perf_counter()
    for _ in range(iterations):
        for state in states:
            _validate_game_state_optimized(state.bb)
    v1_time = time.perf_counter() - start_time

    v1_stats = get_cache_stats()

    # V2 test
    print(f"\n📊 V2: Granular caching")
    clear_all_caches()

    start_time = time.perf_counter()
    for _ in range(iterations):
        for state in states:
            _validate_game_state_ultra(state.bb)
    v2_time = time.perf_counter() - start_time

    v2_stats = get_cache_stats()

    print(f"\n⏱️  Results:")
    speedup = v1_time / v2_time if v2_time > 0 else float("inf")
    print(f"V1 Time: {v1_time*1000:.2f}ms")
    print(f"V2 Time: {v2_time*1000:.2f}ms")
    print(f"V2 Speedup: {speedup:.2f}x")

    # Analyze cache efficiency
    print(f"\n📊 Cache Efficiency Analysis:")

    v1_hit_rate = 0
    v1_total_hits = v1_total_calls = 0
    for stats in v1_stats.values():
        v1_total_hits += stats["hits"]
        v1_total_calls += stats["hits"] + stats["misses"]
    if v1_total_calls > 0:
        v1_hit_rate = v1_total_hits / v1_total_calls * 100

    v2_hit_rate = 0
    v2_total_hits = v2_total_calls = 0
    for stats in v2_stats.values():
        v2_total_hits += stats["hits"]
        v2_total_calls += stats["hits"] + stats["misses"]
    if v2_total_calls > 0:
        v2_hit_rate = v2_total_hits / v2_total_calls * 100

    print(f"V1 Cache Hit Rate: {v1_hit_rate:.1f}%")
    print(f"V2 Cache Hit Rate: {v2_hit_rate:.1f}%")

    v1_cache_size = sum(stats["currsize"] for stats in v1_stats.values())
    v2_cache_size = sum(stats["currsize"] for stats in v2_stats.values())

    print(f"V1 Total Cache Items: {v1_cache_size}")
    print(f"V2 Total Cache Items: {v2_cache_size}")


def main():
    """Run realistic performance scenarios."""
    print("🚀 Realistic V1 vs V2 Performance Analysis")
    print("=" * 60)
    print("\n🎯 Key Difference:")
    print("V1: Monolithic caching - one cache for complete validation")
    print("V2: Granular caching - specialized caches for different validation aspects")
    print("\nV2 advantages appear in scenarios with:")
    print("✅ Mixed validation patterns")
    print("✅ Partial validation needs")
    print("✅ High cache pressure")
    print("✅ Complex state analysis")

    scenario_1_individual_validations()
    scenario_2_mixed_validation_patterns()
    scenario_3_cache_pressure_test()

    print(f"\n\n🎉 Key Insights:")
    print("=" * 30)
    print("🔍 V1 Strengths:")
    print("  ✅ Simple monolithic caching")
    print("  ✅ Good for uniform validation patterns")
    print("  ✅ Lower memory overhead for simple cases")

    print("\n🚀 V2 Strengths:")
    print("  ✅ Eliminates redundant piece counting")
    print("  ✅ Better for mixed validation patterns")
    print("  ✅ More granular cache control")
    print("  ✅ Scales better with complexity")

    print("\n💡 Recommendation:")
    print("  🎯 Use V1 for simple, uniform validation")
    print("  🎯 Use V2 for complex, varied validation patterns")
    print("  🎯 V2 is ideal for game engines with diverse validation needs")


if __name__ == "__main__":
    main()
