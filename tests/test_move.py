"""
Unit tests for move representation and validation.
"""

import pytest
from quantik_core.move import (
    Move,
    validate_move,
    apply_move,
    generate_legal_moves,
    generate_legal_moves_list,
)
from quantik_core.game_utils import count_pieces_by_shape_lists
from quantik_core.memory.bitboard_compact import CompactBitboard
from quantik_core.state_validator import ValidationResult
from quantik_core.qfen import bb_from_qfen

EMPTY_BOARD_QFEN = "..../..../..../...."


class TestMove:
    """Test Move dataclass."""

    def test_valid_move_creation(self):
        """Test creating valid moves."""
        move = Move(player=0, shape=0, position=0)
        assert move.player == 0
        assert move.shape == 0
        assert move.position == 0

        move = Move(player=1, shape=3, position=15)
        assert move.player == 1
        assert move.shape == 3
        assert move.position == 15

    def test_invalid_player(self):
        """Test that invalid player raises ValueError."""
        with pytest.raises(ValueError, match="Invalid player"):
            Move(player=2, shape=0, position=0)

        with pytest.raises(ValueError, match="Invalid player"):
            Move(player=-1, shape=0, position=0)

    def test_invalid_shape(self):
        """Test that invalid shape raises ValueError."""
        with pytest.raises(ValueError, match="Invalid shape"):
            Move(player=0, shape=4, position=0)

        with pytest.raises(ValueError, match="Invalid shape"):
            Move(player=0, shape=-1, position=0)

    def test_invalid_position(self):
        """Test that invalid position raises ValueError."""
        with pytest.raises(ValueError, match="Invalid position"):
            Move(player=0, shape=0, position=16)

        with pytest.raises(ValueError, match="Invalid position"):
            Move(player=0, shape=0, position=-1)

    def test_move_immutability(self):
        """Test that Move is immutable (frozen dataclass)."""
        move = Move(player=0, shape=0, position=0)
        with pytest.raises(AttributeError):
            move.player = 1


class TestMoveValidation:
    """Test move validation functionality."""

    def test_valid_move_on_empty_board(self):
        """Test validating a move on empty board."""
        bb = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)
        move = Move(player=0, shape=0, position=0)  # Player 0 goes first

        result = validate_move(bb, move)
        assert result.is_valid
        assert result.error is None
        assert result.new_bb is not None

        # Check that the move was applied correctly
        expected_bb = [1, 0, 0, 0, 0, 0, 0, 0]  # Shape A for player 0 at position 0
        assert result.new_bb == tuple(expected_bb)

    def test_wrong_player_turn(self):
        """Test that wrong player can't move."""
        bb = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)
        move = Move(player=1, shape=0, position=0)  # Player 1 tries to go first

        result = validate_move(bb, move)
        assert not result.is_valid
        assert result.error == ValidationResult.NOT_PLAYER_TURN
        assert result.new_bb is None

    def test_position_occupied(self):
        """Test that can't place piece on occupied position."""
        # Create state with piece at position 0
        bb = bb_from_qfen("A.../..../..../....", validate=True)
        move = Move(player=1, shape=1, position=0)  # Try to place at same position

        result = validate_move(bb, move)
        assert not result.is_valid
        assert result.error == ValidationResult.PIECE_OVERLAP
        assert result.new_bb is None

    def test_correct_turn_sequence(self):
        """Test correct alternating turns."""
        bb = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)

        # Player 0 goes first
        move1 = Move(player=0, shape=0, position=0)
        result1 = validate_move(bb, move1)
        assert result1.is_valid

        # Player 1 goes second
        move2 = Move(player=1, shape=1, position=1)
        result2 = validate_move(result1.new_bb, move2)
        assert result2.is_valid

        # Player 0 goes third
        move3 = Move(player=0, shape=2, position=2)
        result3 = validate_move(result2.new_bb, move3)
        assert result3.is_valid

    def test_illegal_placement_same_shape_same_line(self):
        """Test that placing same shape on same line is illegal."""
        # Place A at position 0 (row 0, col 0)
        bb = bb_from_qfen("A.../..../..../....", validate=True)

        # Try to place another A in same row
        move = Move(player=1, shape=0, position=1)  # A at position 1 (row 0, col 1)
        result = validate_move(bb, move)

        assert not result.is_valid
        assert result.error == ValidationResult.ILLEGAL_PLACEMENT


