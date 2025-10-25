"""
Move utilities and validation for Quantik game.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Union, TYPE_CHECKING, cast

from .commons import Bitboard, PlayerId, WIN_MASKS, MAX_PIECES_PER_SHAPE
from .game_utils import (
    calculate_bitboard_index,
    validate_move_parameters,
    create_position_mask,
    is_position_occupied,
)
from .state_validator import (
    ValidationResult,
    _validate_game_state_single_pass,
)

if TYPE_CHECKING:
    from .memory.bitboard_compact import CompactBitboard


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
        validate_move_parameters(self.player, self.shape, self.position)


class MoveValidationResult:
    """
    Result of move validation containing both success/failure and the new state.
    """

    def __init__(
        self,
        is_valid: bool,
        error: Optional[ValidationResult] = None,
        new_bb: Optional[Union[Bitboard, "CompactBitboard"]] = None,
    ):
        self.is_valid = is_valid
        self.error = error
        self.new_bb = new_bb


def validate_move(
    bb: Union[Bitboard, "CompactBitboard"], move: Move
) -> MoveValidationResult:
    """
    Validate if a move can be applied to the given state.

    This function checks:
    1. If it's the player's turn
    2. If the position is empty
    3. If the resulting bitboard would be valid

    Args:
        bb: Current game bitboard (tuple or CompactBitboard)
        move: Move to validate

    Returns:
        MoveValidationResult with validation outcome and potentially new state
    """
    from .memory.bitboard_compact import CompactBitboard

    # Convert CompactBitboard to tuple if needed for compatibility
    bb_tuple: Bitboard
    if isinstance(bb, CompactBitboard):
        bb_tuple = bb.to_tuple()
    else:
        bb_tuple = bb

    # Check if it's the player's turn
    current_player, validation_result = _validate_game_state_single_pass(bb_tuple)
    if validation_result != ValidationResult.OK:
        return MoveValidationResult(False, validation_result)

    if current_player != move.player:
        return MoveValidationResult(False, ValidationResult.NOT_PLAYER_TURN)

    # Check if position is empty
    if isinstance(bb, CompactBitboard):
        position_occupied = bb.is_position_occupied(move.position)
    else:
        position_occupied = is_position_occupied(bb_tuple, move.position)

    if position_occupied:
        return MoveValidationResult(False, ValidationResult.PIECE_OVERLAP)

    # Apply move using appropriate method
    result_bb: Union[Bitboard, "CompactBitboard"]
    if isinstance(bb, CompactBitboard):
        new_bb = bb.apply_move_functional(move.player, move.shape, move.position)
        new_bb_tuple = new_bb.to_tuple()
        result_bb = new_bb  # Return the CompactBitboard
    else:  # Regular tuple bitboard
        lst_bb = list(bb_tuple)
        bitboard_index = calculate_bitboard_index(move.player, move.shape)
        position_mask = create_position_mask(move.position)
        lst_bb[bitboard_index] |= position_mask
        result_bb_tuple: Bitboard = (
            lst_bb[0],
            lst_bb[1],
            lst_bb[2],
            lst_bb[3],
            lst_bb[4],
            lst_bb[5],
            lst_bb[6],
            lst_bb[7],
        )
        new_bb_tuple = result_bb_tuple
        result_bb = result_bb_tuple  # Return the tuple

    # Validate the new bitboard representation
    _, new_validation_result = _validate_game_state_single_pass(new_bb_tuple)

    if new_validation_result != ValidationResult.OK:
        return MoveValidationResult(False, new_validation_result)

    return MoveValidationResult(True, None, result_bb)


def apply_move(
    bb: Union[Bitboard, "CompactBitboard"], move: Move
) -> Union[Bitboard, "CompactBitboard"]:
    """
    Apply a move to a bitboard, returning the new bitboard.

    This function assumes the move is valid. Use validate_move() first if unsure.

    Args:
        bb: Current game Bitboard (tuple or CompactBitboard)
        move: Move to apply

    Returns:
        New state with the move applied (same type as input)
    """
    from .memory.bitboard_compact import CompactBitboard

    # Handle CompactBitboard with optimized method
    if isinstance(bb, CompactBitboard):
        return bb.apply_move_functional(move.player, move.shape, move.position)

    # Handle regular tuple bitboard
    bitboard_index = calculate_bitboard_index(move.player, move.shape)
    position_mask = create_position_mask(move.position)
    return cast(
        Bitboard,
        (
            bb[:bitboard_index]
            + (bb[bitboard_index] | position_mask,)
            + bb[bitboard_index + 1 :]
        ),
    )


def _is_move_legal_on_position(
    position: int,
    shape: int,
    opponent_shape_bits: int,
    bb: Union[Bitboard, "CompactBitboard"],
    bb_tuple: Bitboard,
) -> bool:
    """Check if a move is legal at a specific position."""
    from .memory.bitboard_compact import CompactBitboard

    # Check if position is already occupied
    if isinstance(bb, CompactBitboard):
        position_occupied = bb.is_position_occupied(position)
    else:
        position_occupied = is_position_occupied(bb_tuple, position)

    if position_occupied:
        return False

    position_mask = create_position_mask(position)

    # Check if this position conflicts with opponent's same shape on any win line
    for win_mask in WIN_MASKS:
        # If this position is on a win line that has opponent's same shape, illegal
        if (position_mask & win_mask) and (opponent_shape_bits & win_mask):
            return False

    return True


def generate_legal_moves(
    bb: Union[Bitboard, "CompactBitboard"], player_id: Optional[PlayerId] = None
) -> tuple[PlayerId, Dict[int, List[Move]]]:
    """
    Generate all legal moves for the current player.

    Args:
        bb: Current game Bitboard (tuple or CompactBitboard)
        player_id: Optional player ID to validate (if None, uses current turn)

    Returns:
        Tuple of (current_player, moves_by_shape) where moves_by_shape is
        a dict with keys 0-3 (shapes A-D) and values as lists of legal moves
    """
    from .memory.bitboard_compact import CompactBitboard

    # Convert CompactBitboard to tuple if needed for compatibility
    bb_tuple: Bitboard
    if isinstance(bb, CompactBitboard):
        bb_tuple = bb.to_tuple()
    else:
        bb_tuple = bb

    # First, determine whose turn it is
    current_player, validation_result = _validate_game_state_single_pass(bb_tuple)
    if validation_result != ValidationResult.OK or current_player is None:
        return 0, {}  # Invalid state, no legal moves

    # If player_id is specified, validate it matches current turn
    if player_id is not None and player_id != current_player:
        return current_player, {}  # Wrong player, no legal moves

    moves_by_shape: Dict[int, List[Move]] = {0: [], 1: [], 2: [], 3: []}  # A, B, C, D

    # Count existing pieces for current player by shape (for max pieces constraint)
    # Use optimized access for CompactBitboard if available
    if hasattr(bb, "__getitem__"):  # CompactBitboard with fast indexing
        current_shape_counts = [
            bb[calculate_bitboard_index(current_player, shape)].bit_count()
            for shape in range(4)
        ]
    else:
        current_shape_counts = [
            bb_tuple[calculate_bitboard_index(current_player, shape)].bit_count()
            for shape in range(4)
        ]

    # For each shape that the player can still place
    for shape in range(4):
        if current_shape_counts[shape] >= MAX_PIECES_PER_SHAPE:
            continue  # Player already has max pieces of this shape

        # Get opponent's pieces of the same shape using optimized access if available
        if isinstance(bb, CompactBitboard):
            opponent_shape_bits = bb[
                calculate_bitboard_index(1 - current_player, shape)
            ]
        else:
            opponent_shape_bits = bb_tuple[
                calculate_bitboard_index(1 - current_player, shape)
            ]

        # For each position on the board
        for position in range(16):
            if _is_move_legal_on_position(
                position, shape, opponent_shape_bits, bb, bb_tuple
            ):
                moves_by_shape[shape].append(Move(current_player, shape, position))

    return current_player, moves_by_shape


def generate_legal_moves_list(
    bb: Union[Bitboard, "CompactBitboard"], player_id: Optional[PlayerId] = None
) -> List[Move]:
    """
    Generate all legal moves as a flat list (for backward compatibility).

    Args:
        bb: Current game state bitboard (tuple or CompactBitboard)
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
