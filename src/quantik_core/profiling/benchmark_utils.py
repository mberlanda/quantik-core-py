"""Benchmarking utilities for game tree analysis performance measurement."""

import time
import gc
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, Any, Tuple
from .memory_tracker import MemoryTracker


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""

    operation_name: str
    execution_time: float  # seconds
    memory_used: int  # bytes
    states_processed: int
    depth: int

    @property
    def states_per_second(self) -> float:
        """Processing rate in states per second."""
        return (
            self.states_processed / self.execution_time
            if self.execution_time > 0
            else 0.0
        )

    @property
    def memory_per_state(self) -> float:
        """Memory usage per state in bytes."""
        return (
            self.memory_used / self.states_processed
            if self.states_processed > 0
            else 0.0
        )


@dataclass
class BenchmarkReport:
    """Comprehensive benchmark results."""

    results: List[BenchmarkResult]
    summary: Dict[str, Any]

    def format_report(self) -> str:
        """Format benchmark report as human-readable string."""
        lines = ["=== Game Tree Analysis Benchmark Report ===", ""]

        # Summary
        if self.summary:
            lines.append("Summary:")
            for key, value in self.summary.items():
                lines.append(f"  {key}: {value}")
            lines.append("")

        # Individual results
        lines.append("Detailed Results:")
        for result in self.results:
            lines.append(
                f"  {result.operation_name} (depth {result.depth}): "
                f"{result.execution_time:.3f}s, "
                f"{result.states_processed:,} states, "
                f"{result.states_per_second:,.0f} states/sec, "
                f"{result.memory_per_state:.0f} bytes/state"
            )

        return "\n".join(lines)


