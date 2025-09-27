"""
Unit tests for the SymmetryHandler and SymmetryTransform classes.

Tests verify:
- Correct application of symmetry operations to bitboards
- Preservation of symmetry invariants
- Identity of canonical forms for symmetric positions
- Correct symmetry-aware QFEN canonicalization
- Correct application of symmetries to moves
- Consistency of transformation inverse operations
"""

import pytest

from quantik_core import (
    Move,
    SymmetryHandler,
    SymmetryTransform,
    Bitboard,
    State,
    ALL_SHAPE_PERMS,
)

from quantik_core.symmetry import D4Index


def bb_to_qfen(bb: Bitboard) -> str:
    return State(bb).to_qfen()


class TestSymmetryTransform:
    """Test SymmetryTransform class."""

    def test_valid_creation(self):
        """Test creation of valid symmetry transforms."""
        # Test all valid combinations
        for d4_idx in range(8):
            for color_swap in (False, True):
                for perm in [(0, 1, 2, 3), (3, 2, 1, 0), (1, 0, 3, 2)]:
                    transform = SymmetryTransform(
                        d4_index=d4_idx, color_swap=color_swap, shape_perm=perm
                    )
                    assert transform.d4_index == d4_idx
                    assert transform.color_swap == color_swap
                    assert transform.shape_perm == perm

    def test_invalid_creation(self):
        """Test creation of invalid symmetry transforms."""
        # Invalid D4 index
        with pytest.raises(ValueError):
            SymmetryTransform(d4_index=8, color_swap=False, shape_perm=(0, 1, 2, 3))

        # Invalid shape permutation (wrong length)
        with pytest.raises(ValueError):
            SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(0, 1, 2))

        # Invalid shape permutation (invalid values)
        with pytest.raises(ValueError):
            SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(0, 1, 2, 5))

    def test_inverse_transform(self):
        """Test that applying a transform and then its inverse yields identity."""
        transforms = [
            SymmetryTransform(
                d4_index=D4Index.ID, color_swap=False, shape_perm=(0, 1, 2, 3)
            ),  # identity
            SymmetryTransform(
                d4_index=D4Index.ROT90, color_swap=False, shape_perm=(0, 1, 2, 3)
            ),  # rot90
            SymmetryTransform(
                d4_index=D4Index.REFLV, color_swap=True, shape_perm=(1, 0, 3, 2)
            ),  # reflV + color swap + perm
        ]

        for transform in transforms:
            inverse = transform.inverse()

            # Identity transform should be its own inverse
            if (
                transform.d4_index == 0
                and not transform.color_swap
                and transform.shape_perm == (0, 1, 2, 3)
            ):
                assert inverse == transform

            # Verify inverse properties
            assert (
                inverse.color_swap == transform.color_swap
            )  # Color swap is its own inverse
            assert inverse.d4_index == SymmetryHandler.get_d4_inverse(
                transform.d4_index
            )

            # Verify shape perm inverse
            for i, j in enumerate(transform.shape_perm):
                assert inverse.shape_perm[j] == i


