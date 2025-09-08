from typing import Optional, Tuple, List
from enum import IntEnum
from functools import lru_cache
from ..core import State, Bitboard, PlayerId


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
    return _count_pieces_by_shape(state.bb)


def get_current_player(state: State) -> Tuple[Optional[PlayerId], ValidationResult]:
    """
    Determine whose turn it is based on piece counts.

    Player 0 goes first, so:
    - If equal pieces: it's Player 0's turn
    - If Player 0 has 1 more: it's Player 1's turn
    - If Player 1 has 1 more: invalid state

    Returns:
        0 if it's Player 0's turn, 1 if it's Player 1's turn, None if invalid state
    """
    player0_counts, player1_counts = count_pieces_by_shape(state)
    total0 = sum(player0_counts)
    total1 = sum(player1_counts)

    if total0 == total1:
        return 0, ValidationResult.OK
    elif total0 == total1 + 1:
        return 1, ValidationResult.OK
    else:
        return None, ValidationResult.TURN_BALANCE_INVALID


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

    if err is not ValidationResult.OK:
        return err

    if actual_player != expected_player:
        return ValidationResult.NOT_PLAYER_TURN

    return ValidationResult.OK
