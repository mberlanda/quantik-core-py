"""
Constants for Quantik game validation and win detection.
"""

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

# Maximum pieces per shape per player
MAX_PIECES_PER_SHAPE = 2