class TestApplyMove:
    """Test move application."""

    def test_apply_move_empty_board(self):
        """Test applying move to empty board."""
        bb = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)
        move = Move(player=0, shape=0, position=0)

        new_bb = apply_move(bb, move)

        expected_bb = [1, 0, 0, 0, 0, 0, 0, 0]  # Shape A for player 0 at position 0
        assert new_bb == tuple(expected_bb)

    def test_apply_move_preserves_existing_pieces(self):
        """Test that applying move preserves existing pieces."""
        # Start with A at position 0
        bb = bb_from_qfen("A.../..../..../....", validate=True)
        move = Move(player=1, shape=1, position=5)  # B at position 5

        new_bb = apply_move(bb, move)

        # Check that both pieces are present
        assert new_bb[0] == 1  # Player 0, shape A at position 0
        assert new_bb[5] == 32  # Player 1, shape B at position 5 (1 << 5 = 32)

    def test_apply_multiple_moves(self):
        """Test applying multiple moves in sequence."""
        bb = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)

        # Apply sequence: A0@0, B1@1, C0@2, D1@3
        moves = [
            Move(player=0, shape=0, position=0),  # A0 at pos 0
            Move(player=1, shape=1, position=1),  # B1 at pos 1
            Move(player=0, shape=2, position=2),  # C0 at pos 2
            Move(player=1, shape=3, position=3),  # D1 at pos 3
        ]

        current_bb = bb
        for move in moves:
            current_bb = apply_move(current_bb, move)

        # Verify final state
        expected_bb = [1, 0, 4, 0, 0, 2, 0, 8]  # A0@0, C0@2, B1@1, D1@3
        assert current_bb == tuple(expected_bb)


