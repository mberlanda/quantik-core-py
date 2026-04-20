"""
Monte Carlo Tree Search (MCTS) implementation for Quantik.

Implements the UCT (Upper Confidence Bounds for Trees) algorithm with
integration into the compact game tree structure.
"""

import math
import random
from typing import Optional, Tuple
from dataclasses import dataclass
import numpy as np

from quantik_core import State, Move, generate_legal_moves, apply_move
from quantik_core.commons import Bitboard
from quantik_core.game_utils import check_game_winner, WinStatus
from quantik_core.memory.compact_tree import (
    CompactGameTree,
    NODE_FLAG_TERMINAL,
    NODE_FLAG_WINNING_P0,
    NODE_FLAG_WINNING_P1,
    NODE_FLAG_EXPANDED,
)


@dataclass
class MCTSConfig:
    """Configuration for MCTS algorithm."""

    exploration_weight: float = 1.414  # sqrt(2) for UCB1
    max_iterations: int = 10000  # Maximum number of MCTS iterations
    max_depth: int = 16  # Maximum search depth
    random_seed: Optional[int] = None  # Seed for reproducibility
    use_transposition_table: bool = True  # Use existing tree nodes


class MCTSEngine:
    """
    Monte Carlo Tree Search engine for Quantik.

    Uses UCB1 (Upper Confidence Bounds) for node selection and
    integrates with the compact game tree for memory efficiency.
    """

    def __init__(self, config: MCTSConfig):
        """Initialize MCTS engine with configuration."""
        self.config = config
        if config.random_seed is not None:
            random.seed(config.random_seed)

        self.tree = CompactGameTree(initial_capacity=100_000)
        self.root_id: Optional[int] = None
        self.iterations_performed = 0

    def search(self, initial_state: State) -> Tuple[Move, float]:
        """
        Perform MCTS search from initial state.

        Args:
            initial_state: Starting game state

        Returns:
            Tuple of (best_move, win_probability)
        """
        # Create or find root node
        self.root_id = self.tree.create_root_node(initial_state)
        self.iterations_performed = 0

        # Perform MCTS iterations
        for _ in range(self.config.max_iterations):
            # Selection: traverse tree using UCB
            node_id = self._select(self.root_id)

            # Expansion: add new child if not terminal
            node = self.tree.get_node(node_id)
            if not (node.flags & NODE_FLAG_TERMINAL):
                child_id = self._expand(node_id)
                if child_id is not None:
                    node_id = child_id

            # Simulation: play out random game
            value = self._simulate(node_id)

            # Backpropagation: update statistics
            self._backpropagate(node_id, value)

            self.iterations_performed += 1

        # Extract best move
        return self._get_best_move()

    def _select(self, node_id: int) -> int:
        """
        Select most promising node using UCB1.

        Args:
            node_id: Starting node ID

        Returns:
            Selected node ID
        """
        current_id = node_id

        while True:
            node = self.tree.get_node(current_id)

            # If terminal or not expanded, return this node
            if (node.flags & NODE_FLAG_TERMINAL) or not (
                node.flags & NODE_FLAG_EXPANDED
            ):
                return current_id

            # Get children
            children = self.tree.get_children(current_id)
            if not children:
                return current_id

            # Select child with highest UCB value
            best_ucb = -float("inf")
            best_child = children[0]

            for child_id in children:
                ucb_value = self._calculate_ucb(current_id, child_id)
                if ucb_value > best_ucb:
                    best_ucb = ucb_value
                    best_child = child_id

            current_id = best_child

    def _calculate_ucb(self, parent_id: int, child_id: int) -> float:
        """
        Calculate UCB1 value for a child node.

        UCB1 = win_rate + c * sqrt(ln(parent_visits) / child_visits)

        Args:
            parent_id: Parent node ID
            child_id: Child node ID

        Returns:
            UCB1 value
        """
        parent = self.tree.get_node(parent_id)
        child = self.tree.get_node(child_id)

        # If child unvisited, return infinity (explore first)
        if child.visit_count == 0:
            return float("inf")

        # If parent unvisited, return child win rate only
        if parent.visit_count == 0:
            player = int(child.player_turn)
            if player == 0:
                wins = child.win_count_p0
            else:
                wins = child.win_count_p1
            return wins / child.visit_count

        # Calculate win rate from perspective of current player
        player = int(child.player_turn)
        if player == 0:
            wins = child.win_count_p0
        else:
            wins = child.win_count_p1

        win_rate = wins / child.visit_count

        # UCB1 formula
        exploitation = win_rate
        exploration = self.config.exploration_weight * math.sqrt(
            math.log(parent.visit_count) / child.visit_count
        )

        return exploitation + exploration

    def _expand(self, node_id: int) -> Optional[int]:
        """
        Expand node by adding one unvisited child.

        Args:
            node_id: Node to expand

        Returns:
            ID of newly added child, or None if no children possible
        """
        node = self.tree.get_node(node_id)
        state = self.tree.get_state(node_id)

        # Check if already terminal
        winner = check_game_winner(state.bb)
        if winner != WinStatus.NO_WIN:
            # Mark as terminal
            flags = node.flags | NODE_FLAG_TERMINAL
            if winner == WinStatus.PLAYER_0_WINS:
                flags |= NODE_FLAG_WINNING_P0
                node.terminal_value = np.float32(1.0)
            else:
                flags |= NODE_FLAG_WINNING_P1
                node.terminal_value = np.float32(-1.0)

            node.flags = np.uint8(flags)
            self.tree.storage.store_node(node_id, node)
            return None

        # Generate legal moves
        current_player, moves_by_shape = generate_legal_moves(state.bb)
        all_moves = []
        for shape_moves in moves_by_shape.values():
            all_moves.extend(shape_moves)

        if not all_moves:
            # No legal moves - the player who cannot move loses (opponent wins)
            node.flags = np.uint8(node.flags | NODE_FLAG_TERMINAL)
            if int(node.player_turn) == 0:
                node.flags = np.uint8(node.flags | NODE_FLAG_WINNING_P1)
                node.terminal_value = np.float32(-1.0)
            else:
                node.flags = np.uint8(node.flags | NODE_FLAG_WINNING_P0)
                node.terminal_value = np.float32(1.0)
            self.tree.storage.store_node(node_id, node)
            return None

        # Get existing children to find unvisited move
        existing_children = self.tree.get_children(node_id)
        existing_states = set()
        for child_id in existing_children:
            child_state = self.tree.get_state(child_id)
            existing_states.add(child_state.canonical_key())

        # Find first move that creates a new state
        for move in all_moves:
            new_bb = apply_move(state.bb, move)
            new_state = State(new_bb)

            if new_state.canonical_key() not in existing_states:
                # Add this child
                child_id = self.tree.add_child_node(node_id, new_state)

                # Mark parent as expanded if all moves tried
                if len(existing_children) + 1 == len(all_moves):
                    node.flags = np.uint8(node.flags | NODE_FLAG_EXPANDED)
                    self.tree.storage.store_node(node_id, node)

                return child_id

        # All moves already expanded
        node.flags = np.uint8(node.flags | NODE_FLAG_EXPANDED)
        self.tree.storage.store_node(node_id, node)
        return None

    def _simulate(self, node_id: int) -> float:
        """
        Simulate random playout from node.

        Args:
            node_id: Starting node for simulation

        Returns:
            Game result from perspective of player 0 (1.0 = win, 0.0 = draw, -1.0 = loss)
        """
        node = self.tree.get_node(node_id)

        # If terminal, return known value
        if node.flags & NODE_FLAG_TERMINAL:
            if node.flags & NODE_FLAG_WINNING_P0:
                return 1.0
            elif node.flags & NODE_FLAG_WINNING_P1:
                return -1.0
            else:
                return 0.0

        # Start simulation from this state
        state = self.tree.get_state(node_id)
        current_bb: Bitboard = state.bb
        depth = int(node.depth)

        # Random playout until terminal or max depth
        while depth < self.config.max_depth:
            # Check for win
            winner = check_game_winner(current_bb)
            if winner != WinStatus.NO_WIN:
                if winner == WinStatus.PLAYER_0_WINS:
                    return 1.0
                else:
                    return -1.0

            # Generate legal moves
            current_player, moves_by_shape = generate_legal_moves(current_bb)
            all_moves = []
            for shape_moves in moves_by_shape.values():
                all_moves.extend(shape_moves)

            if not all_moves:
                # No legal moves: player who cannot move loses
                return -1.0 if current_player == 0 else 1.0

            # Pick random move
            move = random.choice(all_moves)
            current_bb = apply_move(current_bb, move)  # type: ignore[assignment]
            depth += 1

        # Reached max depth without resolution
        return 0.0

    def _backpropagate(self, node_id: int, value: float) -> None:
        """
        Backpropagate simulation result up the tree.

        Args:
            node_id: Starting node (leaf)
            value: Simulation result (1.0, 0.0, or -1.0)
        """
        current_id = node_id

        while current_id is not None:
            node = self.tree.get_node(current_id)

            # Update visit count
            node.visit_count = np.uint32(node.visit_count + 1)

            # Update win counts based on value and player perspective
            if value > 0:  # Player 0 win
                node.win_count_p0 = np.uint32(node.win_count_p0 + 1)
            elif value < 0:  # Player 1 win
                node.win_count_p1 = np.uint32(node.win_count_p1 + 1)

            # Update best value (running average)
            current_value = float(node.best_value)
            visits = int(node.visit_count)
            new_value = current_value + (value - current_value) / visits
            node.best_value = np.float32(new_value)

            # Store updated node
            self.tree.storage.store_node(current_id, node)

            # Stop at root
            if current_id == self.root_id:
                break

            # Move to parent
            parent_id = int(node.parent_id)
            current_id = parent_id

    def _get_best_move(self) -> Tuple[Move, float]:  # noqa: C901
        """
        Extract best move from root node.

        Returns:
            Tuple of (best_move, win_probability)
        """
        if self.root_id is None:
            raise ValueError("No search performed yet")

        root_state = self.tree.get_state(self.root_id)

        # Get all children
        children = self.tree.get_children(self.root_id)
        if not children:
            # No children expanded - return random legal move
            current_player, moves_by_shape = generate_legal_moves(root_state.bb)
            all_moves = []
            for shape_moves in moves_by_shape.values():
                all_moves.extend(shape_moves)

            if not all_moves:
                raise ValueError("No moves available")
            return all_moves[0], 0.5

        # Find child with most visits (robust child selection)
        best_child_id: int = children[0]
        best_visits = -1
        best_win_rate = 0.0

        for child_id in children:
            child = self.tree.get_node(child_id)
            if child.visit_count > best_visits:
                best_visits = int(child.visit_count)
                best_child_id = child_id

                # Calculate win rate for player 0
                if child.visit_count > 0:
                    best_win_rate = child.win_count_p0 / child.visit_count

        # Find the move that leads to best child
        best_child_state = self.tree.get_state(best_child_id)
        current_player, moves_by_shape = generate_legal_moves(root_state.bb)

        all_moves = []
        for shape_moves in moves_by_shape.values():
            all_moves.extend(shape_moves)

        for move in all_moves:
            new_bb = apply_move(root_state.bb, move)
            new_state = State(new_bb)
            if new_state.canonical_key() == best_child_state.canonical_key():
                return move, best_win_rate

        # Fallback (should not happen)
        return all_moves[0], 0.5

    def get_statistics(self) -> dict:
        """Get MCTS statistics."""
        return {
            "iterations": self.iterations_performed,
            "nodes_created": self.tree.storage.node_count,
            "memory_usage": self.tree.memory_usage(),
            "tree_stats": self.tree.get_stats(),
        }
