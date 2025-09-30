"""Memory-efficient compact game tree implementation with ultra-compact nodes."""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from quantik_core import State


@dataclass
class CompactGameTreeNode:
    """Ultra-compact 64-byte game tree node optimized for cache efficiency.

    Memory layout designed for CPU cache lines and minimal overhead.
    Current implementation uses State.pack() but designed for future bitboard optimization.
    """

    # Core state identification (18 bytes) - using existing State.pack()
    canonical_state_data: bytes  # 18 bytes - canonical state in pack format

    # Tree structure (12 bytes)
    parent_id: np.uint32  # 4 bytes - parent node ID (0 = root)
    depth: np.uint16  # 2 bytes - depth in tree (max 16, but uint16 for alignment)
    player_turn: (
        np.uint8
    )  # 1 byte - current player (0 or 1, but uint8 for future flexibility)
    flags: np.uint8  # 1 byte - status flags (terminal, expanded, etc.)
    num_children: np.uint16  # 2 bytes - number of child nodes
    first_child_id: np.uint32  # 4 bytes - ID of first child (siblings are consecutive)

    # Game statistics (16 bytes)
    multiplicity: np.uint32  # 4 bytes - symmetry multiplicity
    total_descendants: np.uint32  # 4 bytes - total nodes in subtree
    win_count_p0: np.uint32  # 4 bytes - player 0 wins from this node
    win_count_p1: np.uint32  # 4 bytes - player 1 wins from this node

    # Analysis metadata (16 bytes) - for future MCTS/UCB integration
    visit_count: np.uint32  # 4 bytes - number of visits (MCTS)
    best_value: np.float32  # 4 bytes - best evaluation score
    terminal_value: np.float32  # 4 bytes - terminal game value (-1, 0, 1)
    reserved: np.uint32  # 4 bytes - reserved for future use

    # Total: 62 bytes (fits in 64-byte cache line with 2 bytes padding)

    def __post_init__(self) -> None:
        """Validate node data after creation."""
        if len(self.canonical_state_data) != 18:
            raise ValueError(
                f"canonical_state_data must be 18 bytes, got {len(self.canonical_state_data)}"
            )


# Flag constants for the flags field
NODE_FLAG_TERMINAL = 0x01  # Node represents a terminal game state
NODE_FLAG_EXPANDED = 0x02  # Node has been expanded (children generated)
NODE_FLAG_WINNING_P0 = 0x04  # Player 0 wins from this position
NODE_FLAG_WINNING_P1 = 0x08  # Player 1 wins from this position