class TestSymmetryOperations:
    """Test basic symmetry operations."""

    def test_d4_mappings(self):
        """Test D4 mappings for basic positions."""
        # Corner position (0)
        corner = 1  # bit 0 set (top-left corner)

        # Get the actual mappings for verification
        rot90 = SymmetryHandler.permute16(corner, 1)
        rot180 = SymmetryHandler.permute16(corner, 2)
        rot270 = SymmetryHandler.permute16(corner, 3)

        # Verify basic properties rather than specific values
        assert (
            SymmetryHandler.permute16(corner, 0) == corner
        )  # Identity preserves the value
        assert rot90 != corner  # Each rotation should change the value
        assert rot180 != corner
        assert rot180 != rot90
        assert rot270 != corner
        assert rot270 != rot90
        assert rot270 != rot180

        # Test that applying rotations sequentially works as expected
        assert SymmetryHandler.permute16(rot90, 1) == rot180  # 90° + 90° = 180°
        assert SymmetryHandler.permute16(rot180, 1) == rot270  # 180° + 90° = 270°
        assert (
            SymmetryHandler.permute16(rot270, 1) == corner
        )  # 270° + 90° = 360° (identity)

    def test_apply_symmetry(self):
        """Test applying symmetry to a bitboard."""
        # Create a simple bitboard with one piece in each quadrant
        bb: Bitboard = (1, 0, 0, 0, 0, 32, 0, 0)  # P0 shape0 at pos0, P1 shape1 at pos5

        assert bb_to_qfen(bb) == "A.../.b../..../...."

        # Identity transform
        identity = SymmetryTransform(
            d4_index=D4Index.ID, color_swap=False, shape_perm=(0, 1, 2, 3)
        )
        result = SymmetryHandler.apply_symmetry(bb, identity)
        assert result == bb

        # Get the transformed positions using permute16
        pos0_rot90 = SymmetryHandler.permute16(1, 1)  # Pos 0 after 90° rotation
        pos5_rot90 = SymmetryHandler.permute16(32, 1)  # Pos 5 after 90° rotation

        # 90° rotation
        rot90 = SymmetryTransform(
            d4_index=D4Index.ROT90, color_swap=False, shape_perm=(0, 1, 2, 3)
        )
        result = SymmetryHandler.apply_symmetry(bb, rot90)

        # Expected: P0 shape0 at rotated pos0, P1 shape1 at rotated pos5
        expected: Bitboard = (pos0_rot90, 0, 0, 0, 0, pos5_rot90, 0, 0)
        assert result == expected
        assert bb_to_qfen(result) == "...A/..b./..../...."

        # Color swap
        color_swap = SymmetryTransform(
            d4_index=D4Index.ID, color_swap=True, shape_perm=(0, 1, 2, 3)
        )
        result = SymmetryHandler.apply_symmetry(bb, color_swap)
        expected = (0, 32, 0, 0, 1, 0, 0, 0)
        assert result == expected
        assert bb_to_qfen(result) == "a.../.B../..../...."

        # Shape permutation
        shape_perm = SymmetryTransform(
            d4_index=D4Index.ID, color_swap=False, shape_perm=(1, 0, 3, 2)
        )
        result = SymmetryHandler.apply_symmetry(bb, shape_perm)
        # P0 shape0 -> shape1, P1 shape1 -> shape0
        expected = (0, 1, 0, 0, 32, 0, 0, 0)
        assert result == expected
        assert bb_to_qfen(result) == "B.../.a../..../...."

        # Combined transformation - for complex transformations, we'll just check the result is different
        combined = SymmetryTransform(
            d4_index=D4Index.ROT90, color_swap=True, shape_perm=(1, 0, 3, 2)
        )
        result = SymmetryHandler.apply_symmetry(bb, combined)
        assert result != bb  # Should be different from original
        assert bb_to_qfen(result) == "...b/..A./..../...."

        # We can also verify that undoing the transformation restores the original
        inverse = combined.inverse()
        restored = SymmetryHandler.apply_symmetry(result, inverse)
        assert restored == bb  # Should restore the original


