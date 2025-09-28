"""
Tests for the QFEN conversion module.

This module tests the dedicated QFEN conversion functions that handle
conversion between bitboards and QFEN strings without circular imports.
"""

from quantik_core.qfen import bb_to_qfen, bb_from_qfen
from quantik_core.core import State
from quantik_core.symmetry import SymmetryHandler
import pytest


class TestQFENModule:
    """Test the dedicated QFEN conversion module."""

    def test_empty_board_conversion(self):
        """Test conversion of empty board."""
        empty_bb = (0, 0, 0, 0, 0, 0, 0, 0)
        qfen = bb_to_qfen(empty_bb)
        assert qfen == "..../..../..../....", f"Expected empty QFEN, got {qfen}"

        # Test roundtrip
        converted_bb = bb_from_qfen(qfen)
        assert converted_bb == empty_bb

    def test_qfen_roundtrip(self):
        """Test QFEN roundtrip conversion."""
        test_cases = [
            "A.../..../..../....",
            "A.bC/..../d..B/...a",
            "AB../ba../..../....",
            "ABCD/..../..../....",
        ]

        for original_qfen in test_cases:
            bb = bb_from_qfen(original_qfen)
            converted_qfen = bb_to_qfen(bb)
            assert (
                converted_qfen == original_qfen
            ), f"Roundtrip failed for {original_qfen}"

    def test_consistency_with_state_api(self):
        """Test that QFEN module produces same results as State API."""
        test_cases = [
            "..../..../..../....",
            "A.../..../..../....",
            "A.bC/..../d..B/...a",
        ]

        for qfen in test_cases:
            # Using QFEN module
            bb = bb_from_qfen(qfen)
            qfen_from_module = bb_to_qfen(bb)

            # Using State API
            state = State.from_qfen(qfen)
            qfen_from_state = state.to_qfen()

            assert qfen_from_module == qfen_from_state, f"Mismatch for {qfen}"
            assert bb == state.bb, f"Bitboard mismatch for {qfen}"

    def test_canonical_form(self):
        """Test canonical form generation."""
        # Test that canonical form function works
        qfen = "A.../..../..../...."
        canonical = SymmetryHandler.get_qfen_canonical_form(qfen)
        assert isinstance(canonical, str)
        assert "/" in canonical  # Should be valid QFEN format

        # Canonical form should be reproducible
        canonical2 = SymmetryHandler.get_qfen_canonical_form(qfen)
        assert canonical == canonical2

    def test_invalid_qfen_handling(self):
        """Test error handling for invalid QFEN strings."""
        invalid_qfens = [
            "A.../..../..../",  # Too few ranks
            "A.../..../..../..../",  # Too many ranks
            "A../..../..../....",  # Wrong rank length
            "X.../..../..../....",  # Invalid character
        ]

        for invalid_qfen in invalid_qfens:
            with pytest.raises(ValueError):
                bb_from_qfen(invalid_qfen)

    def test_validation_flag(self):
        """Test the validation flag in bb_from_qfen."""
        # Valid QFEN should work with validation
        valid_qfen = "A.../..../..../...."
        bb = bb_from_qfen(valid_qfen, validate=True)
        assert isinstance(bb, tuple)
        assert len(bb) == 8

        # For this basic test, we just ensure validation doesn't crash
        # More complex validation scenarios are tested in other modules
