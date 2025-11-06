"""
Consolidated game utilities for Quantik.

This module serves as the central hub for shared game functionality,
eliminating duplication across the codebase while maintaining full
backward compatibility.
"""

from functools import lru_cache
from enum import IntEnum
from typing import List, Tuple
from .commons import Bitboard, WIN_MASKS


# ===== GAME CONSTANTS =====

# Player identifiers - consolidated from scattered definitions
PLAYER_0 = 0
PLAYER_1 = 1
TOTAL_PLAYERS = 2

# Common board states
EMPTY_BOARD_QFEN = "..../..../..../...."

# Shape and piece limits
SHAPES_PER_PLAYER = 4
TOTAL_SHAPES = 8  # 4 shapes * 2 players
BOARD_SIZE = 16  # 4x4 grid
TOTAL_POSITIONS = 16  # Total positions on the board
MAX_PIECES_PER_SHAPE = 2  # Maximum pieces per shape per player


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
    - board.get_player_inventory() / board.get_remaining_pieces()
    - state_validator._validate_piece_counts_and_overlaps()
    - Various scattered piece counting logic across files

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
    player0_counts = tuple(bb[shape].bit_count() for shape in range(SHAPES_PER_PLAYER))
    player1_counts = tuple(
        bb[shape + SHAPES_PER_PLAYER].bit_count() for shape in range(SHAPES_PER_PLAYER)
    )
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
    player0_counts = [bb[shape].bit_count() for shape in range(SHAPES_PER_PLAYER)]
    player1_counts = [
        bb[shape + SHAPES_PER_PLAYER].bit_count() for shape in range(SHAPES_PER_PLAYER)
    ]
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
    bitboard_index = calculate_bitboard_index(player, shape)
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

    This is the consolidated implementation for checking winning lines.

    Args:
        bb: The bitboard representation of the game state

    Returns:
        True if there is a winning line, False otherwise
    """
    # Precompute shape unions (combine both players for each shape)
    shape_unions = [
        bb[shape]
        | bb[shape + SHAPES_PER_PLAYER]  # Player 0 and Player 1 for each shape
        for shape in range(SHAPES_PER_PLAYER)
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

    This is the consolidated implementation for determining game winners.

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

    Args:
        bb: The bitboard representation of the game state

    Returns:
        True if the game is over, False otherwise
    """
    return check_game_winner(bb) != WinStatus.NO_WIN


# ===== VALIDATION UTILITIES =====


def get_current_player_from_counts(player0_total: int, player1_total: int) -> int:
    """
    Determine current player based on piece counts.

    This is the consolidated implementation that replaces:
    - state_validator._validate_turn_balance() logic
    - Various manual calculations across files

    Args:
        player0_total: Total pieces for player 0
        player1_total: Total pieces for player 1

    Returns:
        Current player (0 or 1)

    Raises:
        ValueError: If piece counts indicate invalid game state
    """
    diff = player0_total - player1_total

    if diff == 0:
        return PLAYER_0  # Player 0 goes first when counts are equal
    elif diff == 1:
        return PLAYER_1  # Player 1's turn after Player 0 moved
    else:
        raise ValueError(
            f"Invalid turn balance: P0={player0_total}, P1={player1_total}"
        )


def validate_piece_counts(bb: Bitboard) -> bool:
    """
    Validate that piece counts don't exceed limits.

    This is the consolidated implementation that replaces:
    - state_validator._validate_piece_counts_and_overlaps() piece count logic
    - Various inline checks across files

    Args:
        bb: Bitboard to validate

    Returns:
        True if all piece counts are valid, False otherwise
    """
    for shape in range(TOTAL_SHAPES):
        if bb[shape].bit_count() > MAX_PIECES_PER_SHAPE:
            return False
    return True


def calculate_bitboard_index(player: int, shape: int) -> int:
    """
    Calculate bitboard index for a player's shape.

    This is the consolidated implementation that replaces:
    - Various manual player * 4 + shape calculations
    - Scattered index computations across files

    Args:
        player: Player ID (0 or 1)
        shape: Shape ID (0-3 for A, B, C, D)

    Returns:
        Bitboard index (0-7)

    Raises:
        ValueError: If player or shape is invalid
    """
    if player not in (0, 1):
        raise ValueError(f"Invalid player {player}, must be 0 or 1")
    if shape not in range(SHAPES_PER_PLAYER):
        raise ValueError(f"Invalid shape {shape}, must be 0-{SHAPES_PER_PLAYER - 1}")

    return player * SHAPES_PER_PLAYER + shape


# ============================================================================
# Validation Utilities
# ============================================================================


def validate_player(player: int) -> None:
    """Validate player parameter.

    Args:
        player: Player ID to validate

    Raises:
        ValueError: If player is invalid
    """
    if player not in (0, 1):
        raise ValueError(f"Invalid player: {player}")


def validate_shape(shape: int) -> None:
    """Validate shape parameter.

    Args:
        shape: Shape ID to validate

    Raises:
        ValueError: If shape is invalid
    """
    if shape not in range(SHAPES_PER_PLAYER):
        raise ValueError(f"Invalid shape: {shape}")


def validate_position(position: int) -> None:
    """Validate position parameter.

    Args:
        position: Position to validate

    Raises:
        ValueError: If position is invalid
    """
    if position not in range(TOTAL_POSITIONS):
        raise ValueError(f"Invalid position: {position}")


def validate_move_parameters(player: int, shape: int, position: int) -> None:
    """Validate all move parameters.

    Args:
        player: Player ID to validate
        shape: Shape ID to validate
        position: Position to validate

    Raises:
        ValueError: If any parameter is invalid
    """
    validate_player(player)
    validate_shape(shape)
    validate_position(position)


# ============================================================================
# Position and Bit Manipulation Utilities
# ============================================================================


def create_position_mask(position: int) -> int:
    """Create bit mask for a specific position.

    Args:
        position: Position index (0-15)

    Returns:
        Bit mask with only the specified position bit set

    Raises:
        ValueError: If position is invalid
    """
    validate_position(position)
    return 1 << position


def position_to_coordinates(position: int) -> tuple[int, int]:
    """Convert position index to row and column coordinates.

    Args:
        position: Position index (0-15)

    Returns:
        Tuple of (row, column) where both are 0-3

    Raises:
        ValueError: If position is invalid
    """
    validate_position(position)
    return position // 4, position % 4


def coordinates_to_position(row: int, col: int) -> int:
    """Convert row and column coordinates to position index.

    Args:
        row: Row index (0-3)
        col: Column index (0-3)

    Returns:
        Position index (0-15)

    Raises:
        ValueError: If coordinates are invalid
    """
    if not (0 <= row <= 3):
        raise ValueError(f"Invalid row: {row}, must be 0-3")
    if not (0 <= col <= 3):
        raise ValueError(f"Invalid col: {col}, must be 0-3")
    return row * 4 + col


def is_position_occupied(bb: "Bitboard", position: int) -> bool:
    """Check if any piece occupies the specified position.

    Args:
        bb: Bitboard to check
        position: Position to check (0-15)

    Returns:
        True if position is occupied by any piece

    Raises:
        ValueError: If position is invalid
    """
    position_mask = create_position_mask(position)
    return any(bb_value & position_mask for bb_value in bb)
