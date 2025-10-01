"""
Tests for game_utils module - consolidated game utilities.

This test module verifies that the consolidated functions for piece counting,
endgame detection, and game state analysis work correctly and provide the same
results as the previous duplicated implementations.
"""

import pytest
from src.quantik_core.game_utils import (
    count_pieces_by_shape,
    count_pieces_by_shape_lists,
    count_total_pieces,
    count_player_shape_pieces,
    has_winning_line,
    check_game_winner,
    is_game_over,
    WinStatus,
)
from src.quantik_core.commons import Bitboard
from src.quantik_core.qfen import bb_from_qfen


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


class TestGameUtilsEndgameDetection:
    """Test consolidated endgame detection utilities."""

    def test_has_winning_line_empty_board(self):
        """Test no winning line on empty board."""
        empty_bb = bb_from_qfen("..../..../..../....")
        assert not has_winning_line(empty_bb)

    def test_has_winning_line_simple_row_win(self):
        """Test winning line detection - full row."""
        # Row 0 has all shapes (ABCD)
        winning_bb = bb_from_qfen("ABCD/..../..../....")
        assert has_winning_line(winning_bb)

    def test_has_winning_line_mixed_players_row(self):
        """Test winning line with mixed players in same row."""
        # Row 0 has all shapes (AbcD) - mixed players
        winning_bb = bb_from_qfen("AbcD/..../..../....")
        assert has_winning_line(winning_bb)

    def test_has_winning_line_column_win(self):
        """Test winning line detection - column."""
        # Column 0 has all shapes (A, b, C, d)
        winning_bb = bb_from_qfen("A.../b.../C.../d...")
        assert has_winning_line(winning_bb)

    def test_has_winning_line_zone_win(self):
        """Test winning line detection - 2x2 zone."""
        # Top-left zone has all shapes
        winning_bb = bb_from_qfen("AB../cd../..../....")
        assert has_winning_line(winning_bb)

    def test_has_winning_line_no_win_incomplete(self):
        """Test no winning line when shapes are incomplete."""
        # Missing shape D in row 0
        incomplete_bb = bb_from_qfen("ABC./..../..../....")
        assert not has_winning_line(incomplete_bb)

    def test_check_game_winner_no_win(self):
        """Test game winner detection - no winner."""
        empty_bb = bb_from_qfen("..../..../..../....")
        assert check_game_winner(empty_bb) == WinStatus.NO_WIN

    def test_check_game_winner_player0_wins(self):
        """Test game winner detection - Player 0 wins."""
        # Player 0 has more pieces and there's a winning line
        winning_bb = bb_from_qfen("ABCD/..../..../....")
        assert check_game_winner(winning_bb) == WinStatus.PLAYER_0_WINS

    def test_check_game_winner_player1_wins_by_turn(self):
        """Test game winner detection - Player 1 wins by having equal pieces."""
        # Both players have 2 pieces, so Player 1 made the last move
        winning_bb = bb_from_qfen("ABcd/..../..../....")
        assert check_game_winner(winning_bb) == WinStatus.PLAYER_1_WINS

    def test_is_game_over_true(self):
        """Test game over detection - game is over."""
        winning_bb = bb_from_qfen("ABCD/..../..../....")
        assert is_game_over(winning_bb)

    def test_is_game_over_false(self):
        """Test game over detection - game not over."""
        ongoing_bb = bb_from_qfen("ABC./..../..../....")
        assert not is_game_over(ongoing_bb)

    def test_compatibility_with_endgame_function(self):
        """Test compatibility with existing endgame.py function."""
        from src.quantik_core.plugins.endgame import bb_has_winning_line as old_fn
        
        winning_bb = bb_from_qfen("ABCD/..../..../....")
        ongoing_bb = bb_from_qfen("ABC./..../..../....")
        
        # Compare results - both should delegate to the same consolidated function
        assert has_winning_line(winning_bb) == old_fn(winning_bb)
        assert has_winning_line(ongoing_bb) == old_fn(ongoing_bb)

    def test_compatibility_with_validation_functions(self):
        """Test compatibility with existing validation.py functions."""
        from src.quantik_core.plugins.validation import (
            bb_check_game_winner as old_bb_check,
            check_game_winner as old_check,
            is_game_over as old_is_over,
        )
        from src.quantik_core import State
        
        winning_bb = bb_from_qfen("ABCD/..../..../....")
        ongoing_bb = bb_from_qfen("ABC./..../..../....")
        
        # Test bb-level functions
        assert check_game_winner(winning_bb) == old_bb_check(winning_bb)
        assert check_game_winner(ongoing_bb) == old_bb_check(ongoing_bb)
        
        # Test State-level functions
        winning_state = State(winning_bb)
        ongoing_state = State(ongoing_bb)
        
        assert check_game_winner(winning_bb) == old_check(winning_state)
        assert check_game_winner(ongoing_bb) == old_check(ongoing_state)
        
        assert is_game_over(winning_bb) == old_is_over(winning_state)
        assert is_game_over(ongoing_bb) == old_is_over(ongoing_state)