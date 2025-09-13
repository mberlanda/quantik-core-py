from ..core import Bitboard, State
from ..constants import WIN_MASKS


def _has_winning_line(bb: Bitboard) -> bool:
    """
    Check if there is a winning line (row, column, or 2×2 zone) with all four
    different shapes (A, B, C, D).

    Colors don't matter for winning - only the presence of all four shapes in a line.

    Examples of valid wins in row 0:
    - ABCD (all Player 0)
    - abcd (all Player 1)
    - AbCd (mixed players)
    - aBcD (mixed players)
    - etc.

    Args:
        bb: The bitboard representation of the game state

    Returns:
        True if there is a winning line, False otherwise
    """
    # Precompute shape unions (combine both players for each shape)
    shape_unions = [
        bb[shape] | bb[shape + 4]  # Player 0 and Player 1 for each shape
        for shape in range(4)
    ]

    # Check each possible win line (row, column, or zone)
    for mask in WIN_MASKS:
        # Check if all 4 shapes are present in this line using bitwise operations
        if all(shape_union & mask for shape_union in shape_unions):
            return True

    return False


def has_winning_line(state: State) -> bool:
    return _has_winning_line(state.bb)
