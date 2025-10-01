"""
Move representation and validation for Quantik game bbs.

This module provides the foundation for game state iteration, move generation,
and game tree construction by defining moves and their validation.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, cast, Union, overload, TYPE_CHECKING
from .commons import Bitboard, PlayerId, WIN_MASKS, MAX_PIECES_PER_SHAPE
from .game_utils import (
    count_pieces_by_shape_lists,
    calculate_bitboard_index,
    validate_move_parameters,
    create_position_mask,
    is_position_occupied,
)
from .state_validator import ValidationResult, _validate_game_state_single_pass

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
        new_bb: Optional[Bitboard] = None,
    ):
        self.is_valid = is_valid
        self.error = error
        self.new_bb = new_bb


@overload
def validate_move(bb: Bitboard, move: Move) -> MoveValidationResult: ...


@overload
def validate_move(bb: "CompactBitboard", move: Move) -> MoveValidationResult: ...


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
    # Convert CompactBitboard to tuple if needed for compatibility
    bb_tuple: Bitboard
    if hasattr(bb, "to_tuple") and callable(
        getattr(bb, "to_tuple", None)
    ):  # It's a CompactBitboard
        bb_tuple = bb.to_tuple()  # type: ignore[union-attr]
    else:
        bb_tuple = bb  # type: ignore[assignment]

    # Check if it's the player's turn
    current_player, validation_result = _validate_game_state_single_pass(bb_tuple)
    if validation_result != ValidationResult.OK:
        return MoveValidationResult(False, validation_result)

    if current_player != move.player:
        return MoveValidationResult(False, ValidationResult.NOT_PLAYER_TURN)

    # Check if position is empty
    if is_position_occupied(cast(Bitboard, bb_tuple), move.position):
        return MoveValidationResult(False, ValidationResult.PIECE_OVERLAP)

    # Create new state with the move applied
    lst_bb = list(bb_tuple)
    bitboard_index = calculate_bitboard_index(move.player, move.shape)
    position_mask = create_position_mask(move.position)
    lst_bb[bitboard_index] |= position_mask

    # Validate the new bitboard representation
    new_bb: Bitboard = cast(Bitboard, tuple(lst_bb))
    _, new_validation_result = _validate_game_state_single_pass(new_bb)

    if new_validation_result != ValidationResult.OK:
        return MoveValidationResult(False, new_validation_result)

    return MoveValidationResult(True, None, new_bb)


@overload
def apply_move(bb: Bitboard, move: Move) -> Bitboard: ...


@overload
def apply_move(bb: "CompactBitboard", move: Move) -> "CompactBitboard": ...


def apply_move(
    bb: Union[Bitboard, "CompactBitboard"], move: Move
) -> Union[Bitboard, "CompactBitboard"]:
    """
    Apply a move to a bb, returning the new bb.

    This function assumes the move is valid. Use validate_move() first if unsure.

    Args:
        bb: Current game Bitboard (tuple or CompactBitboard)
        move: Move to apply

    Returns:
        New state with the move applied (same type as input)
    """
    bitboard_index = calculate_bitboard_index(move.player, move.shape)
    position_mask = create_position_mask(move.position)

    # Handle CompactBitboard
    if hasattr(bb, "apply_move_functional"):  # It's a CompactBitboard
        return bb.apply_move_functional(move.player, move.shape, move.position)  # type: ignore

    # Handle regular tuple bitboard
    return cast(
        Bitboard,
        (
            bb[:bitboard_index]
            + (bb[bitboard_index] | position_mask,)
            + bb[bitboard_index + 1 :]
        ),
    )


@overload
def generate_legal_moves(
    bb: Bitboard, player_id: Optional[PlayerId] = None
) -> tuple[PlayerId, Dict[int, List[Move]]]: ...


@overload
def generate_legal_moves(
    bb: "CompactBitboard", player_id: Optional[PlayerId] = None
) -> tuple[PlayerId, Dict[int, List[Move]]]: ...


def generate_legal_moves(
    bb: Union[Bitboard, "CompactBitboard"], player_id: Optional[PlayerId] = None
) -> tuple[PlayerId, Dict[int, List[Move]]]:
    """
    Generate all legal moves for the current player in the given state.

    This function applies all Quantik game constraints:
    1. Maximum 2 pieces per shape per player
    2. Cannot place same shape on same line (row/column/zone) as opponent
    3. Position must be empty
    4. Must be player's turn

    Args:
        bb: Current game bitboard (tuple or CompactBitboard)
        player_id: Optional player ID to validate against current turn

    Returns:
        Tuple of (current_player, moves_by_shape) where moves_by_shape is
        a dict with keys 0-3 (shapes A-D) and values as lists of legal moves
    """
    # Convert CompactBitboard to tuple if needed for compatibility
    bb_tuple: Bitboard
    if hasattr(bb, "to_tuple") and callable(
        getattr(bb, "to_tuple", None)
    ):  # It's a CompactBitboard
        bb_tuple = bb.to_tuple()  # type: ignore[union-attr]
    else:
        bb_tuple = bb  # type: ignore[assignment]

    # First, determine whose turn it is
    current_player, validation_result = _validate_game_state_single_pass(bb_tuple)
    if validation_result != ValidationResult.OK or current_player is None:
        return 0, {}  # Invalid state, no legal moves

    # If player_id is specified, validate it matches current turn
    if player_id is not None and player_id != current_player:
        return current_player, {}  # Wrong player, no legal moves

    moves_by_shape: Dict[int, List[Move]] = {0: [], 1: [], 2: [], 3: []}  # A, B, C, D

    # Count existing pieces for current player by shape (for max pieces constraint)
    current_shape_counts = [
        bb_tuple[calculate_bitboard_index(current_player, shape)].bit_count()
        for shape in range(4)
    ]

    # For each shape that the player can still place
    for shape in range(4):
        if current_shape_counts[shape] >= MAX_PIECES_PER_SHAPE:
            continue  # Player already has max pieces of this shape

        # Get opponent's pieces of the same shape
        opponent_shape_bits = bb_tuple[
            calculate_bitboard_index(1 - current_player, shape)
        ]

        # For each position on the board
        for position in range(16):
            # Check if position is already occupied
            if is_position_occupied(cast(Bitboard, bb_tuple), position):
                continue

            position_mask = create_position_mask(position)

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
    return count_pieces_by_shape_lists(bb)
