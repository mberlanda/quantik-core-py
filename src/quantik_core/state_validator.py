"""
Comprehensive state validation for Quantik games.

This module provides validation functions to ensure game states follow all Quantik rules:
1. Position validation: No opponent pieces in same row/column/zone where you want to place
2. Piece count validation: Maximum 2 pieces per shape per player
3. Turn balance validation: Proper alternating turns starting with Player 0
"""

from typing import Optional, Tuple, List
from enum import IntEnum
from functools import lru_cache

from .core import State, Bitboard, PlayerId
from .constants import WIN_MASKS, MAX_PIECES_PER_SHAPE


class ValidationError(Exception):
    """Exception raised when game state validation fails."""

    pass


class ValidationResult(IntEnum):
    """Enumeration of validation result codes."""

    OK = 0
    TURN_BALANCE_INVALID = 1
    SHAPE_COUNT_EXCEEDED = 2
    NOT_PLAYER_TURN = 3
    ILLEGAL_PLACEMENT = 4
    PIECE_OVERLAP = 5
    INVALID_POSITION = 6
    INVALID_SHAPE = 7
    INVALID_PLAYER = 8


@lru_cache(maxsize=1024)
def _count_pieces_by_shape(bb: Bitboard) -> Tuple[List[int], List[int]]:
    """
    Count pieces for each shape for each player.

    Returns:
        Tuple of (player0_counts, player1_counts) where each is a list of 4 ints
        representing count of shapes A, B, C, D respectively.
    """
    player0_counts = []
    player1_counts = []

    for shape in range(4):
        # Count bits set in each shape's bitboard using optimized bit_count()
        count0 = bb[0 * 4 + shape].bit_count()
        count1 = bb[1 * 4 + shape].bit_count()
        player0_counts.append(count0)
        player1_counts.append(count1)

    return player0_counts, player1_counts


def count_pieces_by_shape(state: State) -> Tuple[List[int], List[int]]:
    """Public interface for counting pieces by shape."""
    return _count_pieces_by_shape(state.bb)


def validate_piece_counts(state: State) -> ValidationResult:
    """
    Validate that no player exceeds the maximum number of pieces per shape.

    Rule: Each player can have at most 2 pieces of each shape (A, B, C, D).

    Args:
        state: The game state to validate

    Returns:
        ValidationResult.OK if valid, ValidationResult.SHAPE_COUNT_EXCEEDED otherwise
    """
    player0_counts, player1_counts = count_pieces_by_shape(state)

    # Check if any player exceeds max pieces per shape
    for shape in range(4):
        if player0_counts[shape] > MAX_PIECES_PER_SHAPE:
            return ValidationResult.SHAPE_COUNT_EXCEEDED
        if player1_counts[shape] > MAX_PIECES_PER_SHAPE:
            return ValidationResult.SHAPE_COUNT_EXCEEDED

    return ValidationResult.OK


def validate_turn_balance(state: State) -> Tuple[Optional[PlayerId], ValidationResult]:
    """
    Validate turn balance and determine whose turn it is.

    Rule: Player 0 goes first, so:
    - If equal pieces: it's Player 0's turn
    - If Player 0 has 1 more: it's Player 1's turn
    - If Player 1 has 1 more: invalid state (Player 1 can't go first)
    - If difference > 1: invalid state (someone took too many turns)

    Returns:
        Tuple of (current_player, validation_result)
        current_player is None if state is invalid
    """
    player0_counts, player1_counts = count_pieces_by_shape(state)
    total0 = sum(player0_counts)
    total1 = sum(player1_counts)

    difference = total0 - total1

    if difference == 0:
        # Equal pieces, Player 0's turn
        return 0, ValidationResult.OK
    elif difference == 1:
        # Player 0 has one more, Player 1's turn
        return 1, ValidationResult.OK
    else:
        # Invalid turn balance
        return None, ValidationResult.TURN_BALANCE_INVALID


