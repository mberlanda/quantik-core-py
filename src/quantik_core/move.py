"""
Move representation and validation for Quantik game states.

This module provides the foundation for game state iteration, move generation,
and game tree construction by defining moves and their validation.
"""

from dataclasses import dataclass
from typing import Optional
from .core import PlayerId, State
from .state_validator import ValidationResult, _validate_game_state_single_pass


@dataclass(frozen=True)
class Move:
    """
    Represents a single move in the Quantik game.
    
    A move consists of placing a piece of a specific shape at a specific position
    by a specific player.
    """
    player: PlayerId
    shape: int  # 0=A, 1=B, 2=C, 3=D
    position: int  # 0-15 (4x4 board)
    
    def __post_init__(self):
        """Validate move parameters."""
        if self.player not in (0, 1):
            raise ValueError(f"Invalid player: {self.player}")
        if self.shape not in range(4):
            raise ValueError(f"Invalid shape: {self.shape}")
        if self.position not in range(16):
            raise ValueError(f"Invalid position: {self.position}")


class MoveValidationResult:
    """
    Result of move validation containing both success/failure and the new state.
    """
    def __init__(self, is_valid: bool, error: Optional[ValidationResult] = None, 
                 new_state: Optional[State] = None):
        self.is_valid = is_valid
        self.error = error
        self.new_state = new_state


def validate_move(state: State, move: Move) -> MoveValidationResult:
    """
    Validate if a move can be applied to the given state.
    
    This function checks:
    1. If it's the player's turn
    2. If the position is empty
    3. If the resulting state would be valid
    
    Args:
        state: Current game state
        move: Move to validate
        
    Returns:
        MoveValidationResult with validation outcome and potentially new state
    """
    # Check if it's the player's turn
    current_player, validation_result = _validate_game_state_single_pass(state.bb)
    if validation_result != ValidationResult.OK:
        return MoveValidationResult(False, validation_result)
    
    if current_player != move.player:
        return MoveValidationResult(False, ValidationResult.NOT_PLAYER_TURN)
    
    # Check if position is empty
    position_mask = 1 << move.position
    for bb_value in state.bb:
        if bb_value & position_mask:
            return MoveValidationResult(False, ValidationResult.PIECE_OVERLAP)
    
    # Create new state with the move applied
    new_bb = list(state.bb)
    bitboard_index = move.shape if move.player == 0 else move.shape + 4
    new_bb[bitboard_index] |= position_mask
    
    # Validate the new state
    new_state = State(tuple(new_bb))
    _, new_validation_result = _validate_game_state_single_pass(new_state.bb)
    
    if new_validation_result != ValidationResult.OK:
        return MoveValidationResult(False, new_validation_result)
    
    return MoveValidationResult(True, None, new_state)


def apply_move(state: State, move: Move) -> State:
    """
    Apply a move to a state, returning the new state.
    
    This function assumes the move is valid. Use validate_move() first if unsure.
    
    Args:
        state: Current game state
        move: Move to apply
        
    Returns:
        New state with the move applied
    """
    new_bb = list(state.bb)
    position_mask = 1 << move.position
    bitboard_index = move.shape if move.player == 0 else move.shape + 4
    new_bb[bitboard_index] |= position_mask
    
    return State(tuple(new_bb))
