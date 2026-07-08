"""Tests for the parametrizable beam search engine."""

from typing import Dict, List

import pytest

from quantik_core import State, Move, apply_move, generate_legal_moves
from quantik_core.beam_search import (
    BeamSearchConfig,
    BeamSearchEngine,
    BeamSearchResult,
    BeamLeaf,
    RankedRootMove,
    UNIQUE_CANONICAL_STATES_PER_DEPTH,
)
from quantik_core.mcts import MCTSEngine, MCTSConfig
from quantik_core.memory.compact_tree import (
    CompactGameTree,
    NODE_FLAG_TERMINAL,
    NODE_FLAG_WINNING_P0,
    NODE_FLAG_WINNING_P1,
)
from quantik_core.game_utils import check_game_winner, WinStatus

EMPTY_QFEN = "..../..../..../...."


class TestBeamSearchConfig:
    """Test beam search configuration defaults, custom values, validation."""

    def test_default_config(self):
        config = BeamSearchConfig()
        assert config.beam_width == 64
        assert config.max_depth == 16
        assert config.rollouts_per_candidate == 8
        assert config.random_seed is None
        assert config.evaluator is None
        assert config.initial_tree_capacity == 4096
        assert config.beam_schedule is None

    def test_custom_config(self):
        def evaluator(state: State) -> float:
            return 0.0

        config = BeamSearchConfig(
            beam_width=8,
            max_depth=4,
            rollouts_per_candidate=2,
            random_seed=7,
            evaluator=evaluator,
            initial_tree_capacity=128,
            beam_schedule=[3, 51, 8],
        )
        assert config.beam_width == 8
        assert config.max_depth == 4
        assert config.rollouts_per_candidate == 2
        assert config.random_seed == 7
        assert config.evaluator is evaluator
        assert config.initial_tree_capacity == 128
        assert config.beam_schedule == [3, 51, 8]

    def test_invalid_beam_width(self):
        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(beam_width=0))

    def test_invalid_max_depth_too_low(self):
        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(max_depth=0))

    def test_invalid_max_depth_too_high(self):
        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(max_depth=17))

    def test_invalid_rollouts_per_candidate(self):
        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(rollouts_per_candidate=0))

    def test_invalid_beam_schedule_empty(self):
        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(beam_schedule=[]))

    def test_invalid_beam_schedule_zero_entry(self):
        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(beam_schedule=[3, 0, 5]))

    def test_invalid_beam_schedule_negative_entry(self):
        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(beam_schedule=[3, -1]))


