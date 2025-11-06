"""Memory optimization package for quantik-core."""

from .compact_state import UltraCompactState, CompactStatePool, CompactStateCollection
from .binary_serialization import StateSerializer, CompressionLevel, BatchStateManager
from .compact_tree import (
    CompactGameTreeNode,
    CompactGameTreeStorage,
    CompactGameTree,
    NODE_FLAG_TERMINAL,
    NODE_FLAG_EXPANDED,
    NODE_FLAG_WINNING_P0,
    NODE_FLAG_WINNING_P1,
)

__all__ = [
    "UltraCompactState",
    "CompactStatePool",
    "CompactStateCollection",
    "StateSerializer",
    "CompressionLevel",
    "BatchStateManager",
    "CompactGameTreeNode",
    "CompactGameTreeStorage",
    "CompactGameTree",
    "NODE_FLAG_TERMINAL",
    "NODE_FLAG_EXPANDED",
    "NODE_FLAG_WINNING_P0",
    "NODE_FLAG_WINNING_P1",
]
