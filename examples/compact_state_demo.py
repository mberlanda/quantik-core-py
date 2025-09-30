#!/usr/bin/env python3
"""
Memory Optimization Demonstration

This script demonstrates the memory savings achieved with ultra-compact
state representation compared to regular State objects.
"""

from quantik_core.profiling import MemoryTracker
from quantik_core.memory.binary_serialization import (
    BatchStateManager,
    compare_memory_usage,
)
from quantik_core.memory import (
    UltraCompactState,
    CompactStateCollection,
    StateSerializer,
    CompressionLevel,
)
from quantik_core import State
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def demonstrate_basic_compression():
    """Demonstrate basic state compression."""
    print("BASIC COMPRESSION DEMONSTRATION")
    print("=" * 50)

    # Create some states
    states = [State.empty() for _ in range(100)]

    # Convert to compact representation
    compact_states = [UltraCompactState.from_state(state) for state in states]

    # Compare memory usage
    comparison = compare_memory_usage(states, compact_states)

    print(f"Regular states: {comparison['regular_memory_bytes']:,} bytes")
    print(f"Compact states: {comparison['compact_memory_bytes']:,} bytes")
    print(
        f"Memory savings: {comparison['memory_savings_bytes']:,} bytes ({comparison['savings_percent']:.1f}%)"
    )
    print(f"Bytes per regular state: {comparison['bytes_per_regular_state']:.1f}")
    print(f"Bytes per compact state: {comparison['bytes_per_compact_state']}")
    print(f"Compression ratio: {comparison['memory_ratio']:.3f}x")


def demonstrate_pooled_vs_unpooled():
    """Demonstrate pooled vs unpooled collections."""
    print("\n\nPOOLED VS UNPOOLED COLLECTIONS")
    print("=" * 50)

    states = [State.empty() for _ in range(500)]

    # Unpooled collection
    start_time = time.time()
    collection_unpooled = CompactStateCollection(use_pool=False)
    for state in states:
        collection_unpooled.add_state(state)
    unpooled_time = time.time() - start_time

    # Pooled collection
    start_time = time.time()
    collection_pooled = CompactStateCollection(use_pool=True, pool_size=1000)
    for state in states:
        collection_pooled.add_state(state)
    pooled_time = time.time() - start_time

    # Get statistics
    unpooled_stats = collection_unpooled.get_memory_stats()
    pooled_stats = collection_pooled.get_memory_stats()

    print(f"States processed: {len(states):,}")
    print("\nUnpooled collection:")
    print(f"  Time: {unpooled_time:.4f} seconds")
    print(f"  Memory: {unpooled_stats['total_memory']:,} bytes")

    print("\nPooled collection:")
    print(f"  Time: {pooled_time:.4f} seconds")
    print(f"  Memory: {pooled_stats['total_memory']:,} bytes")
    print(f"  Pool utilization: {pooled_stats['utilization_percent']:.1f}%")

    speedup = unpooled_time / pooled_time if pooled_time > 0 else 1.0
    print(f"\nPooled speedup: {speedup:.2f}x")


def demonstrate_compression_levels():
    """Demonstrate different compression levels."""
    print("\n\nCOMPRESSION LEVELS COMPARISON")
    print("=" * 50)

    # Create test states
    states = [UltraCompactState.from_state(State.empty()) for _ in range(200)]

    compression_levels = [
        CompressionLevel.NONE,
        CompressionLevel.FAST,
        CompressionLevel.BALANCED,
        CompressionLevel.MAXIMUM,
    ]

    results = []

    for level in compression_levels:
        serializer = StateSerializer(level)

        start_time = time.time()
        data = serializer.serialize_states(states)
        serialize_time = time.time() - start_time

        start_time = time.time()
        serializer.deserialize_states(data)  # Validate deserialization works
        deserialize_time = time.time() - start_time

        # Calculate compression ratio
        uncompressed_size = len(states) * 18
        compressed_size = len(data)
        ratio = compressed_size / uncompressed_size

        results.append(
            {
                "level": level.name,
                "size": compressed_size,
                "ratio": ratio,
                "serialize_time": serialize_time,
                "deserialize_time": deserialize_time,
            }
        )

    print(f"{'Level':<10} {'Size':<8} {'Ratio':<6} {'Ser.Time':<10} {'Deser.Time':<12}")
    print("-" * 50)

    for result in results:
        print(
            f"{
                result['level']:<10} {
                result['size']:<8} {
                result['ratio']:.3f}x {
                    result['serialize_time']:.4f}s   {
                        result['deserialize_time']:.4f}s"
        )


