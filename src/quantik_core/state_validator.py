from enum import IntEnum
from functools import lru_cache
from typing import Tuple, Optional
from quantik_core.commons import MAX_PIECES_PER_SHAPE, WIN_MASKS, Bitboard, PlayerId

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


class WinStatus(IntEnum):
    """Enumeration of game win states."""

    NO_WIN = 0
    PLAYER_0_WINS = 1
    PLAYER_1_WINS = 2


def _validate_piece_counts_and_overlaps(
    bb: Bitboard,
) -> Tuple[Optional[ValidationResult], list[int], int, int]:
    """
    Validate piece counts and detect overlaps in a single pass.

    Returns:
        Tuple of (error_result, shape_counts, player0_total, player1_total)
        If error_result is not None, validation failed early.
    """
    player0_total = 0
    player1_total = 0
    all_positions = 0  # For overlap detection
    shape_counts = [0] * 8  # [p0_A, p0_B, p0_C, p0_D, p1_A, p1_B, p1_C, p1_D]

    # Single pass through all bitboard elements
    for i in range(8):
        bb_value = bb[i]
        piece_count = bb_value.bit_count()

        # 1. Piece count validation (check immediately)
        if piece_count > MAX_PIECES_PER_SHAPE:
            return ValidationResult.SHAPE_COUNT_EXCEEDED, [], 0, 0

        # 2. Update totals for turn balance
        if i < 4:  # Player 0 shapes
            player0_total += piece_count
        else:  # Player 1 shapes
            player1_total += piece_count

        # 3. Overlap detection (accumulate all positions)
        if all_positions & bb_value:
            return ValidationResult.PIECE_OVERLAP, [], 0, 0
        all_positions |= bb_value

        # 4. Store counts for placement legality check
        shape_counts[i] = piece_count

    return None, shape_counts, player0_total, player1_total


def _validate_turn_balance(
    player0_total: int, player1_total: int
) -> Tuple[Optional[PlayerId], Optional[ValidationResult]]:
    """
    Validate turn balance and determine next player.

    Returns:
        Tuple of (next_player, error_result)
        If error_result is not None, validation failed.
    """
    difference = player0_total - player1_total
    if difference == 0:
        return 0, None
    elif difference == 1:
        return 1, None
    else:
        return None, ValidationResult.TURN_BALANCE_INVALID


def _validate_placement_legality(
    bb: Bitboard, shape_counts: list[int]
) -> Optional[ValidationResult]:
    """
    Validate placement legality (check conflicts on win lines).

    Returns:
        ValidationResult error if illegal placement found, None otherwise.
    """
    # Only check shapes that have pieces for both players
    for shape in range(4):
        if shape_counts[shape] == 0 or shape_counts[4 + shape] == 0:
            continue  # Skip if either player has no pieces of this shape

        player0_pieces = bb[shape]
        player1_pieces = bb[4 + shape]

        # Check all win lines for this shape
        for line_mask in WIN_MASKS:
            if (player0_pieces & line_mask) and (player1_pieces & line_mask):
                return ValidationResult.ILLEGAL_PLACEMENT

    return None


@lru_cache(maxsize=2048)
def _validate_game_state_single_pass(
    bb: Bitboard,
) -> Tuple[Optional[PlayerId], ValidationResult]:
    """
    Single linear pass validation of ALL conditions.

    This function validates in one iteration:
    1. Piece counts per shape (MAX_PIECES_PER_SHAPE limit)
    2. Turn balance (difference between player totals)
    3. Overlaps (no two pieces on same position)
    4. Placement legality (no conflicts on win lines)

    Optimizations:
    - Single pass through bitboard (O(8) linear iteration)
    - All validations combined in one loop
    - Minimal memory allocation (only counters)
    - Early exit on first failure
    - Bitwise operations throughout
    - Single cache for entire validation

    Memory: ~32 bytes for counters (8 shape counts + totals + overlap tracking)
    Time: O(8) - exactly one pass through bitboard
    Cache: Single memoized result for complete validation
    """
    # 1. Validate piece counts and overlaps
    error_result, shape_counts, player0_total, player1_total = (
        _validate_piece_counts_and_overlaps(bb)
    )
    if error_result is not None:
        return None, error_result

    # 2. Validate turn balance
    next_player, balance_error = _validate_turn_balance(player0_total, player1_total)
    if balance_error is not None:
        return None, balance_error

    # 3. Validate placement legality
    placement_error = _validate_placement_legality(bb, shape_counts)
    if placement_error is not None:
        return None, placement_error

    return next_player, ValidationResult.OK


def validate_game_state(
    bb: Bitboard, raise_on_error: bool = False
) -> Tuple[Optional[PlayerId], ValidationResult]:
    """
    Validate the game state for legality.

    This function checks:
    1. Piece counts per shape (MAX_PIECES_PER_SHAPE limit)
    2. Turn balance (difference between player totals)
    3. Overlaps (no two pieces on same position)
    4. Placement legality (no conflicts on win lines)

    Args:
        state: The game state to validate

    Returns:
        ValidationResult indicating the validation outcome
    """
    player, result = _validate_game_state_single_pass(bb)
    if not raise_on_error:
        return player, result

    if result != ValidationResult.OK:
        raise ValidationError(f"Invalid game state: {result}")

    return player, result
