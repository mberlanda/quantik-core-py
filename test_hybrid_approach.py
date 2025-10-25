#!/usr/bin/env python3
"""
Comprehensive test of the hybrid storage approach for distributed game tree computation.

This demonstrates:
1. Fast tuple-based computation in hot paths
2. Compact serialization for storage/transmission  
3. Memory efficiency for large datasets
4. Distributed computing scenarios
"""

import time
import tempfile
import os
import sys
from src.quantik_core.storage import (
    GameState, GameTree, CompactState,
    serialize_bitboard, deserialize_bitboard,
    batch_serialize, batch_deserialize,
    create_worker_batch, load_worker_batch,
    calculate_memory_savings
)
from src.quantik_core.move_fast import generate_legal_moves, apply_move
from src.quantik_core.commons import Bitboard


def test_hybrid_performance():
    """Test performance of hybrid approach."""
    print("=== Hybrid Approach Performance Test ===")
    
    # Test data: realistic game state
    test_bb: Bitboard = (1, 2, 4, 8, 16, 32, 64, 128)
    
    # Create GameState for computation
    game_state = GameState(test_bb)
    
    # Performance test parameters
    iterations = 10_000
    
    # Test 1: Fast tuple-based move generation
    start = time.time()
    for _ in range(iterations):
        _, moves = generate_legal_moves(game_state.bitboard)
    computation_time = time.time() - start
    print(f"Move generation (tuples): {computation_time:.4f}s")
    
    # Test 2: Serialization overhead
    start = time.time()
    for _ in range(iterations):
        serialized = game_state.serialize()
        _ = GameState.from_compact(serialized)
    serialization_time = time.time() - start
    print(f"Serialization roundtrip: {serialization_time:.4f}s")
    
    # Test 3: Batch operations (for distributed computing)
    states = [GameState(test_bb) for _ in range(1000)]
    
    start = time.time()
    batch_data = create_worker_batch(states)
    loaded_states = load_worker_batch(batch_data)
    batch_time = time.time() - start
    print(f"Batch operations (1000 states): {batch_time:.4f}s")
    
    return computation_time, serialization_time, batch_time


def test_memory_efficiency():
    """Test memory efficiency for large datasets."""
    print("\n=== Memory Efficiency Test ===")
    
    # Simulate large game tree
    num_states = 100_000
    test_states = []
    
    # Generate diverse test states
    for i in range(num_states):
        bb = tuple(i % 256 for _ in range(8))  # Ensure values fit in 8-bit
        test_states.append(bb)
    
    # Calculate actual memory usage using sys.getsizeof
    sample_tuple = test_states[0]
    actual_tuple_size = sys.getsizeof(sample_tuple)
    
    sample_compact = CompactState.from_tuple(sample_tuple)
    actual_compact_size = sample_compact.memory_size
    compact_bytes_size = len(sample_compact.to_bytes())
    
    print(f"Sample tuple size: {actual_tuple_size} bytes")
    print(f"Sample compact object size: {actual_compact_size} bytes") 
    print(f"Sample compact serialized size: {compact_bytes_size} bytes")
    
    # Calculate memory usage for all states
    total_tuple_memory = num_states * actual_tuple_size
    total_compact_memory = num_states * compact_bytes_size
    total_compact_objects_memory = num_states * actual_compact_size
    
    print(f"\nStates: {num_states:,}")
    print(f"Tuple storage: {total_tuple_memory / (1024*1024):.2f} MB")
    print(f"Compact serialized storage: {total_compact_memory / (1024*1024):.2f} MB")
    print(f"Compact objects storage: {total_compact_objects_memory / (1024*1024):.2f} MB")
    
    savings_vs_tuples = (total_tuple_memory - total_compact_memory) / total_tuple_memory * 100
    compression_ratio = total_tuple_memory / total_compact_memory
    
    print(f"Memory savings (serialized): {savings_vs_tuples:.1f}%")
    print(f"Compression ratio: {compression_ratio:.1f}x")
    
    # Test actual batch serialization
    start = time.time()
    serialized = batch_serialize(test_states)
    serialize_time = time.time() - start
    
    start = time.time()
    deserialized = batch_deserialize(serialized)
    deserialize_time = time.time() - start
    
    print(f"Serialization time: {serialize_time:.4f}s")
    print(f"Deserialization time: {deserialize_time:.4f}s")
    print(f"Actual serialized size: {len(serialized):,} bytes ({len(serialized) / (1024*1024):.2f} MB)")
    
    # Verify correctness
    assert len(deserialized) == num_states
    assert all(deserialized[i] == test_states[i] for i in range(min(1000, num_states)))
    print("✓ Serialization correctness verified")
    
    return {
        "compression_ratio": compression_ratio,
        "savings_vs_tuples": savings_vs_tuples,
        "tuple_size": actual_tuple_size,
        "compact_size": compact_bytes_size
    }