class TestBeamSearchEngine:
    """Test core beam search behavior."""

    def test_immediate_win_found(self):
        """Near-win fixture: best_leaf is the winning terminal at depth 1."""
        # P0: A at (0,0), B at (0,1); P1: c at (0,2), a at (3,3).
        # Row 0 has shapes A, B, C — P0 can win by placing D at (0,3), and
        # this is the *only* one-move win available from this position.
        config = BeamSearchConfig(
            beam_width=4, max_depth=2, rollouts_per_candidate=2, random_seed=1
        )
        engine = BeamSearchEngine(config)

        state = State.from_qfen("ABc./..../..../...a")
        result = engine.search(state)

        assert result.best_leaf is not None
        assert result.best_leaf.is_terminal
        assert result.best_leaf.depth == 1
        assert result.best_leaf.value == pytest.approx(1.0)
        assert len(result.best_leaf.moves) == 1
        winning_move = result.best_leaf.moves[0]
        assert winning_move.player == 0
        assert winning_move.shape == 3  # D
        assert winning_move.position == 3  # (0,3)

    def test_full_game_reachability(self):
        """From the empty board, a small seeded beam reaches true terminals."""
        config = BeamSearchConfig(
            beam_width=4, max_depth=16, rollouts_per_candidate=2, random_seed=42
        )
        engine = BeamSearchEngine(config)

        state = State.from_qfen(EMPTY_QFEN)
        result = engine.search(state)

        assert result.reached_terminal is True
        assert len(result.terminal_leaves) > 0

        for leaf in result.terminal_leaves:
            bb = state.bb
            for move in leaf.moves:
                bb = apply_move(bb, move)
            winner = check_game_winner(bb)
            if winner == WinStatus.NO_WIN:
                # Mover-blocked terminal: the player to move has no legal moves.
                from quantik_core import generate_legal_moves

                current_player, moves_by_shape = generate_legal_moves(bb)
                all_moves = [m for ms in moves_by_shape.values() for m in ms]
                assert not all_moves
            else:
                assert winner != WinStatus.NO_WIN

    def test_symmetry_dedup_depth_one(self):
        """From the empty board, 64 depth-1 moves collapse to 3 canonical states."""
        config = BeamSearchConfig(
            beam_width=64, max_depth=1, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config)

        state = State.from_qfen(EMPTY_QFEN)
        result = engine.search(state)

        assert result.stats["candidates_generated"] == 64
        # 64 candidates - 3 unique canonical states = 61 deduped
        assert result.stats["candidates_deduped"] == 61
        assert result.stats["nodes_inserted"] == 3

    def test_memory_bound(self):
        """nodes_inserted stays within the beam_width * depth + terminals bound."""
        state = State.from_qfen(EMPTY_QFEN)

        config_small = BeamSearchConfig(
            beam_width=2, max_depth=4, rollouts_per_candidate=1, random_seed=3
        )
        engine_small = BeamSearchEngine(config_small)
        result_small = engine_small.search(state)

        config_large = BeamSearchConfig(
            beam_width=16, max_depth=4, rollouts_per_candidate=1, random_seed=3
        )
        engine_large = BeamSearchEngine(config_large)
        result_large = engine_large.search(state)

        terminal_count_small = len(result_small.terminal_leaves)
        terminal_count_large = len(result_large.terminal_leaves)

        assert result_small.stats["nodes_inserted"] <= (
            config_small.beam_width * result_small.max_depth_reached
            + terminal_count_small
        )
        assert result_large.stats["nodes_inserted"] <= (
            config_large.beam_width * result_large.max_depth_reached
            + terminal_count_large
        )

    def test_determinism_same_seed(self):
        """Same seed produces an identical result."""
        state = State.from_qfen(EMPTY_QFEN)

        config1 = BeamSearchConfig(
            beam_width=4, max_depth=6, rollouts_per_candidate=2, random_seed=99
        )
        result1 = BeamSearchEngine(config1).search(state)

        config2 = BeamSearchConfig(
            beam_width=4, max_depth=6, rollouts_per_candidate=2, random_seed=99
        )
        result2 = BeamSearchEngine(config2).search(state)

        assert result1.stats == result2.stats
        assert result1.max_depth_reached == result2.max_depth_reached
        assert result1.reached_terminal == result2.reached_terminal
        assert [leaf.moves for leaf in result1.terminal_leaves] == [
            leaf.moves for leaf in result2.terminal_leaves
        ]
        assert result1.best_leaf is not None and result2.best_leaf is not None
        assert result1.best_leaf.moves == result2.best_leaf.moves
        assert result1.best_leaf.value == pytest.approx(result2.best_leaf.value)

    def test_determinism_different_seed_may_differ(self):
        """Different seeds are allowed to (and typically do) diverge."""
        state = State.from_qfen(EMPTY_QFEN)

        config1 = BeamSearchConfig(
            beam_width=3, max_depth=6, rollouts_per_candidate=3, random_seed=1
        )
        result1 = BeamSearchEngine(config1).search(state)

        config2 = BeamSearchConfig(
            beam_width=3, max_depth=6, rollouts_per_candidate=3, random_seed=2
        )
        result2 = BeamSearchEngine(config2).search(state)

        # Spec only guarantees same-seed determinism; different seeds are
        # merely allowed (not required) to diverge. Just assert both runs
        # complete and produce well-formed, independently valid results.
        assert result1.best_leaf is not None
        assert result2.best_leaf is not None
        assert result1.stats["evaluations"] > 0
        assert result2.stats["evaluations"] > 0

    def test_pluggable_evaluator_is_used(self):
        """A custom evaluator callable is invoked and biases the beam."""
        calls: List[State] = []

        def evaluator(state: State) -> float:
            calls.append(state)
            return 1.0  # always favor player 0

        config = BeamSearchConfig(
            beam_width=1, max_depth=2, evaluator=evaluator, random_seed=5
        )
        engine = BeamSearchEngine(config)

        state = State.from_qfen(EMPTY_QFEN)
        engine.search(state)

        assert len(calls) > 0

    def test_evaluator_clamping(self):
        """Evaluator values outside [-1, 1] are clamped."""

        def evaluator(state: State) -> float:
            return 5.0

        config = BeamSearchConfig(
            beam_width=2, max_depth=1, evaluator=evaluator, random_seed=1
        )
        engine = BeamSearchEngine(config)

        state = State.from_qfen(EMPTY_QFEN)
        result = engine.search(state)

        for node_id in engine.tree.get_children(engine.tree.root_id):
            node = engine.tree.get_node(node_id)
            if not (node.flags & NODE_FLAG_TERMINAL):
                assert float(node.best_value) <= 1.0

        assert result is not None

    def test_adversarial_perspective_p1_winning_reply(self):
        """When P1 is to move at depth 1 and has a winning reply, beam keeps it."""
        # P0 has placed A at (0,0). P1 to move.
        # Give P1 a winning reply: place B, C, D such that the row completes.
        # Row 0: A . . . ; P1 places b at 1, c at 2, then can win with d at 3
        # is too many moves; instead build a position where p1 has an
        # immediate one-move win: row 0 has A B C already (P0, P0, P1) and
        # it's P1's turn - wait shape D must be placed by whoever completes.
        # Use: P0 A at 0, B at 1; P1 c at 2. It's P1's turn (counts 2 vs 1).
        state = State.from_qfen("ABc./..../..../....")

        config = BeamSearchConfig(
            beam_width=2, max_depth=1, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config)
        result = engine.search(state)

        # P1 wins by placing shape D (index 3) at position 3.
        winning_moves = [
            leaf for leaf in result.terminal_leaves if leaf.value == pytest.approx(-1.0)
        ]
        assert len(winning_moves) > 0
        assert any(
            leaf.moves[0].player == 1
            and leaf.moves[0].shape == 3
            and leaf.moves[0].position == 3
            for leaf in winning_moves
        )

    def test_pruning_uses_mover_relative_score(self):
        """_score_and_prune must rank candidates mover-relative, not P0-fixed.

        Regression test: with only depth-1 TERMINAL wins exercised elsewhere,
        a mutant that drops the P1 sign flip (`score = raw_value` instead of
        `score = raw_value if mover == 0 else -raw_value`) still passes every
        other test in this file. This fixture forces every depth-1 reply to
        be NON-terminal, so the survivor must come from the mover-relative
        ranking in `_score_and_prune`, not from terminal-leaf handling.
        """
        # P0 has already placed A at (0,0); it is P1's turn. With only 2
        # pieces on the board after any reply, no line can be completed, so
        # every depth-1 candidate is non-terminal.
        root_state = State.from_qfen("A.../..../..../....")
        root_player, moves_by_shape = generate_legal_moves(root_state.bb)
        assert root_player == 1
        all_moves = [m for ms in moves_by_shape.values() for m in ms]
        assert len(all_moves) > 1

        # Assign each resulting state a distinct, known P0-perspective value.
        value_by_bb = {}
        for i, move in enumerate(all_moves):
            new_bb = apply_move(root_state.bb, move)
            value_by_bb[new_bb] = -1.0 + (2.0 * i) / len(all_moves)

        min_value = min(value_by_bb.values())
        max_value = max(value_by_bb.values())
        assert min_value != max_value  # sanity: evaluator actually discriminates

        def evaluator(state: State) -> float:
            return value_by_bb[state.bb]

        config = BeamSearchConfig(
            beam_width=1, max_depth=1, evaluator=evaluator, random_seed=1
        )
        engine = BeamSearchEngine(config)
        result = engine.search(root_state)

        # P1 is the mover; P1 wants the most negative P0-perspective value.
        # A correct mover-relative score keeps exactly that survivor. A
        # P0-fixed (unsigned) score would instead keep the candidate with
        # max_value, which is what this test guards against.
        assert result.best_leaf is not None
        assert not result.best_leaf.is_terminal
        assert result.best_leaf.value == pytest.approx(min_value)
        assert result.best_leaf.value != pytest.approx(max_value)

    def test_shared_tree_integration(self):
        """Passing an existing CompactGameTree writes terminal data into it."""
        mcts_config = MCTSConfig(random_seed=1)
        mcts_engine = MCTSEngine(mcts_config)

        config = BeamSearchConfig(
            beam_width=4, max_depth=2, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config, tree=mcts_engine.tree)
        assert engine.tree is mcts_engine.tree

        state = State.from_qfen("ABc./d.../..../....")
        result = engine.search(state)

        assert result.best_leaf is not None
        found_terminal_flag = False
        for node_id in range(engine.tree.storage.node_count):
            node = engine.tree.get_node(node_id)
            if node.flags & NODE_FLAG_TERMINAL:
                found_terminal_flag = True
                assert (node.flags & NODE_FLAG_WINNING_P0) or (
                    node.flags & NODE_FLAG_WINNING_P1
                )
        assert found_terminal_flag
        assert (
            engine.tree.storage.node_count
            <= config.beam_width * 2 + len(result.terminal_leaves) + 1
        )  # +1 for the root

    def test_shared_tree_with_fresh_compact_tree(self):
        """A fresh CompactGameTree instance can also be shared."""
        tree = CompactGameTree(initial_capacity=64)
        config = BeamSearchConfig(
            beam_width=2, max_depth=1, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config, tree=tree)

        state = State.from_qfen(EMPTY_QFEN)
        result = engine.search(state)

        assert engine.tree is tree
        assert result.stats["nodes_inserted"] > 0

    def test_root_already_terminal_raises(self):
        """Root state with a winning line raises ValueError."""
        config = BeamSearchConfig(random_seed=1)
        engine = BeamSearchEngine(config)

        state = State.from_qfen("ABCD/..../..../....")
        with pytest.raises(ValueError):
            engine.search(state)

    def test_root_no_legal_moves_raises(self):
        """Root state with no legal moves raises ValueError."""
        config = BeamSearchConfig(random_seed=1)
        engine = BeamSearchEngine(config)

        state = State.from_qfen(EMPTY_QFEN)
        from unittest.mock import patch

        with patch(
            "quantik_core.beam_search.generate_legal_moves", return_value=(0, {})
        ):
            with pytest.raises(ValueError):
                engine.search(state)

    def test_get_statistics(self):
        """get_statistics mirrors MCTSEngine's tree-delegated statistics."""
        config = BeamSearchConfig(
            beam_width=4, max_depth=2, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config)

        state = State.from_qfen(EMPTY_QFEN)
        engine.search(state)

        stats = engine.get_statistics()
        assert stats["nodes_created"] > 0
        assert stats["memory_usage"] > 0
        assert "tree_stats" in stats

    def test_beam_leaf_fields(self):
        """BeamLeaf exposes the documented fields."""
        leaf = BeamLeaf(moves=(), value=1.0, depth=0, is_terminal=True)
        assert leaf.moves == ()
        assert leaf.value == 1.0
        assert leaf.depth == 0
        assert leaf.is_terminal is True

    def test_stalemate_frontier_entry_marked_terminal(self):
        """A frontier state with no legal moves is terminal (mover loses)."""
        config = BeamSearchConfig(
            beam_width=2, max_depth=2, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config)

        state = State.from_qfen(EMPTY_QFEN)

        from unittest.mock import patch

        call_count = {"n": 0}
        real_generate = None

        import quantik_core.beam_search as beam_search_module

        real_generate = beam_search_module.generate_legal_moves

        def fake_generate(bb, player_id=None):
            call_count["n"] += 1
            if call_count["n"] == 2:
                # Force the second call (root expansion happened already via
                # validation, so this hits the first frontier-entry expansion)
                # to look like a stalemate.
                current_player, _ = real_generate(bb, player_id)
                return current_player, {0: [], 1: [], 2: [], 3: []}
            return real_generate(bb, player_id)

        with patch(
            "quantik_core.beam_search.generate_legal_moves", side_effect=fake_generate
        ):
            result = engine.search(state)

        assert any(leaf.depth == 0 for leaf in result.terminal_leaves)