def validate_position_placement(
    state: State, position: int, shape: int, player: PlayerId
) -> ValidationResult:
    """
    Validate that a piece can be placed at the given position according to Quantik rules.

    Rule: A player cannot place a piece in a row, column, or zone where their opponent
    has already placed a piece of the same shape.

    Args:
        state: Current game state
        position: Board position (0-15)
        shape: Shape index (0=A, 1=B, 2=C, 3=D)
        player: Player making the move (0 or 1)

    Returns:
        ValidationResult indicating whether the placement is valid
    """
    if not (0 <= position <= 15):
        return ValidationResult.INVALID_POSITION
    if not (0 <= shape <= 3):
        return ValidationResult.INVALID_SHAPE
    if player not in (0, 1):
        return ValidationResult.INVALID_PLAYER

    # Check if position is already occupied by any piece
    position_mask = 1 << position
    for bb_index in range(8):  # Check all 8 bitboards
        if state.bb[bb_index] & position_mask:
            return ValidationResult.PIECE_OVERLAP

    # Get opponent's pieces of the same shape
    opponent = 1 - player
    opponent_shape_bb = state.bb[opponent * 4 + shape]

    # Check each line (row, column, zone) that contains this position
    for line_mask in WIN_MASKS:
        if position_mask & line_mask:  # This line contains our position
            # Check if opponent has same shape anywhere in this line
            if opponent_shape_bb & line_mask:
                return ValidationResult.ILLEGAL_PLACEMENT

    return ValidationResult.OK


def validate_game_state(state: State, raise_on_error: bool = False) -> ValidationResult:
    """
    Comprehensive validation of a game state.

    Checks:
    1. Piece count limits (max 2 per shape per player)
    2. Turn balance (proper alternating turns)
    3. No overlapping pieces (each position has at most one piece)
    4. No illegal placements (opponent shapes in same row/column/zone)

    Args:
        state: The game state to validate
        raise_on_error: If True, raises ValidationError on invalid state

    Returns:
        ValidationResult.OK if valid, specific error code otherwise

    Raises:
        ValidationError: If raise_on_error=True and state is invalid
    """
    # 1. Validate piece counts
    result = validate_piece_counts(state)
    if result != ValidationResult.OK:
        if raise_on_error:
            raise ValidationError(f"Shape count exceeded: {result}")
        return result

    # 2. Validate turn balance
    _, result = validate_turn_balance(state)
    if result != ValidationResult.OK:
        if raise_on_error:
            raise ValidationError(f"Invalid turn balance: {result}")
        return result

    # 3. Validate no overlapping pieces
    result = _validate_no_overlaps(state)
    if result != ValidationResult.OK:
        if raise_on_error:
            raise ValidationError(f"Overlapping pieces detected: {result}")
        return result

    # 4. Validate no illegal placements
    result = _validate_placement_legality(state)
    if result != ValidationResult.OK:
        if raise_on_error:
            raise ValidationError(f"Illegal placement detected: {result}")
        return result

    return ValidationResult.OK


def _validate_placement_legality(state: State) -> ValidationResult:
    """
    Validate that no illegal placements exist in the current state.

    Rule: A player cannot have a piece in a row, column, or zone where their opponent
    has already placed a piece of the same shape.

    Args:
        state: The game state to validate

    Returns:
        ValidationResult.OK if valid, ValidationResult.ILLEGAL_PLACEMENT otherwise
    """
    # For each shape, check that players don't have the same shape in conflicting lines
    for shape in range(4):
        player0_pieces = state.bb[0 * 4 + shape]
        player1_pieces = state.bb[1 * 4 + shape]

        # Check each line (row, column, zone)
        for line_mask in WIN_MASKS:
            # Check if both players have this shape in this line
            if (player0_pieces & line_mask) and (player1_pieces & line_mask):
                return ValidationResult.ILLEGAL_PLACEMENT

    return ValidationResult.OK


def _validate_no_overlaps(state: State) -> ValidationResult:
    """
    Validate that no position has multiple pieces.

    Args:
        state: The game state to validate

    Returns:
        ValidationResult.OK if valid, ValidationResult.PIECE_OVERLAP otherwise
    """
    # Check that no two bitboards have overlapping bits
    all_positions = 0
    for bb in state.bb:
        if all_positions & bb:  # Overlap detected
            return ValidationResult.PIECE_OVERLAP
        all_positions |= bb

    return ValidationResult.OK


def get_current_player(state: State) -> Tuple[Optional[PlayerId], ValidationResult]:
    """
    Determine whose turn it is based on the current game state.

    Args:
        state: The game state to analyze

    Returns:
        Tuple of (current_player, validation_result)
        current_player is None if state is invalid
    """
    return validate_turn_balance(state)


def validate_player_turn(state: State, expected_player: PlayerId) -> ValidationResult:
    """
    Validate that it's the expected player's turn.

    Args:
        state: The game state to validate
        expected_player: The player who is expected to move (0 or 1)

    Returns:
        ValidationResult.OK if valid, error code otherwise
    """
    if expected_player not in (0, 1):
        return ValidationResult.INVALID_PLAYER

    actual_player, err = get_current_player(state)

    if err != ValidationResult.OK:
        return err

    if actual_player != expected_player:
        return ValidationResult.NOT_PLAYER_TURN

    return ValidationResult.OK
