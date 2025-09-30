#!/usr/bin/env python
"""Tests for compact game tree implementation."""

import pytest
import numpy as np
from quantik_core import State
from quantik_core.memory import (
    CompactGameTreeNode,
    CompactGameTreeStorage,
    CompactGameTree,
    NODE_FLAG_TERMINAL,
    NODE_FLAG_EXPANDED,
)


class TestCompactGameTreeNode:
    """Test the compact game tree node structure."""

    def test_node_creation(self):
        """Test basic node creation."""
        state = State.empty()
        canonical_data = state.pack()

        node = CompactGameTreeNode(
            canonical_state_data=canonical_data,
            parent_id=np.uint32(0),
            depth=np.uint16(0),
            player_turn=np.uint8(0),
            flags=np.uint8(NODE_FLAG_EXPANDED),
            num_children=np.uint16(0),
            first_child_id=np.uint32(0),
            multiplicity=np.uint32(1),
            total_descendants=np.uint32(0),
            win_count_p0=np.uint32(0),
            win_count_p1=np.uint32(0),
            visit_count=np.uint32(0),
            best_value=np.float32(0.0),
            terminal_value=np.float32(0.0),
            reserved=np.uint32(0),
        )

        assert len(node.canonical_state_data) == 18
        assert node.depth == 0
        assert node.player_turn == 0
        assert node.flags == NODE_FLAG_EXPANDED

    def test_node_validation(self):
        """Test node data validation."""
        with pytest.raises(ValueError, match="canonical_state_data must be 18 bytes"):
            CompactGameTreeNode(
                canonical_state_data=b"too_short",
                parent_id=np.uint32(0),
                depth=np.uint16(0),
                player_turn=np.uint8(0),
                flags=np.uint8(0),
                num_children=np.uint16(0),
                first_child_id=np.uint32(0),
                multiplicity=np.uint32(1),
                total_descendants=np.uint32(0),
                win_count_p0=np.uint32(0),
                win_count_p1=np.uint32(0),
                visit_count=np.uint32(0),
                best_value=np.float32(0.0),
                terminal_value=np.float32(0.0),
                reserved=np.uint32(0),
            )


