"""
Hybrid bitboard representation for Quantik game states.

This module provides both fast tuple-based computation and compact serialization
for distributed computing and memory-efficient storage.

Design:
- Hot paths use tuples for maximum performance
- Serialization uses 16-byte compact format (significant compression vs tuples)
- Easy conversion between formats as needed
"""

from typing import Union
import struct
import sys
from ..commons import Bitboard


class CompactState:
    """
    Ultra-compact 16-byte representation for serialization and storage.

    Uses 16-bit integers (0-65535) which is sufficient for Quantik's bitboards.
    This provides 6.5x memory reduction vs Python tuples for storage/transmission.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Union[bytes, Bitboard]):
        """
        Initialize from bytes or tuple.

        Args:
            data: Either 16-byte bytes or 8-tuple of integers (0-65535)
        """
        if isinstance(data, bytes):
            if len(data) != 16:
                raise ValueError(f"Byte data must be exactly 16 bytes, got {len(data)}")
            self._data = data
        elif isinstance(data, tuple) and len(data) == 8:
            # Validate range for 16-bit storage
            for i, val in enumerate(data):
                if not (0 <= val <= 65535):
                    raise ValueError(
                        f"Value at index {i} is {val}, must be 0-65535 for compact storage"
                    )
            self._data = struct.pack("<8H", *data)  # 8 unsigned shorts, little-endian
        else:
            raise TypeError(f"Expected bytes or 8-tuple, got {type(data)}")

    @classmethod
    def from_tuple(cls, bitboard: Bitboard) -> "CompactState":
        """Create from tuple bitboard."""
        return cls(bitboard)

    @classmethod
    def from_bytes(cls, data: bytes) -> "CompactState":
        """Create from byte data."""
        return cls(data)

    def to_tuple(self) -> Bitboard:
        """Convert to tuple for fast computation."""
        return struct.unpack("<8H", self._data)

    def to_bytes(self) -> bytes:
        """Get raw 16-byte representation for serialization."""
        return self._data

    def __len__(self) -> int:
        """Always 8 for bitboard positions."""
        return 8

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if isinstance(other, CompactState):
            return self._data == other._data
        elif isinstance(other, tuple) and len(other) == 8:
            return self.to_tuple() == other
        return False

    def __hash__(self) -> int:
        """Hash for use as dictionary keys."""
        return hash(self._data)

    def __repr__(self) -> str:
        """String representation."""
        values = ", ".join(str(v) for v in self.to_tuple())
        return f"CompactState([{values}])"

    @property
    def memory_size(self) -> int:
        """Memory size in bytes (16 bytes + minimal object overhead)."""
        return 16 + 24  # 16 bytes data + Python object overhead


def serialize_bitboard(bb: Bitboard) -> bytes:
    """
    Convert tuple bitboard to compact 8-byte format for storage/transmission.

    Args:
        bb: Tuple bitboard

    Returns:
        8-byte representation

    Raises:
        ValueError: If any value > 255 (can't fit in compact format)
    """
    return CompactState.from_tuple(bb).to_bytes()


def deserialize_bitboard(data: bytes) -> Bitboard:
    """
    Convert 8-byte compact format back to tuple bitboard for computation.

    Args:
        data: 8-byte compact representation

    Returns:
        Tuple bitboard ready for fast computation
    """
    return CompactState.from_bytes(data).to_tuple()


def batch_serialize(bitboards: list[Bitboard]) -> bytes:
    """
    Serialize multiple bitboards into a compact byte array.

    Efficient for map-reduce operations and checkpoint storage.

    Args:
        bitboards: List of tuple bitboards

    Returns:
        Concatenated bytes (16 bytes per bitboard)
    """
    if not bitboards:
        return b""

    # Pre-allocate buffer for efficiency
    result = bytearray(len(bitboards) * 16)

    for i, bb in enumerate(bitboards):
        compact = CompactState.from_tuple(bb)
        result[i * 16 : (i + 1) * 16] = compact.to_bytes()

    return bytes(result)


def batch_deserialize(data: bytes) -> list[Bitboard]:
    """
    Deserialize byte array back to list of tuple bitboards.

    Args:
        data: Concatenated bytes from batch_serialize

    Returns:
        List of tuple bitboards ready for computation
    """
    if len(data) % 16 != 0:
        raise ValueError(f"Data length {len(data)} is not multiple of 16")

    count = len(data) // 16
    result = []

    for i in range(count):
        start = i * 16
        end = start + 16
        bb_bytes = data[start:end]
        result.append(deserialize_bitboard(bb_bytes))

    return result


# Memory efficiency comparison
def calculate_memory_savings(num_bitboards: int) -> dict:
    """
    Calculate memory savings for different storage approaches using actual measurements.

    Args:
        num_bitboards: Number of bitboards to store

    Returns:
        Dictionary with memory usage comparisons
    """
    # Create sample objects to measure actual sizes
    sample_tuple = (0, 1, 2, 3, 4, 5, 6, 7)
    sample_compact = CompactState.from_tuple(sample_tuple)

    # Actual memory measurements
    tuple_size = sys.getsizeof(sample_tuple)
    compact_bytes_size = len(sample_compact.to_bytes())
    compact_object_size = sample_compact.memory_size

    # Calculate totals
    tuple_memory = num_bitboards * tuple_size
    compact_memory = num_bitboards * compact_bytes_size
    compact_objects_memory = num_bitboards * compact_object_size

    return {
        "sample_tuple_size": tuple_size,
        "sample_compact_size": compact_bytes_size,
        "sample_compact_object_size": compact_object_size,
        "tuples_mb": tuple_memory / (1024 * 1024),
        "compact_bytes_mb": compact_memory / (1024 * 1024),
        "compact_objects_mb": compact_objects_memory / (1024 * 1024),
        "savings_vs_tuples": (tuple_memory - compact_memory) / tuple_memory * 100,
        "compression_ratio": tuple_memory / compact_memory,
    }
