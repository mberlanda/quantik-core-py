"""
Test suite for compact bitboard optimization.
Tests memory efficiency, functionality, and performance characteristics.
"""

import pytest

from quantik_core.memory.bitboard_compact import CompactBitboard


class TestCompactBitboard:
    """Test compact bitboard functionality."""

    def test_creation_from_tuple(self):
        """Test creating CompactBitboard from tuple."""
        original = (1, 2, 3, 4, 5, 6, 7, 8)
        compact = CompactBitboard.from_tuple(original)

        assert compact.to_tuple() == original
        assert len(compact) == 8

    def test_creation_from_bytes(self):
        """Test creating CompactBitboard from bytes."""
        data = bytes(
            [10, 0, 20, 0, 30, 0, 40, 0, 50, 0, 60, 0, 70, 0, 80, 0]
        )  # 16 bytes: 8 shorts
        compact = CompactBitboard.from_bytes(data)

        assert compact.to_bytes() == data
        assert compact.to_tuple() == (
            10,
            20,
            30,
            40,
            50,
            60,
            70,
            80,
        )  # Little-endian unpacked

    def test_creation_validation(self):
        """Test validation during creation."""
        # Valid cases
        CompactBitboard((0, 1, 2, 3, 4, 5, 6, 65535))  # Max valid values
        CompactBitboard(bytes(16))  # Zero bytes

        # Invalid cases
        with pytest.raises(ValueError, match="exactly 8 elements"):
            CompactBitboard((1, 2, 3))  # Too few elements

    def test_bit_count(self):
        """Test bit counting functionality."""
        # Single bit set
        compact = CompactBitboard.from_tuple((1, 0, 0, 0, 0, 0, 0, 0))
        assert compact.bit_count(0) == 1
        assert compact.bit_count(1) == 0

        # Multiple bits set
        compact = CompactBitboard.from_tuple((7, 0, 0, 0, 0, 0, 0, 0))  # 7 = 0b111
        assert compact.bit_count(0) == 3

        # Test bounds
        with pytest.raises(IndexError):
            compact.bit_count(8)
        with pytest.raises(IndexError):
            compact.bit_count(-1)

    def test_occupied_mask(self):
        """Test occupied position mask calculation."""
        # Empty board
        empty = CompactBitboard.from_tuple((0, 0, 0, 0, 0, 0, 0, 0))
        assert empty.get_occupied_mask() == 0

        # Single piece
        single = CompactBitboard.from_tuple((1, 0, 0, 0, 0, 0, 0, 0))
        assert single.get_occupied_mask() == 1

        # Multiple pieces, different bitboards
        multiple = CompactBitboard.from_tuple((1, 2, 0, 0, 4, 0, 0, 0))
        assert multiple.get_occupied_mask() == (1 | 2 | 4)  # 7

    def test_position_occupied(self):
        """Test position occupation checking."""
        compact = CompactBitboard.from_tuple(
            (1, 2, 0, 0, 0, 0, 0, 0)
        )  # Pos 0 and 1 occupied

        assert compact.is_position_occupied(0) is True
        assert compact.is_position_occupied(1) is True
        assert compact.is_position_occupied(2) is False
        assert compact.is_position_occupied(15) is False

        # Test bounds
        with pytest.raises(ValueError):
            compact.is_position_occupied(16)
        with pytest.raises(ValueError):
            compact.is_position_occupied(-1)

    def test_apply_move_functional(self):
        """Test functional move application."""
        empty = CompactBitboard.from_tuple((0, 0, 0, 0, 0, 0, 0, 0))

        # Apply move: player 0, shape 0, position 0
        result = empty.apply_move_functional(0, 0, 0)
        assert result.to_tuple() == (1, 0, 0, 0, 0, 0, 0, 0)

        # Apply move: player 1, shape 2, position 5
        result = empty.apply_move_functional(1, 2, 5)
        assert result.to_tuple() == (0, 0, 0, 0, 0, 0, 32, 0)  # 32 = 1 << 5

        # Original should be unchanged
        assert empty.to_tuple() == (0, 0, 0, 0, 0, 0, 0, 0)

        # Test validation
        with pytest.raises(ValueError, match="Invalid player"):
            empty.apply_move_functional(2, 0, 0)
        with pytest.raises(ValueError, match="Invalid shape"):
            empty.apply_move_functional(0, 4, 0)
        with pytest.raises(ValueError, match="Invalid position"):
            empty.apply_move_functional(0, 0, 16)

    def test_iteration(self):
        """Test iteration over bitboard values."""
        values = (10, 20, 30, 40, 50, 60, 70, 80)
        compact = CompactBitboard.from_tuple(values)

        result = list(compact)
        assert result == list(values)

    def test_from_any(self):
        """Test creation from various input types."""
        original = (1, 2, 3, 4, 5, 6, 7, 8)

        # From tuple
        from_tuple = CompactBitboard.from_any(original)
        assert from_tuple.to_tuple() == original

        # From existing CompactBitboard
        from_compact = CompactBitboard.from_any(from_tuple)
        assert from_compact.to_tuple() == original
        assert from_compact is from_tuple  # Should return same instance

        # From bytes
        data = bytes([1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0, 7, 0, 8, 0])
        from_bytes = CompactBitboard.from_any(data)
        assert from_bytes.to_tuple() == original

        # Invalid type
        with pytest.raises(TypeError):
            CompactBitboard.from_any("invalid")

        with pytest.raises(TypeError):
            CompactBitboard.from_any(123)

        with pytest.raises(ValueError, match="exactly 16 bytes"):
            CompactBitboard(bytes(8))  # Wrong byte length

        with pytest.raises(ValueError, match="0-65535"):
            CompactBitboard((1, 2, 3, 4, 5, 6, 7, 65536))  # Value too large

        with pytest.raises(ValueError, match="0-65535"):
            CompactBitboard((-1, 0, 1, 2, 3, 4, 5, 6))  # Negative value

        with pytest.raises(TypeError):
            CompactBitboard("invalid")  # Wrong type


class TestQFENIntegration:
    """Test QFEN serialization/deserialization functionality."""

    def test_qfen_roundtrip_empty(self):
        """Test QFEN roundtrip with empty board."""
        qfen = "..../..../..../...."  # Proper 4x4 empty board
        compact = CompactBitboard.from_qfen(qfen)

        # Should be all zeros
        assert compact.to_tuple() == (0, 0, 0, 0, 0, 0, 0, 0)

        # Roundtrip should work
        reconstructed = compact.to_qfen()
        assert reconstructed == qfen

    def test_qfen_roundtrip_single_piece(self):
        """Test QFEN roundtrip with single piece."""
        qfen = "A.../..../..../...."  # Proper 4x4 with single piece
        compact = CompactBitboard.from_qfen(qfen)

        # Should have bit set for player 0, shape 0, position 0
        bitboard = compact.to_tuple()
        assert bitboard[0] == 1  # Player 0, Shape A (0), position 0
        assert all(bitboard[i] == 0 for i in range(1, 8))  # All others zero

        # Roundtrip should work
        reconstructed = compact.to_qfen()
        assert reconstructed == qfen

    def test_qfen_roundtrip_mixed_position(self):
        """Test QFEN roundtrip with mixed position."""
        qfen = "A.bC/..../d..B/...a"
        compact = CompactBitboard.from_qfen(qfen)

        # Roundtrip should work
        reconstructed = compact.to_qfen()
        assert reconstructed == qfen


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
