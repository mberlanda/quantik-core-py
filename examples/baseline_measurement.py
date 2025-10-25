#!/usr/bin/env python3
"""
Baseline Memory Measurement Script

This script measures current memory usage of game tree analysis
to establish optimization targets for the memory-optimized implementation.
"""

from quantik_core.profiling import MemoryTracker, GameTreeBenchmark
from quantik_core.game_stats import SymmetryTable


def measure_baseline_memory():
    """Measure baseline memory usage for depths 1-4."""
    print("Baseline Memory Measurement")
    print("=" * 50)

    # Initialize memory tracker
    tracker = MemoryTracker()
    tracker.start_tracking()

    # Initial memory sample
    tracker.sample_memory("initial_state", depth=0, states_count=1)

    try:
        # Create symmetry table analyzer
        table = SymmetryTable()

        # Measure memory for depths 1-4
        for depth in range(1, 5):
            print(f"\nAnalyzing depth {depth}...")

            # Sample memory before analysis
            tracker.sample_memory(f"before_depth_{depth}", depth=depth, states_count=0)

            # Run analysis (this is our current memory-heavy implementation)
            try:
                table.analyze_game_tree(depth)
                depth_stats = table.get_stats_at_depth(depth)
                states_count = depth_stats.unique_canonical_states if depth_stats else 0

                # Sample memory after analysis
                tracker.sample_memory(
                    f"after_depth_{depth}", depth=depth, states_count=states_count
                )

                print(f"  SUCCESS: Depth {depth}: {states_count:,} states analyzed")

            except Exception as e:
                print(f"  ERROR: Depth {depth} failed: {e}")
                # Sample memory even on failure
                tracker.sample_memory(
                    f"failed_depth_{depth}", depth=depth, states_count=0
                )

        # Generate and display report
        print("\n" + "=" * 50)
        print("MEMORY ANALYSIS REPORT")
        print("=" * 50)

        report = tracker.generate_report()
        print(report.format_report())

        # Calculate memory targets
        print("\nOPTIMIZATION TARGETS")
        print("=" * 30)

        peak_memory_mb = report.profile.peak_memory / (1024 * 1024)
        target_80_percent = peak_memory_mb * 0.2
        target_90_percent = peak_memory_mb * 0.1

        print(f"Current peak memory: {peak_memory_mb:.1f} MB")
        print(f"80% reduction target: {target_80_percent:.1f} MB")
        print(f"90% reduction target: {target_90_percent:.1f} MB")

        # Estimate memory at depth 8 (extrapolation)
        if len(report.profile.samples) >= 4:
            growth_rate = report.profile.memory_growth_rate
            depth_4_memory = max(
                s.memory_rss for s in report.profile.samples if s.depth == 4
            )
            estimated_depth_8 = depth_4_memory * (growth_rate**4)

            print("\nDEPTH 8 ESTIMATES")
            print(f"Growth rate per depth: {growth_rate:.2f}x")
            print(f"Estimated depth 8 memory: {estimated_depth_8 / (1024**3):.1f} GB")
            print(f"With 80% reduction: {estimated_depth_8 * 0.2 / (1024**3):.1f} GB")
            print(f"With 90% reduction: {estimated_depth_8 * 0.1 / (1024**3):.1f} GB")

    finally:
        tracker.stop_tracking()


def benchmark_current_implementation():
    """Benchmark current implementation for comparison."""
    print("\n\nPERFORMANCE BASELINE")
    print("=" * 50)

    benchmark = GameTreeBenchmark(enable_memory_tracking=False)  # Focus on speed

    def analyze_depth_1():
        table = SymmetryTable()
        table.analyze_game_tree(1)
        stats = table.get_stats_at_depth(1)
        return [stats] if stats else []

    def analyze_depth_2():
        table = SymmetryTable()
        table.analyze_game_tree(2)
        stats = table.get_stats_at_depth(2)
        return [stats] if stats else []

    def analyze_depth_3():
        table = SymmetryTable()
        table.analyze_game_tree(3)
        stats = table.get_stats_at_depth(3)
        return [stats] if stats else []

    try:
        # Benchmark each depth
        results = []

        print("Benchmarking depth 1...")
        result_1 = benchmark.benchmark_operation(
            analyze_depth_1, "current_depth_1", depth=1
        )
        results.append(result_1)
        print(
            f"  SUCCESS: {result_1.states_processed:,} states in "
            f"{result_1.execution_time:.3f}s ({result_1.states_per_second:,.0f} states/sec)"
        )

        print("Benchmarking depth 2...")
        result_2 = benchmark.benchmark_operation(
            analyze_depth_2, "current_depth_2", depth=2
        )
        results.append(result_2)
        print(
            f"  SUCCESS: {result_2.states_processed:,} states in "
            f"{result_2.execution_time:.3f}s ({result_2.states_per_second:,.0f} states/sec)"
        )

        print("Benchmarking depth 3...")
        result_3 = benchmark.benchmark_operation(
            analyze_depth_3, "current_depth_3", depth=3
        )
        results.append(result_3)
        print(
            f"  SUCCESS: {result_3.states_processed:,} states in "
            f"{result_3.execution_time:.3f}s ({result_3.states_per_second:,.0f} states/sec)"
        )

        # Estimate time for depth 8
        print("\nDEPTH 8 TIME ESTIMATES")
        if len(results) >= 2:
            # Calculate growth factor
            time_ratio = result_3.execution_time / result_2.execution_time
            states_ratio = result_3.states_processed / result_2.states_processed

            # Estimate depth 8 (extrapolate from depth 3)
            estimated_depth_8_states = result_3.states_processed * (states_ratio**5)
            estimated_depth_8_time = result_3.execution_time * (time_ratio**5)

            print(f"States growth per depth: {states_ratio:.1f}x")
            print(f"Time growth per depth: {time_ratio:.1f}x")
            print(f"Estimated depth 8 states: {estimated_depth_8_states:,.0f}")
            print(f"Estimated depth 8 time: {estimated_depth_8_time / 3600:.1f} hours")

    except Exception as e:
        print(f"ERROR: Benchmarking failed: {e}")


if __name__ == "__main__":
    try:
        measure_baseline_memory()
        benchmark_current_implementation()

        print("\n" + "=" * 50)
        print("Baseline measurement complete!")
        print("Results will guide memory optimization implementation.")

    except KeyboardInterrupt:
        print("\nMeasurement interrupted by user")
    except Exception as e:
        print(f"\nMeasurement failed: {e}")
        import traceback

        traceback.print_exc()