class TestCanonicalForms:
    """Test canonical form calculations."""

    def test_empty_board_canonical(self):
        """Test canonical form of empty board."""
        empty_bb: Bitboard = (0, 0, 0, 0, 0, 0, 0, 0)
        canonical_bb, _ = SymmetryHandler.find_canonical_form(empty_bb)
        assert canonical_bb == empty_bb

    def test_single_piece_canonical(self):
        """Test canonical forms with a single piece."""
        # According to core.py tests, we expect three canonical forms for single pieces
        # Test a corner piece (should map to top-left)
        corner_bb: Bitboard = (
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            128,
        )  # P1 shape3 at pos7 (bottom-right)
        canonical_bb, transform = SymmetryHandler.find_canonical_form(corner_bb)
        expected = (
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            256,
        )  # Should map to a specific corner in canonical form
        assert canonical_bb == expected

        # Test center piece
        center_bb: Bitboard = (0, 0, 0, 4096, 0, 0, 0, 0)  # P0 shape3 at pos12
        canonical_bb, transform = SymmetryHandler.find_canonical_form(center_bb)
        expected = (0, 0, 0, 0, 0, 0, 0, 4096)  # Maps to a specific center position
        assert canonical_bb == expected

    def test_canonical_form_invariance(self):
        """Test that symmetric positions map to the same canonical form."""
        # Start with a specific bitboard
        bb: Bitboard = (1, 16, 0, 0, 0, 0, 128, 0)
        canonical1, _ = SymmetryHandler.find_canonical_form(bb)

        # Try various symmetry transformations
        for d4_idx in range(8):
            for color_swap in (False, True):
                for perm_idx in range(min(5, len(ALL_SHAPE_PERMS))):  # Test a few perms
                    transform = SymmetryTransform(
                        d4_index=d4_idx,
                        color_swap=color_swap,
                        shape_perm=ALL_SHAPE_PERMS[perm_idx],
                    )
                    transformed_bb = SymmetryHandler.apply_symmetry(bb, transform)
                    canonical2, _ = SymmetryHandler.find_canonical_form(transformed_bb)

                    # All should map to the same canonical form
                    assert canonical2 == canonical1

    def test_qfen_canonical(self):
        """Test QFEN canonical form calculation."""
        # For testing, we'll just verify that the canonical form is consistent
        test_qfens = [
            "..../..../..../....",  # Empty board
            "A.../..../..../....",  # Single piece
            "A.B./..../..../....",  # Two pieces
            "A..b/.c../..D./....",  # Mixed position
        ]

        for qfen in test_qfens:
            # Get the canonical form
            canonical = SymmetryHandler.get_qfen_canonical_form(qfen)
            state = State.from_qfen(qfen)

            # Apply a few symmetry transformations
            variations = []
            for d4_idx in range(8):
                transform = SymmetryTransform(
                    d4_index=d4_idx, color_swap=False, shape_perm=(0, 1, 2, 3)
                )
                transformed_bb = SymmetryHandler.apply_symmetry(state.bb, transform)
                variations.append(State(transformed_bb).to_qfen())

            # All variations should map to the same canonical form
            for var in variations:
                var_canonical = SymmetryHandler.get_qfen_canonical_form(var)
                assert var_canonical == canonical


class TestMoveSymmetry:
    """Test applying symmetry to moves."""

    def test_move_transformation(self):
        """Test transforming moves with symmetry operations."""
        # Create a move
        move = Move(
            player=0, shape=1, position=3
        )  # P0, shape B at position 3 (top-right)

        # Apply identity transform
        identity = SymmetryTransform(
            d4_index=D4Index.ID, color_swap=False, shape_perm=(0, 1, 2, 3)
        )
        result = SymmetryHandler.apply_symmetry_to_move(move, identity)
        assert result.player == move.player
        assert result.shape == move.shape
        assert result.position == move.position

        # Apply 90° rotation
        rot90 = SymmetryTransform(
            d4_index=D4Index.ROT90, color_swap=False, shape_perm=(0, 1, 2, 3)
        )
        result = SymmetryHandler.apply_symmetry_to_move(move, rot90)
        assert result.player == move.player
        assert result.shape == move.shape
        assert result.position == 15  # Position 3 rotated 90° becomes position 15

        # Apply color swap
        color_swap = SymmetryTransform(
            d4_index=D4Index.ID, color_swap=True, shape_perm=(0, 1, 2, 3)
        )
        result = SymmetryHandler.apply_symmetry_to_move(move, color_swap)
        assert result.player == 1  # Player 0 becomes player 1
        assert result.shape == move.shape
        assert result.position == move.position

        # Apply shape permutation
        shape_perm = SymmetryTransform(
            d4_index=D4Index.ID, color_swap=False, shape_perm=(1, 0, 3, 2)
        )
        result = SymmetryHandler.apply_symmetry_to_move(move, shape_perm)
        assert result.player == move.player
        assert result.shape == 0  # Shape 1 becomes shape 0 in the permutation
        assert result.position == move.position

    def test_transform_and_inverse(self):
        """Test that applying a transform and then its inverse preserves the original move."""
        move = Move(player=0, shape=2, position=6)

        # Define a complex transformation
        transform = SymmetryTransform(
            d4_index=D4Index.REFLV, color_swap=True, shape_perm=(3, 1, 0, 2)
        )

        # Apply transform
        transformed = SymmetryHandler.apply_symmetry_to_move(move, transform)

        # Apply inverse transform
        inverse = transform.inverse()
        restored = SymmetryHandler.apply_symmetry_to_move(transformed, inverse)

        # Check that we got back to the original move
        assert restored.player == move.player
        assert restored.shape == move.shape
        assert restored.position == move.position


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
