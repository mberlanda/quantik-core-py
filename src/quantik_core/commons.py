"""
Common types, constants and configuration for Quantik core.

This module provides essential types and constants used throughout the Quantik core library.
"""

from typing import Tuple, Literal

# --- Type aliases ------------------------------------------------------------
# Bitboard: 8 uint16 values representing player pieces by color and shape
# Layout: [C0S0, C0S1, C0S2, C0S3, C1S0, C1S1, C1S2, C1S3]
# where C = color (0=player0, 1=player1), S = shape (0=A, 1=B, 2=C, 3=D)
Bitboard = Tuple[int, int, int, int, int, int, int, int]

# PlayerId: either 0 or 1
PlayerId = Literal[0, 1]

# --- Game constants ----------------------------------------------------------
# Maximum pieces per shape per player
MAX_PIECES_PER_SHAPE = 2

# --- Win masks --------------------------------------------------------------
# Row masks: each row has 4 consecutive positions
ROW_MASKS = [
    0b0000000000001111,  # Row 0: positions 0,1,2,3
    0b0000000011110000,  # Row 1: positions 4,5,6,7
    0b0000111100000000,  # Row 2: positions 8,9,10,11
    0b1111000000000000,  # Row 3: positions 12,13,14,15
]

# Column masks: each column has 4 positions spaced 4 apart
COLUMN_MASKS = [
    0b0001000100010001,  # Column 0: positions 0,4,8,12
    0b0010001000100010,  # Column 1: positions 1,5,9,13
    0b0100010001000100,  # Column 2: positions 2,6,10,14
    0b1000100010001000,  # Column 3: positions 3,7,11,15
]

# Zone masks: 2x2 squares
ZONE_MASKS = [
    0b0000000000110011,  # Top-left: positions 0,1,4,5
    0b0000000011001100,  # Top-right: positions 2,3,6,7
    0b0011001100000000,  # Bottom-left: positions 8,9,12,13
    0b1100110000000000,  # Bottom-right: positions 10,11,14,15
]

# All win lines (rows + columns + zones) - used for both win detection and validation
WIN_MASKS = ROW_MASKS + COLUMN_MASKS + ZONE_MASKS

# --- Versioning/flags --------------------------------------------------------
VERSION = 1
FLAG_CANON = 1 << 1  # bit1


class ValidationError(Exception):
    """Exception raised when game state validation fails."""

    pass
