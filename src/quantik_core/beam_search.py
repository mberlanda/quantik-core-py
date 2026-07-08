"""
Parametrizable beam search for Quantik.

Descends level-by-level from a root state, keeping only the top
`beam_width` non-terminal candidates per depth (breadth pruning) while
always discovering and recording every true terminal state encountered,
regardless of the beam width. Shares the `CompactGameTree` structure used
by `MCTSEngine` so results from both engines can enrich the same
transposition table.
"""

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from quantik_core import State, Move, generate_legal_moves, apply_move
from quantik_core.commons import Bitboard
from quantik_core.game_utils import check_game_winner, WinStatus
from quantik_core.memory.compact_tree import (
    CompactGameTree,
    NODE_FLAG_TERMINAL,
    NODE_FLAG_WINNING_P0,
    NODE_FLAG_WINNING_P1,
)


@dataclass
class BeamSearchConfig:
    """Configuration for the beam search algorithm."""

    beam_width: int = 64  # frontier nodes kept per depth (>= 1)
    max_depth: int = 16  # plies from root; 16 = full Quantik game
    rollouts_per_candidate: int = 8  # rollout budget for the default evaluator (>= 1)
    random_seed: Optional[int] = None
    evaluator: Optional[Callable[[State], float]] = None
    initial_tree_capacity: int = 4096
    # Depth-dependent beam width: width at depth d = beam_schedule[min(d-1,
    # len(beam_schedule)-1)], so the last entry extends to all deeper
    # levels. None (default) applies the flat `beam_width` everywhere.
    # Quantik's canonical state space is tiny early and explodes later
    # (see UNIQUE_CANONICAL_STATES_PER_DEPTH), so a schedule can afford an
    # exhaustive shallow prefix followed by guided sampling, e.g.:
    #   schedule = [UNIQUE_CANONICAL_STATES_PER_DEPTH[d] for d in (1, 2, 3)] + [64]
    beam_schedule: Optional[Sequence[int]] = None


@dataclass
class BeamLeaf:
    """A single collected leaf: a principal variation and its value."""

    moves: Tuple[Move, ...]  # principal variation from the root
    value: float  # P0 perspective; +/-1.0 for terminal leaves
    depth: int
    is_terminal: bool


@dataclass
class RankedRootMove:
    """Aggregated beam-sampled statistics for one first move from the root.

    These are optimistic, beam-sampled statistics computed over whichever
    leaves this particular engine run happened to discover and keep — they
    are **not** a minimax-proven guarantee, just a summary of the lines the
    beam actually explored. `win_probability` is a heuristic rescaling of
    `mean_value` into `[0, 1]`, not a calibrated probability.
    """

    move: Move
    best_value: float  # max leaf value via this move, root-player perspective
    mean_value: float  # mean leaf value via this move, root-player perspective
    win_probability: float  # heuristic rescaling: (mean_value + 1) / 2
    leaf_count: int  # number of collected leaves supporting this move
    has_terminal_win: bool  # a proven root-player-winning terminal exists


@dataclass
class BeamSearchResult:
    """Result of a beam search run."""

    best_leaf: Optional[BeamLeaf]  # best for the ROOT player to move
    terminal_leaves: List[BeamLeaf]  # all terminals discovered, best first
    reached_terminal: bool
    max_depth_reached: int
    stats: Dict[str, int]
    root_player: int = 0  # player to move at the root
    # Non-terminal leaves still live at max_depth_reached; empty once the
    # search fully resolves (reached_terminal is True).
    frontier_leaves: List[BeamLeaf] = field(default_factory=list)

    def ranked_root_moves(self, top_k: Optional[int] = None) -> List[RankedRootMove]:
        """Aggregate every collected leaf by its first move from the root.

        Groups `terminal_leaves` and `frontier_leaves` by the first move of
        each leaf's principal variation and summarizes each group's value
        from the root player's perspective. See `RankedRootMove` for the
        important caveat: these are beam-sampled statistics, not proven
        minimax values.

        Args:
            top_k: If given, return only the top `top_k` ranked moves.

        Returns:
            One `RankedRootMove` per distinct first move seen, sorted by
            `best_value`, then `mean_value`, then `leaf_count` (all
            descending), with a deterministic final tiebreak on the move
            itself.
        """
        groups: Dict[Tuple[int, int, int], List[BeamLeaf]] = {}
        move_by_key: Dict[Tuple[int, int, int], Move] = {}

        for leaf in (*self.terminal_leaves, *self.frontier_leaves):
            if not leaf.moves:
                continue
            first_move = leaf.moves[0]
            key = (first_move.player, first_move.shape, first_move.position)
            groups.setdefault(key, []).append(leaf)
            move_by_key.setdefault(key, first_move)

        def root_perspective(leaf: BeamLeaf) -> float:
            return leaf.value if self.root_player == 0 else -leaf.value

        ranked: List[RankedRootMove] = []
        for group_key, leaves in groups.items():
            values = [root_perspective(leaf) for leaf in leaves]
            best_value = max(values)
            mean_value = sum(values) / len(values)
            has_terminal_win = any(
                leaf.is_terminal and value == 1.0 for leaf, value in zip(leaves, values)
            )
            ranked.append(
                RankedRootMove(
                    move=move_by_key[group_key],
                    best_value=best_value,
                    mean_value=mean_value,
                    win_probability=(mean_value + 1.0) / 2.0,
                    leaf_count=len(leaves),
                    has_terminal_win=has_terminal_win,
                )
            )

        ranked.sort(
            key=lambda r: (
                -r.best_value,
                -r.mean_value,
                -r.leaf_count,
                (r.move.player, r.move.shape, r.move.position),
            )
        )

        if top_k is not None:
            ranked = ranked[:top_k]
        return ranked


