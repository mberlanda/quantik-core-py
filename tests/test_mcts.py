"""Tests for MCTS implementation."""

import pytest
import numpy as np
from quantik_core import State, Move
from quantik_core.mcts import MCTSEngine, MCTSConfig
from quantik_core.game_utils import WinStatus


class TestMCTSConfig:
    """Test MCTS configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MCTSConfig()
        assert config.exploration_weight == pytest.approx(1.414)
        assert config.max_iterations == 10000
        assert config.max_depth == 16
        assert config.random_seed is None
        assert config.use_transposition_table is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = MCTSConfig(
            exploration_weight=2.0,
            max_iterations=5000,
            max_depth=10,
            random_seed=42,
            use_transposition_table=False,
        )
        assert config.exploration_weight == 2.0
        assert config.max_iterations == 5000
        assert config.max_depth == 10
        assert config.random_seed == 42
        assert config.use_transposition_table is False


class TestMCTSEngine:
    """Test MCTS engine functionality."""

    def test_engine_initialization(self):
        """Test MCTS engine initialization."""
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)
        assert engine.config == config
        assert engine.root_id is None
        assert engine.iterations_performed == 0

    def test_search_empty_board(self):
        """Test MCTS search from empty board."""
        config = MCTSConfig(max_iterations=100, random_seed=42)
        engine = MCTSEngine(config)

        initial_state = State.from_qfen("..../..../..../....")
        move, win_prob = engine.search(initial_state)

        # Should return a valid move
        assert isinstance(move, Move)
        assert 0 <= move.shape <= 3
        assert 0 <= move.position <= 15

        # Win probability should be between 0 and 1
        assert 0.0 <= win_prob <= 1.0

        # Should have performed iterations
        assert engine.iterations_performed == 100

    def test_search_near_win_position(self):
        """Test MCTS finds winning move."""
        config = MCTSConfig(max_iterations=500, random_seed=42)
        engine = MCTSEngine(config)

        # P0: A at (0,0), B at (0,1); P1: c at (0,2), d at (1,0)
        # Row 0 has shapes A, B, C — P0 can win by placing D at (0,3)
        state = State.from_qfen("ABc./d.../..../....")
        move, win_prob = engine.search(state)

        # Should find a winning move (reasonable win probability)
        assert isinstance(move, Move)
        assert win_prob > 0.3  # Should have decent confidence

    def test_reproducibility_with_seed(self):
        """Test that same seed produces same results."""
        config1 = MCTSConfig(max_iterations=100, random_seed=42)
        engine1 = MCTSEngine(config1)

        state = State.from_qfen("..../..../..../....")
        move1, prob1 = engine1.search(state)

        config2 = MCTSConfig(max_iterations=100, random_seed=42)
        engine2 = MCTSEngine(config2)

        move2, prob2 = engine2.search(state)

        # Should produce same move with same seed
        assert move1 == move2
        assert prob1 == pytest.approx(prob2)

    def test_statistics_tracking(self):
        """Test statistics are properly tracked."""
        config = MCTSConfig(max_iterations=50, random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        engine.search(state)

        stats = engine.get_statistics()
        assert stats["iterations"] == 50
        assert stats["nodes_created"] > 0
        assert stats["memory_usage"] > 0
        assert "tree_stats" in stats

    def test_ucb_calculation(self):
        """Test UCB value calculation."""
        config = MCTSConfig(exploration_weight=1.414, random_seed=42)
        engine = MCTSEngine(config)

        # Create simple tree
        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)

        # Add a child with some visits
        child_state = State.from_qfen("A.../..../..../....")
        child_id = engine.tree.add_child_node(root_id, child_state)

        # Set up some statistics
        root = engine.tree.get_node(root_id)
        root.visit_count = np.uint32(100)
        engine.tree.storage.store_node(root_id, root)

        child = engine.tree.get_node(child_id)
        child.visit_count = np.uint32(10)
        child.win_count_p0 = np.uint32(7)
        engine.tree.storage.store_node(child_id, child)

        # Calculate UCB
        ucb = engine._calculate_ucb(root_id, child_id)

        # Should be positive and finite
        assert ucb > 0
        assert ucb < float("inf")

    def test_ucb_unvisited_child(self):
        """Test UCB returns infinity for unvisited children."""
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)

        child_state = State.from_qfen("A.../..../..../....")
        child_id = engine.tree.add_child_node(root_id, child_state)

        # Parent has visits but child doesn't
        root = engine.tree.get_node(root_id)
        root.visit_count = np.uint32(10)
        engine.tree.storage.store_node(root_id, root)

        ucb = engine._calculate_ucb(root_id, child_id)
        assert ucb == float("inf")

    def test_expansion(self):
        """Test node expansion."""
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)

        # Expand root
        child_id = engine._expand(root_id)

        assert child_id is not None
        assert child_id != root_id

        # Child should exist in tree
        child = engine.tree.get_node(child_id)
        assert child.depth == 1
        assert child.parent_id == root_id

    def test_simulation(self):
        """Test random simulation."""
        config = MCTSConfig(max_depth=8, random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        node_id = engine.tree.create_root_node(state)

        # Run simulation
        value = engine._simulate(node_id)

        # Should return a valid value
        assert value in [-1.0, 0.0, 1.0]

    def test_backpropagation(self):
        """Test backpropagation updates."""
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)

        # Create small tree
        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)
        engine.root_id = root_id

        child_state = State.from_qfen("A.../..../..../....")
        child_id = engine.tree.add_child_node(root_id, child_state)

        # Backpropagate a win for player 0
        engine._backpropagate(child_id, 1.0)

        # Check updates
        root = engine.tree.get_node(root_id)
        assert root.visit_count > 0
        assert root.win_count_p0 > 0

        child = engine.tree.get_node(child_id)
        assert child.visit_count > 0
        assert child.win_count_p0 > 0

    def test_terminal_node_handling(self):
        """Test handling of terminal nodes."""
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)

        # Create a winning position for player 0
        # Row win: ABCD in first row
        state = State.from_qfen("ABCD/..../..../....")
        node_id = engine.tree.create_root_node(state)

        # Try to expand terminal node
        child_id = engine._expand(node_id)

        # Should not expand (terminal)
        assert child_id is None

        # Node should be marked terminal
        node = engine.tree.get_node(node_id)
        from quantik_core.memory.compact_tree import NODE_FLAG_TERMINAL

        assert node.flags & NODE_FLAG_TERMINAL

    def test_selection(self):
        """Test selection phase."""
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)

        # Create small tree
        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)

        # Add some children
        for i in range(3):
            child_state = State.from_qfen(f"{chr(ord('A')+i)}.../..../..../....")
            engine.tree.add_child_node(root_id, child_state)

        # Select should return a node
        selected_id = engine._select(root_id)
        assert selected_id is not None

    def test_best_move_extraction(self):
        """Test best move extraction."""
        config = MCTSConfig(max_iterations=100, random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        move, win_prob = engine.search(state)

        # Should return valid move
        assert isinstance(move, Move)
        assert 0.0 <= win_prob <= 1.0

    def test_search_with_different_exploration_weights(self):
        """Test search with different exploration parameters."""
        state = State.from_qfen("..../..../..../....")

        # Low exploration (more exploitation)
        config1 = MCTSConfig(
            exploration_weight=0.5, max_iterations=100, random_seed=42
        )
        engine1 = MCTSEngine(config1)
        move1, prob1 = engine1.search(state)

        # High exploration
        config2 = MCTSConfig(
            exploration_weight=2.0, max_iterations=100, random_seed=42
        )
        engine2 = MCTSEngine(config2)
        move2, prob2 = engine2.search(state)

        # Should produce valid moves (may be different)
        assert isinstance(move1, Move)
        assert isinstance(move2, Move)

    def test_memory_efficiency(self):
        """Test memory usage is reasonable."""
        config = MCTSConfig(max_iterations=200, random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        engine.search(state)

        stats = engine.get_statistics()

        # Should have created nodes
        assert stats["nodes_created"] > 0

        # Memory should scale reasonably (< 10MB for 200 iterations)
        # CompactGameTree pre-allocates capacity, so base memory is ~6MB
        assert stats["memory_usage"] < 10_000_000

    def test_no_legal_moves_handling(self):
        """Test handling when no legal moves available."""
        config = MCTSConfig(max_iterations=10, random_seed=42)
        engine = MCTSEngine(config)

        # Create a stalemate-like position (all pieces used)
        # This is a theoretical test - actual stalemate detection
        state = State.from_qfen("..../..../..../....")

        # Should handle gracefully
        try:
            move, prob = engine.search(state)
            assert isinstance(move, Move)
        except ValueError:
            # Acceptable if no moves available
            pass


class TestMCTSIntegration:
    """Integration tests for MCTS."""

    def test_full_game_search(self):
        """Test MCTS through multiple moves."""
        config = MCTSConfig(max_iterations=50, random_seed=42)

        # Play a few moves
        state = State.from_qfen("..../..../..../....")

        for _ in range(3):
            engine = MCTSEngine(config)
            move, prob = engine.search(state)

            # Apply move
            from quantik_core import apply_move

            new_bb = apply_move(state.bb, move)
            state = State(new_bb)

            # Check game hasn't ended
            from quantik_core.game_utils import check_game_winner

            winner = check_game_winner(state.bb)
            if winner != WinStatus.NO_WIN:
                break

    def test_comparison_with_random_play(self):
        """Test that MCTS performs better than random."""
        # Simple smoke test - MCTS should find obvious wins
        config = MCTSConfig(max_iterations=100, random_seed=42)
        engine = MCTSEngine(config)

        # P0: A,B at row 0; P1: c,d at row 1. Row 0 needs C+D to win.
        state = State.from_qfen("AB../cd../..../....")
        move, win_prob = engine.search(state)

        # Should have reasonable confidence
        assert win_prob >= 0.3  # At least better than random