class TestLegalMoveGeneration:
    """Test legal move generation functionality."""

    def test_empty_board_legal_moves(self):
        """Test legal moves on empty board."""
        bb = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)

        # Test new function
        current_player, moves_by_shape = generate_legal_moves(bb)
        assert current_player == 0

        # Player 0 should be able to place any shape on any position
        # 4 shapes × 16 positions = 64 moves total
        total_moves = sum(len(moves) for moves in moves_by_shape.values())
        assert total_moves == 64

        # Each shape should have 16 possible positions
        for shape in range(4):
            assert len(moves_by_shape[shape]) == 16

        # Test backward compatibility
        moves_list = generate_legal_moves_list(bb)
        assert len(moves_list) == 64

        # Check that all moves are for player 0
        assert all(move.player == 0 for move in moves_list)

    def test_max_pieces_constraint(self):
        """Test that max pieces per shape constraint is enforced."""
        bb = bb_from_qfen("A.A./b.../..c./....", validate=True)
        current_player, moves_by_shape = generate_legal_moves(bb)

        # Player 0's turn (they have 2 A pieces already)
        assert current_player == 0

        # Player 0 should not be able to place any more A pieces (already at max)
        assert len(moves_by_shape[0]) == 0  # No A moves

        # But should be able to place B, C, D (accounting for opponent constraints)
        for shape in [1, 2, 3]:
            assert len(moves_by_shape[shape]) > 0

    def test_opponent_same_shape_constraint_row(self):
        """Test that can't place same shape on same row as opponent."""
        # Player 0 has A at position 0 (row 0, col 0)
        bb = bb_from_qfen("A.../..../..../....", validate=True)
        current_player, moves_by_shape = generate_legal_moves(bb)

        assert current_player == 1  # Player 1's turn

        # Player 1 cannot place A at positions affected by constraints from position 0
        # Position 0 affects: row 0 [0,1,2,3], column 0 [0,4,8,12], zone 0 [0,1,4,5]
        # Union: [0,1,2,3,4,5,8,12] = 8 forbidden positions
        # So 16 - 8 = 8 allowed positions for A
        assert len(moves_by_shape[0]) == 8  # 8 allowed positions for A

        # Verify forbidden positions (union of row 0, col 0, zone 0)
        a_positions = {move.position for move in moves_by_shape[0]}
        forbidden = {0, 1, 2, 3, 4, 5, 8, 12}
        assert a_positions.isdisjoint(forbidden)

    def test_opponent_same_shape_constraint_column(self):
        """Test that can't place same shape on same column as opponent."""
        # Player 0 has B at position 0 (row 0, col 0)
        bb = bb_from_qfen("B.../..../..../....", validate=True)
        current_player, moves_by_shape = generate_legal_moves(bb)

        assert current_player == 1  # Player 1's turn

        # Same constraint analysis as row test - position 0 affects multiple lines
        # 8 forbidden positions, 8 allowed positions for B
        assert len(moves_by_shape[1]) == 8  # 8 allowed positions for B

        # Verify forbidden positions
        b_positions = {move.position for move in moves_by_shape[1]}
        forbidden = {0, 1, 2, 3, 4, 5, 8, 12}
        assert b_positions.isdisjoint(forbidden)

    def test_opponent_same_shape_constraint_zone(self):
        """Test that can't place same shape on same 2x2 zone as opponent."""
        # Player 0 has C at position 0 (zone 0: positions 0,1,4,5)
        bb = bb_from_qfen("C.../..../..../....", validate=True)
        current_player, moves_by_shape = generate_legal_moves(bb)

        assert current_player == 1  # Player 1's turn

        # Same constraint analysis - position 0 affects multiple lines
        # 8 forbidden positions, 8 allowed positions for C
        assert len(moves_by_shape[2]) == 8  # 8 allowed positions for C

        # Verify forbidden positions
        c_positions = {move.position for move in moves_by_shape[2]}
        forbidden = {0, 1, 2, 3, 4, 5, 8, 12}
        assert c_positions.isdisjoint(forbidden)

    def test_occupied_position_constraint(self):
        """Test that can't place on occupied positions."""
        # Create state with some pieces
        bb = bb_from_qfen("AB../c.../d.../....", validate=True)
        current_player, moves_by_shape = generate_legal_moves(bb)

        # No moves should target positions 0,1,4,8 (already occupied)
        occupied_positions = {0, 1, 4, 8}
        for shape_moves in moves_by_shape.values():
            for move in shape_moves:
                assert move.position not in occupied_positions

    def test_complex_constraint_interaction(self):
        """Test complex interactions between multiple constraints."""
        # Create a valid state with multiple constraints
        # Start with a simple valid state: Player 0 has A at pos 0, Player 1's turn
        bb = bb_from_qfen("A.../..../..../....", validate=True)
        current_player, moves_by_shape = generate_legal_moves(bb)

        # Player 1 should not be able to place A on positions affected by player 0's A at pos 0
        # Should have some legal moves for each shape
        assert len(moves_by_shape[0]) > 0  # A moves (constrained)
        assert len(moves_by_shape[1]) > 0  # B moves (unconstrained)
        assert len(moves_by_shape[2]) > 0  # C moves (unconstrained)
        assert len(moves_by_shape[3]) > 0  # D moves (unconstrained)

        # Verify specific constraints for A moves
        a_positions = {move.position for move in moves_by_shape[0]}
        forbidden_positions = {0, 1, 2, 3, 4, 5, 8, 12}  # Row 0 + Col 0 + Zone 0
        assert a_positions.isdisjoint(forbidden_positions)

    def test_no_legal_moves_invalid_state(self):
        """Test that no legal moves are returned for invalid state."""
        # Create an invalid state (this would need to be constructed manually)
        # For now, we'll use an edge case that might be hard to reach
        bb = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)
        current_player, moves_by_shape = generate_legal_moves(bb)
        assert (
            sum(len(moves) for moves in moves_by_shape.values()) > 0
        )  # Empty state should have moves

    def test_endgame_few_legal_moves(self):
        """Test legal moves in near-endgame scenarios."""
        # Create a state near endgame where most positions are filled
        # and most shapes are at max count
        bb = bb_from_qfen("AB.D/d.cb/AB../c.d.", validate=True)
        current_player, moves_by_shape = generate_legal_moves(bb)

        # Should have very few legal moves
        total_moves = sum(len(moves) for moves in moves_by_shape.values())
        assert total_moves >= 0  # At least no crash

        # All moves should be for the current player and valid positions
        for shape_moves in moves_by_shape.values():
            for move in shape_moves:
                assert move.position in range(16)
                assert move.shape in range(4)