def demonstrate_batch_management():
    """Demonstrate batch state management."""
    print("\n\nBATCH MANAGEMENT DEMONSTRATION")
    print("=" * 50)

    # Create batch manager
    manager = BatchStateManager(batch_size=50, compression=CompressionLevel.BALANCED)

    # Add states in batches
    num_states = 300
    states = [State.empty() for _ in range(num_states)]

    start_time = time.time()
    for state in states:
        manager.add_state(state)
    manager.finalize()
    batch_time = time.time() - start_time

    # Get statistics
    stats = manager.get_memory_stats()

    print(f"Processed {num_states:,} states in {batch_time:.4f} seconds")
    print(f"Batches created: {stats['completed_batches']}")
    print(f"Compression ratio: {stats['compression_ratio']:.3f}x")
    print(f"Memory savings: {stats['memory_savings_percent']:.1f}%")
    print(f"Total memory: {stats['total_memory_bytes']:,} bytes")
    print(f"Uncompressed size: {stats['uncompressed_size_bytes']:,} bytes")

    # Verify data integrity
    recovered_states = manager.get_all_states()
    print(f"Recovered {len(recovered_states):,} states successfully")


def demonstrate_memory_profiling_integration():
    """Demonstrate integration with memory profiling."""
    print("\n\nMEMORY PROFILING INTEGRATION")
    print("=" * 50)

    tracker = MemoryTracker()
    tracker.start_tracking()

    # Sample before
    tracker.sample_memory("baseline", depth=0, states_count=0)

    # Create regular states
    regular_states = [State.empty() for _ in range(200)]
    tracker.sample_memory(
        "regular_states_created", depth=1, states_count=len(regular_states)
    )

    # Convert to compact states
    compact_states = [UltraCompactState.from_state(state) for state in regular_states]
    tracker.sample_memory(
        "compact_states_created", depth=1, states_count=len(compact_states)
    )

    # Use batch manager
    manager = BatchStateManager(batch_size=25, compression=CompressionLevel.BALANCED)
    for state in regular_states:
        manager.add_state(state)
    manager.finalize()
    tracker.sample_memory(
        "batch_manager_complete", depth=1, states_count=len(regular_states)
    )

    # Generate report
    report = tracker.generate_report()
    tracker.stop_tracking()

    print("Memory usage progression:")
    for i, sample in enumerate(report.profile.samples):
        labels = [
            "baseline",
            "regular_states_created",
            "compact_states_created",
            "batch_manager_complete",
        ]
        label = labels[i] if i < len(labels) else f"sample_{i}"
        print(f"  {label:<25}: {sample.memory_rss / (1024 * 1024):.1f} MB")

    print(f"\nPeak memory: {report.profile.peak_memory / (1024 * 1024):.1f} MB")


def run_performance_benchmark():
    """Run performance benchmark comparing approaches."""
    print("\n\nPERFORMANCE BENCHMARK")
    print("=" * 50)

    num_states = 1000
    iterations = 5

    print(f"Benchmarking with {num_states:,} states, {iterations} iterations")

    # Benchmark regular state creation
    regular_times = []
    for _ in range(iterations):
        start = time.time()
        states = [State.empty() for _ in range(num_states)]
        regular_times.append(time.time() - start)

    # Benchmark compact state creation
    compact_times = []
    for _ in range(iterations):
        start = time.time()
        states = [State.empty() for _ in range(num_states)]
        compact_states = [UltraCompactState.from_state(state) for state in states]
        compact_times.append(time.time() - start)

    # Benchmark roundtrip
    roundtrip_times = []
    for _ in range(iterations):
        states = [State.empty() for _ in range(num_states)]
        compact_states = [UltraCompactState.from_state(state) for state in states]

        start = time.time()
        [
            compact.to_state() for compact in compact_states
        ]  # Validate roundtrip conversion
        roundtrip_times.append(time.time() - start)

    avg_regular = sum(regular_times) / len(regular_times)
    avg_compact = sum(compact_times) / len(compact_times)
    avg_roundtrip = sum(roundtrip_times) / len(roundtrip_times)

    print(f"\nResults (average over {iterations} runs):")
    print(
        f"Regular state creation: {avg_regular:.4f} seconds ({num_states / avg_regular:.0f} states/sec)"
    )
    print(
        f"Compact state creation: {avg_compact:.4f} seconds ({num_states / avg_compact:.0f} states/sec)"
    )
    print(
        f"Roundtrip conversion:   {avg_roundtrip:.4f} seconds ({num_states / avg_roundtrip:.0f} states/sec)"
    )

    overhead = ((avg_compact - avg_regular) / avg_regular) * 100
    print(f"Compression overhead: {overhead:.1f}%")


if __name__ == "__main__":
    try:
        print("ULTRA-COMPACT STATE REPRESENTATION DEMO")
        print("=" * 60)
        print("Demonstrating memory optimizations for game tree analysis")

        demonstrate_basic_compression()
        demonstrate_pooled_vs_unpooled()
        demonstrate_compression_levels()
        demonstrate_batch_management()
        demonstrate_memory_profiling_integration()
        run_performance_benchmark()

        print("\n" + "=" * 60)
        print("DEMONSTRATION COMPLETE!")
        print("Memory optimization infrastructure ready for game tree analysis.")

    except KeyboardInterrupt:
        print("\nDemonstration interrupted by user")
    except Exception as e:
        print(f"\nDemonstration failed: {e}")
        import traceback

        traceback.print_exc()