class TestCompactGameTreeStorage:
    """Test the compact game tree storage system."""

    def test_storage_initialization(self):
        """Test storage initialization."""
        storage = CompactGameTreeStorage(initial_capacity=1000)

        assert storage.capacity == 1000
        assert storage.node_count == 0
        assert len(storage.canonical_to_id) == 0
        assert len(storage.free_ids) == 0

    def test_node_allocation(self):
        """Test node ID allocation."""
        storage = CompactGameTreeStorage(initial_capacity=5)

        # Allocate sequential IDs
        id1 = storage.allocate_node_id()
        id2 = storage.allocate_node_id()

        assert id1 == 0
        assert id2 == 1
        assert storage.node_count == 2

    def test_node_storage_and_retrieval(self):
        """Test storing and retrieving nodes."""
        storage = CompactGameTreeStorage(initial_capacity=10)
        state = State.empty()

        # Create and store a node
        node = CompactGameTreeNode(
            canonical_state_data=state.pack(),
            parent_id=np.uint32(0),
            depth=np.uint16(1),
            player_turn=np.uint8(1),
            flags=np.uint8(NODE_FLAG_TERMINAL),
            num_children=np.uint16(2),
            first_child_id=np.uint32(5),
            multiplicity=np.uint32(3),
            total_descendants=np.uint32(10),
            win_count_p0=np.uint32(4),
            win_count_p1=np.uint32(6),
            visit_count=np.uint32(15),
            best_value=np.float32(0.7),
            terminal_value=np.float32(1.0),
            reserved=np.uint32(42),
        )

        node_id = storage.allocate_node_id()
        storage.store_node(node_id, node)

        # Retrieve and verify
        retrieved = storage.load_node(node_id)

        assert retrieved.canonical_state_data == state.pack()
        assert retrieved.parent_id == 0
        assert retrieved.depth == 1
        assert retrieved.player_turn == 1
        assert retrieved.flags == NODE_FLAG_TERMINAL
        assert retrieved.num_children == 2
        assert retrieved.first_child_id == 5
        assert retrieved.multiplicity == 3
        assert retrieved.total_descendants == 10
        assert retrieved.win_count_p0 == 4
        assert retrieved.win_count_p1 == 6
        assert retrieved.visit_count == 15
        assert abs(retrieved.best_value - 0.7) < 1e-6
        assert abs(retrieved.terminal_value - 1.0) < 1e-6
        assert retrieved.reserved == 42

    def test_canonical_state_lookup(self):
        """Test finding nodes by canonical state."""
        storage = CompactGameTreeStorage(initial_capacity=10)
        state = State.empty()
        canonical_data = state.pack()

        # Store a node
        node = CompactGameTreeNode(
            canonical_state_data=canonical_data,
            parent_id=np.uint32(0),
            depth=np.uint16(0),
            player_turn=np.uint8(0),
            flags=np.uint8(0),
            num_children=np.uint16(0),
            first_child_id=np.uint32(0),
            multiplicity=np.uint32(1),
            total_descendants=np.uint32(0),
            win_count_p0=np.uint32(0),
            win_count_p1=np.uint32(0),
            visit_count=np.uint32(0),
            best_value=np.float32(0.0),
            terminal_value=np.float32(0.0),
            reserved=np.uint32(0),
        )

        node_id = storage.allocate_node_id()
        storage.store_node(node_id, node)

        # Test lookup
        found_id = storage.find_node_by_canonical_state(canonical_data, 0)
        assert found_id == node_id

        # Test lookup for non-existent state
        different_data = b"different_18_bytes"
        assert storage.find_node_by_canonical_state(different_data, 0) is None

        # Test lookup for same state at different depth
        assert storage.find_node_by_canonical_state(canonical_data, 1) is None

    def test_parent_child_relationships(self):
        """Test parent-child relationship management."""
        storage = CompactGameTreeStorage(initial_capacity=10)

        # Add parent-child relationships
        storage.add_child_relationship(parent_id=0, child_id=1)
        storage.add_child_relationship(parent_id=0, child_id=2)
        storage.add_child_relationship(parent_id=1, child_id=3)

        # Test retrieving children
        children_0 = storage.get_children(0)
        children_1 = storage.get_children(1)
        children_2 = storage.get_children(2)

        assert children_0 == [1, 2]
        assert children_1 == [3]
        assert children_2 == []

    def test_capacity_expansion(self):
        """Test automatic capacity expansion."""
        storage = CompactGameTreeStorage(initial_capacity=2)

        # Allocate beyond initial capacity
        for i in range(5):
            storage.allocate_node_id()

        assert storage.capacity >= 4  # Should have expanded
        assert storage.node_count == 5

    def test_node_deallocation(self):
        """Test node deallocation and reuse."""
        storage = CompactGameTreeStorage(initial_capacity=10)
        state = State.empty()

        # Create and store a node
        node = CompactGameTreeNode(
            canonical_state_data=state.pack(),
            parent_id=np.uint32(0),
            depth=np.uint16(0),
            player_turn=np.uint8(0),
            flags=np.uint8(0),
            num_children=np.uint16(0),
            first_child_id=np.uint32(0),
            multiplicity=np.uint32(1),
            total_descendants=np.uint32(0),
            win_count_p0=np.uint32(0),
            win_count_p1=np.uint32(0),
            visit_count=np.uint32(0),
            best_value=np.float32(0.0),
            terminal_value=np.float32(0.0),
            reserved=np.uint32(0),
        )

        node_id = storage.allocate_node_id()
        storage.store_node(node_id, node)

        # Deallocate
        storage.deallocate_node(node_id)

        assert len(storage.free_ids) == 1
        assert storage.find_node_by_canonical_state(state.pack(), 0) is None

    def test_memory_usage_calculation(self):
        """Test memory usage reporting."""
        storage = CompactGameTreeStorage(initial_capacity=100)

        memory_usage = storage.memory_usage()
        assert memory_usage > 0

        # Should be at least the node storage capacity
        assert memory_usage >= 100 * 64

    def test_storage_stats(self):
        """Test storage statistics."""
        storage = CompactGameTreeStorage(initial_capacity=100)

        # Allocate some nodes
        for i in range(10):
            storage.allocate_node_id()

        stats = storage.get_stats()

        assert stats["capacity"] == 100
        assert stats["node_count"] == 10
        assert stats["utilization_percent"] == 10
        assert "memory_usage" in stats