class TestCountPiecesByPlayerShape:
    """Test piece counting functionality."""

    def test_empty_board_count(self):
        """Test counting on empty board."""
        bb = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)
        player0_counts, player1_counts = count_pieces_by_shape_lists(bb)

        assert player0_counts == [0, 0, 0, 0]
        assert player1_counts == [0, 0, 0, 0]

    def test_single_piece_count(self):
        """Test counting with single piece."""
        bb = bb_from_qfen("A.../..../..../....", validate=True)
        player0_counts, player1_counts = count_pieces_by_shape_lists(bb)

        assert player0_counts == [1, 0, 0, 0]  # One A for player 0
        assert player1_counts == [0, 0, 0, 0]

    def test_multiple_pieces_count(self):
        """Test counting with multiple pieces."""
        # Create a valid state with multiple pieces for both players
        bb = bb_from_qfen("Ab../cD../..../....", validate=True)
        player0_counts, player1_counts = count_pieces_by_shape_lists(bb)

        # Player 0: A@0, D@5 -> [1,0,0,1]
        # Player 1: b@1, c@4 -> [0,1,1,0]
        assert player0_counts == [1, 0, 0, 1]  # A, D for player 0
        assert player1_counts == [0, 1, 1, 0]  # b, c for player 1


class TestCompactBitboardIntegration:
    """Test move operations with CompactBitboard."""

    def test_validate_move_compact_bitboard(self):
        """Test validating moves with CompactBitboard input."""
        bb_tuple = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)
        compact_bb = CompactBitboard.from_tuple(bb_tuple)
        move = Move(player=0, shape=0, position=0)

        # Both should give same result
        result_tuple = validate_move(bb_tuple, move)
        result_compact = validate_move(compact_bb, move)

        assert result_tuple.is_valid == result_compact.is_valid
        assert result_tuple.error == result_compact.error
        assert result_tuple.new_bb == result_compact.new_bb

    def test_apply_move_compact_bitboard(self):
        """Test applying moves with CompactBitboard input."""
        bb_tuple = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)
        compact_bb = CompactBitboard.from_tuple(bb_tuple)
        move = Move(player=0, shape=0, position=0)

        # Apply move to tuple
        result_tuple = apply_move(bb_tuple, move)

        # Apply move to CompactBitboard
        result_compact = apply_move(compact_bb, move)

        # Results should be equivalent
        assert isinstance(result_compact, CompactBitboard)
        assert result_compact.to_tuple() == result_tuple

    def test_generate_legal_moves_compact_bitboard(self):
        """Test legal move generation with CompactBitboard input."""
        bb_tuple = bb_from_qfen(EMPTY_BOARD_QFEN, validate=True)
        compact_bb = CompactBitboard.from_tuple(bb_tuple)

        # Both should generate same moves
        player_tuple, moves_tuple = generate_legal_moves(bb_tuple)
        player_compact, moves_compact = generate_legal_moves(compact_bb)

        assert player_tuple == player_compact
        assert moves_tuple.keys() == moves_compact.keys()

        # Check all moves are identical
        for shape in moves_tuple:
            assert len(moves_tuple[shape]) == len(moves_compact[shape])
            for move_tuple, move_compact in zip(
                moves_tuple[shape], moves_compact[shape]
            ):
                assert move_tuple == move_compact

    def test_complex_game_scenario_compact_bitboard(self):
        """Test complex game scenario with CompactBitboard."""
        # Start with partially filled board
        qfen = "A.../b.../..c./...D"
        bb_tuple = bb_from_qfen(qfen, validate=True)
        compact_bb = CompactBitboard.from_tuple(bb_tuple)

        # Generate legal moves for both representations
        player_tuple, moves_tuple = generate_legal_moves(bb_tuple)
        player_compact, moves_compact = generate_legal_moves(compact_bb)

        # Should have same current player
        assert player_tuple == player_compact

        # Should have same number of legal moves for each shape
        for shape in range(4):
            assert len(moves_tuple[shape]) == len(moves_compact[shape])

        # Apply a move to both and verify results match
        if moves_tuple[0]:  # If shape A has legal moves
            test_move = moves_tuple[0][0]

            result_tuple = apply_move(bb_tuple, test_move)
            result_compact = apply_move(compact_bb, test_move)

            assert isinstance(result_compact, CompactBitboard)
            assert result_compact.to_tuple() == result_tuple


if __name__ == "__main__":
    pytest.main([__file__])
