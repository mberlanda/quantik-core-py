"""Tests for ultra-compact state representation."""

import pytest
import struct

from quantik_core import State
from quantik_core.memory import (
    UltraCompactState,
    CompactStatePool,
    StateSerializer,
    CompressionLevel,
    CompactStateCollection,
)
from quantik_core.memory.binary_serialization import (
    BatchStateManager,
    compare_memory_usage,
)


class TestUltraCompactState:
    """Test ultra-compact state representation."""

    def test_compact_state_creation(self):
        """Test creating compact state from regular state."""
        # Create empty state
        state = State.empty()
        compact = UltraCompactState.from_state(state)

        assert len(compact.packed_data) == 18
        assert compact.memory_footprint == 18
        assert len(compact) == 18

    def test_state_roundtrip(self):
        """Test state -> compact -> state roundtrip."""
        # Test with empty state
        empty_state = State.empty()
        compact = UltraCompactState.from_state(empty_state)
        restored = compact.to_state()

        assert empty_state.pack() == restored.pack()

    def test_compact_state_equality(self):
        """Test compact state equality and hashing."""
        state1 = State.empty()
        state2 = State.empty()

        compact1 = UltraCompactState.from_state(state1)
        compact2 = UltraCompactState.from_state(state2)

        assert compact1 == compact2
        assert hash(compact1) == hash(compact2)

    def test_compact_state_validation(self):
        """Test validation of compact state data."""
        # Valid 18-byte data
        valid_data = b"x" * 18
        compact = UltraCompactState(packed_data=valid_data)
        assert compact.memory_footprint == 18

        # Invalid data length
        with pytest.raises(ValueError, match="must be exactly 18 bytes"):
            UltraCompactState(packed_data=b"x" * 17)

        with pytest.raises(ValueError, match="must be exactly 18 bytes"):
            UltraCompactState(packed_data=b"x" * 19)

    def test_compact_state_repr(self):
        """Test compact state string representation."""
        state = State.empty()
        compact = UltraCompactState.from_state(state)
        repr_str = repr(compact)

        assert "UltraCompactState" in repr_str
        assert "18 bytes" in repr_str
        assert "hash=" in repr_str


class TestCompactStatePool:
    """Test compact state memory pool."""

    def test_pool_initialization(self):
        """Test pool initialization."""
        pool = CompactStatePool(initial_size=100)

        assert pool.size == 100
        assert pool.free_count == 100
        assert pool.allocated_count == 0
        assert pool.utilization == 0.0

    def test_state_allocation(self):
        """Test allocating states in pool."""
        pool = CompactStatePool(initial_size=10)
        state = State.empty()
        state_data = state.pack()

        # Allocate first state
        index1 = pool.allocate_state(state_data)
        assert index1 == 0
        assert pool.allocated_count == 1
        assert pool.utilization == 10.0

        # Allocate second state
        index2 = pool.allocate_state(state_data)
        assert index2 == 1
        assert pool.allocated_count == 2

    def test_state_retrieval(self):
        """Test retrieving states from pool."""
        pool = CompactStatePool(initial_size=10)
        state = State.empty()
        state_data = state.pack()

        index = pool.allocate_state(state_data)
        retrieved = pool.get_state(index)

        assert isinstance(retrieved, UltraCompactState)
        assert retrieved.packed_data == state_data

    def test_state_deallocation(self):
        """Test deallocating states."""
        pool = CompactStatePool(initial_size=10)
        state = State.empty()
        state_data = state.pack()

        index = pool.allocate_state(state_data)
        assert pool.allocated_count == 1

        pool.deallocate_state(index)
        assert pool.allocated_count == 0
        assert pool.free_count == 10

        # Should raise error when accessing deallocated state
        with pytest.raises(IndexError, match="has been deallocated"):
            pool.get_state(index)

    def test_pool_expansion(self):
        """Test pool expansion when full."""
        pool = CompactStatePool(initial_size=2)
        state = State.empty()
        state_data = state.pack()

        # Fill initial pool
        pool.allocate_state(state_data)  # index 0
        pool.allocate_state(state_data)  # index 1
        assert pool.size == 2

        # Should expand pool
        index3 = pool.allocate_state(state_data)
        assert pool.size == 3
        assert index3 == 2

    def test_pool_reuse(self):
        """Test reusing deallocated slots."""
        pool = CompactStatePool(initial_size=5)
        state = State.empty()
        state_data = state.pack()

        # Allocate all initial slots
        indices = []
        for i in range(5):
            index = pool.allocate_state(state_data)
            indices.append(index)

        # Deallocate one slot
        pool.deallocate_state(indices[2])  # Deallocate index 2
        original_reuse_count = pool.reuse_count

        # Should reuse the deallocated slot
        reused_index = pool.allocate_state(state_data)
        assert reused_index == indices[2]  # Should get back index 2
        assert pool.reuse_count == original_reuse_count + 1

    def test_pool_stats(self):
        """Test pool statistics."""
        pool = CompactStatePool(initial_size=10)
        state = State.empty()
        state_data = state.pack()

        pool.allocate_state(state_data)
        pool.allocate_state(state_data)

        stats = pool.get_stats()
        expected_memory = 10 * 18  # 10 slots * 18 bytes each

        assert stats["total_size"] == 10
        assert stats["allocated"] == 2
        assert stats["free"] == 8
        assert stats["utilization_percent"] == 20.0
        assert stats["memory_bytes"] == expected_memory

    def test_pool_clear(self):
        """Test clearing pool."""
        pool = CompactStatePool(initial_size=5)
        state = State.empty()
        state_data = state.pack()

        pool.allocate_state(state_data)
        pool.allocate_state(state_data)

        pool.clear()
        assert pool.allocated_count == 0
        assert pool.free_count == 5
        assert pool.reuse_count == 0