class TestBeamSearchResultRanking:
    """Test result ranking/best_leaf selection semantics."""

    def test_best_leaf_prefers_root_player_perspective(self):
        """best_leaf is ranked from the root player's perspective, not P0-fixed."""
        # P1 to move; give P1 an immediate winning reply among the candidates.
        state = State.from_qfen("ABc./..../..../....")
        config = BeamSearchConfig(
            beam_width=4, max_depth=1, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config)

        result = engine.search(state)

        assert result.best_leaf is not None
        assert result.best_leaf.value == pytest.approx(
            -1.0
        )  # P1 (mover) wins -> P0-perspective -1

    def test_best_leaf_none_only_when_no_leaves(self):
        """best_leaf is derived from collected leaves; sanity check the invariant."""
        config = BeamSearchConfig(
            beam_width=1, max_depth=1, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config)
        state = State.from_qfen(EMPTY_QFEN)
        result = engine.search(state)
        assert result.best_leaf is not None


class TestBeamSearchResultNewFields:
    """Test the root_player and frontier_leaves result fields."""

    def test_root_player_populated(self):
        """root_player reflects who is actually to move at the root."""
        state = State.from_qfen("ABc./..../..../....")  # P1 to move
        config = BeamSearchConfig(
            beam_width=2, max_depth=1, rollouts_per_candidate=1, random_seed=1
        )
        result = BeamSearchEngine(config).search(state)
        assert result.root_player == 1

        state0 = State.from_qfen(EMPTY_QFEN)  # P0 to move
        result0 = BeamSearchEngine(config).search(state0)
        assert result0.root_player == 0

    def test_frontier_leaves_populated_when_unresolved(self):
        """frontier_leaves holds the live, non-terminal leaves when max_depth
        cuts the search short of full resolution."""
        config = BeamSearchConfig(
            beam_width=2, max_depth=2, rollouts_per_candidate=1, random_seed=1
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        assert result.reached_terminal is False
        assert len(result.frontier_leaves) > 0
        assert all(not leaf.is_terminal for leaf in result.frontier_leaves)

    def test_frontier_leaves_empty_when_resolved(self):
        """frontier_leaves is empty once every line resolves to a terminal."""
        config = BeamSearchConfig(
            beam_width=4, max_depth=16, rollouts_per_candidate=2, random_seed=42
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        assert result.reached_terminal is True
        assert result.frontier_leaves == []


class TestRankedRootMoves:
    """Test BeamSearchResult.ranked_root_moves() aggregation."""

    def test_aggregation_correctness(self):
        """Leaves are grouped by first move; stats aggregate correctly."""
        move_a = Move(player=0, shape=0, position=0)
        move_b = Move(player=0, shape=1, position=1)

        leaf_a_win = BeamLeaf(
            moves=(move_a, Move(0, 2, 2)), value=1.0, depth=2, is_terminal=True
        )
        leaf_a_live = BeamLeaf(
            moves=(move_a, Move(0, 3, 3)), value=0.5, depth=2, is_terminal=False
        )
        leaf_b = BeamLeaf(moves=(move_b,), value=-0.2, depth=1, is_terminal=False)

        result = BeamSearchResult(
            best_leaf=None,
            terminal_leaves=[leaf_a_win],
            reached_terminal=False,
            max_depth_reached=2,
            stats={},
            root_player=0,
            frontier_leaves=[leaf_a_live, leaf_b],
        )

        ranked = result.ranked_root_moves()
        assert len(ranked) == 2
        assert all(isinstance(entry, RankedRootMove) for entry in ranked)

        entry_a = next(r for r in ranked if r.move == move_a)
        assert entry_a.leaf_count == 2
        assert entry_a.best_value == pytest.approx(1.0)
        assert entry_a.mean_value == pytest.approx(0.75)
        assert entry_a.win_probability == pytest.approx(0.875)
        assert entry_a.has_terminal_win is True

        entry_b = next(r for r in ranked if r.move == move_b)
        assert entry_b.leaf_count == 1
        assert entry_b.best_value == pytest.approx(-0.2)
        assert entry_b.mean_value == pytest.approx(-0.2)
        assert entry_b.win_probability == pytest.approx(0.4)
        assert entry_b.has_terminal_win is False

        # move_a strictly dominates on best_value, so it ranks first.
        assert ranked[0].move == move_a
        assert ranked[1].move == move_b

    def test_perspective_sign_for_p1_root(self):
        """ranked_root_moves negates P0-perspective values when root_player == 1.

        Mutation guard: if the root-perspective negation were dropped (using
        leaf.value as-is instead of flipping it for a P1 root), this test
        would see best_value == -1.0 instead of +1.0 and fail.
        """
        move = Move(player=1, shape=0, position=0)
        # P0-perspective -1.0 means player 1 (the root mover) actually won.
        leaf = BeamLeaf(moves=(move,), value=-1.0, depth=1, is_terminal=True)

        result = BeamSearchResult(
            best_leaf=None,
            terminal_leaves=[leaf],
            reached_terminal=True,
            max_depth_reached=1,
            stats={},
            root_player=1,
            frontier_leaves=[],
        )

        ranked = result.ranked_root_moves()
        assert len(ranked) == 1
        entry = ranked[0]
        assert entry.best_value == pytest.approx(1.0)
        assert entry.mean_value == pytest.approx(1.0)
        assert entry.win_probability == pytest.approx(1.0)
        assert entry.has_terminal_win is True

    def test_top_k_truncation(self):
        """top_k truncates the ranked list without changing relative order."""
        moves = [Move(player=0, shape=i, position=i) for i in range(4)]
        leaves = [
            BeamLeaf(moves=(moves[i],), value=i / 3.0, depth=1, is_terminal=False)
            for i in range(4)
        ]
        result = BeamSearchResult(
            best_leaf=None,
            terminal_leaves=[],
            reached_terminal=False,
            max_depth_reached=1,
            stats={},
            root_player=0,
            frontier_leaves=leaves,
        )

        ranked_all = result.ranked_root_moves()
        assert len(ranked_all) == 4

        ranked_top2 = result.ranked_root_moves(top_k=2)
        assert ranked_top2 == ranked_all[:2]

    def test_sorted_descending_by_best_value(self):
        """Entries are sorted by best_value (then mean_value, then leaf_count)."""
        move_high = Move(player=0, shape=0, position=0)
        move_mid = Move(player=0, shape=1, position=1)
        move_low = Move(player=0, shape=2, position=2)

        leaves = [
            BeamLeaf(moves=(move_low,), value=-0.5, depth=1, is_terminal=False),
            BeamLeaf(moves=(move_high,), value=0.9, depth=1, is_terminal=False),
            BeamLeaf(moves=(move_mid,), value=0.1, depth=1, is_terminal=False),
        ]
        result = BeamSearchResult(
            best_leaf=None,
            terminal_leaves=[],
            reached_terminal=False,
            max_depth_reached=1,
            stats={},
            root_player=0,
            frontier_leaves=leaves,
        )

        ranked = result.ranked_root_moves()
        assert [r.move for r in ranked] == [move_high, move_mid, move_low]
        values = [r.best_value for r in ranked]
        assert values == sorted(values, reverse=True)

    def test_win_probability_within_bounds(self):
        """win_probability always lands in [0, 1], even at value extremes."""
        for value in (-1.0, 0.0, 1.0):
            move = Move(player=0, shape=0, position=0)
            leaf = BeamLeaf(
                moves=(move,), value=value, depth=1, is_terminal=abs(value) == 1.0
            )
            result = BeamSearchResult(
                best_leaf=None,
                terminal_leaves=[leaf] if leaf.is_terminal else [],
                reached_terminal=leaf.is_terminal,
                max_depth_reached=1,
                stats={},
                root_player=0,
                frontier_leaves=[] if leaf.is_terminal else [leaf],
            )
            entry = result.ranked_root_moves()[0]
            assert 0.0 <= entry.win_probability <= 1.0

    def test_empty_when_no_leaves(self):
        """ranked_root_moves returns an empty list when nothing was collected."""
        result = BeamSearchResult(
            best_leaf=None,
            terminal_leaves=[],
            reached_terminal=True,
            max_depth_reached=0,
            stats={},
            root_player=0,
            frontier_leaves=[],
        )
        assert result.ranked_root_moves() == []

    def test_integration_with_real_search(self):
        """ranked_root_moves works end-to-end on a real search result."""
        config = BeamSearchConfig(
            beam_width=4, max_depth=2, rollouts_per_candidate=2, random_seed=7
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        ranked = result.ranked_root_moves(top_k=3)
        assert 0 < len(ranked) <= 3
        for entry in ranked:
            assert 0.0 <= entry.win_probability <= 1.0
            assert entry.leaf_count > 0


class TestBeamSchedule:
    """Test the depth-dependent beam_schedule config field."""

    def test_unique_canonical_states_per_depth_constant(self):
        """Sanity-check the published constant against GAME_TREE_ANALYSIS.md."""
        assert UNIQUE_CANONICAL_STATES_PER_DEPTH[1] == 3
        assert UNIQUE_CANONICAL_STATES_PER_DEPTH[2] == 51
        assert UNIQUE_CANONICAL_STATES_PER_DEPTH[3] == 726
        schedule = [UNIQUE_CANONICAL_STATES_PER_DEPTH[d] for d in (1, 2, 3)] + [64]
        assert schedule == [3, 51, 726, 64]

    def test_width_resolution_last_entry_extension(self):
        """Depths beyond the schedule's length reuse its last entry."""
        config = BeamSearchConfig(beam_schedule=[3, 51, 8])
        engine = BeamSearchEngine(config)
        assert engine._beam_width_for_depth(1) == 3
        assert engine._beam_width_for_depth(2) == 51
        assert engine._beam_width_for_depth(3) == 8
        assert engine._beam_width_for_depth(4) == 8
        assert engine._beam_width_for_depth(5) == 8

    def test_width_resolution_flat_when_no_schedule(self):
        """Without a schedule, every depth resolves to the flat beam_width."""
        config = BeamSearchConfig(beam_width=7)
        engine = BeamSearchEngine(config)
        assert engine._beam_width_for_depth(1) == 7
        assert engine._beam_width_for_depth(10) == 7

    def test_schedule_depth_indexing_not_off_by_one(self):
        """Regression/mutation guard: depth 1 must resolve to schedule[0].

        If `_beam_width_for_depth` used `depth` instead of `depth - 1` (an
        off-by-one), depth 1 would incorrectly resolve to schedule[1] = 999,
        keeping all 3 available canonical candidates instead of being capped
        to schedule[0] = 1.
        """
        config = BeamSearchConfig(
            beam_schedule=[1, 999], max_depth=1, evaluator=lambda s: 0.0, random_seed=1
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))
        assert len(result.frontier_leaves) == 1

    def test_schedule_flat_equivalent_to_beam_width(self):
        """A single-entry schedule matches flat beam_width behavior exactly."""
        state = State.from_qfen(EMPTY_QFEN)

        config_flat = BeamSearchConfig(
            beam_width=4, max_depth=4, rollouts_per_candidate=2, random_seed=5
        )
        result_flat = BeamSearchEngine(config_flat).search(state)

        config_schedule = BeamSearchConfig(
            beam_schedule=[4], max_depth=4, rollouts_per_candidate=2, random_seed=5
        )
        result_schedule = BeamSearchEngine(config_schedule).search(state)

        assert result_flat.stats == result_schedule.stats
        assert result_flat.max_depth_reached == result_schedule.max_depth_reached
        assert result_flat.reached_terminal == result_schedule.reached_terminal
        assert [leaf.moves for leaf in result_flat.terminal_leaves] == [
            leaf.moves for leaf in result_schedule.terminal_leaves
        ]

    def test_exhaustive_prefix_no_pruning(self):
        """A schedule matching each depth's exact unique-canonical count keeps
        every candidate: nodes_pruned == 0 for a fully exhaustive prefix."""
        config = BeamSearchConfig(
            beam_schedule=[3, 51, 726],
            max_depth=3,
            evaluator=lambda s: 0.0,
            random_seed=1,
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        assert result.stats["nodes_pruned"] == 0
        # 3 + 51 + 726 unique canonical survivors across the three depths
        # (no wins are possible this early, so nothing is a terminal leaf).
        assert result.stats["nodes_inserted"] == 3 + 51 + 726


class TestSymmetryMultiplicity:
    """Test path-multiplicity accounting for beam-visible symmetry orbits.

    A constant evaluator (`lambda s: 0.0`) is used throughout so exhaustive
    shallow-depth runs stay cheap (no rollouts).
    """

    def test_depth_1_exact_orbits(self):
        """64 raw depth-1 moves split into 3 canonical orbits of size 16/16/32."""
        config = BeamSearchConfig(
            beam_schedule=[3], max_depth=1, evaluator=lambda s: 0.0, random_seed=1
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        assert len(result.frontier_leaves) == 3
        multiplicities = sorted(leaf.multiplicity for leaf in result.frontier_leaves)
        assert multiplicities == [16, 16, 32]
        assert sum(multiplicities) == 64

    def test_depth_2_exact_multiplicity_sum(self):
        """Depth-2 multiplicities sum to the 3,392 total legal moves at depth 2."""
        config = BeamSearchConfig(
            beam_schedule=[3, 51], max_depth=2, evaluator=lambda s: 0.0, random_seed=1
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        assert len(result.frontier_leaves) == 51
        assert sum(leaf.multiplicity for leaf in result.frontier_leaves) == 3392

    def test_depth_3_exact_multiplicity_sum(self):
        """Depth-3 multiplicities sum to the 167,552 total legal moves at depth 3."""
        config = BeamSearchConfig(
            beam_schedule=[3, 51, 726],
            max_depth=3,
            evaluator=lambda s: 0.0,
            random_seed=1,
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        assert len(result.frontier_leaves) == 726
        assert sum(leaf.multiplicity for leaf in result.frontier_leaves) == 167552

    @pytest.mark.slow
    def test_depth_4_exact_terminal_and_frontier_mass(self):
        """Depth-4 terminal mass (all P1 wins) plus frontier mass sum to the
        6,776,960 total legal moves at depth 4 (per GAME_TREE_ANALYSIS.md)."""
        config = BeamSearchConfig(
            beam_schedule=[3, 51, 726, 10946],
            max_depth=4,
            evaluator=lambda s: 0.0,
            random_seed=1,
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        depth_4_terminals = [leaf for leaf in result.terminal_leaves if leaf.depth == 4]
        assert sum(leaf.multiplicity for leaf in depth_4_terminals) == 6912
        assert all(leaf.value == -1.0 for leaf in depth_4_terminals)

        assert len(result.frontier_leaves) == 10946
        assert (
            sum(leaf.multiplicity for leaf in result.frontier_leaves) == 6776960 - 6912
        )

    def test_every_leaf_multiplicity_at_least_one(self):
        """Regression: every collected leaf has multiplicity >= 1."""
        config = BeamSearchConfig(
            beam_width=6, max_depth=4, rollouts_per_candidate=1, random_seed=3
        )
        engine = BeamSearchEngine(config)
        result = engine.search(State.from_qfen(EMPTY_QFEN))

        for leaf in (*result.terminal_leaves, *result.frontier_leaves):
            assert leaf.multiplicity >= 1

    def test_ranked_root_moves_weighted_mean_differs_from_unweighted(self):
        """Multiplicity-weighted mean must differ from a naive unweighted mean.

        Mutation guard: if `ranked_root_moves` reverted to an unweighted
        `sum(values) / len(values)`, this test's exact mean_value assertion
        would fail.
        """
        move = Move(player=0, shape=0, position=0)
        leaf_light = BeamLeaf(
            moves=(move,), value=1.0, depth=1, is_terminal=False, multiplicity=1
        )
        leaf_heavy = BeamLeaf(
            moves=(move,), value=-1.0, depth=1, is_terminal=False, multiplicity=9
        )

        result = BeamSearchResult(
            best_leaf=None,
            terminal_leaves=[],
            reached_terminal=False,
            max_depth_reached=1,
            stats={},
            root_player=0,
            frontier_leaves=[leaf_light, leaf_heavy],
        )

        ranked = result.ranked_root_moves()
        assert len(ranked) == 1
        entry = ranked[0]

        # Weighted mean: (1 * 1.0 + 9 * -1.0) / 10 = -0.8
        assert entry.mean_value == pytest.approx(-0.8)
        assert entry.total_multiplicity == 10

        unweighted_mean = (1.0 + -1.0) / 2  # 0.0 - a materially different number
        assert entry.mean_value != pytest.approx(unweighted_mean)

    def test_tree_node_multiplicity_matches_leaf(self):
        """Survivor tree nodes are inserted with their accumulated multiplicity."""
        config = BeamSearchConfig(
            beam_schedule=[3], max_depth=1, evaluator=lambda s: 0.0, random_seed=1
        )
        engine = BeamSearchEngine(config)
        state = State.from_qfen(EMPTY_QFEN)
        result = engine.search(state)

        assert len(result.frontier_leaves) == 3
        children = engine.tree.get_children(engine.tree.root_id)
        assert len(children) == 3

        leaf_multiplicity_by_key = {}
        for leaf in result.frontier_leaves:
            child_bb = apply_move(state.bb, leaf.moves[0])
            leaf_multiplicity_by_key[State(child_bb).canonical_key()] = (
                leaf.multiplicity
            )

        for child_id in children:
            child_state = engine.tree.get_state(child_id)
            node = engine.tree.get_node(child_id)
            expected = leaf_multiplicity_by_key[child_state.canonical_key()]
            assert int(node.multiplicity) == expected

    def test_tree_multiplicity_merges_across_parents(self):
        """Two different parents whose completing moves reach the exact same
        literal terminal board have their multiplicities summed on the
        merged tree node (CompactGameTree.add_child_node's own additive
        transposition-merge semantics)."""
        config = BeamSearchConfig(evaluator=lambda s: 0.0, random_seed=1)
        engine = BeamSearchEngine(config)

        # Both miss exactly one piece of the same row-0 win "AbCd"; P1 to
        # move in both, completing with the piece each is missing.
        predecessor_1 = State.from_qfen("A.Cd/..../..../....")  # missing b@1
        predecessor_2 = State.from_qfen("AbC./..../..../....")  # missing d@3

        node_1 = engine.tree.create_root_node(predecessor_1)
        node_2 = engine.tree.create_root_node(predecessor_2)

        stats: Dict[str, int] = {
            "candidates_generated": 0,
            "candidates_deduped": 0,
            "nodes_inserted": 0,
            "nodes_pruned": 0,
            "evaluations": 0,
        }
        terminal_leaves: List[BeamLeaf] = []
        frontier = [
            (node_1, predecessor_1.bb, (), 0.0, 5),
            (node_2, predecessor_2.bb, (), 0.0, 7),
        ]
        engine._expand_frontier(frontier, 1, stats, terminal_leaves)

        winning_bb = apply_move(predecessor_1.bb, Move(player=1, shape=1, position=1))
        merged_id = engine.tree.storage.find_node_by_canonical_state(
            State(winning_bb).pack(), 1
        )
        assert merged_id is not None
        merged_node = engine.tree.get_node(merged_id)
        assert int(merged_node.multiplicity) == 5 + 7

        # Both raw completions were recorded as their own terminal leaves,
        # each carrying only its own parent's multiplicity (not the merged
        # total) — the merge happens on the shared tree node, not the leaf.
        matching_leaves = [
            leaf for leaf in terminal_leaves if leaf.value == pytest.approx(-1.0)
        ]
        assert sorted(leaf.multiplicity for leaf in matching_leaves) == [5, 7]
