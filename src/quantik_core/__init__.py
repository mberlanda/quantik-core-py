"""
Quantik Core - High-performance game state manipulation library.

This library provides the foundational components for building Quantik game engines,
Monte Carlo simulations, and AI analysis tools.
"""

from .commons import Bitboard, PlayerId, VERSION, FLAG_CANON
from .core import State
from .symmetry import SymmetryHandler, SymmetryTransform
from .qfen import bb_to_qfen, bb_from_qfen
from .move import (
    Move,
    validate_move,
    apply_move,
    generate_legal_moves,
    generate_legal_moves_list,
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
    "VERSION",
    "FLAG_CANON",
    "State",
    "Bitboard",
    "CompactBitboard",
    "UltraCompactState",
    "Move",
    "validate_move",
    "apply_move",
    "generate_legal_moves",
    "generate_legal_moves_list",
    "bb_to_qfen",
    "bb_from_qfen",
    "ValidationResult",
    "PlayerId",
    "GameResult",
    "SymmetryHandler",
    "SymmetryTransform",
    "QuantikBoard",
    "PlayerInventory",
    "MoveRecord",
]
