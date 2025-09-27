"""
Quantik Core - High-performance game state manipulation library.

This library provides the foundational components for building Quantik game engines,
Monte Carlo simulations, and AI analysis tools.
"""

from .core import State, VERSION, FLAG_CANON, D4, permute16, ALL_SHAPE_PERMS, Bitboard
from .move import (
    Move,
    MoveValidationResult,
    validate_move,
    apply_move,
    generate_legal_moves,
    generate_legal_moves_list,
    count_pieces_by_player_shape,
)
from .board import (
    QuantikBoard,
    PlayerInventory,
    GameResult,
    MoveRecord,
)

__version__ = "0.1.0"
__author__ = "Mauro Berlanda"

__all__ = [
    "State",
    "Bitboard",
    "VERSION",
    "FLAG_CANON",
    "D4",
    "permute16",
    "ALL_SHAPE_PERMS",
    "Move",
    "MoveValidationResult",
    "validate_move",
    "apply_move",
    "generate_legal_moves",
    "generate_legal_moves_list",
    "count_pieces_by_player_shape",
    "QuantikBoard",
    "PlayerInventory",
    "GameResult",
    "MoveRecord",
]
