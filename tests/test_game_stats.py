#!/usr/bin/env python
"""
Unit tests for game_stats module to debug the symmetry analysis.
"""

import pytest
from quantik_core import apply_move, SymmetryHandler, generate_legal_moves, Move
from quantik_core.game_stats import SymmetryTable, CanonicalState
from quantik_core.qfen import bb_from_qfen
from quantik_core.move import _validate_game_state_single_pass


class TestGameStats:
    """Test suite for game stats functionality."""

    def test_empty_board_analysis(self):
        """Test analysis starting from empty board."""
        empty_bb = bb_from_qfen("..../..../..../....")

        # Test basic legal moves generation
        _, moves_by_shape = generate_legal_moves(empty_bb)
        all_moves = [
            move for move_list in moves_by_shape.values() for move in move_list
        ]

        assert len(all_moves) == 64, f"Expected 64 moves, got {len(all_moves)}"

        # Test canonical form
        canonical_bb, transformation = SymmetryHandler.find_canonical_form(empty_bb)

        # Should be the same since empty board is already canonical
        assert canonical_bb == empty_bb

    def test_first_move_canonicalization(self):
        """Test first move canonical analysis."""
        empty_bb = bb_from_qfen("..../..../..../....")

        # Get all legal moves
        _, moves_by_shape = generate_legal_moves(empty_bb)
        all_moves = [
            move for move_list in moves_by_shape.values() for move in move_list
        ]

        # Apply each move and find canonical forms
        canonical_forms = set()
        canonical_to_moves = {}

        for move in all_moves:
            new_bb = apply_move(empty_bb, move)
            canonical_bb, _ = SymmetryHandler.find_canonical_form(new_bb)
            canonical_key = tuple(canonical_bb)
            canonical_forms.add(canonical_key)

            if canonical_key not in canonical_to_moves:
                canonical_to_moves[canonical_key] = []
            canonical_to_moves[canonical_key].append(move)

        # Should reduce to 3 canonical forms
        assert (
            len(canonical_forms) == 3
        ), f"Expected 3 canonical forms, got {len(canonical_forms)}"

        # Verify each canonical form has the expected number of moves
        move_counts = [len(moves) for moves in canonical_to_moves.values()]
        assert (
            sum(move_counts) == 64
        ), f"Total moves should be 64, got {sum(move_counts)}"

    def test_second_move_generation(self):
        """Test second move generation from a specific first move."""
        empty_bb = bb_from_qfen("..../..../..../....")

        # Make a specific first move (player 0)
        first_move = Move(
            player=0, shape=0, position=0
        )  # Player 0, first shape, position 0
        bb_after_first = apply_move(empty_bb, first_move)

        # Generate second moves (should be player 1's turn)
        _, moves_by_shape = generate_legal_moves(bb_after_first)
        second_moves = [
            move for move_list in moves_by_shape.values() for move in move_list
        ]

        assert len(second_moves) > 0, "Should have legal second moves available"
        assert (
            len(second_moves) < 64
        ), f"Should have fewer than 64 moves, got {len(second_moves)}"

        # All second moves should be for player 1
        for move in second_moves:
            assert move.player == 1, f"Expected player 1, got player {move.player}"

    def test_canonical_state_creation(self):
        """Test CanonicalState creation and manipulation."""
        empty_bb = bb_from_qfen("..../..../..../....")
        canonical_bb, _ = SymmetryHandler.find_canonical_form(empty_bb)
        canonical_key = tuple(canonical_bb)

        state = CanonicalState(
            canonical_bb=canonical_key,
            representative_bb=canonical_key,  # Empty board is its own representative
            multiplicity=1,
            player_turn=0,
            depth=0,
        )

        assert state.multiplicity == 1
        assert state.player_turn == 0
        assert state.depth == 0
        assert len(state.canonical_bb) == 8

    def test_symmetry_table_initialization(self):
        """Test SymmetryTable initialization."""
        table = SymmetryTable()

        # Should start empty
        assert len(table.stats_by_depth) == 0
        assert len(table.canonical_states) == 0
        assert len(table.state_queue) == 0

        # Cumulative stats should be zero
        assert table.cumulative_stats.total_legal_moves == 0
        assert table.cumulative_stats.unique_canonical_states == 0

    def test_process_depth_one(self):
        """Test processing depth 1 manually to understand the bug."""
        table = SymmetryTable()

        # Initialize with empty board
        empty_bb = bb_from_qfen("..../..../..../....")
        canonical_empty, _ = SymmetryHandler.find_canonical_form(empty_bb)
        canonical_key = tuple(canonical_empty)

        initial_state = CanonicalState(
            canonical_bb=canonical_key,
            representative_bb=canonical_key,  # Empty board is its own representative
            multiplicity=1,
            player_turn=0,
            depth=0,
        )

        table.canonical_states[canonical_key] = initial_state
        table.state_queue = [initial_state]

        # Process depth 1
        depth_1_stats = table._process_depth(1)

        # Should have 64 total moves and 3 canonical states
        assert (
            depth_1_stats.total_legal_moves == 64
        ), f"Expected 64 moves, got {depth_1_stats.total_legal_moves}"
        assert (
            depth_1_stats.unique_canonical_states == 3
        ), f"Expected 3 canonical states, got {depth_1_stats.unique_canonical_states}"
        assert (
            depth_1_stats.ongoing_games == 64
        ), f"Expected 64 ongoing games, got {depth_1_stats.ongoing_games}"

        # Check the state queue for depth 1
        depth_1_states = [s for s in table.state_queue if s.depth == 1]
        assert (
            len(depth_1_states) == 3
        ), f"Expected 3 depth-1 states, got {len(depth_1_states)}"

        # Verify total multiplicity
        total_multiplicity = sum(state.multiplicity for state in depth_1_states)
        assert (
            total_multiplicity == 64
        ), f"Expected total multiplicity 64, got {total_multiplicity}"

    def test_debug_canonical_reconstruction(self):
        """Debug canonical state reconstruction."""
        empty_bb = bb_from_qfen("..../..../..../....")

        # Make a first move manually
        first_move = Move(player=0, shape=0, position=0)
        bb_after_first = apply_move(empty_bb, first_move)

        print(f"Original BB after first move: {bb_after_first}")

        # Check whose turn it is in original
        current_player, validation_result = _validate_game_state_single_pass(
            bb_after_first
        )
        print(
            f"Original - Current player: {current_player}, Validation: {validation_result}"
        )

        # Find canonical form
        canonical_bb, transformation = SymmetryHandler.find_canonical_form(
            bb_after_first
        )

        print(f"Canonical BB: {canonical_bb}")
        print(f"Transformation: {transformation}")

        # Check whose turn it is in canonical form
        current_player_canonical, validation_result_canonical = (
            _validate_game_state_single_pass(canonical_bb)
        )
        print(
            f"Canonical - Current player: {current_player_canonical}, Validation: {validation_result_canonical}"
        )

        # Test legal moves on canonical
        _, moves_by_shape = generate_legal_moves(canonical_bb)
        legal_moves = [
            move for move_list in moves_by_shape.values() for move in move_list
        ]

        print(f"Legal moves on canonical: {len(legal_moves)}")
        if len(legal_moves) > 0:
            print(f"First few moves: {legal_moves[:3]}")

        assert len(legal_moves) > 0, "Canonical state should have legal moves"

    def test_process_depth_two(self):
        """Test processing depth 2 to find the bug."""
        table = SymmetryTable()

        # Set up initial state and process depth 1
        empty_bb = bb_from_qfen("..../..../..../....")
        canonical_empty, _ = SymmetryHandler.find_canonical_form(empty_bb)
        canonical_key = tuple(canonical_empty)

        initial_state = CanonicalState(
            canonical_bb=canonical_key,
            representative_bb=canonical_key,  # Empty board is its own representative
            multiplicity=1,
            player_turn=0,
            depth=0,
        )

        table.canonical_states[canonical_key] = initial_state
        table.state_queue = [initial_state]

        # Process depth 1
        table._process_depth(1)

        # Verify we have states for depth 2 processing
        depth_1_states = [s for s in table.state_queue if s.depth == 1]
        assert len(depth_1_states) > 0, "Should have depth 1 states for processing"

        # Debug the first depth 1 state
        first_state = depth_1_states[0]
        print(f"First depth 1 state canonical_bb: {first_state.canonical_bb}")
        print(f"First depth 1 state player_turn: {first_state.player_turn}")
        print(f"First depth 1 state multiplicity: {first_state.multiplicity}")

        # Test reconstruction of bitboards from depth 1 states
        for i, state in enumerate(depth_1_states):
            reconstructed_bb = table._canonical_to_bitboard(state.canonical_bb)
            print(f"State {i} reconstructed BB: {reconstructed_bb}")
            assert (
                len(reconstructed_bb) == 8
            ), "Reconstructed bitboard should have length 8"

            # Try to generate legal moves
            _, moves_by_shape = generate_legal_moves(reconstructed_bb)
            legal_moves = [
                move for move_list in moves_by_shape.values() for move in move_list
            ]

            print(f"State {i} legal moves count: {len(legal_moves)}")
            if len(legal_moves) > 0:
                print(f"State {i} first move: {legal_moves[0]}")

            assert (
                len(legal_moves) > 0
            ), f"State {i} should have legal moves, got {len(legal_moves)}"

            # All moves should be for player 1 (since we processed player 0's moves in depth 1)
            for move in legal_moves[:5]:  # Check first few moves
                assert (
                    move.player == 1
                ), f"Expected player 1 moves at depth 2, got player {move.player}"

        # Process depth 2
        depth_2_stats = table._process_depth(2)

        assert (
            depth_2_stats.total_legal_moves > 0
        ), f"Depth 2 should have positive moves, got {depth_2_stats.total_legal_moves}"
        assert (
            depth_2_stats.unique_canonical_states > 0
        ), f"Depth 2 should have positive canonical states, got {depth_2_stats.unique_canonical_states}"

    def test_process_depth_three(self):
        """Test processing depth 3 to verify the pattern."""
        table = SymmetryTable()

        # Set up and process depths 1 and 2
        empty_bb = bb_from_qfen("..../..../..../....")
        canonical_empty, _ = SymmetryHandler.find_canonical_form(empty_bb)
        canonical_key = tuple(canonical_empty)

        initial_state = CanonicalState(
            canonical_bb=canonical_key,
            representative_bb=canonical_key,  # Empty board is its own representative
            multiplicity=1,
            player_turn=0,
            depth=0,
        )

        table.canonical_states[canonical_key] = initial_state
        table.state_queue = [initial_state]

        # Process depths 1 and 2
        table._process_depth(1)
        table._process_depth(2)

        # Verify we have states for depth 3 processing
        depth_2_states = [s for s in table.state_queue if s.depth == 2]
        assert (
            len(depth_2_states) > 0
        ), "Should have depth 2 states for processing depth 3"

        # Process depth 3
        depth_3_stats = table._process_depth(3)

        assert (
            depth_3_stats.total_legal_moves >= 0
        ), f"Depth 3 should have non-negative moves, got {depth_3_stats.total_legal_moves}"
        assert (
            depth_3_stats.unique_canonical_states >= 0
        ), f"Depth 3 should have non-negative canonical states, got {depth_3_stats.unique_canonical_states}"

        # Verify player turns are correct (depth 3 should be player 1's turn)
        depth_3_states = [s for s in table.state_queue if s.depth == 3]
        for state in depth_3_states:
            assert (
                state.player_turn == 1
            ), f"Depth 3 should be player 1's turn, got player {state.player_turn}"


