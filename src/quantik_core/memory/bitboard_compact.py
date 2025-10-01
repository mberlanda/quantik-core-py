"""
Commit 4: Bitboard Optimization

Ultra-compact bitboard representation    def __getitem__(self, index: int) -> int:
        # Get value at specific bitboard position.
        if not (0 <= index < 8):
            raise IndexError(f"Index {index} out of range [0, 7]")
        # Unpack single value at offset
        return int(struct.unpack("<H", self._data[index * 2 : (index + 1) * 2])[0])emory-efficient game trees.
Replaces Tuple[int, int, int, int, int, int, int, int] with 16-byte struct.

This provides:
- Significant memory reduction (224+ bytes -> 16 bytes)
- Cache-friendly fixed-size representation
- Direct byte-level operations
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

    def __init__(self, data: Union[bytes, bytearray, Bitboard]):
        """
        Initialize compact bitboard from various formats.

        Args:
            data: Either 16-byte bytes/bytearray or 8-tuple of integers (0-65535)
        """
        if isinstance(data, (bytes, bytearray)):
            if len(data) != 16:
                raise ValueError(f"Byte data must be exactly 16 bytes, got {len(data)}")
            self._data = bytes(data)
        elif isinstance(data, tuple):
            if len(data) != 8:
                raise ValueError(f"Tuple must have exactly 8 elements, got {len(data)}")
            # Validate range and pack as little-endian 16-bit unsigned integers
            for val in data:
                if not (0 <= val <= 65535):
                    raise ValueError(f"All values must be 0-65535, got {val}")
            self._data = struct.pack("<8H", *data)  # 8 unsigned shorts, little-endian
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
        return struct.unpack("<8H", self._data)  # Unpack 8 unsigned shorts

    def to_bytes(self) -> bytes:
        """Get raw byte representation."""
        return self._data

    def bit_count(self, bitboard_index: int) -> int:
        """Get the number of set bits in a specific bitboard."""
        if not (0 <= bitboard_index < 8):
            raise IndexError(f"Index {bitboard_index} out of range [0, 7]")
        return self[bitboard_index].bit_count()

    def get_occupied_mask(self) -> int:
        """Get a mask of all occupied positions across all bitboards."""
        occupied = 0
        for i in range(8):
            occupied |= self[i]
        return occupied

    def apply_move_functional(
        self, player: int, shape: int, position: int
    ) -> "CompactBitboard":
        """Apply a move and return a new CompactBitboard (functional approach)."""
        validate_move_parameters(player, shape, position)

        # Convert to tuple, apply move, convert back
        bb_tuple = list(self.to_tuple())
        bitboard_idx = player * 4 + shape
        bb_tuple[bitboard_idx] |= 1 << position
        # Ensure we have exactly 8 values for the tuple
        if len(bb_tuple) != 8:
            raise ValueError(f"Expected 8 bitboard values, got {len(bb_tuple)}")
        return CompactBitboard.from_tuple(
            (
                bb_tuple[0],
                bb_tuple[1],
                bb_tuple[2],
                bb_tuple[3],
                bb_tuple[4],
                bb_tuple[5],
                bb_tuple[6],
                bb_tuple[7],
            )
        )

    def is_position_occupied(self, position: int) -> bool:
        """Check if a position is occupied by any piece."""
        if not (0 <= position <= 15):
            raise ValueError(f"Invalid position {position}, must be 0-15")
        return bool(self.get_occupied_mask() & (1 << position))

    def __iter__(self) -> Iterator[int]:
        """Iterate over the 8 bitboard values."""
        for i in range(8):
            yield self[i]

    @classmethod
    def from_any(
        cls, data: Union["CompactBitboard", Bitboard, bytes, bytearray]
    ) -> "CompactBitboard":
        """Create CompactBitboard from various input types."""
        if isinstance(data, CompactBitboard):
            return data
        elif isinstance(data, (tuple, list)) and len(data) == 8:
            # Ensure we have the correct type for from_tuple
            return cls.from_tuple(
                (
                    data[0],
                    data[1],
                    data[2],
                    data[3],
                    data[4],
                    data[5],
                    data[6],
                    data[7],
                )
            )
        elif isinstance(data, (bytes, bytearray)):
            return cls.from_bytes(data)
        else:
            raise TypeError(f"Cannot create CompactBitboard from {type(data)}")

    def __getitem__(self, index: int) -> int:
        """Get value at specific bitboard position."""
        if not (0 <= index < 8):
            raise IndexError(f"Index {index} out of range [0, 7]")
        # Unpack single value at offset
        return int(struct.unpack("<H", self._data[index * 2 : (index + 1) * 2])[0])

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
        """Get memory size in bytes (16 bytes data + object overhead)."""
        return 16 + 24  # 16 bytes data + minimal object overhead

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
