"""
Storage and serialization utilities for distributed game tree computation.

This module provides hybrid storage solutions that use fast tuples for computation
and compact representations for storage, checkpoints, and distributed computing.
"""

from .compact_state import (
    CompactState,
    serialize_bitboard,
    deserialize_bitboard,
    batch_serialize,
    batch_deserialize,
    calculate_memory_savings
)

from .game_tree import (
    GameState,
    GameTree,
    create_worker_batch,
    load_worker_batch
)

__all__ = [
    "CompactState",
    "serialize_bitboard", 
    "deserialize_bitboard",
    "batch_serialize",
    "batch_deserialize",
    "calculate_memory_savings",
    "GameState",
    "GameTree", 
    "create_worker_batch",
    "load_worker_batch"
]