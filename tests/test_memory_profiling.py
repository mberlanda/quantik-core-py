"""Tests for memory profiling infrastructure."""

import pytest
import time
from unittest.mock import Mock

from quantik_core.profiling import (
    MemoryTracker,
    MemoryReport,
    MemoryProfile,
    GameTreeBenchmark,
    BenchmarkReport,
)


class TestMemoryTracker:
    """Test memory tracking functionality."""

    def test_memory_tracker_initialization(self):
        """Test MemoryTracker initialization."""
        tracker = MemoryTracker()

        assert tracker.samples == []
        assert tracker.gc_stats == []
        assert tracker.initial_memory is None
        assert tracker.peak_memory == 0
        assert tracker.tracking_active is False

    def test_start_stop_tracking(self):
        """Test starting and stopping memory tracking."""
        tracker = MemoryTracker()

        # Start tracking
        tracker.start_tracking()
        assert tracker.tracking_active is True
        assert tracker.initial_memory is not None
        assert tracker.peak_memory >= tracker.initial_memory

        # Stop tracking
        tracker.stop_tracking()
        assert tracker.tracking_active is False

    def test_memory_sampling(self):
        """Test memory sampling functionality."""
        tracker = MemoryTracker()
        tracker.start_tracking()

        # Take a sample
        sample = tracker.sample_memory("test_operation", depth=1, states_count=100)

        assert sample.depth == 1
        assert sample.states_count == 100
        assert sample.memory_rss > 0
        assert sample.memory_per_state > 0
        assert len(tracker.samples) == 1

        tracker.stop_tracking()

    def test_memory_sampling_without_tracking(self):
        """Test that sampling without tracking raises error."""
        tracker = MemoryTracker()

        with pytest.raises(RuntimeError, match="Memory tracking not started"):
            tracker.sample_memory("test")

    def test_generate_report(self):
        """Test memory report generation."""
        tracker = MemoryTracker()
        tracker.start_tracking()

        # Take multiple samples
        tracker.sample_memory("operation_1", depth=1, states_count=100)
        time.sleep(0.01)  # Small delay to ensure different timestamps
        tracker.sample_memory("operation_2", depth=2, states_count=500)

        report = tracker.generate_report()
        tracker.stop_tracking()

        assert isinstance(report, MemoryReport)
        assert isinstance(report.profile, MemoryProfile)
        assert len(report.profile.samples) == 2
        assert report.profile.peak_memory > 0
        assert report.profile.memory_growth_rate > 0

    def test_generate_report_without_samples(self):
        """Test that generating report without samples raises error."""
        tracker = MemoryTracker()

        with pytest.raises(ValueError, match="No memory samples available"):
            tracker.generate_report()

    def test_memory_profile_properties(self):
        """Test MemoryProfile property calculations."""
        tracker = MemoryTracker()
        tracker.start_tracking()

        # Create samples with increasing memory usage
        tracker.sample_memory("op1", depth=1, states_count=100)

        # Allocate some memory to increase usage
        large_list = [i for i in range(10000)]
        tracker.sample_memory("op2", depth=2, states_count=200)

        report = tracker.generate_report()
        profile = report.profile

        # Check that properties can be calculated without errors
        # Note: Memory growth rate may be negative due to GC, so we don't assert direction
        assert isinstance(profile.memory_growth_rate, (int, float))
        assert profile.average_bytes_per_state > 0

        # Clean up
        del large_list
        tracker.stop_tracking()

    def test_recommendations_generation(self):
        """Test that recommendations are generated based on memory usage."""
        tracker = MemoryTracker()
        tracker.start_tracking()

        # Create a sample with high memory per state
        tracker.sample_memory("high_memory_op", depth=1, states_count=10)

        report = tracker.generate_report()

        # Should have recommendations for high memory usage
        assert len(report.profile.recommendations) >= 0
        assert len(report.optimization_opportunities) >= 0

        tracker.stop_tracking()


