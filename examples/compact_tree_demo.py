#!/usr/bin/env python
"""Demonstration of compact game tree memory optimization.

This script showcases the memory efficiency improvements achieved with
the compact game tree implementation compared to traditional object-based
approaches.
"""

import time

from quantik_core import State
from quantik_core.memory import (
    CompactGameTree,
    NODE_FLAG_TERMINAL,
    NODE_FLAG_EXPANDED,
)


def demonstrate_compact_tree_basics():
    """Demonstrate basic compact tree operations with transposition table."""
    print("COMPACT GAME TREE BASICS")
    print("=" * 50)

    # Initialize compact tree
    tree = CompactGameTree(initial_capacity=10000)

    # Create root from empty state
    initial_state = State.empty()
    root_id = tree.create_root_node(initial_state)

    print(f"Created root node with ID: {root_id}")

    # Get root node details
    root_node = tree.get_node(root_id)
    print(f"Root depth: {root_node.depth}")
    print(f"Root player: {root_node.player_turn}")
    print(f"Root multiplicity: {root_node.multiplicity}")
    print(f"Canonical state size: {len(root_node.canonical_state_data)} bytes")

    # Add some child nodes - demonstrate transposition table behavior
    print("\nDemonstrating transposition table behavior:")
    for i in range(5):
        child_state = State.empty()  # Same canonical state
        child_id = tree.add_child_node(root_id, child_state, multiplicity=i + 1)
        child_node = tree.get_node(child_id)
        print(
            f"Added child {i}: node_id={child_id}, total_multiplicity={child_node.multiplicity}"
        )

    # Show updated root
    updated_root = tree.get_node(root_id)
    print(
        f"\nRoot now has {updated_root.num_children} children (unique canonical states)"
    )

    # Show children
    children = tree.get_children(root_id)
    print(f"Child IDs: {children}")

    # Show the transposition effect
    if children:
        first_child = tree.get_node(children[0])
        print(f"Single child has combined multiplicity: {first_child.multiplicity}")
        print("(This demonstrates transposition table: 1+2+3+4+5 = 15)")

    print()


def demonstrate_memory_efficiency():
    """Demonstrate memory efficiency with realistic tree structure."""
    print("MEMORY EFFICIENCY DEMONSTRATION")
    print("=" * 50)

    tree = CompactGameTree(initial_capacity=50000)
    initial_state = State.empty()

    # Create a more realistic tree structure
    num_levels = 3
    nodes_per_level = 100
    print(
        f"Creating tree with {num_levels} levels, {nodes_per_level} attempts per level..."
    )

    start_time = time.time()

    # Create root
    root_id = tree.create_root_node(initial_state)

    # Track actual nodes created vs attempts
    total_attempts = 0
    current_parents = [root_id]

    for level in range(1, num_levels + 1):
        new_parents = []
        level_attempts = 0

        for parent_id in current_parents:
            for i in range(min(nodes_per_level, 50)):  # Limit per parent
                child_state = State.empty()  # Would be different states in real game
                child_id = tree.add_child_node(parent_id, child_state, multiplicity=1)
                if child_id not in new_parents:
                    new_parents.append(child_id)
                level_attempts += 1
                total_attempts += 1

        current_parents = new_parents[:20]  # Limit next level parents
        print(
            f"Level {level}: {level_attempts} attempts, {len(new_parents)} unique nodes"
        )

    creation_time = time.time() - start_time

    # Get statistics
    stats = tree.get_stats()
    memory_usage = tree.memory_usage()

    print(f"\nTree creation time: {creation_time:.4f} seconds")
    print(f"Total attempts: {total_attempts:,}")
    print(f"Unique nodes created: {stats['node_count']:,}")
    print(f"Transposition ratio: {total_attempts / stats['node_count']:.1f}:1")
    print(f"Memory usage: {memory_usage:,} bytes ({memory_usage / 1024 / 1024:.2f} MB)")
    print(f"Storage utilization: {stats['utilization_percent']}%")
    print(f"Memory per unique node: {memory_usage / stats['node_count']:.1f} bytes")

    # Compare with theoretical object overhead
    theoretical_object_size = 148  # Estimated size of CanonicalState + Python overhead
    theoretical_memory = stats["node_count"] * theoretical_object_size

    print("\nComparison with object-based approach:")
    print(
        f"Theoretical object memory: {theoretical_memory:,} bytes ({theoretical_memory / 1024 / 1024:.2f} MB)"
    )
    print(f"Memory savings: {theoretical_memory - memory_usage:,} bytes")
    print(f"Compression ratio: {memory_usage / theoretical_memory:.3f}x")
    print(f"Memory reduction: {(1 - memory_usage / theoretical_memory) * 100:.1f}%")

    print()