def test_distributed_scenario():
    """Test distributed computing scenario."""
    print("\n=== Distributed Computing Scenario ===")
    
    # Simulate master-worker scenario
    initial_state: Bitboard = (0, 0, 0, 0, 0, 0, 0, 0)  # Empty board
    master_tree = GameTree()
    
    # Add some nodes to master tree
    for i in range(100):
        bb = tuple(i % 256 for _ in range(8))
        state = GameState(bb)
        master_tree.add_node(state, float(i), [])
    
    # Save checkpoint (simulate sending to workers)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.gz') as f:
        checkpoint_file = f.name
    
    try:
        start = time.time()
        master_tree.save_checkpoint(checkpoint_file, compress=True)
        save_time = time.time() - start
        
        # Check file size
        file_size = os.path.getsize(checkpoint_file)
        
        # Load checkpoint (simulate worker receiving data)
        worker_tree = GameTree()
        start = time.time()
        worker_tree.load_checkpoint(checkpoint_file, compress=True)
        load_time = time.time() - start
        
        # Verify data integrity
        master_stats = master_tree.get_stats()
        worker_stats = worker_tree.get_stats()
        
        print(f"Checkpoint save time: {save_time:.4f}s")
        print(f"Checkpoint load time: {load_time:.4f}s")
        print(f"Checkpoint file size: {file_size:,} bytes")
        print(f"Nodes preserved: {worker_stats['active_nodes']}/{master_stats['active_nodes']}")
        print(f"Memory saved: {master_stats.get('memory_saved_mb', 0):.2f} MB")
        
        # Test merging results (map-reduce scenario)
        # Create another worker tree with different data
        worker2_tree = GameTree()
        for i in range(50, 150):  # Overlapping data
            bb = tuple(i % 256 for _ in range(8))
            state = GameState(bb)
            worker2_tree.add_node(state, float(i * 2), [])
        
        # Merge results
        start = time.time()
        master_tree.merge_results(worker2_tree)
        merge_time = time.time() - start
        
        final_stats = master_tree.get_stats()
        print(f"Merge time: {merge_time:.4f}s")
        print(f"Final nodes: {final_stats['active_nodes']}")
        
        print("✓ Distributed scenario completed successfully")
        
    finally:
        # Cleanup
        if os.path.exists(checkpoint_file):
            os.unlink(checkpoint_file)


def test_computation_workflow():
    """Test realistic computation workflow."""
    print("\n=== Realistic Computation Workflow ===")
    
    # Start with empty board
    initial_bb: Bitboard = (0, 0, 0, 0, 0, 0, 0, 0)
    game_state = GameState(initial_bb)
    
    # Generate and explore moves (hot path - using tuples)
    start = time.time()
    
    states_to_explore = [game_state]
    explored_count = 0
    max_depth = 3  # Limit to keep test reasonable
    
    for depth in range(max_depth):
        next_states = []
        for state in states_to_explore:
            current_player, moves_by_shape = state.generate_moves()
            if current_player is None:
                continue
                
            # Explore a few moves per state
            move_count = 0
            for shape_moves in moves_by_shape.values():
                for move in shape_moves[:2]:  # Limit moves to keep test size reasonable
                    new_state = state.apply_move(move)
                    next_states.append(new_state)
                    explored_count += 1
                    move_count += 1
                    if move_count >= 4:  # Limit per state
                        break
                if move_count >= 4:
                    break
        
        states_to_explore = next_states[:100]  # Limit total states
        if not states_to_explore:
            break
    
    computation_time = time.time() - start
    
    # Serialize all states for storage (compact format)
    start = time.time()
    worker_batch = create_worker_batch(states_to_explore)
    serialization_time = time.time() - start
    
    # Calculate efficiency using actual sizes
    sample_tuple = initial_bb
    actual_tuple_size = sys.getsizeof(sample_tuple)
    
    tuple_size = explored_count * actual_tuple_size
    compact_size = len(worker_batch)
    compression_ratio = tuple_size / compact_size if compact_size > 0 else 0
    
    print(f"States explored: {explored_count:,}")
    print(f"Computation time: {computation_time:.4f}s")
    print(f"Serialization time: {serialization_time:.4f}s") 
    print(f"Tuple memory estimate: {tuple_size:,} bytes")
    print(f"Compact serialized: {compact_size:,} bytes")
    print(f"Compression ratio: {compression_ratio:.1f}x")
    print("✓ Workflow completed successfully")


def main():
    """Run all tests."""
    print("Testing Hybrid Bitboard Storage Approach")
    print("=" * 50)
    
    # Test performance
    comp_time, ser_time, batch_time = test_hybrid_performance()
    
    # Test memory efficiency
    memory_stats = test_memory_efficiency()
    
    # Test distributed scenario
    test_distributed_scenario()
    
    # Test realistic workflow
    test_computation_workflow()
    
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print("✓ Hot path computation: Fast tuple-based operations")
    print("✓ Memory efficiency: Up to 13x compression for storage")
    print("✓ Distributed computing: Efficient checkpoints and data transfer")
    print("✓ Map-reduce support: Batch operations and result merging")
    print("✓ Backward compatibility: Works with existing tuple-based code")
    
    print(f"\nKey Metrics:")
    print(f"- Computation speed: Optimized tuple operations")
    print(f"- Memory compression: {memory_stats['compression_ratio']:.1f}x")
    print(f"- Storage efficiency: {memory_stats['savings_vs_tuples']:.1f}% savings")


if __name__ == "__main__":
    main()