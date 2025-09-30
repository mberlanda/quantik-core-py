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