class TestCompactStateCollection:
    """Test compact state collection."""

    def test_collection_without_pool(self):
        """Test collection without memory pooling."""
        collection = CompactStateCollection(use_pool=False)
        state = State.empty()

        index = collection.add_state(state)
        assert index == 0
        assert len(collection) == 1

        retrieved = collection.get_state(index)
        assert retrieved.pack() == state.pack()

    def test_collection_with_pool(self):
        """Test collection with memory pooling."""
        collection = CompactStateCollection(use_pool=True, pool_size=10)
        state = State.empty()

        index = collection.add_state(state)
        assert index == 0
        assert len(collection) == 1

        retrieved = collection.get_state(index)
        assert retrieved.pack() == state.pack()

    def test_collection_memory_stats(self):
        """Test collection memory statistics."""
        # Test without pool
        collection = CompactStateCollection(use_pool=False)
        state = State.empty()
        collection.add_state(state)

        stats = collection.get_memory_stats()
        assert stats["states_count"] == 1
        assert stats["states_memory"] == 18
        assert stats["pool_enabled"] is False

        # Test with pool
        collection_pooled = CompactStateCollection(use_pool=True, pool_size=10)
        collection_pooled.add_state(state)

        stats_pooled = collection_pooled.get_memory_stats()
        assert stats_pooled["indices_count"] == 1
        assert stats_pooled["total_size"] == 10


class TestStateSerializer:
    """Test state serialization."""

    def test_serialization_no_compression(self):
        """Test serialization without compression."""
        serializer = StateSerializer(CompressionLevel.NONE)
        states = [UltraCompactState.from_state(State.empty()) for _ in range(3)]

        data = serializer.serialize_states(states)
        restored = serializer.deserialize_states(data)

        assert len(restored) == 3
        for original, restored_state in zip(states, restored):
            assert original == restored_state

    def test_serialization_with_compression(self):
        """Test serialization with compression."""
        serializer = StateSerializer(CompressionLevel.BALANCED)
        states = [UltraCompactState.from_state(State.empty()) for _ in range(5)]

        data = serializer.serialize_states(states)
        restored = serializer.deserialize_states(data)

        assert len(restored) == 5
        for original, restored_state in zip(states, restored):
            assert original == restored_state

    def test_empty_serialization(self):
        """Test serializing empty list."""
        serializer = StateSerializer(CompressionLevel.NONE)

        data = serializer.serialize_states([])
        restored = serializer.deserialize_states(data)

        assert len(restored) == 0

    def test_compression_ratio_estimation(self):
        """Test compression ratio estimation."""
        serializer = StateSerializer(CompressionLevel.BALANCED)
        states = [UltraCompactState.from_state(State.empty()) for _ in range(10)]

        ratio = serializer.estimate_compression_ratio(states)
        assert 0.0 < ratio <= 1.0  # Should be between 0 and 1

    def test_invalid_data_deserialization(self):
        """Test handling invalid serialized data."""
        serializer = StateSerializer(CompressionLevel.NONE)

        # Too short data
        with pytest.raises(ValueError, match="too short for header"):
            serializer.deserialize_states(b"abc")

        # Invalid state size
        invalid_header = struct.pack("!IH", 1, 20)  # Wrong state size
        invalid_data = invalid_header + b"x" * 20
        with pytest.raises(ValueError, match="Invalid state size"):
            serializer.deserialize_states(invalid_data)


