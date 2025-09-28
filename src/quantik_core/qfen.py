"""
QFEN (Quantik FEN) conversion utilities.

This module provides functions for converting between Quantik game states
and QFEN (Quantik FEN) string representations, avoiding circular imports.

QFEN Format: 4 slash-separated ranks representing rows from top to bottom.

4x4 Grid Layout:
┌─────┬─────┬─────┬─────┐
│  0  │  1  │  2  │  3  │  ← Rank 1: positions 0-3
├─────┼─────┼─────┼─────┤
│  4  │  5  │  6  │  7  │  ← Rank 2: positions 4-7
├─────┼─────┼─────┼─────┤
│  8  │  9  │ 10  │ 11  │  ← Rank 3: positions 8-11
├─────┼─────┼─────┼─────┤
│ 12  │ 13  │ 14  │ 15  │  ← Rank 4: positions 12-15
└─────┴─────┴─────┴─────┘

Shape Notation:
• A, B, C, D = Player 0 pieces (uppercase)
• a, b, c, d = Player 1 pieces (lowercase)
• . = Empty square

Examples:

1. Starting position:
   QFEN: "..../..../..../....."
   Visual:
   ┌─────┬─────┬─────┬─────┐
   │  .  │  .  │  .  │  .  │
   ├─────┼─────┼─────┼─────┤
   │  .  │  .  │  .  │  .  │
   ├─────┼─────┼─────┼─────┤
   │  .  │  .  │  .  │  .  │
   ├─────┼─────┼─────┼─────┤
   │  .  │  .  │  .  │  .  │
   └─────┴─────┴─────┴─────┘

2. Mixed position:
   QFEN: "A.bC/..../d..B/...a"
   Visual:
   ┌─────┬─────┬─────┬─────┐
   │  A  │  .  │  b  │  C  │ ← Player 0: A,C  Player 1: b
   ├─────┼─────┼─────┼─────┤
   │  .  │  .  │  .  │  .  │
   ├─────┼─────┼─────┼─────┤
   │  d  │  .  │  .  │  B  │ ← Player 0: B    Player 1: d
   ├─────┼─────┼─────┼─────┤
   │  .  │  .  │  .  │  a  │ ← Player 1: a
   └─────┴─────┴─────┴─────┘

3. Winning position (row):
   QFEN: "AbCd/..../..../....."
   Visual:
   ┌─────┬─────┬─────┬─────┐
   │  A  │  b  │  C  │  d  │ ← WIN! All 4 shapes in row
   ├─────┼─────┼─────┼─────┤
   │  .  │  .  │  .  │  .  │
   ├─────┼─────┼─────┼─────┤
   │  .  │  .  │  .  │  .  │
   ├─────┼─────┼─────┼─────┤
   │  .  │  .  │  .  │  .  │
   └─────┴─────┴─────┴─────┘
"""
from .commons import Bitboard, ValidationError
from .state_validator import ValidationResult, _validate_game_state_single_pass

# Shape letters for QFEN notation
SHAPE_LETTERS = "ABCD"


def rc_to_i(r: int, c: int) -> int:
    """
    Convert row and column to 0-15 position index.

    Args:
        r: Row (0-3)
        c: Column (0-3)

    Returns:
        Integer index from 0-15
    """
    return r * 4 + c


def bb_to_qfen(bb: Bitboard) -> str:
    """
    Convert a bitboard to QFEN string representation.

    Args:
        bb: 8-element bitboard in order [C0S0..C0S3, C1S0..C1S3]

    Returns:
        QFEN string representation of the board state
    """
    grid = []
    for r in range(4):
        row = []
        for c in range(4):
            i = rc_to_i(r, c)
            ch = "."
            for color in (0, 1):
                for s in range(4):
                    if (bb[color * 4 + s] >> i) & 1:
                        letter = SHAPE_LETTERS[s]
                        ch = letter if color == 0 else letter.lower()
            row.append(ch)
        grid.append("".join(row))
    return "/".join(grid)


def bb_from_qfen(qfen: str, validate: bool = False) -> Bitboard:
    """
    Parse a QFEN string into a bitboard representation.

    Args:
        qfen: String in format "rank1/rank2/rank3/rank4" where each rank
              contains 4 characters representing one row of the board
        validate: If True, validate the resulting state against Quantik rules (default: False)

    Returns:
        8-element bitboard tuple [C0S0..C0S3, C1S0..C1S3]

    Raises:
        ValueError: If QFEN format is invalid (not 4 ranks of 4 chars each)
                   or if validate=True and the state violates Quantik rules
    """
    parts = [p.strip() for p in qfen.replace(" ", "").split("/")]
    if len(parts) != 4 or any(len(p) != 4 for p in parts):
        raise ValueError("QFEN must be 4 ranks of 4 chars separated by '/'")

    bb = [0] * 8
    letter_to_shape = {ch: i for i, ch in enumerate(SHAPE_LETTERS)}

    for r in range(4):
        for c in range(4):
            ch = parts[r][c]
            if ch == ".":
                continue
            if ch.upper() not in letter_to_shape:
                raise ValueError(
                    f"Invalid character '{ch}' in QFEN. Must be A,B,C,D (uppercase/lowercase) or '.'"
                )
            color = 0 if ch.isupper() else 1
            s = letter_to_shape[ch.upper()]
            bb[color * 4 + s] |= 1 << rc_to_i(r, c)

    bb_tuple: Bitboard = (
        bb[0],
        bb[1],
        bb[2],
        bb[3],
        bb[4],
        bb[5],
        bb[6],
        bb[7],
    )

    # Validate the state if requested
    if validate:
        _, result = _validate_game_state_single_pass(bb_tuple)
        if result != ValidationResult.OK:
            raise ValidationError(f"Invalid qfen: {qfen}. {str(result)}")

    return bb_tuple
