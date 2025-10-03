"""
Legacy validation module - now delegates to state_validator for core validation logic.

This module maintains backward compatibility while using the new comprehensive
state validation system.
"""

from ..game_utils import (
    WinStatus,
    check_game_winner as _check_game_winner,
    has_winning_line as bb_has_winning_line,
    is_game_over as _is_game_over,
)
from ..core import Bitboard, State


def bb_check_game_winner(bb: Bitboard) -> WinStatus:
    """
    Check if the game has been won and determine the winner.
    """
    return _check_game_winner(bb)


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
    return _check_game_winner(state.bb)


def is_game_over(state: State) -> bool:
    """
    Check if the game is over (someone has won).

    Args:
        state: The game state to check

    Returns:
        True if the game is over, False otherwise
    """
    return _is_game_over(state.bb)