class TestInputValidation:
    """Test suite for input validation and error handling."""

    def test_analyze_game_tree_invalid_max_depth_type(self):
        """Test that analyze_game_tree raises ValueError for invalid max_depth type."""
        from quantik_core.game_stats import SymmetryTable

        table = SymmetryTable()

        with pytest.raises(ValueError, match="max_depth must be an integer"):
            table.analyze_game_tree("invalid")  # type: ignore

        with pytest.raises(ValueError, match="max_depth must be an integer"):
            table.analyze_game_tree(3.14)  # type: ignore

    def test_analyze_game_tree_invalid_max_depth_value(self):
        """Test that analyze_game_tree raises ValueError for invalid max_depth values."""
        from quantik_core.game_stats import SymmetryTable

        table = SymmetryTable()

        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            table.analyze_game_tree(0)

        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            table.analyze_game_tree(-1)

        with pytest.raises(ValueError, match="max_depth cannot exceed 16"):
            table.analyze_game_tree(17)

        with pytest.raises(ValueError, match="max_depth cannot exceed 16"):
            table.analyze_game_tree(100)

    def test_analyze_game_tree_valid_edge_values(self):
        """Test that analyze_game_tree accepts valid edge values."""
        from quantik_core.game_stats import SymmetryTable

        table = SymmetryTable()

        # Should not raise for valid minimum
        table.analyze_game_tree(1)

        # Reset table
        table = SymmetryTable()

        # Should not raise for a reasonable test depth (not the actual maximum!)
        table.analyze_game_tree(3)  # Use depth 3 instead of 16 for testing

    def test_analyze_symmetry_reduction_invalid_max_depth(self):
        """Test that analyze_symmetry_reduction validates max_depth properly."""
        from quantik_core.game_stats import analyze_symmetry_reduction

        with pytest.raises(ValueError, match="max_depth must be an integer"):
            analyze_symmetry_reduction("invalid")  # type: ignore

        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            analyze_symmetry_reduction(0)

        with pytest.raises(ValueError, match="max_depth cannot exceed 16"):
            analyze_symmetry_reduction(17)

    def test_analyze_symmetry_reduction_invalid_output_file(self):
        """Test that analyze_symmetry_reduction validates output_file properly."""
        from quantik_core.game_stats import analyze_symmetry_reduction

        with pytest.raises(ValueError, match="output_file must be a string or None"):
            analyze_symmetry_reduction(1, 123)  # type: ignore

        with pytest.raises(ValueError, match="output_file must be a string or None"):
            analyze_symmetry_reduction(1, [])  # type: ignore

    def test_constants_defined(self):
        """Test that module constants are properly defined."""
        from quantik_core import game_stats

        assert hasattr(game_stats, "DEFAULT_MAX_DEPTH")
        assert hasattr(game_stats, "MAX_ALLOWED_DEPTH")
        assert hasattr(game_stats, "INITIAL_PLAYER")
        assert hasattr(game_stats, "EMPTY_BOARD_QFEN")
        assert hasattr(game_stats, "AnalysisError")

        assert game_stats.DEFAULT_MAX_DEPTH == 12
        assert game_stats.MAX_ALLOWED_DEPTH == 16
        assert game_stats.MIN_ALLOWED_DEPTH == 1
        assert game_stats.INITIAL_PLAYER == 0
        assert game_stats.EMPTY_BOARD_QFEN == "..../..../..../...."
        assert game_stats.PLAYER_0 == 0
        assert game_stats.PLAYER_1 == 1
        assert game_stats.TOTAL_PLAYERS == 2
        assert game_stats.PERCENTAGE_MULTIPLIER == 100

        # Test that AnalysisError is an Exception
        assert issubclass(game_stats.AnalysisError, Exception)
