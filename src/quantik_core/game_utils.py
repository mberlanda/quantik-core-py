"""
Common game utilities for piece counting, endgame detection, and state analysis.

This module provides consolidated functions that were previously duplicated
across move.py, board.py, plugins/validation.py, and plugins/endgame.py.
"""

from enum import IntEnum
from functools import lru_cache
from typing import List, Tuple
from .commons import Bitboard, WIN_MASKS


class WinStatus(IntEnum):
    """Enumeration of game win states."""

    NO_WIN = 0
    PLAYER_0_WINS = 1
    PLAYER_1_WINS = 2


@lru_cache(maxsize=1024)
def count_pieces_by_shape(bb: Bitboard) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """
    Count pieces for each shape for each player.

    This is the consolidated implementation that replaces:
    - move.count_pieces_by_player_shape()
    - plugins.validation._count_pieces_by_shape()
    - Various inline implementations in board.py

    Args:
        bb: Bitboard tuple representing game state

    Returns:
        Tuple of (player0_counts, player1_counts) where each is a tuple of 4 ints
        representing count of shapes A, B, C, D respectively.

    Example:
        >>> bb = (1, 2, 0, 0, 4, 0, 0, 0)  # Player 0: 1 A, 1 B; Player 1: 1 A
        >>> count_pieces_by_shape(bb)
        ((1, 1, 0, 0), (1, 0, 0, 0))
    """
    player0_counts = tuple(bb[shape].bit_count() for shape in range(4))
    player1_counts = tuple(bb[4 + shape].bit_count() for shape in range(4))
    return (player0_counts, player1_counts)


def count_pieces_by_shape_lists(bb: Bitboard) -> Tuple[List[int], List[int]]:
    """
    Count pieces for each shape for each player, returning lists.

    This variant returns lists instead of tuples for cases where
    mutability is needed (like in move.py).

    Args:
        bb: Bitboard tuple representing game state

    Returns:
        Tuple of (player0_counts, player1_counts) where each is a list of 4 ints
        representing count of shapes A, B, C, D respectively.
    """
    player0_counts = [bb[shape].bit_count() for shape in range(4)]
    player1_counts = [bb[shape + 4].bit_count() for shape in range(4)]
    return player0_counts, player1_counts


def count_total_pieces(bb: Bitboard) -> Tuple[int, int]:
    """
    Count total pieces for each player.

    Args:
        bb: Bitboard tuple representing game state

    Returns:
        Tuple of (player0_total, player1_total)
    """
    player0_counts, player1_counts = count_pieces_by_shape(bb)
    return sum(player0_counts), sum(player1_counts)


def count_player_shape_pieces(bb: Bitboard, player: int, shape: int) -> int:
    """
    Count pieces for a specific player and shape.

    Args:
        bb: Bitboard tuple representing game state
        player: Player ID (0 or 1)
        shape: Shape ID (0=A, 1=B, 2=C, 3=D)

    Returns:
        Number of pieces of the specified shape for the specified player
    """
    bitboard_index = shape if player == 0 else shape + 4
    return bb[bitboard_index].bit_count()


# ===== ENDGAME DETECTION UTILITIES =====


def has_winning_line(bb: Bitboard) -> bool:
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

    This is the consolidated implementation that replaces:
    - plugins.endgame.bb_has_winning_line()

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


def check_game_winner(bb: Bitboard) -> WinStatus:
    """
    Check if the game has been won and determine the winner.

    Uses the endgame utility to detect if there's a winning line, then infers
    the winner based on turn balance (who made the last move).
    There are some edge cases that may need to be handled such as:
    ABCD/..../cd../..ab => anaylising this state will return player 1 wins
    because both players have 4 pieces, but actually player 0 made the winning move

    This is the consolidated implementation that replaces:
    - plugins.validation.bb_check_game_winner()

    Args:
        bb: The bitboard representation of the game state

    Returns:
        WinStatus indicating the game result (NO_WIN, PLAYER_0_WINS, PLAYER_1_WINS)
    """
    if not has_winning_line(bb):
        return WinStatus.NO_WIN

    player0_counts, player1_counts = count_pieces_by_shape(bb)
    total0 = sum(player0_counts)
    total1 = sum(player1_counts)

    if total0 > total1:
        return WinStatus.PLAYER_0_WINS
    else:
        return WinStatus.PLAYER_1_WINS


def is_game_over(bb: Bitboard) -> bool:
    """
    Check if the game is over (someone has won).

    This is the consolidated implementation that replaces:
    - plugins.validation.is_game_over()

    Args:
        bb: The bitboard representation of the game state

    Returns:
        True if the game is over, False otherwise
    """
    return check_game_winner(bb) != WinStatus.NO_WIN
