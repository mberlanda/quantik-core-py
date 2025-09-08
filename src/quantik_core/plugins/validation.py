from typing import Tuple, List
from enum import IntEnum
from ..core import State

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

def count_pieces_by_shape(state: State) -> Tuple[List[int], List[int]]:
    """
    Count pieces for each shape for each player.
    
    Returns:
        Tuple of (player0_counts, player1_counts) where each is a list of 4 ints
        representing count of shapes A, B, C, D respectively.
    """
    player0_counts = []
    player1_counts = []
    
    for shape in range(4):
        # Count bits set in each shape's bitboard
        count0 = bin(state.bb[0 * 4 + shape]).count('1')
        count1 = bin(state.bb[1 * 4 + shape]).count('1')
        player0_counts.append(count0)
        player1_counts.append(count1)
    
    return player0_counts, player1_counts

