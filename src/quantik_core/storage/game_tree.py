"""
Hybrid game state management for distributed computing.

This module provides the main interface for working with game states
in a way that's optimized for both computation and storage/transmission.
"""

from typing import List, Dict, Tuple, Optional, Union, BinaryIO
import pickle
import gzip
from ..commons import Bitboard, PlayerId
from ..move import Move, generate_legal_moves, apply_move, validate_move
from .compact_state import CompactState, serialize_bitboard, deserialize_bitboard, batch_serialize, batch_deserialize


class GameState:
    """
    Hybrid game state that uses tuples for computation and compact format for storage.
    
    This is the main class for distributed game tree computation.
    """
    
    def __init__(self, bb: Bitboard):
        """
        Initialize with a tuple bitboard for fast computation.
        
        Args:
            bb: Tuple bitboard (8 integers)
        """
        self._bb = bb
    
    @property
    def bitboard(self) -> Bitboard:
        """Get the tuple bitboard for fast computation."""
        return self._bb
    
    @classmethod
    def from_compact(cls, compact: Union[CompactState, bytes]) -> "GameState":
        """
        Create GameState from compact representation.
        
        Args:
            compact: CompactState or raw bytes
            
        Returns:
            GameState ready for computation
        """
        if isinstance(compact, bytes):
            bb = deserialize_bitboard(compact)
        else:
            bb = compact.to_tuple()
        return cls(bb)
    
    def to_compact(self) -> CompactState:
        """
        Convert to compact representation for storage/transmission.
        
        Returns:
            CompactState (8 bytes)
        """
        return CompactState.from_tuple(self._bb)
    
    def serialize(self) -> bytes:
        """
        Serialize to bytes for storage/transmission.
        
        Returns:
            8-byte representation
        """
        return serialize_bitboard(self._bb)
    
    def generate_moves(self, player_id: Optional[PlayerId] = None) -> Tuple[PlayerId, Dict[int, List[Move]]]:
        """Generate legal moves using fast tuple computation."""
        return generate_legal_moves(self._bb, player_id)
    
    def apply_move(self, move: Move) -> "GameState":
        """Apply move and return new GameState using fast tuple computation."""
        new_bb = apply_move(self._bb, move)
        return GameState(new_bb)
    
    def validate_move(self, move: Move) -> bool:
        """Validate move using fast tuple computation."""
        result = validate_move(self._bb, move)
        return result.is_valid
    
    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if isinstance(other, GameState):
            return self._bb == other._bb
        return False
    
    def __hash__(self) -> int:
        """Hash for use as dictionary keys."""
        return hash(self._bb)
    
    def __repr__(self) -> str:
        """String representation."""
        return f"GameState({self._bb})"


class GameTree:
    """
    Game tree optimized for distributed computing and memory efficiency.
    
    Uses hybrid storage: tuples for active computation, compact format for storage.
    """
    
    def __init__(self):
        """Initialize empty game tree."""
        self._nodes: Dict[Bitboard, Dict] = {}  # Active nodes use tuples as keys
        self._stats = {
            "nodes_computed": 0,
            "nodes_serialized": 0,
            "memory_saved_mb": 0.0
        }
    
    def add_node(self, state: GameState, value: float, moves: Optional[List[Move]] = None) -> None:
        """
        Add node to tree.
        
        Args:
            state: GameState
            value: Node evaluation value
            moves: Optional list of legal moves
        """
        self._nodes[state.bitboard] = {
            "value": value,
            "moves": moves or [],
            "visits": 0
        }
        self._stats["nodes_computed"] += 1
    
    def get_node(self, state: GameState) -> Optional[Dict]:
        """Get node data if it exists."""
        return self._nodes.get(state.bitboard)
    
    def save_checkpoint(self, filename: str, compress: bool = True) -> None:
        """
        Save tree to checkpoint file using compact representation.
        
        Args:
            filename: Output filename
            compress: Whether to use gzip compression
        """
        # Convert to compact format for storage
        compact_data = []
        for bb, data in self._nodes.items():
            compact_bb = serialize_bitboard(bb)
            compact_data.append({
                "bb": compact_bb,
                "value": data["value"],
                "moves": data["moves"],
                "visits": data["visits"]
            })
        
        # Calculate memory savings
        original_size = len(self._nodes) * 104  # Tuple size
        compact_size = len(self._nodes) * 8    # Compact size
        self._stats["memory_saved_mb"] = (original_size - compact_size) / (1024 * 1024)
        
        checkpoint = {
            "data": compact_data,
            "stats": self._stats
        }
        
        if compress:
            with gzip.open(filename, 'wb') as f:
                pickle.dump(checkpoint, f)
        else:
            with open(filename, 'wb') as f:
                pickle.dump(checkpoint, f)
        
        self._stats["nodes_serialized"] = len(compact_data)
    
    def load_checkpoint(self, filename: str, compress: bool = True) -> None:
        """
        Load tree from checkpoint file.
        
        Args:
            filename: Input filename  
            compress: Whether file is gzip compressed
        """
        if compress:
            with gzip.open(filename, 'rb') as f:
                checkpoint = pickle.load(f)
        else:
            with open(filename, 'rb') as f:
                checkpoint = pickle.load(f)
        
        # Convert back to tuples for computation
        self._nodes.clear()
        for item in checkpoint["data"]:
            bb = deserialize_bitboard(item["bb"])
            self._nodes[bb] = {
                "value": item["value"],
                "moves": item["moves"],
                "visits": item["visits"]
            }
        
        self._stats = checkpoint.get("stats", self._stats)
    
    def merge_results(self, other_tree: "GameTree") -> None:
        """
        Merge results from another tree (for map-reduce operations).
        
        Args:
            other_tree: Tree to merge into this one
        """
        for bb, data in other_tree._nodes.items():
            if bb in self._nodes:
                # Merge statistics (simple average for now)
                existing = self._nodes[bb]
                total_visits = existing["visits"] + data["visits"]
                if total_visits > 0:
                    existing["value"] = (
                        (existing["value"] * existing["visits"] + 
                         data["value"] * data["visits"]) / total_visits
                    )
                existing["visits"] = total_visits
            else:
                self._nodes[bb] = data.copy()
        
        # Update stats
        self._stats["nodes_computed"] += other_tree._stats["nodes_computed"]
    
    def get_stats(self) -> Dict:
        """Get tree statistics."""
        return {
            **self._stats,
            "active_nodes": len(self._nodes),
            "memory_usage_mb": len(self._nodes) * 104 / (1024 * 1024)  # Tuples in memory
        }


def create_worker_batch(states: List[GameState]) -> bytes:
    """
    Create a batch of states for worker processes using compact format.
    
    Args:
        states: List of GameStates
        
    Returns:
        Compact byte representation for transmission
    """
    bitboards = [state.bitboard for state in states]
    return batch_serialize(bitboards)


def load_worker_batch(data: bytes) -> List[GameState]:
    """
    Load batch of states from compact format for worker processes.
    
    Args:
        data: Compact byte representation
        
    Returns:
        List of GameStates ready for computation
    """
    bitboards = batch_deserialize(data)
    return [GameState(bb) for bb in bitboards]