def demonstrate_tree_navigation():
    """Demonstrate tree navigation capabilities."""
    print("TREE NAVIGATION DEMONSTRATION")
    print("=" * 50)

    tree = CompactGameTree()
    initial_state = State.empty()

    # Create a small tree structure
    root_id = tree.create_root_node(initial_state)

    # Level 1 children
    child_ids = []
    for i in range(3):
        child_state = State.empty()
        child_id = tree.add_child_node(root_id, child_state, multiplicity=i + 1)
        child_ids.append(child_id)

    # Level 2 children (grandchildren)
    grandchild_ids = []
    for child_id in child_ids:
        for j in range(2):
            grandchild_state = State.empty()
            grandchild_id = tree.add_child_node(
                child_id, grandchild_state, multiplicity=1
            )
            grandchild_ids.append(grandchild_id)

    # Navigate and display tree structure
    def print_node_info(node_id: int, indent: int = 0):
        node = tree.get_node(node_id)
        prefix = "  " * indent
        print(
            f"{prefix}Node {node_id}: depth={node.depth}, player={node.player_turn}, "
            f"multiplicity={node.multiplicity}, children={node.num_children}"
        )

        for child_id in tree.get_children(node_id):
            print_node_info(child_id, indent + 1)

    print("Tree structure:")
    print_node_info(root_id)

    print()


def demonstrate_performance_benchmarks():
    """Demonstrate performance characteristics."""
    print("PERFORMANCE BENCHMARKS")
    print("=" * 50)

    # Test node creation performance
    tree = CompactGameTree(initial_capacity=100000)
    initial_state = State.empty()

    num_tests = 1000  # Reduced for realistic demo

    # Benchmark node creation
    start_time = time.time()
    root_id = tree.create_root_node(initial_state)

    created_nodes = []
    for i in range(num_tests):
        child_state = State.empty()
        child_id = tree.add_child_node(root_id, child_state, multiplicity=1)
        if child_id not in created_nodes:
            created_nodes.append(child_id)

    _creation_time = time.time() - start_time

    print("Node creation benchmark:")
    print(f"Attempted to create {num_tests:,} nodes in {_creation_time:.4f} seconds")
    print(f"Actual unique nodes created: {len(created_nodes):,}")
    print(f"Rate: {num_tests / _creation_time:,.0f} attempts/second")
    print(f"Transposition efficiency: {num_tests / len(created_nodes):.1f}:1")

    # Benchmark node retrieval
    start_time = time.time()

    for _ in range(num_tests):
        for node_id in created_nodes:
            node = tree.get_node(node_id)
            _ = node.depth  # Access node data

    retrieval_time = time.time() - start_time
    total_retrievals = num_tests * len(created_nodes)

    print("\nNode retrieval benchmark:")
    print(
        f"Retrieved {total_retrievals:,} node accesses in {retrieval_time:.4f} seconds"
    )
    print(f"Rate: {total_retrievals / retrieval_time:,.0f} retrievals/second")

    # Memory efficiency
    _stats = tree.get_stats()
    _memory_usage = tree.memory_usage()

    print("\nMemory efficiency:")
    print(f"Total unique nodes: {_stats['node_count']:,}")
    print(f"Memory usage: {_memory_usage / 1024 / 1024:.2f} MB")
    print(f"Bytes per node: {_memory_usage / _stats['node_count']:.1f}")

    print()


def demonstrate_flag_system():
    """Demonstrate the node flag system."""
    print("NODE FLAG SYSTEM DEMONSTRATION")
    print("=" * 50)

    tree = CompactGameTree()
    initial_state = State.empty()

    # Create nodes with different flags
    root_id = tree.create_root_node(initial_state)

    # Manually update root to demonstrate flags
    _root_node = tree.get_node(root_id)
    print(f"Root flags: {_root_node.flags:08b} ({_root_node.flags})")
    print(f"Is expanded: {bool(_root_node.flags & NODE_FLAG_EXPANDED)}")
    print(f"Is terminal: {bool(_root_node.flags & NODE_FLAG_TERMINAL)}")

    # Create a terminal child node
    child_state = State.empty()
    child_id = tree.add_child_node(root_id, child_state)

    # Simulate setting terminal flag (would be done by game logic)
    _child_node = tree.get_node(child_id)
    # Note: In real implementation, we'd need a method to update flags
    print(f"\nChild flags: {_child_node.flags:08b} ({_child_node.flags})")

    print("\nFlag meanings:")
    print(f"TERMINAL: {NODE_FLAG_TERMINAL:08b} ({NODE_FLAG_TERMINAL})")
    print(f"EXPANDED: {NODE_FLAG_EXPANDED:08b} ({NODE_FLAG_EXPANDED})")

    print()


def main():
    """Run all demonstrations."""
    print("COMPACT GAME TREE MEMORY OPTIMIZATION DEMO")
    print("=" * 60)
    print("Demonstrating ultra-efficient memory usage for game tree analysis")
    print()

    demonstrate_compact_tree_basics()
    demonstrate_memory_efficiency()
    demonstrate_tree_navigation()
    demonstrate_performance_benchmarks()
    demonstrate_flag_system()

    print("=" * 60)
    print("DEMONSTRATION COMPLETE!")
    print("\nKey benefits of compact game tree:")
    print("- 64-byte nodes (vs ~148+ bytes for object-based)")
    print("- Cache-friendly contiguous memory layout")
    print("- ID-based references eliminate pointer overhead")
    print("- Integrated statistics and analysis metadata")
    print("- Designed for future bitboard optimization")
    print("\nReady for memory-efficient deep game tree analysis!")


if __name__ == "__main__":
    main()
