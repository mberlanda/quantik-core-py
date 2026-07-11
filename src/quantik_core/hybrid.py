"""Hybrid opening->endgame player for Quantik.

Uses an adaptive sampling engine (MCTS or beam search) while the game tree
is intractable to search exactly, then hands off to the exact minimax
solver once few enough cells remain. The handoff is by empty-cell count:
Quantik's branching shrinks as pieces are placed, so a position with few
empty cells has a small remaining tree that `MinimaxEngine.solve` resolves
exactly and quickly.

Known limitation when `opening_engine="mcts"`: `CompactGameTree
.create_root_node` currently marks the root node as fully expanded at
creation instead of only once every legal move has a child, which can
leave MCTS's root with a single explored child regardless of
`max_iterations` (see `docs/MCTS.md`'s "Known limitation" note). When that
happens, the opening move MCTS returns is decided by move-generation
order rather than search quality. `opening_engine="beam"` does not share
this limitation -- `BeamSearchEngine` does not use `CompactGameTree`'s
`NODE_FLAG_EXPANDED`/`_select` traversal at all.
"""

from dataclasses import dataclass, field

from .core import State
from .move import Move
from .minimax import MinimaxConfig, MinimaxEngine
from .mcts import MCTSConfig, MCTSEngine
from .beam_search import BeamSearchConfig, BeamSearchEngine


@dataclass
class HybridConfig:
    """Configuration for `HybridPlayer`.

    `handoff_empty_cells`: at or below this many empty cells, use the exact
    solver; above it, use `opening_engine`. Default 8 (>= 8 pieces placed),
    where exact solves complete in well under a second.
    """

    handoff_empty_cells: int = 8
    opening_engine: str = "mcts"  # "mcts" or "beam"
    mcts_config: MCTSConfig = field(default_factory=MCTSConfig)
    beam_config: BeamSearchConfig = field(default_factory=BeamSearchConfig)
    minimax_config: MinimaxConfig = field(
        default_factory=lambda: MinimaxConfig(max_depth=16)
    )


@dataclass
class HybridResult:
    """Which move was chosen, by which engine, and whether it is exact."""

    best_move: Move
    engine_used: str  # "minimax" | "mcts" | "beam"
    exact: bool


def _empty_cells(state: State) -> int:
    return 16 - state.get_occupied_bb().bit_count()


class HybridPlayer:
    """Composite player: sampling in the open game, exact solve in the endgame."""

    def __init__(self, config: HybridConfig) -> None:
        self.config = config

    def select_move(self, state: State) -> Move:
        return self.search(state).best_move

    def search(self, state: State) -> HybridResult:
        if _empty_cells(state) <= self.config.handoff_empty_cells:
            move = MinimaxEngine(self.config.minimax_config).solve(state).best_move
            return HybridResult(best_move=move, engine_used="minimax", exact=True)

        engine = self.config.opening_engine
        if engine == "mcts":
            move, _ = MCTSEngine(self.config.mcts_config).search(state)
            return HybridResult(best_move=move, engine_used="mcts", exact=False)
        if engine == "beam":
            result = BeamSearchEngine(self.config.beam_config).search(state)
            if result.best_leaf is not None and result.best_leaf.moves:
                move = result.best_leaf.moves[0]
            else:
                ranked = result.ranked_root_moves()
                if not ranked:
                    raise ValueError(
                        "BeamSearchEngine returned no best_leaf and no "
                        "ranked_root_moves() for a non-terminal state; "
                        "cannot select a move."
                    )
                move = ranked[0].move
            return HybridResult(best_move=move, engine_used="beam", exact=False)
        raise ValueError(f"Unknown opening_engine: {engine!r}")