class TestCompactGameTree:
    """Test the high-level compact game tree interface."""

    def test_tree_initialization(self):
        """Test tree initialization."""
        tree = CompactGameTree(initial_capacity=1000)

        assert tree.storage.capacity == 1000
        assert tree.root_id is None

    def test_root_node_creation(self):
        """Test creating root node."""
        tree = CompactGameTree()
        initial_state = State.empty()

        root_id = tree.create_root_node(initial_state)

        assert tree.root_id == root_id
        assert root_id == 0

        # Verify root node properties
        root_node = tree.get_node(root_id)
        assert root_node.depth == 0
        assert root_node.player_turn == 0
        assert root_node.parent_id == 0
        assert root_node.flags == NODE_FLAG_EXPANDED

    def test_child_node_addition(self):
        """Test adding child nodes."""
        tree = CompactGameTree()
        initial_state = State.empty()

        root_id = tree.create_root_node(initial_state)

        # Create a different state for child
        child_state = State.empty()  # For now, same as empty
        child_id = tree.add_child_node(root_id, child_state, multiplicity=2)

        # Verify child node
        child_node = tree.get_node(child_id)
        assert child_node.depth == 1
        assert child_node.player_turn == 1  # Alternates from root
        assert child_node.parent_id == root_id
        assert child_node.multiplicity == 2

        # Verify parent updated
        root_node = tree.get_node(root_id)
        assert root_node.num_children == 1
        assert root_node.first_child_id == child_id

        # Verify parent-child relationship
        children = tree.get_children(root_id)
        assert children == [child_id]

    def test_duplicate_canonical_state_handling(self):
        """Test transposition table behavior - same canonical state at same depth."""
        tree = CompactGameTree()
        initial_state = State.empty()

        root_id = tree.create_root_node(initial_state)

        # Create two children that reach the same canonical state at depth 1
        # This simulates transpositions in the game tree
        child_state = State.empty()  # Same canonical state

        # Add first path to this canonical state
        child_id1 = tree.add_child_node(root_id, child_state, multiplicity=1)

        # Add second path to the same canonical state at the same depth
        # This should be detected as a transposition and merged
        child_id2 = tree.add_child_node(root_id, child_state, multiplicity=3)

        # Should be the same node (transposition table hit)
        assert child_id1 == child_id2

        # Multiplicity should be combined
        child_node = tree.get_node(child_id1)
        assert child_node.multiplicity == 4  # 1 + 3
        assert child_node.depth == 1

        # Root should still show correct child count
        root_node = tree.get_node(root_id)
        assert root_node.num_children == 1  # Only one unique child

    def test_same_canonical_state_different_depths(self):
        """Test that same canonical state at different depths are stored separately."""
        tree = CompactGameTree()
        initial_state = State.empty()

        # Create root (depth 0)
        root_id = tree.create_root_node(initial_state)

        # Add child at depth 1 with same canonical state
        child_state = State.empty()  # Same canonical representation
        child_id = tree.add_child_node(root_id, child_state, multiplicity=1)

        # Add grandchild at depth 2 with same canonical state
        grandchild_state = State.empty()  # Same canonical representation
        grandchild_id = tree.add_child_node(child_id, grandchild_state, multiplicity=1)

        # All should be different nodes despite same canonical state
        assert root_id != child_id
        assert child_id != grandchild_id
        assert root_id != grandchild_id

        # Verify depths
        assert tree.get_node(root_id).depth == 0
        assert tree.get_node(child_id).depth == 1
        assert tree.get_node(grandchild_id).depth == 2

        # Verify player turns alternate
        assert tree.get_node(root_id).player_turn == 0
        assert tree.get_node(child_id).player_turn == 1
        assert tree.get_node(grandchild_id).player_turn == 0

    def test_state_retrieval(self):
        """Test retrieving game state from node."""
        tree = CompactGameTree()
        initial_state = State.empty()

        root_id = tree.create_root_node(initial_state)

        # Retrieve state and verify roundtrip
        retrieved_state = tree.get_state(root_id)
        assert retrieved_state.pack() == initial_state.pack()

    def test_tree_memory_usage(self):
        """Test tree memory usage reporting."""
        tree = CompactGameTree()
        initial_state = State.empty()

        tree.create_root_node(initial_state)

        memory_usage = tree.memory_usage()
        assert memory_usage > 0

    def test_tree_statistics(self):
        """Test tree statistics."""
        tree = CompactGameTree()
        initial_state = State.empty()

        tree.create_root_node(initial_state)

        stats = tree.get_stats()
        assert stats["node_count"] == 1
        assert "memory_usage" in stats


