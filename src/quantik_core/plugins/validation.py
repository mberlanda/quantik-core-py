"""
Legacy validation module - now delegates to state_validator for core validation logic.

This module maintains backward compatibility while using the new comprehensive
state validation system.
"""

from enum import IntEnum
from functools import lru_cache
from typing import Tuple
from ..core import Bitboard, State
from .endgame import has_winning_line


class WinStatus(IntEnum):
    """Enumeration of game win states."""

    NO_WIN = 0
    PLAYER_0_WINS = 1
    PLAYER_1_WINS = 2


@lru_cache(maxsize=1024)
def _count_pieces_by_shape(bb: Bitboard) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """
    Count pieces for each shape for each player.

    Returns:
        Tuple of (player0_counts, player1_counts) where each is a tuple of 4 ints
        representing count of shapes A, B, C, D respectively.
    """
    # Use tuple comprehension for better memory efficiency
    player0_counts = tuple(bb[shape].bit_count() for shape in range(4))
    player1_counts = tuple(bb[4 + shape].bit_count() for shape in range(4))

    return (player0_counts, player1_counts)


def count_pieces_by_shape(
    state: State,
) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """Public interface for counting pieces by shape."""
    return _count_pieces_by_shape(state.bb)


def check_game_winner(state: State) -> WinStatus:
    """
    Check if the game has been won and determine the winner.

    Uses the endgame utility to detect if there's a winning line, then infers
    the winner based on turn balance (who made the last move).
    There are some edge cases that may need to be handled such as:
    ABCD/..../cd../..ab => anaylising this state will return player 1 wins
    because both players have 4 pieces, but actually player 0 made the winning move

    Args:
        state: The game state to check for win conditions

    Returns:
        WinStatus indicating the game result (NO_WIN, PLAYER_0_WINS, PLAYER_1_WINS)
    """
    if not has_winning_line(state):
        return WinStatus.NO_WIN

    # There's a winning line, determine who won based on turn balance
    player0_counts, player1_counts = count_pieces_by_shape(state)
    total0 = sum(player0_counts)
    total1 = sum(player1_counts)

    if total0 > total1:
        # Player 0 has more pieces, so they made the winning move
        return WinStatus.PLAYER_0_WINS
    else:
        # Player 1 has more pieces, so they made the winning move
        return WinStatus.PLAYER_1_WINS


def is_game_over(state: State) -> bool:
    """
    Check if the game is over (someone has won).

    Args:
        state: The game state to check

    Returns:
        True if the game is over, False otherwise
    """
    return check_game_winner(state) != WinStatus.NO_WIN
