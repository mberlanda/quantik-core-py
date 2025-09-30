"""Ultra-compact state representation using existing State.pack() format."""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from collections import deque

from quantik_core import State


@dataclass(frozen=True)
class UltraCompactState:
    """18-byte state representation using existing State.pack() format.

    This class provides a memory-efficient wrapper around the existing
    State.pack() method, reducing memory footprint from ~64 bytes to 18 bytes.
    """

    packed_data: bytes  # Exactly 18 bytes from State.pack()

    def __post_init__(self) -> None:
        """Validate packed data size."""
        if len(self.packed_data) != 18:
            raise ValueError(
                f"Packed data must be exactly 18 bytes, got {len(self.packed_data)}"
            )

    @classmethod
    def from_state(cls, state: State) -> "UltraCompactState":
        """Create compact state from regular State object.

        Args:
            state: Regular State object to compress

        Returns:
            UltraCompactState with 18-byte representation
        """
        packed_data = state.pack()
        return cls(packed_data=packed_data)

    def to_state(self) -> State:
        """Convert back to regular State object.

        Returns:
            State: Fully reconstructed State object
        """
        return State.unpack(self.packed_data)

    @property
    def memory_footprint(self) -> int:
        """Get memory footprint in bytes."""
        return 18

    def __len__(self) -> int:
        """Return memory footprint for compatibility."""
        return 18

    def __hash__(self) -> int:
        """Hash based on packed data for use in sets/dicts."""
        return hash(self.packed_data)

    def __eq__(self, other: object) -> bool:
        """Equality based on packed data."""
        if not isinstance(other, UltraCompactState):
            return False
        return self.packed_data == other.packed_data

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"UltraCompactState({len(self.packed_data)} bytes, hash={hash(self.packed_data)})"


class CompactStatePool:
    """Memory pool for compact states to reduce allocation overhead.

    This pool maintains a collection of pre-allocated compact states
    and reuses them to reduce garbage collection pressure.
    """

    def __init__(self, initial_size: int = 10000) -> None:
        """Initialize the compact state pool.

        Args:
            initial_size: Initial number of slots to pre-allocate
        """
        self.pool: List[Optional[UltraCompactState]] = [None] * initial_size
        self.free_indices: deque[int] = deque(range(initial_size))
        self.next_index = initial_size
        self.allocated_count = 0
        self.reuse_count = 0

    def allocate_state(self, state_data: bytes) -> int:
        """Allocate a compact state and return its index.

        Args:
            state_data: 18-byte packed state data

        Returns:
            int: Index of allocated state in pool
        """
        compact_state = UltraCompactState(packed_data=state_data)

        # Try to reuse an existing slot
        if self.free_indices:
            index = self.free_indices.popleft()
            self.pool[index] = compact_state
            self.reuse_count += 1
        else:
            # Expand pool if needed
            index = self.next_index
            self.pool.append(compact_state)
            self.next_index += 1

        self.allocated_count += 1
        return index

    def get_state(self, index: int) -> UltraCompactState:
        """Retrieve state by index.

        Args:
            index: Index of state in pool

        Returns:
            UltraCompactState: The compact state at given index

        Raises:
            IndexError: If index is invalid or state is deallocated
        """
        if index < 0 or index >= len(self.pool):
            raise IndexError(
                f"Index {index} out of range for pool size {len(self.pool)}"
            )

        state = self.pool[index]
        if state is None:
            raise IndexError(f"State at index {index} has been deallocated")

        return state

    def deallocate_state(self, index: int) -> None:
        """Deallocate a state and mark slot as free.

        Args:
            index: Index of state to deallocate
        """
        if index < 0 or index >= len(self.pool):
            raise IndexError(
                f"Index {index} out of range for pool size {len(self.pool)}"
            )

        if self.pool[index] is not None:
            self.pool[index] = None
            self.free_indices.append(index)
            self.allocated_count -= 1

    def clear(self) -> None:
        """Clear all states and reset pool."""
        self.pool = [None] * len(self.pool)
        self.free_indices = deque(range(len(self.pool)))
        self.allocated_count = 0
        self.reuse_count = 0

    @property
    def size(self) -> int:
        """Total pool size (allocated + free)."""
        return len(self.pool)

    @property
    def free_count(self) -> int:
        """Number of free slots."""
        return len(self.free_indices)

    @property
    def utilization(self) -> float:
        """Pool utilization as percentage."""
        if len(self.pool) == 0:
            return 0.0
        return (self.allocated_count / len(self.pool)) * 100.0

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.

        Returns:
            Dict with pool statistics
        """
        return {
            "total_size": len(self.pool),
            "allocated": self.allocated_count,
            "free": self.free_count,
            "utilization_percent": self.utilization,
            "reuse_count": self.reuse_count,
            "memory_bytes": len(self.pool) * 18,  # Each state is 18 bytes
        }


class CompactStateCollection:
    """Collection of compact states with efficient memory management."""

    def __init__(self, use_pool: bool = True, pool_size: int = 10000) -> None:
        """Initialize collection.

        Args:
            use_pool: Whether to use memory pooling
            pool_size: Initial pool size if using pooling
        """
        self.use_pool = use_pool
        if use_pool:
            self.pool = CompactStatePool(initial_size=pool_size)
            self.indices: List[int] = []
        else:
            self.states: List[UltraCompactState] = []

    def add_state(self, state: State) -> int:
        """Add a state to the collection.

        Args:
            state: State to add

        Returns:
            int: Index of added state
        """
        if self.use_pool:
            index = self.pool.allocate_state(state.pack())
            self.indices.append(index)
            return len(self.indices) - 1
        else:
            compact_state = UltraCompactState.from_state(state)
            self.states.append(compact_state)
            return len(self.states) - 1

    def get_state(self, index: int) -> State:
        """Get state by collection index.

        Args:
            index: Index in collection

        Returns:
            State: Reconstructed state
        """
        if self.use_pool:
            pool_index = self.indices[index]
            compact_state = self.pool.get_state(pool_index)
            return compact_state.to_state()
        else:
            return self.states[index].to_state()

    def __len__(self) -> int:
        """Number of states in collection."""
        return len(self.indices) if self.use_pool else len(self.states)

    @property
    def memory_usage(self) -> int:
        """Total memory usage in bytes."""
        if self.use_pool:
            # Pool overhead + indices overhead
            pool_memory = self.pool.size * 18  # 18 bytes per slot
            indices_memory = len(self.indices) * 8  # 8 bytes per int
            return pool_memory + indices_memory
        else:
            return len(self.states) * 18

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get detailed memory statistics."""
        if self.use_pool:
            stats = self.pool.get_stats()
            stats["indices_count"] = len(self.indices)
            stats["indices_memory"] = len(self.indices) * 8
            stats["total_memory"] = stats["memory_bytes"] + stats["indices_memory"]
            return stats
        else:
            return {
                "states_count": len(self.states),
                "states_memory": len(self.states) * 18,
                "total_memory": len(self.states) * 18,
                "pool_enabled": False,
            }
