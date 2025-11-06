"""Binary serialization utilities for compact state management."""

from typing import List, Dict, Any
from enum import Enum, auto
import struct
import zstandard as zstd

from quantik_core import State
from .compact_state import UltraCompactState


class CompressionLevel(Enum):
    """Compression levels for state serialization."""

    NONE = auto()  # No compression, fastest
    FAST = auto()  # Fast compression, good for streaming
    BALANCED = auto()  # Balanced compression/speed
    MAXIMUM = auto()  # Maximum compression, slower


class StateSerializer:
    """Serializer for compact states with optional compression."""

    def __init__(
        self, compression: CompressionLevel = CompressionLevel.BALANCED
    ) -> None:
        """Initialize serializer.

        Args:
            compression: Compression level to use
        """
        self.compression = compression
        self._setup_compressor()

    def _setup_compressor(self) -> None:
        """Setup compression based on level."""
        if self.compression == CompressionLevel.NONE:
            self.compressor = None
            self.decompressor = None
        else:
            level_map = {
                CompressionLevel.FAST: 1,
                CompressionLevel.BALANCED: 3,
                CompressionLevel.MAXIMUM: 19,
            }
            level = level_map[self.compression]
            self.compressor = zstd.ZstdCompressor(level=level)
            self.decompressor = zstd.ZstdDecompressor()

    def serialize_states(self, states: List[UltraCompactState]) -> bytes:
        """Serialize a list of compact states.

        Args:
            states: List of compact states to serialize

        Returns:
            bytes: Serialized data
        """
        if not states:
            return b""

        # Header: count (4 bytes) + state_size (2 bytes)
        count = len(states)
        state_size = 18  # UltraCompactState is always 18 bytes

        # Pack header
        header = struct.pack("!IH", count, state_size)

        # Pack all state data
        data_parts = [header]
        for state in states:
            data_parts.append(state.packed_data)

        raw_data = b"".join(data_parts)

        # Apply compression if enabled
        if self.compression == CompressionLevel.NONE:
            return raw_data
        else:
            assert self.compressor is not None  # Should be set in _setup_compressor
            return self.compressor.compress(raw_data)

    def deserialize_states(self, data: bytes) -> List[UltraCompactState]:
        """Deserialize states from binary data.

        Args:
            data: Serialized data

        Returns:
            List of UltraCompactState objects
        """
        if not data:
            return []

        # Decompress if needed
        if self.compression != CompressionLevel.NONE:
            assert self.decompressor is not None  # Should be set in _setup_compressor
            raw_data = self.decompressor.decompress(data)
        else:
            raw_data = data

        # Read header
        if len(raw_data) < 6:  # 4 + 2 bytes for header
            raise ValueError("Invalid serialized data: too short for header")

        count, state_size = struct.unpack("!IH", raw_data[:6])

        if state_size != 18:
            raise ValueError(f"Invalid state size: expected 18, got {state_size}")

        expected_data_size = 6 + (count * state_size)
        if len(raw_data) != expected_data_size:
            raise ValueError(
                f"Invalid data size: expected {expected_data_size}, got {len(raw_data)}"
            )

        # Extract states
        states = []
        offset = 6
        for _ in range(count):
            state_data = raw_data[offset : offset + state_size]
            states.append(UltraCompactState(packed_data=state_data))
            offset += state_size

        return states

    def estimate_compression_ratio(self, states: List[UltraCompactState]) -> float:
        """Estimate compression ratio for given states.

        Args:
            states: States to estimate compression for

        Returns:
            float: Estimated compression ratio (compressed_size / original_size)
        """
        if not states or self.compression == CompressionLevel.NONE:
            return 1.0

        # Take sample of states for estimation
        sample_size = min(100, len(states))
        sample_states = states[:sample_size]

        original_data = self.serialize_states(sample_states)

        # Temporarily disable compression for size comparison
        original_compression = self.compression
        self.compression = CompressionLevel.NONE
        self._setup_compressor()

        uncompressed_data = self.serialize_states(sample_states)

        # Restore original compression
        self.compression = original_compression
        self._setup_compressor()

        if len(uncompressed_data) == 0:
            return 1.0

        return len(original_data) / len(uncompressed_data)