class CompactGameTreeStorage:
    """High-performance storage for compact game tree nodes using numpy arrays.

    Uses ID-based references instead of object pointers for memory efficiency.
    All nodes stored in contiguous memory for cache optimization.
    """

    def __init__(self, initial_capacity: int = 1_000_000):
        """Initialize storage with given capacity.

        Args:
            initial_capacity: Initial number of nodes to allocate space for
        """
        self.capacity = initial_capacity
        self.node_count = 0

        # Core storage: single numpy array for all node data
        # Each row is 64 bytes (62 used + 2 padding for alignment)
        self.node_data = np.zeros((initial_capacity, 64), dtype=np.uint8)

        # Fast lookups - use depth-aware canonical state mapping
        self.canonical_to_id: Dict[Tuple[bytes, int], int] = (
            {}
        )  # (canonical_state, depth) -> node_id
        self.free_ids: List[int] = []  # Recycled node IDs

        # Tree navigation maps
        self.children_map: Dict[int, List[int]] = {}  # parent_id -> [child_ids]

    def allocate_node_id(self) -> int:
        """Allocate a new node ID, reusing freed IDs when possible."""
        if self.free_ids:
            return self.free_ids.pop()

        if self.node_count >= self.capacity:
            self._expand_capacity()

        node_id = self.node_count
        self.node_count += 1
        return node_id

    def _expand_capacity(self) -> None:
        """Double the storage capacity when needed."""
        new_capacity = self.capacity * 2
        new_data = np.zeros((new_capacity, 64), dtype=np.uint8)
        new_data[: self.capacity] = self.node_data
        self.node_data = new_data
        self.capacity = new_capacity

    def store_node(self, node_id: int, node: CompactGameTreeNode) -> None:
        """Store a compact node at the given ID."""
        if node_id >= self.capacity:
            raise ValueError(f"Node ID {node_id} exceeds capacity {self.capacity}")

        # Pack node data into bytes with proper layout
        row = self.node_data[node_id]

        # Store canonical state data (18 bytes: 0-17)
        row[0:18] = np.frombuffer(node.canonical_state_data, dtype=np.uint8)

        # Store tree structure (14 bytes: 18-31)
        row[18:22] = np.frombuffer(
            node.parent_id.astype("<u4").tobytes(), dtype=np.uint8
        )  # parent_id: 18-21
        row[22:24] = np.frombuffer(
            node.depth.astype("<u2").tobytes(), dtype=np.uint8
        )  # depth: 22-23
        row[24] = node.player_turn  # player_turn: 24
        row[25] = node.flags  # flags: 25
        row[26:28] = np.frombuffer(
            node.num_children.astype("<u2").tobytes(), dtype=np.uint8
        )  # num_children: 26-27
        row[28:32] = np.frombuffer(
            node.first_child_id.astype("<u4").tobytes(), dtype=np.uint8
        )  # first_child_id: 28-31

        # Store statistics (16 bytes: 32-47)
        row[32:36] = np.frombuffer(
            node.multiplicity.astype("<u4").tobytes(), dtype=np.uint8
        )  # multiplicity: 32-35
        row[36:40] = np.frombuffer(
            node.total_descendants.astype("<u4").tobytes(), dtype=np.uint8
        )  # total_descendants: 36-39
        row[40:44] = np.frombuffer(
            node.win_count_p0.astype("<u4").tobytes(), dtype=np.uint8
        )  # win_count_p0: 40-43
        row[44:48] = np.frombuffer(
            node.win_count_p1.astype("<u4").tobytes(), dtype=np.uint8
        )  # win_count_p1: 44-47

        # Store analysis metadata (16 bytes: 48-63)
        row[48:52] = np.frombuffer(
            node.visit_count.astype("<u4").tobytes(), dtype=np.uint8
        )  # visit_count: 48-51
        row[52:56] = np.frombuffer(
            node.best_value.astype("<f4").tobytes(), dtype=np.uint8
        )  # best_value: 52-55
        row[56:60] = np.frombuffer(
            node.terminal_value.astype("<f4").tobytes(), dtype=np.uint8
        )  # terminal_value: 56-59
        row[60:64] = np.frombuffer(
            node.reserved.astype("<u4").tobytes(), dtype=np.uint8
        )  # reserved: 60-63

        # Update lookup maps with depth-aware key
        canonical_key = (node.canonical_state_data, int(node.depth))
        self.canonical_to_id[canonical_key] = node_id

    def load_node(self, node_id: int) -> CompactGameTreeNode:
        """Load a compact node from the given ID."""
        if node_id >= self.node_count:
            raise ValueError(f"Node ID {node_id} not found")

        row = self.node_data[node_id]

        # Extract canonical state data (18 bytes: 0-17)
        canonical_state_data = bytes(row[0:18])

        # Extract tree structure (14 bytes: 18-31)
        parent_id = np.frombuffer(row[18:22], dtype="<u4")[0]  # parent_id: 18-21
        depth = np.frombuffer(row[22:24], dtype="<u2")[0]  # depth: 22-23
        player_turn = row[24]  # player_turn: 24
        flags = row[25]  # flags: 25
        num_children = np.frombuffer(row[26:28], dtype="<u2")[0]  # num_children: 26-27
        first_child_id = np.frombuffer(row[28:32], dtype="<u4")[
            0
        ]  # first_child_id: 28-31

        # Extract statistics (16 bytes: 32-47)
        multiplicity = np.frombuffer(row[32:36], dtype="<u4")[0]  # multiplicity: 32-35
        total_descendants = np.frombuffer(row[36:40], dtype="<u4")[
            0
        ]  # total_descendants: 36-39
        win_count_p0 = np.frombuffer(row[40:44], dtype="<u4")[0]  # win_count_p0: 40-43
        win_count_p1 = np.frombuffer(row[44:48], dtype="<u4")[0]  # win_count_p1: 44-47

        # Extract analysis metadata (16 bytes: 48-63)
        visit_count = np.frombuffer(row[48:52], dtype="<u4")[0]  # visit_count: 48-51
        best_value = np.frombuffer(row[52:56], dtype="<f4")[0]  # best_value: 52-55
        terminal_value = np.frombuffer(row[56:60], dtype="<f4")[
            0
        ]  # terminal_value: 56-59
        reserved = np.frombuffer(row[60:64], dtype="<u4")[0]  # reserved: 60-63

        return CompactGameTreeNode(
            canonical_state_data=canonical_state_data,
            parent_id=np.uint32(parent_id),
            depth=np.uint16(depth),
            player_turn=np.uint8(player_turn),
            flags=np.uint8(flags),
            num_children=np.uint16(num_children),
            first_child_id=np.uint32(first_child_id),
            multiplicity=np.uint32(multiplicity),
            total_descendants=np.uint32(total_descendants),
            win_count_p0=np.uint32(win_count_p0),
            win_count_p1=np.uint32(win_count_p1),
            visit_count=np.uint32(visit_count),
            best_value=np.float32(best_value),
            terminal_value=np.float32(terminal_value),
            reserved=np.uint32(reserved),
        )

    def find_node_by_canonical_state(
        self, canonical_state_data: bytes, depth: int
    ) -> Optional[int]:
        """Find node ID by canonical state data and depth."""
        canonical_key = (canonical_state_data, depth)
        return self.canonical_to_id.get(canonical_key)

    def add_child_relationship(self, parent_id: int, child_id: int) -> None:
        """Add parent-child relationship."""
        if parent_id not in self.children_map:
            self.children_map[parent_id] = []
        self.children_map[parent_id].append(child_id)

    def get_children(self, parent_id: int) -> List[int]:
        """Get child node IDs for a parent."""
        return self.children_map.get(parent_id, [])

    def deallocate_node(self, node_id: int) -> None:
        """Deallocate a node ID for reuse."""
        if node_id < self.node_count:
            self.free_ids.append(node_id)
            # Remove from lookup maps
            node = self.load_node(node_id)
            canonical_key = (node.canonical_state_data, int(node.depth))
            self.canonical_to_id.pop(canonical_key, None)
            self.children_map.pop(node_id, None)

    def memory_usage(self) -> int:
        """Calculate total memory usage in bytes."""
        node_storage = self.capacity * 64  # 64 bytes per node slot
        lookup_storage = len(self.canonical_to_id) * (
            18 + 4 + 8
        )  # state data + depth + int
        children_storage = sum(
            len(children) * 8 for children in self.children_map.values()
        )
        return node_storage + lookup_storage + children_storage

    def get_stats(self) -> Dict[str, int]:
        """Get storage statistics."""
        return {
            "capacity": self.capacity,
            "node_count": self.node_count,
            "free_ids": len(self.free_ids),
            "memory_usage": self.memory_usage(),
            "utilization_percent": int((self.node_count / self.capacity) * 100),
        }


