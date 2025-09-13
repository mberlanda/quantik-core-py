"""
Unit tests for move representation and validation.
"""

import pytest
from quantik_core import State
from quantik_core.move import Move, MoveValidationResult, validate_move, apply_move
from quantik_core.state_validator import ValidationResult


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
        state = State.empty()
        move = Move(player=0, shape=0, position=0)  # Player 0 goes first
        
        result = validate_move(state, move)
        assert result.is_valid
        assert result.error is None
        assert result.new_state is not None
        
        # Check that the move was applied correctly
        expected_bb = [1, 0, 0, 0, 0, 0, 0, 0]  # Shape A for player 0 at position 0
        assert result.new_state.bb == tuple(expected_bb)
    
    def test_wrong_player_turn(self):
        """Test that wrong player can't move."""
        state = State.empty()
        move = Move(player=1, shape=0, position=0)  # Player 1 tries to go first
        
        result = validate_move(state, move)
        assert not result.is_valid
        assert result.error == ValidationResult.NOT_PLAYER_TURN
        assert result.new_state is None
    
    def test_position_occupied(self):
        """Test that can't place piece on occupied position."""
        # Create state with piece at position 0
        state = State.from_qfen("A.../..../..../....", validate=False)
        move = Move(player=1, shape=1, position=0)  # Try to place at same position
        
        result = validate_move(state, move)
        assert not result.is_valid
        assert result.error == ValidationResult.PIECE_OVERLAP
        assert result.new_state is None
    
    def test_correct_turn_sequence(self):
        """Test correct alternating turns."""
        state = State.empty()
        
        # Player 0 goes first
        move1 = Move(player=0, shape=0, position=0)
        result1 = validate_move(state, move1)
        assert result1.is_valid
        
        # Player 1 goes second
        move2 = Move(player=1, shape=1, position=1)
        result2 = validate_move(result1.new_state, move2)
        assert result2.is_valid
        
        # Player 0 goes third
        move3 = Move(player=0, shape=2, position=2)
        result3 = validate_move(result2.new_state, move3)
        assert result3.is_valid
    
    def test_illegal_placement_same_shape_same_line(self):
        """Test that placing same shape on same line is illegal."""
        # Place A at position 0 (row 0, col 0)
        state = State.from_qfen("A.../..../..../....", validate=False)
        
        # Try to place another A in same row
        move = Move(player=1, shape=0, position=1)  # A at position 1 (row 0, col 1)
        result = validate_move(state, move)
        
        assert not result.is_valid
        assert result.error == ValidationResult.ILLEGAL_PLACEMENT


class TestApplyMove:
    """Test move application."""
    
    def test_apply_move_empty_board(self):
        """Test applying move to empty board."""
        state = State.empty()
        move = Move(player=0, shape=0, position=0)
        
        new_state = apply_move(state, move)
        
        expected_bb = [1, 0, 0, 0, 0, 0, 0, 0]  # Shape A for player 0 at position 0
        assert new_state.bb == tuple(expected_bb)
    
    def test_apply_move_preserves_existing_pieces(self):
        """Test that applying move preserves existing pieces."""
        # Start with A at position 0
        state = State.from_qfen("A.../..../..../....", validate=False)
        move = Move(player=1, shape=1, position=5)  # B at position 5
        
        new_state = apply_move(state, move)
        
        # Check that both pieces are present
        assert new_state.bb[0] == 1  # Player 0, shape A at position 0
        assert new_state.bb[5] == 32  # Player 1, shape B at position 5 (1 << 5 = 32)
    
    def test_apply_multiple_moves(self):
        """Test applying multiple moves in sequence."""
        state = State.empty()
        
        # Apply sequence: A0@0, B1@1, C0@2, D1@3
        moves = [
            Move(player=0, shape=0, position=0),  # A0 at pos 0
            Move(player=1, shape=1, position=1),  # B1 at pos 1
            Move(player=0, shape=2, position=2),  # C0 at pos 2
            Move(player=1, shape=3, position=3),  # D1 at pos 3
        ]
        
        current_state = state
        for move in moves:
            current_state = apply_move(current_state, move)
        
        # Verify final state
        expected_bb = [1, 0, 4, 0, 0, 2, 0, 8]  # A0@0, C0@2, B1@1, D1@3
        assert current_state.bb == tuple(expected_bb)


if __name__ == "__main__":
    pytest.main([__file__])
