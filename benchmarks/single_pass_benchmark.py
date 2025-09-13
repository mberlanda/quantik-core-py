"""
Comprehensive benchmark comparing all optimization levels including single-pass.

This benchmark tests:
- Original: Baseline unoptimized implementation
- V1: Individual function caching
- V2: Shared piece count caching
- Ultra: Granular specialized caching
- Single-pass: Ultimate O(8) linear optimization
- Hybrid: Single-pass + cached placement
"""

import time
import tracemalloc
from typing import List, Dict

from quantik_core.core import State
from quantik_core.state_validator_comparison import (
    validate_game_state,
    clear_all_caches,
    get_cache_stats,
)


def generate_test_states() -> List[State]:
    """Generate a variety of test states for benchmarking."""
    test_qfens = [
        "..../..../..../....",  # Empty
        "A.../..../..../....",  # Single piece
        "A.../..../a.../....",  # Two pieces
        "AB../..../..../....",  # Adjacent pieces
        "AB../..../ab../....",  # Mirror pattern
        "A.B./..../a.b./....",  # Scattered
        "AB../CD../..../....",  # Player 0 line
        "AB../CD../ab../cd..",  # Full mirror
        "ABCD/..../abcd/....",  # Two full rows
        "AB../CD../ab../cd..",  # Complex state
        # Add some invalid states for comprehensive testing
        "A.../..../..a./....",  # Valid placement
        "AA../..../..../....",  # Invalid (too many A's)
        "A.../B.../a.../b...",  # Valid complex
    ]

    states = []
    for qfen in test_qfens:
        try:
            state = State.from_qfen(qfen, validate=False)
            states.append(state)
        except:
            continue

    # Add repeated states to test cache efficiency
    repeated_states = states[:5] * 10  # Repeat first 5 states 10 times each
    states.extend(repeated_states)

    return states


def benchmark_optimization_level(
    states: List[State], optimization_level: str, iterations: int = 100
) -> Dict:
    """Benchmark a specific optimization level."""
    clear_all_caches()

    # Memory tracking
    tracemalloc.start()

    # Performance timing
    start_time = time.perf_counter()

    for _ in range(iterations):
        for state in states:
            validate_game_state(state, optimization_level=optimization_level)

    end_time = time.perf_counter()

    # Get memory usage
    current_memory, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Get cache statistics
    cache_stats = get_cache_stats()

    # Calculate cache metrics
    total_hits = sum(stats["hits"] for stats in cache_stats.values())
    total_misses = sum(stats["misses"] for stats in cache_stats.values())
    total_calls = total_hits + total_misses
    hit_rate = (total_hits / total_calls * 100) if total_calls > 0 else 0
    cache_size = sum(stats["currsize"] for stats in cache_stats.values())

    return {
        "time_ms": (end_time - start_time) * 1000,
        "peak_memory_kb": peak_memory / 1024,
        "current_memory_kb": current_memory / 1024,
        "cache_hit_rate": hit_rate,
        "cache_size": cache_size,
        "total_cache_calls": total_calls,
        "cache_stats": cache_stats,
    }


