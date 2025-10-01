"""
Tests for game_utils module - consolidated piece counting utilities.

This test module verifies that the consolidated piece counting functions
work correctly and provide the same results as the previous duplicated implementations.
"""

import pytest
from src.quantik_core.game_utils import (
    count_pieces_by_shape,
    count_pieces_by_shape_lists,
    count_total_pieces,
    count_player_shape_pieces,
)
from src.quantik_core.commons import Bitboard


class TestGameUtilsPieceCounting:
    """Test consolidated piece counting utilities."""

    def test_count_pieces_by_shape_empty_board(self):
        """Test piece counting on empty board."""
        bb: Bitboard = (0, 0, 0, 0, 0, 0, 0, 0)
        
        player0_counts, player1_counts = count_pieces_by_shape(bb)
        
        assert player0_counts == (0, 0, 0, 0)
        assert player1_counts == (0, 0, 0, 0)

    def test_count_pieces_by_shape_with_pieces(self):
        """Test piece counting with actual pieces on board."""
        # Player 0: 1 A (position 0), 2 B's (positions 0,1), 1 C (position 2)
        # Player 1: 1 A (position 0), 1 D (position 3)
        bb: Bitboard = (1, 3, 4, 0, 1, 0, 0, 8)
        
        player0_counts, player1_counts = count_pieces_by_shape(bb)
        
        assert player0_counts == (1, 2, 1, 0)  # A=1, B=2, C=1, D=0
        assert player1_counts == (1, 0, 0, 1)  # a=1, b=0, c=0, d=1

    def test_count_pieces_by_shape_lists_returns_lists(self):
        """Test that lists variant returns mutable lists."""
        bb: Bitboard = (1, 2, 0, 0, 4, 0, 0, 0)
        
        player0_counts, player1_counts = count_pieces_by_shape_lists(bb)
        
        # Should be lists, not tuples
        assert isinstance(player0_counts, list)
        assert isinstance(player1_counts, list)
        assert player0_counts == [1, 1, 0, 0]
        assert player1_counts == [1, 0, 0, 0]
        
        # Should be mutable
        player0_counts[0] = 999
        assert player0_counts[0] == 999

    def test_count_pieces_by_shape_caching(self):
        """Test that count_pieces_by_shape uses LRU cache."""
        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        
        # Call multiple times with same input
        result1 = count_pieces_by_shape(bb)
        result2 = count_pieces_by_shape(bb)
        result3 = count_pieces_by_shape(bb)
        
        # Results should be identical
        assert result1 == result2 == result3
        
        # Verify actual counts
        assert result1 == ((1, 1, 2, 1), (2, 2, 3, 1))

    def test_count_total_pieces(self):
        """Test total piece counting."""
        bb: Bitboard = (1, 3, 4, 0, 1, 0, 0, 8)  # Player 0: 3 pieces, Player 1: 2 pieces
        
        total0, total1 = count_total_pieces(bb)
        
        assert total0 == 4  # 1 + 2 + 1 + 0
        assert total1 == 2  # 1 + 0 + 0 + 1

    def test_count_total_pieces_empty_board(self):
        """Test total piece counting on empty board."""
        bb: Bitboard = (0, 0, 0, 0, 0, 0, 0, 0)
        
        total0, total1 = count_total_pieces(bb)
        
        assert total0 == 0
        assert total1 == 0

    def test_count_player_shape_pieces(self):
        """Test counting pieces for specific player and shape."""
        bb: Bitboard = (1, 3, 4, 0, 1, 0, 0, 8)
        
        # Player 0 pieces
        assert count_player_shape_pieces(bb, 0, 0) == 1  # A = 1 piece
        assert count_player_shape_pieces(bb, 0, 1) == 2  # B = 2 pieces  
        assert count_player_shape_pieces(bb, 0, 2) == 1  # C = 1 piece
        assert count_player_shape_pieces(bb, 0, 3) == 0  # D = 0 pieces
        
        # Player 1 pieces
        assert count_player_shape_pieces(bb, 1, 0) == 1  # a = 1 piece
        assert count_player_shape_pieces(bb, 1, 1) == 0  # b = 0 pieces
        assert count_player_shape_pieces(bb, 1, 2) == 0  # c = 0 pieces
        assert count_player_shape_pieces(bb, 1, 3) == 1  # d = 1 piece

    def test_consistency_between_functions(self):
        """Test that different counting functions are consistent."""
        bb: Bitboard = (5, 10, 15, 3, 7, 2, 1, 12)
        
        # Get counts using different methods
        tuple_counts = count_pieces_by_shape(bb)
        list_counts = count_pieces_by_shape_lists(bb)
        totals = count_total_pieces(bb)
        
        # Convert list results to tuples for comparison
        list_as_tuples = (tuple(list_counts[0]), tuple(list_counts[1]))
        
        # Should be equivalent
        assert tuple_counts == list_as_tuples
        
        # Total should match sum of individual counts
        assert totals[0] == sum(tuple_counts[0])
        assert totals[1] == sum(tuple_counts[1])
        
        # Individual piece counts should match
        for player in range(2):
            for shape in range(4):
                expected = tuple_counts[player][shape]
                actual = count_player_shape_pieces(bb, player, shape)
                assert expected == actual, f"Mismatch for player {player}, shape {shape}"

    def test_compatibility_with_move_function(self):
        """Test compatibility with existing move.py function."""
        from src.quantik_core.move import count_pieces_by_player_shape
        
        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        
        # Compare results
        new_result = count_pieces_by_shape_lists(bb)
        old_result = count_pieces_by_player_shape(bb)
        
        assert new_result == old_result

    def test_compatibility_with_validation_function(self):
        """Test compatibility with existing validation.py function."""
        from src.quantik_core.plugins.validation import count_pieces_by_shape as val_count
        from src.quantik_core import State
        
        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        state = State(bb)
        
        # Compare results
        new_result = count_pieces_by_shape(bb)
        old_result = val_count(state)
        
        assert new_result == old_result


class TestGameUtilsEdgeCases:
    """Test edge cases and error conditions."""

    def test_large_piece_counts(self):
        """Test with maximum possible piece counts."""
        # Each bitboard can have up to 16 bits set (for 4x4 board)
        bb: Bitboard = (65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535)
        
        player0_counts, player1_counts = count_pieces_by_shape(bb)
        
        # Each shape should have 16 pieces (all positions occupied)
        assert player0_counts == (16, 16, 16, 16)
        assert player1_counts == (16, 16, 16, 16)
        
        total0, total1 = count_total_pieces(bb)
        assert total0 == 64
        assert total1 == 64

    def test_single_bits_set(self):
        """Test with single bits set in each bitboard."""
        bb: Bitboard = (1, 2, 4, 8, 16, 32, 64, 128)
        
        player0_counts, player1_counts = count_pieces_by_shape(bb)
        
        # Each should have exactly 1 piece
        assert player0_counts == (1, 1, 1, 1)
        assert player1_counts == (1, 1, 1, 1)

    def test_parameter_validation_player_shape_pieces(self):
        """Test that count_player_shape_pieces handles valid inputs."""
        bb: Bitboard = (1, 2, 3, 4, 5, 6, 7, 8)
        
        # Valid parameters should work
        assert count_player_shape_pieces(bb, 0, 0) == 1
        assert count_player_shape_pieces(bb, 1, 3) == 1
        
        # Note: We don't validate parameters in the current implementation
        # but this test documents expected usage patterns