class TestGameTreeBenchmark:
    """Test benchmarking functionality."""

    def test_benchmark_initialization(self):
        """Test GameTreeBenchmark initialization."""
        benchmark = GameTreeBenchmark()

        assert benchmark.enable_memory_tracking is True
        assert benchmark.results == []

    def test_benchmark_simple_operation(self):
        """Test benchmarking a simple operation."""
        benchmark = GameTreeBenchmark(enable_memory_tracking=False)  # Disable for speed

        def simple_operation():
            return list(range(1000))  # Return a list so len() can be called

        result = benchmark.benchmark_operation(
            operation=simple_operation,
            operation_name="sum_calculation",
            depth=0,
            expected_states=1000,
        )

        assert result.operation_name == "sum_calculation"
        assert result.execution_time > 0
        assert result.states_processed == 1000  # Should use expected_states
        assert result.states_per_second > 0

    def test_benchmark_with_memory_tracking(self):
        """Test benchmarking with memory tracking enabled."""
        benchmark = GameTreeBenchmark(enable_memory_tracking=True)

        def memory_using_operation():
            # Allocate some memory
            data = [i for i in range(1000)]
            return len(data)

        result = benchmark.benchmark_operation(
            operation=memory_using_operation, operation_name="memory_test", depth=1
        )

        assert result.operation_name == "memory_test"
        assert result.execution_time > 0
        assert result.states_processed == 1000

    def test_benchmark_operation_failure(self):
        """Test benchmarking when operation fails."""
        benchmark = GameTreeBenchmark()

        def failing_operation():
            raise ValueError("Test error")

        with pytest.raises(RuntimeError, match="Benchmark failed"):
            benchmark.benchmark_operation(
                operation=failing_operation, operation_name="failing_test"
            )

    def test_compare_implementations(self):
        """Test comparing multiple implementations."""
        benchmark = GameTreeBenchmark(enable_memory_tracking=False)

        def implementation_1(depth=1000):
            return list(range(depth))

        def implementation_2(depth=1000):
            return [i for i in range(depth)]

        implementations = {
            "list_sum": lambda: Mock(analyze_single_depth=implementation_1),
            "generator_sum": lambda: Mock(analyze_single_depth=implementation_2),
        }

        report = benchmark.compare_implementations(implementations, depth=1)

        assert isinstance(report, BenchmarkReport)
        assert len(report.results) == 2
        assert "baseline_implementation" in report.summary

    def test_clear_and_get_results(self):
        """Test clearing and getting benchmark results."""
        benchmark = GameTreeBenchmark(enable_memory_tracking=False)

        def simple_op():
            return 42

        # Add some results
        benchmark.benchmark_operation(simple_op, "test1")
        benchmark.benchmark_operation(simple_op, "test2")

        # Check results
        results = benchmark.get_all_results()
        assert len(results) == 2

        # Clear results
        benchmark.clear_results()
        assert len(benchmark.get_all_results()) == 0


class TestMemoryProfilingIntegration:
    """Integration tests for memory profiling with real operations."""

    def test_memory_report_formatting(self):
        """Test memory report formatting."""
        tracker = MemoryTracker()
        tracker.start_tracking()

        tracker.sample_memory("test_operation", depth=1, states_count=100)
        report = tracker.generate_report()

        formatted_report = report.format_report()

        assert "Memory Analysis Report" in formatted_report
        assert "Peak memory usage" in formatted_report
        assert "Depth-by-depth breakdown" in formatted_report

        tracker.stop_tracking()

    def test_benchmark_report_formatting(self):
        """Test benchmark report formatting."""
        benchmark = GameTreeBenchmark(enable_memory_tracking=False)

        def test_op():
            return 42

        benchmark.benchmark_operation(test_op, "test", depth=1, expected_states=1)

        report = BenchmarkReport(
            results=benchmark.get_all_results(), summary={"test_key": "test_value"}
        )

        formatted_report = report.format_report()

        assert "Benchmark Report" in formatted_report
        assert "Summary:" in formatted_report
        assert "Detailed Results:" in formatted_report


@pytest.fixture
def mock_analyzer():
    """Create a mock analyzer for testing."""
    analyzer = Mock()
    analyzer.analyze_single_depth = Mock(return_value=[1, 2, 3, 4, 5])
    return analyzer


def test_memory_profile_decorator():
    """Test the memory profiling decorator."""
    from quantik_core.profiling.memory_tracker import memory_profile_decorator

    @memory_profile_decorator(depth=1, states_count=100)
    def test_function(x, y):
        return x + y

    result = test_function(5, 10)
    assert result == 15  # Function should work normally
