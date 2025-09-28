"""
Move representation and validation for Quantik game bbs.

This module provides the foundation for game state iteration, move generation,
and game tree construction by defining moves and their validation.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
from .commons import Bitboard, PlayerId, WIN_MASKS, MAX_PIECES_PER_SHAPE
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

    def __post_init__(self) -> None:
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

    def __init__(
        self,
        is_valid: bool,
        error: Optional[ValidationResult] = None,
        new_bb: Optional[Bitboard] = None,
    ):
        self.is_valid = is_valid
        self.error = error
        self.new_bb = new_bb


def validate_move(bb: Bitboard, move: Move) -> MoveValidationResult:
    """
    Validate if a move can be applied to the given state.

    This function checks:
    1. If it's the player's turn
    2. If the position is empty
    3. If the resulting bitboard would be valid

    Args:
        bb: Current game bitboard
        move: Move to validate

    Returns:
        MoveValidationResult with validation outcome and potentially new state
    """
    # Check if it's the player's turn
    current_player, validation_result = _validate_game_state_single_pass(bb)
    if validation_result != ValidationResult.OK:
        return MoveValidationResult(False, validation_result)

    if current_player != move.player:
        return MoveValidationResult(False, ValidationResult.NOT_PLAYER_TURN)

    # Check if position is empty
    position_mask = 1 << move.position
    for bb_value in bb:
        if bb_value & position_mask:
            return MoveValidationResult(False, ValidationResult.PIECE_OVERLAP)

    # Create new state with the move applied
    new_bb = list(bb)
    bitboard_index = move.shape if move.player == 0 else move.shape + 4
    new_bb[bitboard_index] |= position_mask

    # Validate the new bitboard representation
    # TypeError: unhashable type: 'list'
    new_bb = tuple(new_bb)
    _, new_validation_result = _validate_game_state_single_pass(new_bb)

    if new_validation_result != ValidationResult.OK:
        return MoveValidationResult(False, new_validation_result)

    return MoveValidationResult(True, None, new_bb)


def apply_move(bb: Bitboard, move: Move) -> Bitboard:
    """
    Apply a move to a bb, returning the new bb.

    This function assumes the move is valid. Use validate_move() first if unsure.

    Args:
        bb: Current game Bitboard
        move: Move to apply

    Returns:
        New state with the move applied
    """
    new_bb = list(bb)  # TODO: check if I can do it without list conversion
    position_mask = 1 << move.position
    bitboard_index = move.shape if move.player == 0 else move.shape + 4
    new_bb[bitboard_index] |= position_mask

    return tuple(new_bb)  # type: ignore[arg-type]


def generate_legal_moves(
    bb: Bitboard, player_id: Optional[PlayerId] = None
) -> tuple[PlayerId, Dict[int, List[Move]]]:
    """
    Generate all legal moves for the current player in the given state.

    This function applies all Quantik game constraints:
    1. Maximum 2 pieces per shape per player
    2. Cannot place same shape on same line (row/column/zone) as opponent
    3. Position must be empty
    4. Must be player's turn

    Args:
        state: Current game state
        player_id: Optional player ID to validate against current turn

    Returns:
        Tuple of (current_player, moves_by_shape) where moves_by_shape is
        a dict with keys 0-3 (shapes A-D) and values as lists of legal moves
    """
    # First, determine whose turn it is
    current_player, validation_result = _validate_game_state_single_pass(bb)
    if validation_result != ValidationResult.OK or current_player is None:
        return 0, {}  # Invalid state, no legal moves

    # If player_id is specified, validate it matches current turn
    if player_id is not None and player_id != current_player:
        return current_player, {}  # Wrong player, no legal moves

    moves_by_shape: Dict[int, List[Move]] = {0: [], 1: [], 2: [], 3: []}  # A, B, C, D

    # Count current pieces for the player to enforce max pieces constraint
    player_shape_counts = [
        bb[current_player * 4 + shape].bit_count() for shape in range(4)
    ]

    # For each shape that the player can still place
    for shape in range(4):
        if player_shape_counts[shape] >= MAX_PIECES_PER_SHAPE:
            continue  # Player already has max pieces of this shape

        # Get opponent's pieces of the same shape
        opponent_shape_bits = bb[(1 - current_player) * 4 + shape]

        # For each position on the board
        for position in range(16):
            position_mask = 1 << position

            # Check if position is already occupied
            if any(bb_value & position_mask for bb_value in bb):
                continue

            # Check if this position conflicts with opponent's same shape on any win line
            is_legal = True
            for win_mask in WIN_MASKS:
                # If this position is on a win line that has opponent's same shape, illegal
                if (position_mask & win_mask) and (opponent_shape_bits & win_mask):
                    is_legal = False
                    break

            if is_legal:
                moves_by_shape[shape].append(Move(current_player, shape, position))

    return current_player, moves_by_shape


def generate_legal_moves_list(
    bb: Bitboard, player_id: Optional[PlayerId] = None
) -> List[Move]:
    """
    Generate all legal moves as a flat list (for backward compatibility).

    Args:
        bb: Current game state bitboard
        player_id: Optional player ID to validate against current turn

    Returns:
        List of all legal moves for the current player
    """
    _, moves_by_shape = generate_legal_moves(bb, player_id)

    # Flatten the moves from all shapes into a single list
    all_moves = []
    for shape_moves in moves_by_shape.values():
        all_moves.extend(shape_moves)

    return all_moves


def count_pieces_by_player_shape(bb: Bitboard) -> tuple[List[int], List[int]]:
    """
    Count pieces by player and shape for analysis.

    Returns:
        Tuple of (player0_counts, player1_counts) where each is [A_count, B_count, C_count, D_count]
    """
    player0_counts = [bb[shape].bit_count() for shape in range(4)]
    player1_counts = [bb[shape + 4].bit_count() for shape in range(4)]
    return player0_counts, player1_counts
