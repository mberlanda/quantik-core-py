"""Memory optimization package for quantik-core."""

from typing import Any

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


def __getattr__(name: str) -> Any:
    if name in {"UltraCompactState", "CompactStatePool", "CompactStateCollection"}:
        from .compact_state import (
            CompactStateCollection,
            CompactStatePool,
            UltraCompactState,
        )

        return {
            "UltraCompactState": UltraCompactState,
            "CompactStatePool": CompactStatePool,
            "CompactStateCollection": CompactStateCollection,
        }[name]

    if name in {"StateSerializer", "CompressionLevel", "BatchStateManager"}:
        from .binary_serialization import (
            BatchStateManager,
            CompressionLevel,
            StateSerializer,
        )

        return {
            "StateSerializer": StateSerializer,
            "CompressionLevel": CompressionLevel,
            "BatchStateManager": BatchStateManager,
        }[name]

    if name in {
        "CompactGameTreeNode",
        "CompactGameTreeStorage",
        "CompactGameTree",
        "NODE_FLAG_TERMINAL",
        "NODE_FLAG_EXPANDED",
        "NODE_FLAG_WINNING_P0",
        "NODE_FLAG_WINNING_P1",
    }:
        from .compact_tree import (
            CompactGameTree,
            CompactGameTreeNode,
            CompactGameTreeStorage,
            NODE_FLAG_EXPANDED,
            NODE_FLAG_TERMINAL,
            NODE_FLAG_WINNING_P0,
            NODE_FLAG_WINNING_P1,
        )

        return {
            "CompactGameTreeNode": CompactGameTreeNode,
            "CompactGameTreeStorage": CompactGameTreeStorage,
            "CompactGameTree": CompactGameTree,
            "NODE_FLAG_TERMINAL": NODE_FLAG_TERMINAL,
            "NODE_FLAG_EXPANDED": NODE_FLAG_EXPANDED,
            "NODE_FLAG_WINNING_P0": NODE_FLAG_WINNING_P0,
            "NODE_FLAG_WINNING_P1": NODE_FLAG_WINNING_P1,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