class TestBatchStateManager:
    """Test batch state manager."""

    def test_batch_manager_basic(self):
        """Test basic batch manager functionality."""
        manager = BatchStateManager(batch_size=2, compression=CompressionLevel.NONE)

        # Add states
        state = State.empty()
        manager.add_state(state)
        manager.add_state(state)
        manager.add_state(state)  # Should trigger batch flush

        manager.finalize()

        all_states = manager.get_all_states()
        assert len(all_states) == 3

    def test_batch_manager_stats(self):
        """Test batch manager statistics."""
        manager = BatchStateManager(batch_size=2, compression=CompressionLevel.NONE)

        state = State.empty()
        manager.add_state(state)
        manager.add_state(state)
        manager.add_state(state)

        stats = manager.get_memory_stats()
        assert stats["total_states"] == 3
        assert stats["completed_batches"] == 1
        assert stats["current_batch_size"] == 1

    def test_batch_manager_clear(self):
        """Test clearing batch manager."""
        manager = BatchStateManager(batch_size=2)

        state = State.empty()
        manager.add_state(state)
        manager.add_state(state)

        manager.clear()

        stats = manager.get_memory_stats()
        assert stats["total_states"] == 0
        assert stats["completed_batches"] == 0


class TestMemoryComparison:
    """Test memory usage comparison utilities."""

    def test_memory_comparison(self):
        """Test comparing memory usage between regular and compact states."""
        regular_states = [State.empty() for _ in range(5)]
        compact_states = [
            UltraCompactState.from_state(state) for state in regular_states
        ]

        comparison = compare_memory_usage(regular_states, compact_states)

        assert comparison["state_count"] == 5
        assert comparison["compact_memory_bytes"] == 5 * 18
        assert comparison["bytes_per_compact_state"] == 18
        assert comparison["memory_ratio"] < 1.0  # Compact should be smaller
        assert comparison["savings_percent"] > 0

    def test_memory_comparison_validation(self):
        """Test memory comparison validation."""
        regular_states = [State.empty()]
        compact_states = [UltraCompactState.from_state(State.empty()) for _ in range(2)]

        with pytest.raises(ValueError, match="must have same length"):
            compare_memory_usage(regular_states, compact_states)


class TestIntegrationScenarios:
    """Integration tests for real-world scenarios."""

    def test_memory_optimization_workflow(self):
        """Test complete memory optimization workflow."""
        # Simulate analyzing states
        states = [State.empty() for _ in range(100)]

        # Convert to compact representation
        [
            UltraCompactState.from_state(state) for state in states
        ]  # Validate conversion works

        # Use batch manager for efficient storage
        manager = BatchStateManager(
            batch_size=20, compression=CompressionLevel.BALANCED
        )
        for state in states:
            manager.add_state(state)
        manager.finalize()

        # Verify we can recover all states
        recovered_states = manager.get_all_states()
        assert len(recovered_states) == 100

        # Check memory savings
        stats = manager.get_memory_stats()
        assert stats["compression_ratio"] < 1.0  # Should be compressed
        assert stats["memory_savings_percent"] > 0

    def test_pool_vs_no_pool_comparison(self):
        """Compare pooled vs non-pooled collections."""
        states = [State.empty() for _ in range(50)]

        # Non-pooled collection
        collection_no_pool = CompactStateCollection(use_pool=False)
        for state in states:
            collection_no_pool.add_state(state)

        # Pooled collection
        collection_with_pool = CompactStateCollection(use_pool=True, pool_size=100)
        for state in states:
            collection_with_pool.add_state(state)

        # Both should store same number of states
        assert len(collection_no_pool) == len(collection_with_pool) == 50

        # Memory usage should be comparable
        stats_no_pool = collection_no_pool.get_memory_stats()
        stats_with_pool = collection_with_pool.get_memory_stats()

        # Both approaches should work for storing states
        assert stats_no_pool["total_memory"] > 0
        assert stats_with_pool["total_memory"] > 0
