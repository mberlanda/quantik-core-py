"""
Symmetry handling for Quantik boards.

This module provides functionality to handle the symmetries of the 4x4 Quantik board,
including rotations, reflections, color swaps, and shape permutations.
It implements efficient methods for:
- Applying symmetry operations to game states
- Converting positions to their canonical forms
- Translating moves between different symmetry orientations
"""

from typing import Dict, List, Tuple, Callable, Union, TYPE_CHECKING
from dataclasses import dataclass
from enum import IntEnum
import struct
import itertools
from .commons import VERSION, FLAG_CANON, Bitboard
from .qfen import bb_from_qfen, bb_to_qfen

if TYPE_CHECKING:
    from .move import Move

# Type aliases for symmetry operations
D4Mapping = List[int]  # 16-element list mapping positions under symmetry


class D4Index(IntEnum):
    ID = 0
    ROT90 = 1
    ROT180 = 2
    ROT270 = 3
    REFLV = 4
    REFLH = 5
    REFLD = 6
    REFLAD = 7


D4IndexLike = Union[D4Index, int]

ShapePerm = Tuple[int, ...]  # Permutation of shapes 0-3
ColorSwap = bool  # Whether to swap player colors


@dataclass(frozen=True)
class SymmetryTransform:
    """
    Represents a complete symmetry transformation.

    Combines a D4 spatial symmetry, optional color swap, and shape permutation.
    """

    d4_index: D4IndexLike  # Index into D4 list (0-7)
    color_swap: ColorSwap  # Whether to swap player colors
    shape_perm: ShapePerm  # Permutation of shapes 0-3

    def __post_init__(self) -> None:
        """Validate transform parameters."""
        if not 0 <= self.d4_index < 8:
            raise ValueError(f"D4 index must be 0-7, got {self.d4_index}")
        if len(self.shape_perm) != 4 or set(self.shape_perm) != set(range(4)):
            raise ValueError(
                f"Shape perm must be a permutation of [0,1,2,3], got {self.shape_perm}"
            )

    def inverse(self) -> "SymmetryTransform":
        """
        Return the inverse transformation that undoes this transformation.

        Returns:
            The inverse SymmetryTransform
        """
        # Get inverse of D4 transform
        d4_inv_idx = SymmetryHandler.get_d4_inverse(self.d4_index)

        # For shape permutation, compute the inverse permutation
        shape_inv = [0] * 4
        for i, j in enumerate(self.shape_perm):
            shape_inv[j] = i

        # Color swap is its own inverse
        return SymmetryTransform(
            d4_index=d4_inv_idx, color_swap=self.color_swap, shape_perm=tuple(shape_inv)
        )