class BatchStateManager:
    """Manager for efficient batch operations on compact states."""

    def __init__(
        self,
        batch_size: int = 1000,
        compression: CompressionLevel = CompressionLevel.BALANCED,
    ) -> None:
        """Initialize batch manager.

        Args:
            batch_size: Number of states per batch
            compression: Compression level for serialization
        """
        self.batch_size = batch_size
        self.serializer = StateSerializer(compression)
        self.batches: List[bytes] = []
        self.current_batch: List[UltraCompactState] = []
        self.total_states = 0

    def add_state(self, state: State) -> None:
        """Add a state to the current batch.

        Args:
            state: State to add
        """
        compact_state = UltraCompactState.from_state(state)
        self.current_batch.append(compact_state)
        self.total_states += 1

        if len(self.current_batch) >= self.batch_size:
            self._flush_batch()

    def _flush_batch(self) -> None:
        """Flush current batch to storage."""
        if self.current_batch:
            serialized = self.serializer.serialize_states(self.current_batch)
            self.batches.append(serialized)
            self.current_batch = []

    def finalize(self) -> None:
        """Finalize by flushing any remaining states."""
        self._flush_batch()

    def get_all_states(self) -> List[State]:
        """Get all states, decompressing as needed.

        Returns:
            List of all State objects
        """
        all_states = []

        # Get states from completed batches
        for batch_data in self.batches:
            compact_states = self.serializer.deserialize_states(batch_data)
            for compact_state in compact_states:
                all_states.append(compact_state.to_state())

        # Get states from current batch
        for compact_state in self.current_batch:
            all_states.append(compact_state.to_state())

        return all_states

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics.

        Returns:
            Dict with memory statistics
        """
        # Calculate memory for completed batches
        batch_memory = sum(len(batch) for batch in self.batches)

        # Calculate memory for current batch
        current_batch_memory = len(self.current_batch) * 18

        # Estimate uncompressed size
        uncompressed_size = self.total_states * 18

        compression_ratio = (
            batch_memory / uncompressed_size if uncompressed_size > 0 else 1.0
        )

        return {
            "total_states": self.total_states,
            "completed_batches": len(self.batches),
            "current_batch_size": len(self.current_batch),
            "batch_memory_bytes": batch_memory,
            "current_batch_memory_bytes": current_batch_memory,
            "total_memory_bytes": batch_memory + current_batch_memory,
            "uncompressed_size_bytes": uncompressed_size,
            "compression_ratio": compression_ratio,
            "memory_savings_percent": (1.0 - compression_ratio) * 100,
        }

    def clear(self) -> None:
        """Clear all states and reset manager."""
        self.batches = []
        self.current_batch = []
        self.total_states = 0


def compare_memory_usage(
    regular_states: List[State], compact_states: List[UltraCompactState]
) -> Dict[str, Any]:
    """Compare memory usage between regular and compact states.

    Args:
        regular_states: List of regular State objects
        compact_states: List of UltraCompactState objects

    Returns:
        Dict with comparison statistics
    """
    import sys

    if len(regular_states) != len(compact_states):
        raise ValueError("State lists must have same length")

    count = len(regular_states)

    # Estimate regular state memory (rough approximation)
    regular_memory = sum(sys.getsizeof(state) for state in regular_states)

    # Compact state memory (precise)
    compact_memory = count * 18

    # Calculate savings
    memory_ratio = compact_memory / regular_memory if regular_memory > 0 else 1.0
    memory_savings = regular_memory - compact_memory
    savings_percent = (1.0 - memory_ratio) * 100

    return {
        "state_count": count,
        "regular_memory_bytes": regular_memory,
        "compact_memory_bytes": compact_memory,
        "memory_savings_bytes": memory_savings,
        "memory_ratio": memory_ratio,
        "savings_percent": savings_percent,
        "bytes_per_regular_state": regular_memory / count if count > 0 else 0,
        "bytes_per_compact_state": 18,
    }