class CompactGameTree:
    """High-level interface for memory-efficient game tree operations."""

    def __init__(self, initial_capacity: int = 1_000_000):
        """Initialize compact game tree.

        Args:
            initial_capacity: Initial node capacity
        """
        self.storage = CompactGameTreeStorage(initial_capacity)
        self.root_id: Optional[int] = None

    def create_root_node(self, initial_state: State) -> int:
        """Create the root node from initial game state."""
        canonical_state_data = initial_state.pack()

        node_id = self.storage.allocate_node_id()
        node = CompactGameTreeNode(
            canonical_state_data=canonical_state_data,
            parent_id=np.uint32(0),  # Root has no parent
            depth=np.uint16(0),
            player_turn=np.uint8(0),  # Player 0 starts
            flags=np.uint8(NODE_FLAG_EXPANDED),
            num_children=np.uint16(0),
            first_child_id=np.uint32(0),
            multiplicity=np.uint32(1),
            total_descendants=np.uint32(0),
            win_count_p0=np.uint32(0),
            win_count_p1=np.uint32(0),
            visit_count=np.uint32(0),
            best_value=np.float32(0.0),
            terminal_value=np.float32(0.0),
            reserved=np.uint32(0),
        )

        self.storage.store_node(node_id, node)
        self.root_id = node_id
        return node_id

    def add_child_node(
        self, parent_id: int, child_state: State, multiplicity: int = 1
    ) -> int:
        """Add a child node to the tree with proper transposition table behavior.

        If the same canonical state already exists at the target depth,
        merge multiplicities (transposition table behavior).
        """
        parent = self.storage.load_node(parent_id)
        canonical_state_data = child_state.pack()
        target_depth = parent.depth + 1

        # Check if this canonical state already exists at the target depth
        existing_id = self.storage.find_node_by_canonical_state(
            canonical_state_data, int(target_depth)
        )
        if existing_id is not None:
            # Transposition found! Update multiplicity of existing node
            existing = self.storage.load_node(existing_id)
            existing.multiplicity = np.uint32(existing.multiplicity + multiplicity)
            self.storage.store_node(existing_id, existing)

            # Also add this parent-child relationship if not already present
            existing_children = self.storage.get_children(parent_id)
            if existing_id not in existing_children:
                self.storage.add_child_relationship(parent_id, existing_id)
                # Update parent's child count
                parent.num_children = np.uint16(parent.num_children + 1)
                if parent.num_children == 1:
                    parent.first_child_id = np.uint32(existing_id)
                self.storage.store_node(parent_id, parent)

            return existing_id

        # Create new child node
        child_id = self.storage.allocate_node_id()
        child_node = CompactGameTreeNode(
            canonical_state_data=canonical_state_data,
            parent_id=np.uint32(parent_id),
            depth=np.uint16(target_depth),
            player_turn=np.uint8(1 - parent.player_turn),  # Alternate players
            flags=np.uint8(0),
            num_children=np.uint16(0),
            first_child_id=np.uint32(0),
            multiplicity=np.uint32(multiplicity),
            total_descendants=np.uint32(0),
            win_count_p0=np.uint32(0),
            win_count_p1=np.uint32(0),
            visit_count=np.uint32(0),
            best_value=np.float32(0.0),
            terminal_value=np.float32(0.0),
            reserved=np.uint32(0),
        )

        self.storage.store_node(child_id, child_node)
        self.storage.add_child_relationship(parent_id, child_id)

        # Update parent's child count
        parent.num_children = np.uint16(parent.num_children + 1)
        if parent.num_children == 1:
            parent.first_child_id = np.uint32(child_id)
        self.storage.store_node(parent_id, parent)

        return child_id

    def get_node(self, node_id: int) -> CompactGameTreeNode:
        """Get node by ID."""
        return self.storage.load_node(node_id)

    def get_children(self, node_id: int) -> List[int]:
        """Get child node IDs."""
        return self.storage.get_children(node_id)

    def get_state(self, node_id: int) -> State:
        """Get game state for a node."""
        node = self.storage.load_node(node_id)
        return State.unpack(node.canonical_state_data)

    def memory_usage(self) -> int:
        """Get total memory usage."""
        return self.storage.memory_usage()

    def get_stats(self) -> Dict[str, int]:
        """Get tree statistics."""
        return self.storage.get_stats()
