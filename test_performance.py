#!/usr/bin/env python3
"""
Performance test to compare CompactBitboard vs tuple performance.
"""

import time
import sys
from src.quantik_core.memory.bitboard_compact import CompactBitboard

def test_performance():
    # Test data
    test_data = (1, 2, 4, 8, 16, 32, 64, 128)
    
    # Create instances
    compact_bb = CompactBitboard(test_data)
    tuple_bb = test_data
    
    # Performance test parameters
    iterations = 100_000
    
    print("=== Performance Comparison ===")
    
    # Test 1: Direct indexing CompactBitboard
    start = time.time()
    for _ in range(iterations):
        for i in range(8):
            _ = compact_bb[i]
    compact_time = time.time() - start
    print(f"CompactBitboard indexing: {compact_time:.4f}s")
    
    # Test 2: Direct indexing tuple
    start = time.time()
    for _ in range(iterations):
        for i in range(8):
            _ = tuple_bb[i]
    tuple_time = time.time() - start
    print(f"Tuple indexing: {tuple_time:.4f}s")
    
    # Test 3: Conversion overhead
    start = time.time()
    for _ in range(iterations):
        _ = compact_bb.to_tuple()
    conversion_time = time.time() - start
    print(f"Conversion overhead: {conversion_time:.4f}s")
    
    # Calculate speedup
    speedup = tuple_time / compact_time
    print(f"Speedup: {speedup:.2f}x ({'faster' if speedup > 1 else 'slower'})")
    
    print("\n=== Memory Usage ===")
    print(f"CompactBitboard memory: {sys.getsizeof(compact_bb)} bytes")
    print(f"Tuple memory: {sys.getsizeof(tuple_bb)} bytes")
    
    # Memory efficiency
    memory_ratio = sys.getsizeof(tuple_bb) / sys.getsizeof(compact_bb)
    print(f"Memory efficiency: {memory_ratio:.2f}x ({'better' if memory_ratio > 1 else 'worse'})")
    
    return speedup, memory_ratio

if __name__ == "__main__":
    test_performance()