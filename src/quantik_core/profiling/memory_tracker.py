"""Memory tracking and profiling tools for game tree analysis optimization."""

import gc
import tracemalloc
import psutil
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable, Any


@dataclass
class MemorySample:
    """Single memory measurement sample."""

    timestamp: datetime
    depth: int
    states_count: int
    memory_rss: int  # Resident Set Size in bytes
    memory_vms: int  # Virtual Memory Size in bytes
    tracemalloc_current: int
    tracemalloc_peak: int
    gc_collections: Tuple[int, int, int]  # Gen 0, 1, 2 collection counts

    @property
    def memory_per_state(self) -> float:
        """Memory usage per state in bytes."""
        return self.memory_rss / self.states_count if self.states_count > 0 else 0.0

    @property
    def memory_rss_mb(self) -> float:
        """RSS memory in MB."""
        return self.memory_rss / (1024 * 1024)

    @property
    def memory_vms_mb(self) -> float:
        """VMS memory in MB."""
        return self.memory_vms / (1024 * 1024)


@dataclass
class MemoryProfile:
    """Complete memory profiling results."""

    samples: List[MemorySample]
    total_memory_used: int
    peak_memory: int
    initial_memory: int
    recommendations: List[str]
    gc_overhead_percent: float

    @property
    def memory_growth_rate(self) -> float:
        """Average memory growth rate between depths."""
        if len(self.samples) < 2:
            return 0.0

        growth_rates = []
        for i in range(1, len(self.samples)):
            prev_memory = self.samples[i - 1].memory_rss
            curr_memory = self.samples[i].memory_rss
            if prev_memory > 0:
                growth_rate = curr_memory / prev_memory
                growth_rates.append(growth_rate)

        return sum(growth_rates) / len(growth_rates) if growth_rates else 0.0

    @property
    def average_bytes_per_state(self) -> float:
        """Average bytes per state across all samples."""
        if not self.samples:
            return 0.0

        valid_samples = [s for s in self.samples if s.states_count > 0]
        if not valid_samples:
            return 0.0

        total_bytes_per_state = sum(s.memory_per_state for s in valid_samples)
        return total_bytes_per_state / len(valid_samples)


@dataclass
class MemoryReport:
    """Detailed memory analysis report."""

    profile: MemoryProfile
    projections: Dict[int, int]  # depth -> projected memory usage
    optimization_opportunities: List[str]
    critical_warnings: List[str]

    def format_report(self) -> str:
        """Format memory report as human-readable string."""
        lines = [
            "=== Memory Analysis Report ===",
            f"Peak memory usage: {self.profile.peak_memory / 1024 / 1024:.1f} MB",
            f"Total memory used: {self.profile.total_memory_used / 1024 / 1024:.1f} MB",
            f"Average bytes per state: {self.profile.average_bytes_per_state:.0f}",
            f"Memory growth rate: {self.profile.memory_growth_rate:.2f}x per depth",
            f"GC overhead: {self.profile.gc_overhead_percent:.1f}%",
            "",
            "Depth-by-depth breakdown:",
        ]

        for sample in self.profile.samples:
            lines.append(
                f"  Depth {sample.depth}: {sample.states_count:,} states, "
                f"{sample.memory_rss_mb:.1f} MB, {sample.memory_per_state:.0f} bytes/state"
            )

        if self.projections:
            lines.extend(
                [
                    "",
                    "Projected memory usage:",
                ]
            )
            for depth, memory in sorted(self.projections.items()):
                lines.append(f"  Depth {depth}: {memory / 1024 / 1024 / 1024:.2f} GB")

        if self.critical_warnings:
            lines.extend(
                [
                    "",
                    "⚠️  CRITICAL WARNINGS:",
                ]
            )
            for warning in self.critical_warnings:
                lines.append(f"  - {warning}")

        if self.optimization_opportunities:
            lines.extend(
                [
                    "",
                    "💡 Optimization opportunities:",
                ]
            )
            for opportunity in self.optimization_opportunities:
                lines.append(f"  - {opportunity}")

        return "\n".join(lines)


