"""
Quantik Core - High-performance game state manipulation library.

This library provides the foundational components for building Quantik game engines,
Monte Carlo simulations, and AI analysis tools.
"""

from .commons import VERSION, FLAG_CANON, Bitboard, PlayerId
from .core import State
from .symmetry import SymmetryHandler, SymmetryTransform
from .qfen import bb_to_qfen, bb_from_qfen
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
    "PlayerId",
    "VERSION",
    "FLAG_CANON",
    "bb_to_qfen",
    "bb_from_qfen",
    "get_qfen_canonical_form",
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
    "SymmetryHandler",
    "SymmetryTransform",
]