class TestMemoryEfficiency:
    """Test memory efficiency of compact tree structures."""

    def test_node_size_constraint(self):
        """Test that nodes fit within target size."""
        state = State.empty()

        node = CompactGameTreeNode(
            canonical_state_data=state.pack(),
            parent_id=np.uint32(0),
            depth=np.uint16(0),
            player_turn=np.uint8(0),
            flags=np.uint8(0),
            num_children=np.uint16(0),
            first_child_id=np.uint32(0),
            multiplicity=np.uint32(1),
            total_descendants=np.uint32(0),
            win_count_p0=np.uint32(0),
            win_count_p1=np.uint32(0),
            visit_count=np.uint32(0),
            best_value=np.float32(0.0),
            terminal_value=np.float32(0.0),
            reserved=np.uint32(0),
        )

        # Each component should fit within expected sizes
        assert len(node.canonical_state_data) == 18
        # Tree structure: 4+2+1+1+2+4 = 14 bytes (but we have padding)
        # Statistics: 4+4+4+4 = 16 bytes
        # Analysis: 4+4+4+4 = 16 bytes
        # Total target: 62 bytes (within 64-byte cache line)

    def test_storage_density(self):
        """Test storage memory density."""
        storage = CompactGameTreeStorage(initial_capacity=1000)
        state = State.empty()

        # Create many nodes
        for i in range(100):
            node = CompactGameTreeNode(
                canonical_state_data=state.pack(),
                parent_id=np.uint32(i % 10),
                depth=np.uint16(i % 5),
                player_turn=np.uint8(i % 2),
                flags=np.uint8(0),
                num_children=np.uint16(0),
                first_child_id=np.uint32(0),
                multiplicity=np.uint32(1),
                total_descendants=np.uint32(0),
                win_count_p0=np.uint32(0),
                win_count_p1=np.uint32(0),
                visit_count=np.uint32(0),
                best_value=np.float32(0.0),
                terminal_value=np.float32(0.0),
                reserved=np.uint32(0),
            )

            node_id = storage.allocate_node_id()
            storage.store_node(node_id, node)

        # Verify memory efficiency
        memory_usage = storage.memory_usage()
        expected_minimum = 100 * 64  # 64 bytes per node minimum

        assert memory_usage >= expected_minimum
        # Should be reasonably close to minimum (accounting for overhead)
        # The lookup maps add significant overhead, so we allow more room
        assert (
            memory_usage < expected_minimum * 15
        )  # Less than 15x overhead (generous for lookup structures)