class SymmetryHandler:
    """
    Handles all symmetry operations for Quantik board states.

    Provides methods to:
    1. Apply symmetries to game states
    2. Find canonical forms of game states
    3. Map moves between symmetry-equivalent board positions
    4. Compute lexicographically smallest QFEN among all symmetric variants

    Uses pre-computed lookup tables for efficiency.
    """

    # 8 D4 symmetries with human-readable names and mapping functions
    D4 = [
        ("id", lambda r, c: (r, c)),
        ("rot90", lambda r, c: (c, 3 - r)),
        ("rot180", lambda r, c: (3 - r, 3 - c)),
        ("rot270", lambda r, c: (3 - c, r)),
        ("reflV", lambda r, c: (r, 3 - c)),
        ("reflH", lambda r, c: (3 - r, c)),
        ("reflD", lambda r, c: (c, r)),
        ("reflAD", lambda r, c: (3 - c, 3 - r)),
    ]

    # Generate all 24 shape permutations
    ALL_SHAPE_PERMS = list(itertools.permutations(range(4)))

    # Pre-compute and cache the D4 inverse mappings for fast lookup
    _D4_INVERSES: Dict[D4IndexLike, D4IndexLike] = {
        D4Index.ID: D4Index.ID,  # identity
        D4Index.ROT90: D4Index.ROT270,  # rot90 <-> rot270
        D4Index.ROT180: D4Index.ROT180,  # rot180 <-> rot180
        D4Index.ROT270: D4Index.ROT90,  # rot270 <-> rot90
        D4Index.REFLV: D4Index.REFLV,  # reflV <-> reflV
        D4Index.REFLH: D4Index.REFLH,  # reflH <-> reflH
        D4Index.REFLD: D4Index.REFLD,  # reflD <-> reflD
        D4Index.REFLAD: D4Index.REFLAD,  # reflAD <-> reflAD
    }

    @staticmethod
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

    @staticmethod
    def i_to_rc(i: int) -> Tuple[int, int]:
        """
        Convert 0-15 position index to row and column.

        Args:
            i: Position index (0-15)

        Returns:
            Tuple of (row, column)
        """
        return divmod(i, 4)

    @classmethod
    def get_d4_inverse(cls, d4_index: D4IndexLike) -> D4IndexLike:
        """Get the inverse D4 transformation index."""
        return cls._D4_INVERSES[d4_index]

    @classmethod
    def build_perm(cls, fn: Callable[[int, int], Tuple[int, int]]) -> List[int]:
        """
        Build a permutation mapping based on a transformation function.

        Args:
            fn: Function that maps (row, col) to transformed (row, col)

        Returns:
            16-element list where list[i] = transformed position of i
        """
        m = [0] * 16
        for i in range(16):
            r, c = cls.i_to_rc(i)
            r2, c2 = fn(r, c)
            m[i] = cls.rc_to_i(r2, c2)
        return m

    # Pre-compute the D4 mappings (will be set in _initialize_class())
    D4_MAPPINGS = None  # type: List[List[int]]

    # Pre-compute LUT for fast 16-bit permutation
    @classmethod
    def _build_perm16_lut(cls) -> List[List[int]]:
        """
        Build lookup tables for fast application of each D4 permutation to 16-bit masks.

        Returns:
            List of 8 tables, each with 65536 entries for all possible 16-bit values
        """
        # First ensure D4_MAPPINGS is initialized
        if not cls.D4_MAPPINGS:
            cls.D4_MAPPINGS = [cls.build_perm(fn) for _, fn in cls.D4]

        tables: List[List[int]] = []
        for mapping in cls.D4_MAPPINGS:
            t = [0] * 65536
            for x in range(65536):
                y = 0
                # Scatter bits by mapping[i] in tight loop
                m = x
                i = 0
                while m:
                    if m & 1:
                        y |= 1 << mapping[i]
                    i += 1
                    m >>= 1
                # Finish remaining zeros if any
                while i < 16:
                    # (no-op; just advance)
                    i += 1
                t[x] = y
            tables.append(t)
        return tables

    # Static LUT: ~1.0MB RAM, provides very fast permutations (will be set in _initialize_class())
    _PERM16_LUT: List[List[int]] = []

    @classmethod
    def _initialize_class(cls) -> None:
        """Initialize class-level data structures that depend on class methods."""
        # Initialize D4 mappings
        cls.D4_MAPPINGS = [cls.build_perm(fn) for _, fn in cls.D4]

        # Initialize permutation lookup table
        cls._PERM16_LUT = cls._build_perm16_lut()

    @classmethod
    def permute16(cls, mask: int, d4_index: D4IndexLike) -> int:
        """
        Apply a D4 permutation to a 16-bit mask using the lookup table.

        Args:
            mask: 16-bit integer mask
            d4_index: Index into D4 list (0-7)

        Returns:
            Transformed 16-bit mask
        """
        return cls._PERM16_LUT[d4_index][mask]

    @classmethod
    def apply_symmetry(cls, bb: Bitboard, transform: SymmetryTransform) -> Bitboard:
        """
        Apply a complete symmetry transformation to a bitboard.

        Args:
            bb: 8-element bitboard in order [C0S0..C0S3, C1S0..C1S3]
            transform: Symmetry transformation to apply

        Returns:
            Transformed 8-element bitboard
        """
        assert len(bb) == 8

        # Split into [2][4] array by color and shape
        B = [[bb[c * 4 + s] for s in range(4)] for c in range(2)]

        # Apply geometric transformation
        G0 = [cls.permute16(B[0][s], transform.d4_index) for s in range(4)]
        G1 = [cls.permute16(B[1][s], transform.d4_index) for s in range(4)]

        # Apply color swap if requested
        C0, C1 = (G0, G1) if not transform.color_swap else (G1, G0)

        # Apply shape permutation
        perm = transform.shape_perm
        return (
            C0[perm[0]],
            C0[perm[1]],
            C0[perm[2]],
            C0[perm[3]],
            C1[perm[0]],
            C1[perm[1]],
            C1[perm[2]],
            C1[perm[3]],
        )

    @classmethod
    def find_canonical_form(cls, bb: Bitboard) -> Tuple[Bitboard, SymmetryTransform]:
        """
        Find the canonical form of a bitboard and the transform that produces it.

        The canonical form is the lexicographically smallest among all symmetric variants,
        considering all combinations of:
        - 8 D4 spatial symmetries
        - 2 possible color swaps
        - 24 shape permutations

        Args:
            bb: 8-element bitboard

        Returns:
            Tuple of (canonical_bitboard, transform_used)
        """
        best_bb = None
        best_transform = None
        best_payload = None

        # Split into [2][4] array by color and shape
        B = [[bb[c * 4 + s] for s in range(4)] for c in range(2)]

        # Try all combinations of symmetries
        for d4_idx in range(8):
            # Apply geometric transformation
            G0 = [cls.permute16(B[0][s], d4_idx) for s in range(4)]
            G1 = [cls.permute16(B[1][s], d4_idx) for s in range(4)]

            # Try both color assignments
            for color_swap in (False, True):
                C0, C1 = (G0, G1) if not color_swap else (G1, G0)

                # Try all shape permutations
                for perm in cls.ALL_SHAPE_PERMS:
                    # Create candidate bitboard
                    candidate_bb = (
                        C0[perm[0]],
                        C0[perm[1]],
                        C0[perm[2]],
                        C0[perm[3]],
                        C1[perm[0]],
                        C1[perm[1]],
                        C1[perm[2]],
                        C1[perm[3]],
                    )

                    # Serialize for comparison
                    candidate_payload = struct.pack("<8H", *candidate_bb)

                    # Update if this is the lexicographically smallest so far
                    if best_payload is None or candidate_payload < best_payload:
                        best_payload = candidate_payload
                        best_bb = candidate_bb
                        best_transform = SymmetryTransform(
                            d4_index=d4_idx, color_swap=color_swap, shape_perm=perm
                        )

        assert best_bb is not None  # We always find at least one candidate
        assert best_transform is not None

        return best_bb, best_transform

    @classmethod
    def get_canonical_payload(cls, bb: Bitboard) -> bytes:
        """
        Get the canonical payload bytes for a bitboard.

        Args:
            bb: 8-element bitboard

        Returns:
            16-byte canonical payload
        """
        canonical_bb, _ = cls.find_canonical_form(bb)
        return struct.pack("<8H", *canonical_bb)

    @classmethod
    def get_canonical_key(cls, bb: Bitboard) -> bytes:
        """
        Get the canonical key bytes for a bitboard.

        Args:
            bb: 8-element bitboard

        Returns:
            18-byte canonical key (version + flag + payload)
        """
        return bytes([VERSION, FLAG_CANON]) + cls.get_canonical_payload(bb)

    @classmethod
    def apply_symmetry_to_move(
        cls, move: "Move", transform: SymmetryTransform  # Type hint for Move
    ) -> "Move":
        """
        Apply a symmetry transformation to a move.

        This translates a move from one orientation to another.

        Args:
            move: A Move object with player, shape, and position attributes
            transform: Symmetry transformation to apply

        Returns:
            New Move object with transformed attributes
        """
        # Import here to avoid issues during module initialization
        from .move import Move

        # Extract move components
        player = move.player
        shape = move.shape
        pos = move.position

        # Apply transformations in the correct order

        # 1. Apply D4 spatial transformation to position
        r, c = cls.i_to_rc(pos)
        fn = cls.D4[transform.d4_index][1]  # Get the transformation function
        r2, c2 = fn(r, c)
        new_pos = cls.rc_to_i(r2, c2)

        # 2. Apply color swap if needed
        new_player = player
        if transform.color_swap:
            new_player = 1 - player  # type: ignore # Toggle between 0 and 1

        # 3. Apply shape permutation
        new_shape = transform.shape_perm.index(shape)

        # Create and return new move
        return Move(player=new_player, shape=new_shape, position=new_pos)

    @classmethod
    def get_qfen_canonical_form(cls, qfen: str) -> str:
        """
        Get the canonical QFEN among all symmetric variants.

        Args:
            qfen: QFEN string

        Returns:
            Canonical QFEN string
        """

        bb = bb_from_qfen(qfen)
        canonical_bb, _ = cls.find_canonical_form(bb)
        return bb_to_qfen(canonical_bb)


# Initialize class structures on module load
SymmetryHandler._initialize_class()