class GameTreeBenchmark:
    """Benchmark game tree operations with memory tracking."""

    def __init__(self, enable_memory_tracking: bool = True):
        self.enable_memory_tracking = enable_memory_tracking
        self.results: List[BenchmarkResult] = []

    def benchmark_operation(
        self,
        operation: Callable[[], Any],
        operation_name: str,
        depth: int = 0,
        expected_states: Optional[int] = None,
    ) -> BenchmarkResult:
        """Benchmark a single operation with memory tracking."""

        # Setup memory tracking
        memory_tracker = None
        if self.enable_memory_tracking:
            memory_tracker = MemoryTracker()
            memory_tracker.start_tracking()
            memory_before = memory_tracker.sample_memory(
                f"before_{operation_name}", depth, 0
            )

        # Force garbage collection before benchmark
        gc.collect()

        # Benchmark the operation
        start_time = time.perf_counter()
        try:
            result = operation()
            end_time = time.perf_counter()
            execution_time = end_time - start_time

            # Determine states processed
            states_processed = expected_states or 0
            if hasattr(result, "__len__"):
                states_processed = len(result)
            elif isinstance(result, (int, float)):
                states_processed = int(result)

        except Exception as e:
            if memory_tracker:
                memory_tracker.stop_tracking()
            raise RuntimeError(f"Benchmark failed for {operation_name}: {e}")

        # Measure memory after
        memory_used = 0
        if memory_tracker:
            memory_after = memory_tracker.sample_memory(
                f"after_{operation_name}", depth, states_processed
            )
            memory_used = memory_after.memory_rss - memory_before.memory_rss
            memory_tracker.stop_tracking()

        # Create result
        benchmark_result = BenchmarkResult(
            operation_name=operation_name,
            execution_time=execution_time,
            memory_used=memory_used,
            states_processed=states_processed,
            depth=depth,
        )

        self.results.append(benchmark_result)
        return benchmark_result

    def benchmark_depth_analysis(
        self, analyzer_factory: Callable[[], Any], max_depth: int = 4
    ) -> BenchmarkReport:
        """Benchmark analysis up to specified depth."""

        depth_results = []
        total_time = 0.0
        total_memory = 0
        total_states = 0

        for depth in range(1, max_depth + 1):

            def analyze_depth() -> Any:
                analyzer = analyzer_factory()
                # Assuming analyzer has analyze_single_depth method
                if hasattr(analyzer, "analyze_single_depth"):
                    return analyzer.analyze_single_depth(depth)
                elif hasattr(analyzer, "analyze_game_tree"):
                    return analyzer.analyze_game_tree(depth)
                else:
                    raise AttributeError(
                        f"Analyzer {type(analyzer)} has no analyze method"
                    )

            result = self.benchmark_operation(
                operation=analyze_depth,
                operation_name=f"depth_{depth}_analysis",
                depth=depth,
            )

            depth_results.append(result)
            total_time += result.execution_time
            total_memory += result.memory_used
            total_states += result.states_processed

        # Calculate summary statistics
        summary = {
            "total_execution_time": f"{total_time:.3f}s",
            "total_memory_used": f"{total_memory / 1024 / 1024:.1f} MB",
            "total_states_processed": f"{total_states:,}",
            "average_states_per_second": (
                f"{total_states / total_time:,.0f}" if total_time > 0 else "0"
            ),
            "average_memory_per_state": (
                f"{total_memory / total_states:.0f} bytes" if total_states > 0 else "0"
            ),
        }

        return BenchmarkReport(results=depth_results, summary=summary)

    def measure_memory_per_state(
        self, analyzer_factory: Callable[[], Any], depth: int
    ) -> Tuple[int, float]:
        """Measure memory usage per state at given depth."""

        def analyze_single_depth() -> Any:
            analyzer = analyzer_factory()
            if hasattr(analyzer, "analyze_single_depth"):
                return analyzer.analyze_single_depth(depth)
            elif hasattr(analyzer, "analyze_game_tree"):
                return analyzer.analyze_game_tree(depth)
            else:
                raise AttributeError(f"Analyzer {type(analyzer)} has no analyze method")

        result = self.benchmark_operation(
            operation=analyze_single_depth,
            operation_name=f"memory_measurement_depth_{depth}",
            depth=depth,
        )

        return result.states_processed, result.memory_per_state

    def compare_implementations(
        self, implementations: Dict[str, Callable[[], Any]], depth: int
    ) -> BenchmarkReport:
        """Compare multiple analyzer implementations."""

        comparison_results = []

        for impl_name, impl_factory in implementations.items():

            def run_implementation() -> Any:
                analyzer = impl_factory()
                if hasattr(analyzer, "analyze_single_depth"):
                    return analyzer.analyze_single_depth(depth)
                elif hasattr(analyzer, "analyze_game_tree"):
                    return analyzer.analyze_game_tree(depth)
                else:
                    raise AttributeError(
                        f"Implementation {impl_name} has no analyze method"
                    )

            result = self.benchmark_operation(
                operation=run_implementation,
                operation_name=f"{impl_name}_depth_{depth}",
                depth=depth,
            )

            comparison_results.append(result)

        # Calculate comparison summary
        if comparison_results:
            baseline = comparison_results[0]
            summary = {
                "baseline_implementation": baseline.operation_name,
                "baseline_time": f"{baseline.execution_time:.3f}s",
                "baseline_memory": f"{baseline.memory_used / 1024 / 1024:.1f} MB",
            }

            # Add relative performance for other implementations
            for i, result in enumerate(comparison_results[1:], 1):
                speedup = (
                    baseline.execution_time / result.execution_time
                    if result.execution_time > 0
                    else 0
                )
                memory_ratio = (
                    result.memory_used / baseline.memory_used
                    if baseline.memory_used > 0
                    else 0
                )

                summary[f"impl_{i + 1}_speedup"] = f"{speedup:.2f}x"
                summary[f"impl_{i + 1}_memory_ratio"] = f"{memory_ratio:.2f}x"
        else:
            summary = {}

        return BenchmarkReport(results=comparison_results, summary=summary)

    def get_all_results(self) -> List[BenchmarkResult]:
        """Get all benchmark results."""
        return self.results.copy()

    def clear_results(self) -> None:
        """Clear all benchmark results."""
        self.results.clear()


def quick_benchmark(
    operation: Callable[[], Any], name: str = "operation"
) -> BenchmarkResult:
    """Quick benchmark for a single operation without full setup."""
    benchmark = GameTreeBenchmark(enable_memory_tracking=False)
    return benchmark.benchmark_operation(operation, name)
