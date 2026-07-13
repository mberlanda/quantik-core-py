"""Quantik Core - high-performance game state manipulation library."""

from importlib.metadata import PackageNotFoundError, version

from .commons import Bitboard, PlayerId, VERSION, FLAG_CANON
from .contracts import SUPPORTED_CONTRACTS, SUPPORTED_CONTRACTS_RELEASE
from .core import State
from .symmetry import SymmetryHandler, SymmetryTransform
from .qfen import bb_to_qfen, bb_from_qfen
from .state_validator import ValidationResult
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
from .evaluation import EvalConfig, evaluate
from .minimax import MinimaxConfig, MinimaxEngine, MinimaxResult

try:
    __version__ = version("quantik-core")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0+editable"

__author__ = "Mauro Berlanda"

__all__ = [
    "VERSION",
    "FLAG_CANON",
    "SUPPORTED_CONTRACTS",
    "SUPPORTED_CONTRACTS_RELEASE",
    "State",
    "Bitboard",
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
    "EvalConfig",
    "evaluate",
    "MinimaxConfig",
    "MinimaxEngine",
    "MinimaxResult",
]