def run_comprehensive_benchmark():
    """Run comprehensive benchmark across all optimization levels."""
    print("🚀 Comprehensive State Validator Optimization Benchmark")
    print("=" * 70)

    states = generate_test_states()
    iterations = 200

    print(f"Test configuration:")
    print(f"  States: {len(states)} (includes cache-friendly repeats)")
    print(f"  Iterations: {iterations}")
    print(f"  Total validations: {len(states) * iterations:,}")

    optimization_levels = [
        ("original", "Original (baseline)"),
        ("v1", "V1 (individual caching)"),
        ("ultra", "V2/Ultra (granular caching)"),
        ("single_pass", "V3 Single-pass (ultimate)"),
        ("hybrid", "V3 Hybrid (single-pass + cached)"),
    ]

    results = {}

    print(f"\n📊 Running benchmarks...")

    for level, description in optimization_levels:
        print(f"\nTesting {description}...")
        results[level] = benchmark_optimization_level(states, level, iterations)
        print(f"  Time: {results[level]['time_ms']:.2f}ms")
        print(f"  Cache hit rate: {results[level]['cache_hit_rate']:.1f}%")

    # Analysis and comparison
    print(f"\n📈 Performance Comparison Results")
    print("=" * 60)

    # Use original as baseline
    baseline_time = results["original"]["time_ms"]

    print(
        f"{'Optimization Level':<25} {'Time (ms)':<12} {'Speedup':<10} {'Hit Rate':<10} {'Memory (KB)':<12}"
    )
    print("-" * 75)

    for level, description in optimization_levels:
        result = results[level]
        speedup = baseline_time / result["time_ms"]

        print(
            f"{description:<25} {result['time_ms']:<12.2f} {speedup:<10.2f}x {result['cache_hit_rate']:<10.1f}% {result['peak_memory_kb']:<12.1f}"
        )

    # Detailed analysis
    print(f"\n🔍 Detailed Analysis")
    print("=" * 40)

    # Find fastest approach
    fastest_level = min(results.keys(), key=lambda x: results[x]["time_ms"])
    fastest_time = results[fastest_level]["time_ms"]

    print(
        f"🏆 Fastest: {dict(optimization_levels)[fastest_level]} ({fastest_time:.2f}ms)"
    )

    # Memory efficiency
    most_memory_efficient = min(
        results.keys(), key=lambda x: results[x]["peak_memory_kb"]
    )
    memory_efficient_usage = results[most_memory_efficient]["peak_memory_kb"]

    print(
        f"💾 Most memory efficient: {dict(optimization_levels)[most_memory_efficient]} ({memory_efficient_usage:.1f}KB)"
    )

    # Cache efficiency
    best_cache_level = max(results.keys(), key=lambda x: results[x]["cache_hit_rate"])
    best_cache_rate = results[best_cache_level]["cache_hit_rate"]

    print(
        f"📈 Best cache hit rate: {dict(optimization_levels)[best_cache_level]} ({best_cache_rate:.1f}%)"
    )

    # Single-pass analysis
    if "single_pass" in results:
        single_pass_result = results["single_pass"]
        ultra_result = results["ultra"]

        single_pass_speedup = ultra_result["time_ms"] / single_pass_result["time_ms"]

        print(f"\n🎯 Single-pass Analysis:")
        print(f"  Single-pass vs Ultra: {single_pass_speedup:.2f}x speedup")
        print(
            f"  Single-pass vs Original: {baseline_time / single_pass_result['time_ms']:.2f}x speedup"
        )
        print(f"  Memory overhead: {single_pass_result['peak_memory_kb']:.1f}KB")
        print(
            f"  Cache efficiency: {single_pass_result['cache_hit_rate']:.1f}% hit rate"
        )

    # Recommendations
    print(f"\n💡 Recommendations")
    print("=" * 30)

    print(f"🎯 For maximum speed: Use '{fastest_level}' optimization")
    print(f"💾 For memory efficiency: Use '{most_memory_efficient}' optimization")
    print(f"📊 For cache efficiency: Use '{best_cache_level}' optimization")

    if fastest_level == "single_pass":
        print(f"\n✨ Single-pass validation achieves optimal performance!")
        print(f"   🚀 Linear O(8) complexity with all validations combined")
        print(
            f"   ⚡ Maximum speedup over baseline: {baseline_time / fastest_time:.1f}x"
        )
        print(f"   🎯 Ideal for performance-critical game engines")
    else:
        print(f"\n🤔 Single-pass performance notes:")
        single_vs_fastest = (
            results["single_pass"]["time_ms"] / results[fastest_level]["time_ms"]
        )
        if single_vs_fastest > 1.1:
            print(
                f"   ⚠️  Single-pass is {single_vs_fastest:.1f}x slower than {fastest_level}"
            )
            print(
                f"   💭 Cache efficiency may outweigh linear optimization in this scenario"
            )
        else:
            print(
                f"   ✅ Single-pass performs competitively ({single_vs_fastest:.1f}x vs {fastest_level})"
            )


def analyze_single_pass_characteristics():
    """Analyze the characteristics of single-pass validation."""
    print(f"\n\n🔬 Single-Pass Validation Analysis")
    print("=" * 50)

    print("✅ What single-pass achieves:")
    print("  🎯 Exactly ONE iteration through the 8-element bitboard")
    print(
        "  ⚡ All validations (piece counts, turn balance, overlaps, placement) in one pass"
    )
    print("  💾 Minimal memory allocation (only counter variables)")
    print("  🚀 O(8) linear complexity - theoretically optimal")
    print("  📊 Single cache for complete validation result")

    print("\n⚖️  Trade-offs:")
    print("  ✅ Pros:")
    print("     - Minimal memory access (single pass)")
    print("     - No redundant calculations")
    print("     - Cache-friendly memory pattern")
    print("     - Optimal algorithmic complexity")

    print("  ⚠️  Cons:")
    print("     - Less cache granularity (all-or-nothing caching)")
    print("     - Cannot skip expensive checks for partial validation")
    print("     - Placement legality still requires separate line checking")

    print("\n🎮 Best use cases:")
    print("  ✅ Game engines requiring complete state validation")
    print("  ✅ Performance-critical paths with repeated states")
    print("  ✅ Systems with memory constraints")
    print("  ✅ Hot paths in AI game tree search")


if __name__ == "__main__":
    run_comprehensive_benchmark()
    analyze_single_pass_characteristics()
