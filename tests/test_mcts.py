"""Tests for MCTS implementation."""

import random
from unittest.mock import patch

import pytest
import numpy as np
from quantik_core import State, Move
from quantik_core.mcts import MCTSEngine, MCTSConfig
from quantik_core.move import generate_legal_moves_list
from quantik_core.memory.compact_tree import (
    NODE_FLAG_TERMINAL,
    NODE_FLAG_WINNING_P0,
    NODE_FLAG_WINNING_P1,
)
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

        # P0: A at (0,0), B at (0,1); P1: c at (0,2), d at (1,0). Two
        # immediate wins exist here: D at (0,3) completes row 0 (A,B,C,D),
        # and C at (1,1) completes the top-left quadrant (A,B,d,C) --
        # verified against MinimaxEngine.solve() and has_winning_line.
        state = State.from_qfen("ABc./d.../..../....")
        move, win_prob = engine.search(state)

        # Should find a winning move with high confidence. Regression:
        # before fixing (1) CompactGameTree.create_root_node marking the
        # root already-expanded and (2) _calculate_ucb using the child's
        # own player_turn instead of the parent's mover to pick the win
        # count, this returned win_prob=0.276 for a NON-winning move.
        from quantik_core import apply_move
        from quantik_core.game_utils import has_winning_line

        assert isinstance(move, Move)
        assert has_winning_line(apply_move(state.bb, move))
        assert win_prob > 0.9

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

    def test_ucb_uses_parent_movers_perspective_not_childs(self):
        """Regression: UCB must select by win rate for the PARENT's mover.

        add_child_node always sets child.player_turn = 1 - parent.player_turn,
        so using the child's own player_turn to pick which win_count
        field to read selects by how often the OPPONENT won through that
        child -- the exact opposite of what UCB1 should optimize for the
        player actually choosing among these children. Concretely: a
        child where the root's own mover (P0) won 9/10 simulated games
        must score HIGHER than a child where P0 only won 1/10, not lower.
        """
        engine = MCTSEngine(MCTSConfig(random_seed=1))
        root_id = engine.tree.create_root_node(State.from_qfen("..../..../..../...."))
        root = engine.tree.get_node(root_id)
        assert int(root.player_turn) == 0  # P0 to move at the root

        good_for_root_id = engine.tree.add_child_node(
            root_id, State.from_qfen("A.../..../..../....")
        )
        bad_for_root_id = engine.tree.add_child_node(
            root_id, State.from_qfen(".A../..../..../....")
        )

        good = engine.tree.get_node(good_for_root_id)
        good.visit_count = np.uint32(10)
        good.win_count_p0 = np.uint32(9)  # good for P0 (the root's mover)
        good.win_count_p1 = np.uint32(1)
        engine.tree.storage.store_node(good_for_root_id, good)

        bad = engine.tree.get_node(bad_for_root_id)
        bad.visit_count = np.uint32(10)
        bad.win_count_p0 = np.uint32(1)  # bad for P0
        bad.win_count_p1 = np.uint32(9)
        engine.tree.storage.store_node(bad_for_root_id, bad)

        root.visit_count = np.uint32(20)
        engine.tree.storage.store_node(root_id, root)

        ucb_good = engine._calculate_ucb(root_id, good_for_root_id)
        ucb_bad = engine._calculate_ucb(root_id, bad_for_root_id)
        assert ucb_good > ucb_bad

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

    def test_root_explores_multiple_children_not_stuck_at_one(self):
        """Regression: the root must gain more than one child over several
        search iterations.

        Before fixing CompactGameTree.create_root_node (it marked the root
        NODE_FLAG_EXPANDED at creation instead of only once every legal
        move had a child), MCTSEngine._select treated the root as fully
        explored as soon as it had a single child, so the root got exactly
        one explored child for the entire search regardless of
        max_iterations. A wide-branching position run for enough
        iterations to clearly exceed one-child-only behavior must now show
        multiple root children.
        """
        state = State.from_qfen("..../..../..../....")
        engine = MCTSEngine(MCTSConfig(max_iterations=200, random_seed=1))
        engine.search(state)

        assert engine.root_id is not None
        root_children = engine.tree.get_children(engine.root_id)
        assert len(root_children) > 1

    def test_expand_wires_use_transposition_table_enabled(self):
        """_expand must forward config.use_transposition_table to the tree.

        MCTSConfig.use_transposition_table was previously declared but never
        consulted; this pins that _expand actually threads it through to
        CompactGameTree.add_child_node rather than silently always merging.
        """
        config = MCTSConfig(random_seed=42, use_transposition_table=True)
        engine = MCTSEngine(config)
        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)

        with patch.object(
            engine.tree, "add_child_node", wraps=engine.tree.add_child_node
        ) as spy:
            engine._expand(root_id)

        spy.assert_called_once()
        assert spy.call_args.kwargs["use_transposition_table"] is True

    def test_expand_wires_use_transposition_table_disabled(self):
        """Mutation guard: flipping the config value must flip the call arg."""
        config = MCTSConfig(random_seed=42, use_transposition_table=False)
        engine = MCTSEngine(config)
        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)

        with patch.object(
            engine.tree, "add_child_node", wraps=engine.tree.add_child_node
        ) as spy:
            engine._expand(root_id)

        spy.assert_called_once()
        assert spy.call_args.kwargs["use_transposition_table"] is False

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
            child_state = State.from_qfen(f"{chr(ord('A') + i)}.../..../..../....")
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
        config1 = MCTSConfig(exploration_weight=0.5, max_iterations=100, random_seed=42)
        engine1 = MCTSEngine(config1)
        move1, prob1 = engine1.search(state)

        # High exploration
        config2 = MCTSConfig(exploration_weight=2.0, max_iterations=100, random_seed=42)
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

    def test_expand_stalemate_player0_loses(self):
        """Test _expand marks node terminal when player 0 has no legal moves."""
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)

        with (
            patch("quantik_core.mcts.check_game_winner", return_value=WinStatus.NO_WIN),
            patch("quantik_core.mcts.generate_legal_moves", return_value=(0, {})),
        ):
            result = engine._expand(root_id)

        assert result is None
        node = engine.tree.get_node(root_id)
        assert node.flags & NODE_FLAG_TERMINAL
        assert node.flags & NODE_FLAG_WINNING_P1
        assert float(node.terminal_value) == pytest.approx(-1.0)

    def test_expand_stalemate_player1_loses(self):
        """Test _expand marks node terminal when player 1 has no legal moves."""
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)

        # Create a child node so player_turn == 1
        child_state = State.from_qfen("A.../..../..../....")
        child_id = engine.tree.add_child_node(root_id, child_state)

        with (
            patch("quantik_core.mcts.check_game_winner", return_value=WinStatus.NO_WIN),
            patch("quantik_core.mcts.generate_legal_moves", return_value=(1, {})),
        ):
            result = engine._expand(child_id)

        assert result is None
        node = engine.tree.get_node(child_id)
        assert node.flags & NODE_FLAG_TERMINAL
        assert node.flags & NODE_FLAG_WINNING_P0
        assert float(node.terminal_value) == pytest.approx(1.0)

    def test_expand_stalemate_at_p1_rooted_tree_attributes_p0_win(self):
        """Rooting directly at a P1-to-move state must attribute the win correctly.

        Integration guard for the create_root_node player_turn derivation:
        the tree is rooted at a state where player 0 has already moved once
        (so player 1 is to move), and player 1 is then blocked. The blocked
        player loses, so player 0 must be recorded as the winner.

        This exercises the fix's downstream consequence, not just the
        isolated derivation: if create_root_node reverted to hardcoding
        player_turn=0, the root would be treated as player-0-to-move and
        the stalemate would be mis-attributed as a player-1 win, flipping
        both the winning flag and the terminal value. The sibling
        test_expand_stalemate_player1_loses cannot catch that regression
        because it reaches player_turn==1 via a child of the root rather
        than the root itself.
        """
        config = MCTSConfig(random_seed=42)
        engine = MCTSEngine(config)

        # Player 0 has placed one piece -> player 1 is to move at the root.
        state = State.from_qfen("A.../..../..../....")
        root_id = engine.tree.create_root_node(state)
        assert int(engine.tree.get_node(root_id).player_turn) == 1

        with (
            patch("quantik_core.mcts.check_game_winner", return_value=WinStatus.NO_WIN),
            patch("quantik_core.mcts.generate_legal_moves", return_value=(1, {})),
        ):
            result = engine._expand(root_id)

        assert result is None
        node = engine.tree.get_node(root_id)
        assert node.flags & NODE_FLAG_TERMINAL
        assert node.flags & NODE_FLAG_WINNING_P0
        assert not (node.flags & NODE_FLAG_WINNING_P1)
        assert float(node.terminal_value) == pytest.approx(1.0)

    def test_simulate_stalemate_player0(self):
        """Test _simulate returns correct value when player 0 has no moves."""
        config = MCTSConfig(max_depth=16, random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        node_id = engine.tree.create_root_node(state)

        with (
            patch("quantik_core.mcts.check_game_winner", return_value=WinStatus.NO_WIN),
            patch("quantik_core.mcts.generate_legal_moves", return_value=(0, {})),
        ):
            value = engine._simulate(node_id)

        assert value == -1.0

    def test_simulate_stalemate_player1(self):
        """Test _simulate returns correct value when player 1 has no moves."""
        config = MCTSConfig(max_depth=16, random_seed=42)
        engine = MCTSEngine(config)

        state = State.from_qfen("..../..../..../....")
        root_id = engine.tree.create_root_node(state)
        child_state = State.from_qfen("A.../..../..../....")
        child_id = engine.tree.add_child_node(root_id, child_state)

        with (
            patch("quantik_core.mcts.check_game_winner", return_value=WinStatus.NO_WIN),
            patch("quantik_core.mcts.generate_legal_moves", return_value=(1, {})),
        ):
            value = engine._simulate(child_id)

        assert value == 1.0


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


class TestMCTSTimeLimit:
    """Optional wall-clock budget on MCTSEngine.search."""

    _QFEN = ".ba./..CC/DcbD/cA.A"  # fast near-endgame anchor, P1 to move

    def test_time_limit_stops_before_max_iterations(self):
        from quantik_core.mcts import MCTSConfig, MCTSEngine

        engine = MCTSEngine(
            MCTSConfig(max_iterations=10_000_000, time_limit_s=0.05, random_seed=0)
        )
        state = State.from_qfen(self._QFEN)
        move, _ = engine.search(state)
        assert engine.iterations_performed < 10_000_000
        assert move in generate_legal_moves_list(state.bb)

    def test_time_limit_always_runs_at_least_one_iteration(self):
        from quantik_core.mcts import MCTSConfig, MCTSEngine

        engine = MCTSEngine(
            MCTSConfig(max_iterations=100, time_limit_s=1e-9, random_seed=0)
        )
        engine.search(State.from_qfen(self._QFEN))
        assert engine.iterations_performed >= 1

    def test_no_time_limit_runs_all_iterations(self):
        from quantik_core.mcts import MCTSConfig, MCTSEngine

        engine = MCTSEngine(MCTSConfig(max_iterations=50, random_seed=0))
        engine.search(State.from_qfen(self._QFEN))
        assert engine.iterations_performed == 50

    def test_non_positive_time_limit_rejected(self):
        from quantik_core.mcts import MCTSConfig, MCTSEngine

        with pytest.raises(ValueError):
            MCTSEngine(MCTSConfig(time_limit_s=0.0))
        with pytest.raises(ValueError):
            MCTSEngine(MCTSConfig(time_limit_s=-1.0))


class TestEvalGuidedRollouts:
    """Tests for the opt-in eval-guided rollout policy."""

    def test_rejects_out_of_range_rollout_epsilon(self):
        from quantik_core.evaluation import EvalConfig

        for bad_epsilon in (-0.1, 1.1):
            with pytest.raises(ValueError):
                MCTSEngine(
                    MCTSConfig(
                        rollout_eval_config=EvalConfig(),
                        rollout_epsilon=bad_epsilon,
                    )
                )

    def test_rollout_epsilon_out_of_range_ignored_without_eval_config(self):
        # No validation needed when rollout_eval_config is None -- epsilon
        # is unused in that path.
        MCTSEngine(MCTSConfig(rollout_eval_config=None, rollout_epsilon=5.0))

    def test_rollout_move_defaults_to_random_when_no_eval(self):
        # With no eval config, the helper must just pick from the legal moves.
        from quantik_core.move import generate_legal_moves_list

        engine = MCTSEngine(MCTSConfig(max_iterations=1, random_seed=0))
        bb = State.from_qfen("A.../..../..../....").bb
        legal = generate_legal_moves_list(bb)
        move = engine._select_rollout_move(bb, 1, legal)
        assert move in legal

    def test_eval_guided_rollout_is_deterministic_and_legal(self):
        from quantik_core.evaluation import EvalConfig
        from quantik_core.move import generate_legal_moves_list

        bb = State.from_qfen("Ab../..Cd/..../....").bb
        legal = generate_legal_moves_list(bb)
        cfg = MCTSConfig(
            max_iterations=1,
            random_seed=7,
            rollout_eval_config=EvalConfig(),
            rollout_epsilon=0.0,
        )
        # epsilon=0 => pure greedy argmax over evaluate; deterministic.
        m1 = MCTSEngine(cfg)._select_rollout_move(bb, 0, legal)
        m2 = MCTSEngine(cfg)._select_rollout_move(bb, 0, legal)
        assert m1 == m2 and m1 in legal

    def test_rollout_epsilon_zero_does_not_consume_a_random_draw(self):
        # Regression: with rollout_epsilon<=0, the epsilon draw must be
        # skipped entirely rather than calling random.random() only to
        # compare it against a value it can never be less than -- that
        # would needlessly advance the shared global RNG state on every
        # eval-guided rollout step.
        from quantik_core.evaluation import EvalConfig
        from quantik_core.move import generate_legal_moves_list

        bb = State.from_qfen("Ab../..Cd/..../....").bb
        legal = generate_legal_moves_list(bb)
        engine = MCTSEngine(
            MCTSConfig(
                max_iterations=1,
                random_seed=7,
                rollout_eval_config=EvalConfig(),
                rollout_epsilon=0.0,
            )
        )
        state_before = random.getstate()
        engine._select_rollout_move(bb, 0, legal)
        assert random.getstate() == state_before

    def test_rollout_move_prefers_immediate_win_over_heuristic_score(self):
        # Regression: evaluate() expects a non-terminal position and its
        # linear heuristic score isn't guaranteed to rank a decided win
        # above a merely good-looking non-winning alternative. An
        # immediately-decisive candidate move must always win the greedy
        # pick outright, without being scored by evaluate() at all. Anchor
        # has exactly 2 legal moves: one decisive (D at pos 2, completes a
        # line), one not (D at pos 0) -- verified directly against
        # has_winning_line/generate_legal_moves_list before writing this.
        from quantik_core.evaluation import EvalConfig
        from quantik_core.move import generate_legal_moves_list

        bb = State.from_qfen(".B.A/a.b./.CCd/bdA.").bb
        legal = generate_legal_moves_list(bb)
        decisive_move = Move(player=0, shape=3, position=2)
        non_decisive_move = Move(player=0, shape=3, position=0)
        assert set(legal) == {decisive_move, non_decisive_move}
        cfg = MCTSConfig(
            max_iterations=1,
            random_seed=0,
            rollout_eval_config=EvalConfig(),
            rollout_epsilon=0.0,
        )
        move = MCTSEngine(cfg)._select_rollout_move(bb, 0, legal)
        assert move == decisive_move

    def test_eval_guided_search_runs_end_to_end(self):
        # Integration smoke test: eval-guided rollouts must complete a real
        # search() and return a legal move with a sane win probability.
        # This position (near-empty, 42 legal moves at the root -- P1 to
        # move, with a mate-in-one at shape=3/pos=3) previously required a
        # downgraded, non-move-specific assertion here (see git history):
        # CompactGameTree.create_root_node marked the root already-
        # expanded, so MCTS's root got exactly one explored child
        # regardless of iteration budget, and _calculate_ucb separately
        # used the child's own player_turn instead of the parent's mover
        # to pick the win-rate perspective, inverting exploitation
        # entirely. With both fixed, MCTS reliably finds the actual
        # mate-in-one here -- restored to the plan's originally-intended
        # assertion.
        from quantik_core.evaluation import EvalConfig
        from quantik_core.move import generate_legal_moves_list

        cfg = MCTSConfig(
            max_iterations=400,
            random_seed=1,
            rollout_eval_config=EvalConfig.load(),
            rollout_epsilon=0.2,
        )
        state = State.from_qfen("AbC./..../..../....")
        best_move, win_prob = MCTSEngine(cfg).search(state)
        assert best_move in generate_legal_moves_list(state.bb)
        assert best_move.shape == 3 and best_move.position == 3
        assert 0.0 <= win_prob <= 1.0

    def test_default_mcts_unchanged(self):
        # Regression: default config still returns a legal move; no eval used.
        best_move, prob = MCTSEngine(
            MCTSConfig(max_iterations=200, random_seed=0)
        ).search(State.from_qfen("ABc./d.../..../...."))
        assert best_move is not None and 0.0 <= prob <= 1.0

    def test_default_config_behavior_is_byte_for_byte_unchanged(self):
        # Binding constraint: rollout_eval_config=None must reproduce the
        # exact same search result as before this feature existed, since
        # _select_rollout_move's cfg-is-None branch consumes random draws
        # identically to the original `random.choice(all_moves)` call site
        # it replaced (no extra random numbers drawn before returning).
        # Reference value captured by running this exact scenario against
        # mcts.py BEFORE this feature was added.
        state = State.from_qfen("AB../cd../..../....")
        move, prob = MCTSEngine(MCTSConfig(max_iterations=100, random_seed=42)).search(
            state
        )
        assert move == Move(player=0, shape=0, position=2)
        assert prob == 0.5
