"""
Common game utilities for piece counting and state analysis.

This module provides consolidated functions that were previously duplicated
across move.py, board.py, and plugins/validation.py.
"""

from functools import lru_cache
from typing import List, Tuple
from .commons import Bitboard


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