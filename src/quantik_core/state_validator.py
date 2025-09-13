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

ShapesMap = Tuple[int, int, int, int]  # Counts of shapes A, B, C, D


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
def _count_pieces_by_shape(bb: Bitboard) -> Tuple[ShapesMap, ShapesMap]:
    """
    Count pieces for each shape for each player.

    Returns:
        Tuple of (player0_counts, player1_counts) where each is a tuple of 4 ints
        representing count of shapes A, B, C, D respectively.
    """
    # Use tuple comprehension for better memory efficiency
    player0_counts = tuple(bb[shape].bit_count() for shape in range(4))
    player1_counts = tuple(bb[4 + shape].bit_count() for shape in range(4))

    return player0_counts, player1_counts


def count_pieces_by_shape(
    state: State,
) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    """Public interface for counting pieces by shape."""
    return _count_pieces_by_shape(state.bb)


@lru_cache(maxsize=2048)
def _validate_piece_counts_fast(bb: Bitboard) -> ValidationResult:
    """
    Fast validation that no player exceeds the maximum number of pieces per shape.
    Uses bitwise operations and avoids intermediate allocations.
    """
    # Check all shapes in single pass using bit counting
    for shape in range(4):
        if bb[shape].bit_count() > MAX_PIECES_PER_SHAPE:
            return ValidationResult.SHAPE_COUNT_EXCEEDED
        if bb[4 + shape].bit_count() > MAX_PIECES_PER_SHAPE:
            return ValidationResult.SHAPE_COUNT_EXCEEDED

    return ValidationResult.OK


def validate_piece_counts(state: State) -> ValidationResult:
    """
    Validate that no player exceeds the maximum number of pieces per shape.

    Rule: Each player can have at most 2 pieces of each shape (A, B, C, D).

    Args:
        state: The game state to validate

    Returns:
        ValidationResult.OK if valid, ValidationResult.SHAPE_COUNT_EXCEEDED otherwise
    """
    return _validate_piece_counts_fast(state.bb)


@lru_cache(maxsize=2048)
def _validate_turn_balance_fast(
    bb: Bitboard,
) -> Tuple[Optional[PlayerId], ValidationResult]:
    """
    Fast validation of turn balance using bitwise operations.
    """
    # Calculate total pieces for each player using bit counting
    total0 = sum(bb[shape].bit_count() for shape in range(4))
    total1 = sum(bb[4 + shape].bit_count() for shape in range(4))

    difference = total0 - total1

    if difference == 0:
        return 0, ValidationResult.OK
    elif difference == 1:
        return 1, ValidationResult.OK
    else:
        return None, ValidationResult.TURN_BALANCE_INVALID


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
    return _validate_turn_balance_fast(state.bb)


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
    # Fast parameter validation using bitwise checks
    if position & ~15:  # position > 15 or position < 0
        return ValidationResult.INVALID_POSITION
    if shape & ~3:  # shape > 3 or shape < 0
        return ValidationResult.INVALID_SHAPE
    if player & ~1:  # player > 1 or player < 0
        return ValidationResult.INVALID_PLAYER

    position_mask = 1 << position

    # Fast overlap check - combine all bitboards and check at once
    all_pieces = 0
    for bb_value in state.bb:
        all_pieces |= bb_value
    if all_pieces & position_mask:
        return ValidationResult.PIECE_OVERLAP

    # Fast opponent conflict check
    opponent = 1 - player
    opponent_shape_bb = state.bb[opponent * 4 + shape]

    # Early exit if opponent has no pieces of this shape
    if not opponent_shape_bb:
        return ValidationResult.OK

    # Check for conflicts using bitwise operations
    for line_mask in WIN_MASKS:
        if (position_mask & line_mask) and (opponent_shape_bb & line_mask):
            return ValidationResult.ILLEGAL_PLACEMENT

    return ValidationResult.OK


@lru_cache(maxsize=2048)
def _validate_game_state_fast(bb: Bitboard) -> ValidationResult:
    """
    Optimized comprehensive validation of a game state using bitwise operations.

    Combines all validation checks into a single optimized pass to minimize
    function call overhead and memory allocations.
    """
    # 1. Fast piece count validation - check all shapes at once
    for shape in range(4):
        if bb[shape].bit_count() > MAX_PIECES_PER_SHAPE:
            return ValidationResult.SHAPE_COUNT_EXCEEDED
        if bb[4 + shape].bit_count() > MAX_PIECES_PER_SHAPE:
            return ValidationResult.SHAPE_COUNT_EXCEEDED

    # 2. Fast turn balance validation
    total0 = sum(bb[shape].bit_count() for shape in range(4))
    total1 = sum(bb[4 + shape].bit_count() for shape in range(4))
    difference = total0 - total1

    if not (difference == 0 or difference == 1):
        return ValidationResult.TURN_BALANCE_INVALID

    # 3. Fast overlap validation - combine all bitboards
    all_positions = 0
    for bb_value in bb:
        if all_positions & bb_value:
            return ValidationResult.PIECE_OVERLAP
        all_positions |= bb_value

    # 4. Fast placement legality validation
    for shape in range(4):
        player0_pieces = bb[shape]
        player1_pieces = bb[4 + shape]

        # Use bitwise operations to check all lines at once
        for line_mask in WIN_MASKS:
            if (player0_pieces & line_mask) and (player1_pieces & line_mask):
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
    result = _validate_game_state_fast(state.bb)

    if result != ValidationResult.OK and raise_on_error:
        error_messages = {
            ValidationResult.SHAPE_COUNT_EXCEEDED: "Shape count exceeded",
            ValidationResult.TURN_BALANCE_INVALID: "Invalid turn balance",
            ValidationResult.PIECE_OVERLAP: "Overlapping pieces detected",
            ValidationResult.ILLEGAL_PLACEMENT: "Illegal placement detected",
        }
        raise ValidationError(
            f"{error_messages.get(result, 'Validation failed')}: {result}"
        )

    return result


@lru_cache(maxsize=1024)
def _validate_placement_legality(bb: Bitboard) -> ValidationResult:
    """
    Validate that no illegal placements exist in the current state.

    Rule: A player cannot have a piece in a row, column, or zone where their opponent
    has already placed a piece of the same shape.

    Args:
        bb: The bitboard tuple to validate

    Returns:
        ValidationResult.OK if valid, ValidationResult.ILLEGAL_PLACEMENT otherwise
    """
    # Optimized: check all shapes and lines in nested loops for better cache locality
    for shape in range(4):
        player0_pieces = bb[shape]
        player1_pieces = bb[4 + shape]

        # Early exit if either player has no pieces of this shape
        if not player0_pieces or not player1_pieces:
            continue

        # Check each line (row, column, zone) for conflicts
        for line_mask in WIN_MASKS:
            if (player0_pieces & line_mask) and (player1_pieces & line_mask):
                return ValidationResult.ILLEGAL_PLACEMENT

    return ValidationResult.OK


@lru_cache(maxsize=1024)
def _validate_no_overlaps(bb: Bitboard) -> ValidationResult:
    """
    Validate that no position has multiple pieces.

    Args:
        bb: The bitboard tuple to validate

    Returns:
        ValidationResult.OK if valid, ValidationResult.PIECE_OVERLAP otherwise
    """
    # Optimized: use reduce-like approach to check overlaps
    all_positions = 0
    for bb_value in bb:
        if all_positions & bb_value:
            return ValidationResult.PIECE_OVERLAP
        all_positions |= bb_value

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
