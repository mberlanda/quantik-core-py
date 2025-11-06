"""
Tests for State class integration with CompactBitboard as internal storage.

This test module verifies that the State class correctly uses CompactBitboard
internally while maintaining full backward compatibility with the existing API.
"""

import pytest
from quantik_core import State
from quantik_core.memory.bitboard_compact import CompactBitboard
from quantik_core.commons import Bitboard


class TestStateCompactBitboardIntegration:
    """Test State class integration with CompactBitboard backend."""

    def test_state_creation_from_tuple(self):
        """Test State creation from traditional Bitboard tuple."""
        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        state = State(bb)

        # Should return the same tuple via bb property
        assert state.bb == bb

        # Internal storage should be CompactBitboard
        assert isinstance(state._compact_bb, CompactBitboard)

    def test_state_creation_from_compact_bitboard(self):
        """Test State creation from CompactBitboard."""
        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        compact_bb = CompactBitboard.from_tuple(bb)
        state = State(compact_bb)

        # Should return the same tuple via bb property
        assert state.bb == bb

        # Internal storage should be the same CompactBitboard instance
        assert state._compact_bb is compact_bb

    def test_state_empty_uses_compact_bitboard(self):
        """Test that State.empty() uses CompactBitboard internally."""
        state = State.empty()

        assert state.bb == (0, 0, 0, 0, 0, 0, 0, 0)
        assert isinstance(state._compact_bb, CompactBitboard)

    def test_qfen_roundtrip_compatibility(self):
        """Test QFEN serialization/deserialization compatibility."""
        original_qfen = "A.../..../..../B..."
        state = State.from_qfen(original_qfen)

        # Should use CompactBitboard internally
        assert isinstance(state._compact_bb, CompactBitboard)

        # Should produce same QFEN output
        assert state.to_qfen() == original_qfen

    def test_pack_unpack_roundtrip(self):
        """Test pack/unpack maintains data integrity."""
        bb: Bitboard = (1, 256, 4096, 8, 16, 32, 64, 128)
        state = State(bb)

        # Pack and unpack
        packed = state.pack()
        unpacked_state = State.unpack(packed)

        # Should maintain data integrity
        assert unpacked_state.bb == state.bb
        assert isinstance(unpacked_state._compact_bb, CompactBitboard)

    def test_canonical_operations_compatibility(self):
        """Test canonical operations work with CompactBitboard backend."""
        bb: Bitboard = (1, 0, 0, 0, 0, 0, 0, 0)
        state = State(bb)

        # Should produce canonical payload and key
        payload = state.canonical_payload()
        key = state.canonical_key()

        assert isinstance(payload, bytes)
        assert len(payload) == 16
        assert isinstance(key, bytes)
        assert len(key) == 18

    def test_get_occupied_bb_optimization(self):
        """Test get_occupied_bb uses CompactBitboard optimization."""
        bb: Bitboard = (1, 2, 0, 4, 0, 0, 8, 0)  # Bits set in positions 0, 1, 2, 3
        state = State(bb)

        # Should return OR of all bitboards
        expected = 1 | 2 | 4 | 8  # = 15
        assert state.get_occupied_bb() == expected

    def test_memory_efficiency_comparison(self):
        """Test that State with CompactBitboard uses less memory than tuple."""
        import sys

        # Create states with same data
        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        state = State(bb)

        # CompactBitboard should be more memory efficient than storing tuple
        # The _data attribute should be exactly 16 bytes
        assert len(state._compact_bb._data) == 16

        # The tuple takes more memory due to Python object overhead
        tuple_size = sys.getsizeof(bb)
        compact_data_size = len(state._compact_bb._data)

        # Tuple should be larger than the raw 16-byte compact data
        assert tuple_size > compact_data_size

    def test_state_equality_with_different_creation_methods(self):
        """Test that States created from tuple and CompactBitboard are equivalent."""
        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)

        # Create from tuple
        state1 = State(bb)

        # Create from CompactBitboard
        compact_bb = CompactBitboard.from_tuple(bb)
        state2 = State(compact_bb)

        # Should be equivalent
        assert state1.bb == state2.bb
        assert state1.to_qfen() == state2.to_qfen()
        assert state1.pack() == state2.pack()

    def test_backward_compatibility_with_board(self):
        """Test that Board class still works with new State implementation."""
        from quantik_core.board import QuantikBoard

        # Create board and verify state usage
        board = QuantikBoard()
        state = board.state

        # Should use CompactBitboard internally but provide tuple interface
        assert isinstance(state._compact_bb, CompactBitboard)
        assert isinstance(state.bb, tuple)
        assert len(state.bb) == 8

    def test_state_validation_error_handling(self):
        """Test that State validation works correctly."""
        # Should raise error for invalid bitboard length
        with pytest.raises(ValueError, match="Invalid bitboard data"):
            State((1, 2, 3))  # Wrong length

        # Should work with valid length
        state = State((0, 0, 0, 0, 0, 0, 0, 0))
        assert state.bb == (0, 0, 0, 0, 0, 0, 0, 0)


class TestStateCompactBitboardPerformance:
    """Performance-related tests for State CompactBitboard integration."""

    def test_creation_performance_comparison(self):
        """Compare creation performance between tuple and CompactBitboard."""
        import time

        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        compact_bb = CompactBitboard.from_tuple(bb)

        # Time tuple creation
        start = time.perf_counter()
        for _ in range(1000):
            State(bb)
        tuple_time = time.perf_counter() - start

        # Time CompactBitboard creation
        start = time.perf_counter()
        for _ in range(1000):
            State(compact_bb)
        compact_time = time.perf_counter() - start

        # CompactBitboard creation should be comparable or faster
        # (mainly testing that it's not dramatically slower)
        assert compact_time < tuple_time * 2  # Allow 2x slower at most

    def test_bb_property_access_performance(self):
        """Test that bb property access is reasonably fast."""
        import time

        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        state = State(bb)

        # Time property access
        start = time.perf_counter()
        for _ in range(1000):
            _ = state.bb
        access_time = time.perf_counter() - start

        # Should be reasonably fast (< 10ms for 1000 accesses)
        assert access_time < 0.010
