"""
Legacy validation module - now delegates to state_validator for core validation logic.

This module maintains backward compatibility while using the new comprehensive
state validation system.
"""

from typing import Optional, Tuple, List
from enum import IntEnum
from ..core import State, PlayerId
from .endgame import has_winning_line
from ..state_validator import (
    ValidationResult, 
    count_pieces_by_shape, 
    get_current_player,
    validate_player_turn
)


class WinStatus(IntEnum):
    """Enumeration of game win states."""

    NO_WIN = 0
    PLAYER_0_WINS = 1
    PLAYER_1_WINS = 2


def check_game_winner(state: State) -> WinStatus:
    """
    Check if the game has been won and determine the winner.

    Uses the endgame utility to detect if there's a winning line, then infers
    the winner based on turn balance (who made the last move).

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
    elif total1 > total0:
        # Player 1 has more pieces, so they made the winning move
        return WinStatus.PLAYER_1_WINS
    else:
        # Equal pieces - this means the game ended on Player 0's turn
        # (since Player 0 goes first)
        return WinStatus.PLAYER_0_WINS


def is_game_over(state: State) -> bool:
    """
    Check if the game is over (someone has won).

    Args:
        state: The game state to check

    Returns:
        True if the game is over, False otherwise
    """
    return check_game_winner(state) != WinStatus.NO_WIN
