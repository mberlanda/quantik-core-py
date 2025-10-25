"""
Compact bitboard representation for memory-efficient game trees.

Ultra-compact bitboard representation that replaces
Tuple[int, int, int, int, int, int, int, int] with 16-byte struct.

This provides:
- Significant memory reduction (224+ bytes -> 16 bytes)
- Cache-friendly fixed-size representation
- Direct byte-level operations
- Fast serialization and deserialization
- Compatibility with existing State.pack() format
- QFEN serialization/deserialization support

Note: Uses 16-bit integers (2 bytes each) to support Quantik bitboard values up to 65535.
"""

from typing import Union, Iterator
import struct
from quantik_core.commons import Bitboard
from quantik_core.qfen import bb_from_qfen, bb_to_qfen
from quantik_core.game_utils import validate_move_parameters


class CompactBitboard:
    """
    Ultra-compact bitboard representation using 16 bytes instead of 8 Python integers.

    Each value is a 16-bit integer (0-65535), sufficient for Quantik 16-position bitmasks.
    Uses struct packing for efficient memory layout and fast operations.
    """

    __slots__ = ("_data",)

    # Pre-compile struct format for performance
    _STRUCT_FORMAT = "<8H"
    _STRUCT_SIZE = 16

    def __init__(self, data: Union[bytes, bytearray, Bitboard]):
        """
        Initialize compact bitboard from various formats.

        Args:
            data: Either 16-byte bytes/bytearray or 8-tuple of integers (0-65535)
        """
        if isinstance(data, (bytes, bytearray)):
            if len(data) != self._STRUCT_SIZE:
                raise ValueError(
                    f"Byte data must be exactly {self._STRUCT_SIZE} bytes, got {len(data)}"
                )
            self._data = bytes(data)
        elif isinstance(data, tuple):
            if len(data) != 8:
                raise ValueError(f"Tuple must have exactly 8 elements, got {len(data)}")
            # Validate range and pack as little-endian 16-bit unsigned integers
            for val in data:
                if not (0 <= val <= 65535):
                    raise ValueError(f"All values must be 0-65535, got {val}")
            self._data = struct.pack(self._STRUCT_FORMAT, *data)
        else:
            raise TypeError(
                f"Data must be bytes, bytearray, or 8-tuple, got {type(data)}"
            )

    @classmethod
    def from_tuple(cls, bitboard: Bitboard) -> "CompactBitboard":
        """Create from traditional bitboard tuple."""
        return cls(bitboard)

    @classmethod
    def from_bytes(cls, data: bytes) -> "CompactBitboard":
        """Create from 8-byte representation."""
        return cls(data)

    def to_tuple(self) -> Bitboard:
        """Convert to traditional bitboard tuple format."""
        return struct.unpack(self._STRUCT_FORMAT, self._data)

    def to_bytes(self) -> bytes:
        """Get raw byte representation."""
        return self._data

    def __getitem__(self, index: int) -> int:
        """Get value at specific bitboard position with optimized access."""
        if not (0 <= index < 8):
            raise IndexError(f"Index {index} out of range [0, 7]")
        # Optimized: unpack only the needed value
        offset = index * 2
        result: int = struct.unpack("<H", self._data[offset : offset + 2])[0]
        return result

    def bit_count(self, bitboard_index: int) -> int:
        """Get the number of set bits in a specific bitboard."""
        if not (0 <= bitboard_index < 8):
            raise IndexError(f"Index {bitboard_index} out of range [0, 7]")
        return self[bitboard_index].bit_count()

    def get_occupied_mask(self) -> int:
        """Get a mask of all occupied positions across all bitboards."""
        # Unpack once and iterate
        values = struct.unpack(self._STRUCT_FORMAT, self._data)
        occupied = 0
        for value in values:
            occupied |= value
        return occupied

    def apply_move_functional(
        self, player: int, shape: int, position: int
    ) -> "CompactBitboard":
        """Apply a move and return a new CompactBitboard (functional approach)."""
        validate_move_parameters(player, shape, position)

        # Optimized: minimal conversions
        values = list(struct.unpack(self._STRUCT_FORMAT, self._data))
        bitboard_idx = player * 4 + shape
        values[bitboard_idx] |= 1 << position

        return CompactBitboard(tuple(values))

    def is_position_occupied(self, position: int) -> bool:
        """Check if a position is occupied by any piece."""
        if not (0 <= position <= 15):
            raise ValueError(f"Invalid position {position}, must be 0-15")
        return bool(self.get_occupied_mask() & (1 << position))

    def __iter__(self) -> Iterator[int]:
        """Iterate over the 8 bitboard values."""
        values = struct.unpack(self._STRUCT_FORMAT, self._data)
        return iter(values)

    @classmethod
    def from_any(
        cls, data: Union["CompactBitboard", Bitboard, bytes, bytearray]
    ) -> "CompactBitboard":
        """Create CompactBitboard from various input types."""
        if isinstance(data, CompactBitboard):
            return data
        elif isinstance(data, (tuple, list)) and len(data) == 8:
            # Ensure we have proper int values and correct typing
            bitboard_tuple = tuple(int(x) for x in data)
            if len(bitboard_tuple) == 8:
                return cls(bitboard_tuple)
            else:
                raise ValueError("Bitboard tuple must have exactly 8 elements")
        elif isinstance(data, (bytes, bytearray)):
            return cls.from_bytes(data)
        else:
            raise TypeError(f"Cannot create CompactBitboard from {type(data)}")

    def __len__(self) -> int:
        """Always returns 8 for bitboard positions."""
        return 8

    def __eq__(self, other: object) -> bool:
        """Check equality with another CompactBitboard or tuple."""
        if isinstance(other, CompactBitboard):
            return self._data == other._data
        elif isinstance(other, tuple) and len(other) == 8:
            return self.to_tuple() == other
        return False

    def __hash__(self) -> int:
        """Hash based on byte data for use as dictionary keys."""
        return hash(self._data)

    def __repr__(self) -> str:
        """String representation showing unpacked values."""
        values = ", ".join(str(v) for v in self.to_tuple())
        return f"CompactBitboard([{values}])"

    def __str__(self) -> str:
        """Compact string representation."""
        return f"CompactBitboard({self.to_tuple()})"

    @property
    def memory_size(self) -> int:
        """Get memory size in bytes (16 bytes data + minimal object overhead)."""
        return 16 + 24  # 16 bytes data + object overhead

    def pack(self) -> bytes:
        """Pack into bytes for serialization (compatible with State.pack format)."""
        return self._data

    @classmethod
    def unpack(cls, data: bytes, offset: int = 0) -> "CompactBitboard":
        """Unpack from bytes (compatible with State.pack format)."""
        return cls(data[offset : offset + 16])

    @classmethod
    def from_qfen(cls, qfen: str) -> "CompactBitboard":
        """
        Create CompactBitboard from QFEN string.

        Args:
            qfen: QFEN string in format "rank1/rank2/rank3/rank4"

        Returns:
            CompactBitboard instance

        Raises:
            ValueError: If QFEN format is invalid
        """
        bitboard_tuple = bb_from_qfen(qfen, validate=False)
        return cls(bitboard_tuple)

    def to_qfen(self) -> str:
        """
        Convert to QFEN string representation.

        Returns:
            QFEN string in format "rank1/rank2/rank3/rank4"
        """
        return bb_to_qfen(self.to_tuple())