# Frontier entry: node id in the tree, its bitboard, the move sequence from
# the root, and its evaluated value (player-0 perspective; 0.0 for the root,
# which is never scored).
_FrontierEntry = Tuple[int, Bitboard, Tuple[Move, ...], float]

# Candidate entry keyed by `State.canonical_key()`: parent node id, the
# candidate's bitboard, its move sequence from the root, and the id of the
# player who made the move leading to it.
_Candidate = Tuple[int, Bitboard, Tuple[Move, ...], int]


UNIQUE_CANONICAL_STATES_PER_DEPTH: Dict[int, int] = {
    1: 3,
    2: 51,
    3: 726,
    4: 10946,
    5: 105632,
    6: 901916,
    7: 4658465,
    8: 17900160,
}
"""Unique canonical states per depth (see `GAME_TREE_ANALYSIS.md`).

Useful for building an exhaustive-prefix `BeamSearchConfig.beam_schedule`
that keeps every legal line up to some depth before switching to guided
sampling, e.g.:

    schedule = [UNIQUE_CANONICAL_STATES_PER_DEPTH[d] for d in (1, 2, 3)] + [64]
"""


class BeamSearchEngine:
    """Level-by-level beam search over the Quantik game tree."""

    def __init__(
        self, config: BeamSearchConfig, tree: Optional[CompactGameTree] = None
    ) -> None:
        """Initialize the engine, validating configuration.

        Args:
            config: Beam search configuration.
            tree: Optional existing `CompactGameTree` to reuse (e.g. an
                `MCTSEngine`'s tree), so results from both engines enrich
                the same transposition structure. A fresh tree is created
                when omitted. Note: `CompactGameTree.create_root_node`
                hardcodes the root's `player_turn` to 0 and alternates from
                there, so when sharing a tree with an `MCTSEngine`, root the
                beam search at a position where player 0 is to move —
                otherwise every node's `player_turn` is inverted, which
                would corrupt MCTS's UCB calculation if that engine later
                resumes on the same tree.

        Raises:
            ValueError: if any configuration value is out of range.
        """
        if config.beam_width < 1:
            raise ValueError("beam_width must be >= 1")
        if not (1 <= config.max_depth <= 16):
            raise ValueError("max_depth must be between 1 and 16")
        if config.rollouts_per_candidate < 1:
            raise ValueError("rollouts_per_candidate must be >= 1")
        if config.beam_schedule is not None:
            if len(config.beam_schedule) == 0:
                raise ValueError("beam_schedule must not be empty")
            if any(width < 1 for width in config.beam_schedule):
                raise ValueError("beam_schedule entries must all be >= 1")

        self.config = config
        self.tree = (
            tree
            if tree is not None
            else CompactGameTree(initial_capacity=config.initial_tree_capacity)
        )
        self._rng = random.Random(config.random_seed)

    def search(self, initial_state: State) -> BeamSearchResult:
        """Run beam search from `initial_state`.

        Args:
            initial_state: Starting game state.

        Returns:
            A `BeamSearchResult` describing the best line found, every
            terminal leaf discovered, and search statistics.

        Raises:
            ValueError: if the root state is already terminal or has no
                legal moves.
        """
        root_player = self._require_non_terminal_root(initial_state)

        root_id = self.tree.create_root_node(initial_state)
        stats: Dict[str, int] = {
            "candidates_generated": 0,
            "candidates_deduped": 0,
            "nodes_inserted": 0,
            "nodes_pruned": 0,
            "evaluations": 0,
        }
        terminal_leaves: List[BeamLeaf] = []
        frontier: List[_FrontierEntry] = [(root_id, initial_state.bb, (), 0.0)]
        max_depth_reached = 0

        for depth in range(1, self.config.max_depth + 1):
            if not frontier:
                break

            candidates = self._expand_frontier(frontier, depth, stats, terminal_leaves)
            beam_width = self._beam_width_for_depth(depth)
            frontier = self._score_and_prune(candidates, stats, beam_width)
            max_depth_reached = depth

        stats["memory_usage"] = self.tree.memory_usage()

        def root_perspective(leaf: BeamLeaf) -> float:
            return leaf.value if root_player == 0 else -leaf.value

        frontier_leaves: List[BeamLeaf] = [
            BeamLeaf(
                moves=moves, value=value, depth=max_depth_reached, is_terminal=False
            )
            for _, _, moves, value in frontier
        ]
        leaves = list(terminal_leaves) + frontier_leaves
        best_leaf = max(leaves, key=root_perspective) if leaves else None
        terminal_leaves.sort(key=root_perspective, reverse=True)

        return BeamSearchResult(
            best_leaf=best_leaf,
            terminal_leaves=terminal_leaves,
            reached_terminal=not frontier,
            max_depth_reached=max_depth_reached,
            stats=stats,
            root_player=root_player,
            frontier_leaves=frontier_leaves,
        )

    def _require_non_terminal_root(self, initial_state: State) -> int:
        """Validate the root state and return the player to move.

        Raises:
            ValueError: if the root is already won or has no legal moves.
        """
        if check_game_winner(initial_state.bb) != WinStatus.NO_WIN:
            raise ValueError("Cannot search from an already-terminal root state.")

        root_player, moves_by_shape = generate_legal_moves(initial_state.bb)
        if not any(moves_by_shape.values()):
            raise ValueError("Cannot search from a root state with no legal moves.")
        return int(root_player)

    def _beam_width_for_depth(self, depth: int) -> int:
        """Resolve the beam width to use at a given depth (1-indexed).

        Without a `beam_schedule`, the flat `beam_width` applies everywhere.
        With one, `depth` indexes into it (`depth - 1`, clamped to the last
        entry), so the schedule's final value extends to all deeper levels.
        """
        schedule = self.config.beam_schedule
        if schedule is None:
            return self.config.beam_width
        index = min(depth - 1, len(schedule) - 1)
        return schedule[index]

    def _expand_frontier(
        self,
        frontier: List[_FrontierEntry],
        depth: int,
        stats: Dict[str, int],
        terminal_leaves: List[BeamLeaf],
    ) -> Dict[bytes, _Candidate]:
        """Expand every frontier entry, recording terminals and candidates."""
        candidates: Dict[bytes, _Candidate] = {}

        for node_id, bb, moves, _ in frontier:
            current_player, moves_by_shape = generate_legal_moves(bb)
            all_moves = [
                m for shape_moves in moves_by_shape.values() for m in shape_moves
            ]

            if not all_moves:
                # Mover has no legal moves: the other player wins.
                value = 1.0 if current_player == 1 else -1.0
                extra_flag = (
                    NODE_FLAG_WINNING_P0
                    if current_player == 1
                    else NODE_FLAG_WINNING_P1
                )
                self._mark_terminal(node_id, extra_flag, value)
                terminal_leaves.append(
                    BeamLeaf(
                        moves=moves, value=value, depth=depth - 1, is_terminal=True
                    )
                )
                continue

            stats["candidates_generated"] += len(all_moves)
            self._expand_moves(
                node_id, bb, moves, all_moves, depth, stats, terminal_leaves, candidates
            )

        return candidates

    def _expand_moves(
        self,
        node_id: int,
        bb: Bitboard,
        moves: Tuple[Move, ...],
        all_moves: List[Move],
        depth: int,
        stats: Dict[str, int],
        terminal_leaves: List[BeamLeaf],
        candidates: Dict[bytes, _Candidate],
    ) -> None:
        """Apply each legal move, splitting terminal children from candidates."""
        for move in all_moves:
            new_bb: Bitboard = apply_move(bb, move)  # type: ignore[assignment]
            new_state = State(new_bb)
            child_moves = moves + (move,)
            winner = check_game_winner(new_bb)

            if winner != WinStatus.NO_WIN:
                value = 1.0 if winner == WinStatus.PLAYER_0_WINS else -1.0
                extra_flag = (
                    NODE_FLAG_WINNING_P0
                    if winner == WinStatus.PLAYER_0_WINS
                    else NODE_FLAG_WINNING_P1
                )
                # add_child_node keys transpositions on the literal
                # State.pack() bytes (its "canonical_state_data" field is
                # not symmetry-reduced), while beam dedup above/below keys
                # on the coarser State.canonical_key(); two different
                # parents can therefore merge into one tree node here.
                nodes_before = self.tree.storage.node_count
                child_id = self.tree.add_child_node(node_id, new_state)
                self._mark_terminal(child_id, extra_flag, value)
                if self.tree.storage.node_count > nodes_before:
                    stats["nodes_inserted"] += 1
                terminal_leaves.append(
                    BeamLeaf(
                        moves=child_moves, value=value, depth=depth, is_terminal=True
                    )
                )
                continue

            key = new_state.canonical_key()
            if key in candidates:
                stats["candidates_deduped"] += 1
                continue
            candidates[key] = (node_id, new_bb, child_moves, move.player)

    def _score_and_prune(
        self,
        candidates: Dict[bytes, _Candidate],
        stats: Dict[str, int],
        beam_width: int,
    ) -> List[_FrontierEntry]:
        """Evaluate candidates, keep the top `beam_width`, insert survivors."""
        scored: List[Tuple[float, int, bytes, float]] = []
        for index, (key, (_, bb, _, mover)) in enumerate(candidates.items()):
            raw_value = self._evaluate(State(bb))
            stats["evaluations"] += 1
            score = raw_value if mover == 0 else -raw_value
            scored.append((score, index, key, raw_value))

        scored.sort(key=lambda item: (-item[0], item[1]))
        survivors = scored[:beam_width]
        stats["nodes_pruned"] += max(0, len(scored) - len(survivors))

        next_frontier: List[_FrontierEntry] = []
        for _, _, key, raw_value in survivors:
            parent_id, bb, moves, _ = candidates[key]
            nodes_before = self.tree.storage.node_count
            child_id = self.tree.add_child_node(parent_id, State(bb))
            node = self.tree.get_node(child_id)
            node.best_value = np.float32(raw_value)
            node.visit_count = np.uint32(node.visit_count + 1)
            self.tree.storage.store_node(child_id, node)
            if self.tree.storage.node_count > nodes_before:
                stats["nodes_inserted"] += 1
            next_frontier.append((child_id, bb, moves, raw_value))

        return next_frontier

    def _mark_terminal(self, node_id: int, extra_flag: int, value: float) -> None:
        """Flag a node terminal with the given winner flag and value."""
        node = self.tree.get_node(node_id)
        node.flags = np.uint8(node.flags | NODE_FLAG_TERMINAL | extra_flag)
        node.terminal_value = np.float32(value)
        node.best_value = np.float32(value)
        node.visit_count = np.uint32(node.visit_count + 1)
        self.tree.storage.store_node(node_id, node)

    def _evaluate(self, state: State) -> float:
        """Evaluate a state from player 0's perspective, clamped to [-1, 1]."""
        if self.config.evaluator is not None:
            raw_value = self.config.evaluator(state)
        else:
            raw_value = self._default_evaluate(state)
        return max(-1.0, min(1.0, float(raw_value)))

    def _default_evaluate(self, state: State) -> float:
        """Mean of `rollouts_per_candidate` random playouts to a true terminal."""
        total = 0.0
        for _ in range(self.config.rollouts_per_candidate):
            total += self._rollout(state.bb)
        return total / self.config.rollouts_per_candidate

    def _rollout(self, bb: Bitboard) -> float:
        """Play uniformly random legal moves until a terminal state.

        A Quantik playout always resolves within 16 plies (each player has
        8 pieces total and the board has 16 cells), so no depth cutoff is
        required.
        """
        current_bb = bb
        while True:
            winner = check_game_winner(current_bb)
            if winner != WinStatus.NO_WIN:
                return 1.0 if winner == WinStatus.PLAYER_0_WINS else -1.0

            current_player, moves_by_shape = generate_legal_moves(current_bb)
            all_moves = [
                m for shape_moves in moves_by_shape.values() for m in shape_moves
            ]
            if not all_moves:
                return -1.0 if current_player == 0 else 1.0

            move = self._rng.choice(all_moves)
            current_bb = apply_move(current_bb, move)  # type: ignore[assignment]

    def get_statistics(self) -> dict:
        """Get beam search tree statistics (mirrors `MCTSEngine.get_statistics`)."""
        return {
            "nodes_created": self.tree.storage.node_count,
            "memory_usage": self.tree.memory_usage(),
            "tree_stats": self.tree.get_stats(),
        }