class MemoryTracker:
    """Track memory usage with detailed allocation breakdown."""

    def __init__(self) -> None:
        self.samples: List[MemorySample] = []
        self.gc_stats: List[Tuple[int, int, int]] = []
        self.initial_memory: Optional[int] = None
        self.peak_memory: int = 0
        self.tracking_active: bool = False
        self.process = psutil.Process()

    def start_tracking(self) -> None:
        """Start memory tracking with tracemalloc."""
        if self.tracking_active:
            return

        tracemalloc.start()
        self.initial_memory = self.process.memory_info().rss
        self.peak_memory = self.initial_memory
        self.tracking_active = True

        # Record initial GC stats
        self.gc_stats.append(tuple(gc.get_stats()[i]["collections"] for i in range(3)))

    def stop_tracking(self) -> None:
        """Stop memory tracking."""
        if not self.tracking_active:
            return

        tracemalloc.stop()
        self.tracking_active = False

    def sample_memory(
        self, label: str, depth: int = 0, states_count: int = 0
    ) -> MemorySample:
        """Take memory sample with label."""
        if not self.tracking_active:
            raise RuntimeError(
                "Memory tracking not started. Call start_tracking() first."
            )

        # Get current memory info
        memory_info = self.process.memory_info()
        current_memory = memory_info.rss

        # Update peak memory
        self.peak_memory = max(self.peak_memory, current_memory)

        # Get tracemalloc info
        tracemalloc_current, tracemalloc_peak = tracemalloc.get_traced_memory()

        # Get GC stats
        current_gc_stats = tuple(gc.get_stats()[i]["collections"] for i in range(3))

        # Create sample
        sample = MemorySample(
            timestamp=datetime.now(),
            depth=depth,
            states_count=states_count,
            memory_rss=current_memory,
            memory_vms=memory_info.vms,
            tracemalloc_current=tracemalloc_current,
            tracemalloc_peak=tracemalloc_peak,
            gc_collections=current_gc_stats,
        )

        self.samples.append(sample)
        return sample

    def generate_report(self) -> MemoryReport:
        """Generate comprehensive memory report."""
        if not self.samples:
            raise ValueError("No memory samples available. Call sample_memory() first.")

        # Calculate GC overhead
        gc_overhead = self._calculate_gc_overhead()

        # Generate recommendations
        recommendations = self._generate_recommendations()

        # Generate projections
        projections = self._generate_projections()

        # Identify optimization opportunities
        optimization_opportunities = self._identify_optimizations()

        # Identify critical warnings
        critical_warnings = self._identify_critical_warnings()

        # Create profile
        profile = MemoryProfile(
            samples=self.samples.copy(),
            total_memory_used=self.peak_memory - (self.initial_memory or 0),
            peak_memory=self.peak_memory,
            initial_memory=self.initial_memory or 0,
            recommendations=recommendations,
            gc_overhead_percent=gc_overhead,
        )

        return MemoryReport(
            profile=profile,
            projections=projections,
            optimization_opportunities=optimization_opportunities,
            critical_warnings=critical_warnings,
        )

    def _calculate_gc_overhead(self) -> float:
        """Calculate garbage collection overhead percentage."""
        if len(self.gc_stats) < 2:
            return 0.0

        initial_collections = sum(self.gc_stats[0])
        final_collections = sum(self.gc_stats[-1])
        total_collections = final_collections - initial_collections

        # Estimate GC time (rough heuristic)
        # Gen 0: ~1ms, Gen 1: ~10ms, Gen 2: ~100ms
        estimated_gc_time = total_collections * 0.001  # Very rough estimate

        # Calculate as percentage of total analysis time
        if len(self.samples) >= 2:
            total_time = (
                self.samples[-1].timestamp - self.samples[0].timestamp
            ).total_seconds()
            if total_time > 0:
                return (estimated_gc_time / total_time) * 100

        return 0.0

    def _generate_recommendations(self) -> List[str]:
        """Generate memory optimization recommendations."""
        recommendations = []

        if len(self.samples) >= 3:
            # Analyze growth pattern
            recent_samples = self.samples[-3:]
            growth_rates = []

            for i in range(1, len(recent_samples)):
                prev_sample = recent_samples[i - 1]
                curr_sample = recent_samples[i]

                if prev_sample.memory_rss > 0:
                    growth_rate = curr_sample.memory_rss / prev_sample.memory_rss
                    growth_rates.append(growth_rate)

            avg_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 1.0

            if avg_growth > 5.0:
                recommendations.append(
                    "Memory growth rate too high - implement state compression"
                )

            # Check bytes per state
            latest_sample = self.samples[-1]
            if latest_sample.memory_per_state > 100:
                recommendations.append(
                    "High memory per state - optimize state representation"
                )

            if latest_sample.memory_per_state > 500:
                recommendations.append(
                    "CRITICAL: Memory per state extremely high - major optimization needed"
                )

        return recommendations

    def _generate_projections(self) -> Dict[int, int]:
        """Generate memory usage projections for higher depths."""
        if len(self.samples) < 2:
            return {}

        # Use latest sample for projection
        latest_sample = self.samples[-1]
        bytes_per_state = latest_sample.memory_per_state

        # Known state counts for projection
        projected_states = {
            6: 901_916,
            7: 4_658_465,
            8: 17_900_160,
            9: 60_000_000,  # Estimated
            10: 180_000_000,  # Estimated
        }

        projections = {}
        for depth, state_count in projected_states.items():
            if depth > latest_sample.depth:  # Only project beyond current depth
                projected_memory = int(state_count * bytes_per_state)
                projections[depth] = projected_memory

        return projections

    def _identify_optimizations(self) -> List[str]:
        """Identify specific optimization opportunities."""
        opportunities: List[str] = []

        if not self.samples:
            return opportunities

        latest_sample = self.samples[-1]

        # State representation optimization
        if latest_sample.memory_per_state > 50:
            opportunities.append(
                "Implement compact state representation (target: 18 bytes per state)"
            )

        # Tree structure optimization
        if latest_sample.memory_per_state > 100:
            opportunities.append("Use ID-based references instead of object pointers")

        # Compression opportunities
        if latest_sample.states_count > 1000:
            opportunities.append("Implement state clustering with compression")

        # GC optimization
        if self._calculate_gc_overhead() > 5.0:
            opportunities.append("Optimize garbage collection settings")

        # Memory growth pattern
        growth_rate = self.profile.memory_growth_rate if hasattr(self, "profile") else 0
        if growth_rate > 10.0:
            opportunities.append("Implement depth-based memory management")

        return opportunities

    def _identify_critical_warnings(self) -> List[str]:
        """Identify critical memory issues."""
        warnings: List[str] = []

        if not self.samples:
            return warnings

        # Check for explosive growth
        if len(self.samples) >= 2:
            growth_rate = self.samples[-1].memory_rss / self.samples[0].memory_rss
            if growth_rate > 100:
                warnings.append(
                    "Explosive memory growth detected - analysis may not complete"
                )

        # Check for very high memory per state
        latest_sample = self.samples[-1]
        if latest_sample.memory_per_state > 1000:
            warnings.append(
                "Extremely high memory per state - immediate optimization required"
            )

        # Check projections
        projections = self._generate_projections()
        for depth, memory in projections.items():
            if memory > 32 * 1024 * 1024 * 1024:  # 32 GB
                warnings.append(
                    f"Depth {depth} projected to use {memory / 1024**3:.1f} GB - exceeds reasonable limits"
                )

        return warnings


def memory_profile_decorator(
    depth: int = 0, states_count: int = 0
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to automatically profile memory usage of a function."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracker = MemoryTracker()
            tracker.start_tracking()

            try:
                # Sample before
                tracker.sample_memory(f"before_{func.__name__}", depth, states_count)

                # Execute function
                result = func(*args, **kwargs)

                # Sample after
                tracker.sample_memory(f"after_{func.__name__}", depth, states_count)

                return result
            finally:
                tracker.stop_tracking()

        return wrapper

    return decorator
