"""
Unit tests for the enhanced QuantikBoard representation.

Tests verify:
- Correct parsing and serialization of QFEN strings
- Legal move generation for various board states
- Accurate detection of winning positions and stalemate
- Inventory management and consistency
- Move execution and undo functionality
"""

import pytest

from quantik_core import (
    QuantikBoard,
    PlayerInventory,
    GameResult,
    Move,
    State,
)
from quantik_core.constants import MAX_PIECES_PER_SHAPE


# STALEMATE_QFEN "A..C/bbd./CD.A/.adB" used for testing


class TestPlayerInventory:
    """Test PlayerInventory functionality."""

    def test_default_inventory(self):
        """Test default full inventory."""
        inv = PlayerInventory()
        assert inv.shape_a == MAX_PIECES_PER_SHAPE
        assert inv.shape_b == MAX_PIECES_PER_SHAPE
        assert inv.shape_c == MAX_PIECES_PER_SHAPE
        assert inv.shape_d == MAX_PIECES_PER_SHAPE
        assert inv.total_pieces == 4 * MAX_PIECES_PER_SHAPE

    def test_custom_inventory(self):
        """Test custom inventory creation."""
        inv = PlayerInventory(shape_a=1, shape_b=2, shape_c=0, shape_d=1)
        assert inv.shape_a == 1
        assert inv.shape_b == 2
        assert inv.shape_c == 0
        assert inv.shape_d == 1
        assert inv.total_pieces == 4

    def test_invalid_inventory(self):
        """Test invalid inventory values."""
        with pytest.raises(ValueError):
            PlayerInventory(shape_a=-1)

        with pytest.raises(ValueError):
            PlayerInventory(shape_b=MAX_PIECES_PER_SHAPE + 1)

        with pytest.raises(ValueError):
            state = State.empty()
            empty_inventories = (
                PlayerInventory(0, 0, 0, 0),
                PlayerInventory(0, 0, 0, 0),
            )
            QuantikBoard(state, empty_inventories)

    def test_get_shape_count(self):
        """Test getting shape counts by index."""
        inv = PlayerInventory(shape_a=1, shape_b=2, shape_c=0, shape_d=1)
        assert inv.get_shape_count(0) == 1
        assert inv.get_shape_count(1) == 2
        assert inv.get_shape_count(2) == 0
        assert inv.get_shape_count(3) == 1

    def test_has_shape(self):
        """Test checking if shapes are available."""
        inv = PlayerInventory(shape_a=1, shape_b=0, shape_c=2, shape_d=0)
        assert inv.has_shape(0) is True  # A
        assert inv.has_shape(1) is False  # B
        assert inv.has_shape(2) is True  # C
        assert inv.has_shape(3) is False  # D

    def test_use_shape_success(self):
        """Test successfully using a shape."""
        inv = PlayerInventory(shape_a=2, shape_b=1, shape_c=0, shape_d=1)
        new_inv = inv.use_shape(0)  # Use shape A
        assert new_inv.shape_a == 1
        assert new_inv.shape_b == 1
        assert new_inv.shape_c == 0
        assert new_inv.shape_d == 1

    def test_add_shape(self):
        """Test adding pieces back to inventory."""
        inv = PlayerInventory(shape_a=1, shape_b=2, shape_c=0, shape_d=1)

        # Add shape C
        new_inv = inv.add_shape(2)
        assert new_inv.shape_c == 1
        assert new_inv.shape_a == 1  # unchanged
        assert new_inv.total_pieces == inv.total_pieces + 1

        # Try to exceed maximum
        full_inv = PlayerInventory()
        with pytest.raises(ValueError):
            full_inv.add_shape(0)


class TestQuantikBoard:
    """Test QuantikBoard functionality."""

    def test_empty_board_creation(self):
        """Test creating empty board."""
        board = QuantikBoard.empty()
        assert board.to_qfen() == "..../..../..../...."
        assert board.current_player == 0
        assert board.move_count == 0
        assert board.last_move is None

        # Check full inventories
        inv0, inv1 = board.player_inventories
        assert inv0.total_pieces == 4 * MAX_PIECES_PER_SHAPE
        assert inv1.total_pieces == 4 * MAX_PIECES_PER_SHAPE

    def test_from_qfen_creation(self):
        """Test creating board from QFEN."""
        qfen = "A.../..../..../...."
        board = QuantikBoard.from_qfen(qfen)
        assert board.to_qfen() == qfen

        # Check that inventory reflects used piece
        inv0, inv1 = board.player_inventories
        assert inv0.shape_a == MAX_PIECES_PER_SHAPE - 1
        assert inv0.shape_b == MAX_PIECES_PER_SHAPE
        assert inv1.total_pieces == 4 * MAX_PIECES_PER_SHAPE

    def test_from_state_creation(self):
        """Test creating board from existing state."""
        state = State.from_qfen("Ab../..../..../....")
        board = QuantikBoard.from_state(state)
        assert board.to_qfen() == "Ab../..../..../...."

        # Check inventory reflects used pieces
        inv0, inv1 = board.player_inventories
        assert inv0.shape_a == MAX_PIECES_PER_SHAPE - 1
        assert inv1.shape_b == MAX_PIECES_PER_SHAPE - 1

    def test_consistency_validation(self):
        """Test that board validates state/inventory consistency."""
        state = State.from_qfen("A.../..../..../....")

        # Create inconsistent inventories (too many pieces)
        bad_inventories = (
            PlayerInventory(),  # Full inventory but A piece is on board
            PlayerInventory(),
        )

        with pytest.raises(ValueError, match="Inconsistent piece count"):
            QuantikBoard(state, bad_inventories)


class TestLegalMoveGeneration:
    """Test legal move generation."""

    def test_empty_board_legal_moves(self):
        """Test legal moves on empty board."""
        board = QuantikBoard.empty()
        moves = board.get_legal_moves()

        # All 64 moves should be legal (4 shapes × 16 positions)
        assert len(moves) == 64

        # Check all positions and shapes are covered
        positions = {move.position for move in moves}
        shapes = {move.shape for move in moves}
        assert positions == set(range(16))
        assert shapes == set(range(4))

        # All moves should be for player 0 (current player)
        players = {move.player for move in moves}
        assert players == {0}

    def test_legal_moves_with_occupied_positions(self):
        """Test legal moves with some positions occupied."""
        # Player 0 plays A at position 0, now it's player 1's turn
        state = State.from_qfen("A.../..../..../....")
        inventories = (
            PlayerInventory(
                shape_a=1, shape_b=2, shape_c=2, shape_d=2
            ),  # Used 1 A piece
            PlayerInventory(
                shape_a=2, shape_b=2, shape_c=2, shape_d=2
            ),  # Full inventory
        )
        board = QuantikBoard(state, inventories)
        moves = board.get_legal_moves()
        print("FOOOO")
        print(moves)
        # Position 0 is occupied, so not available
        positions = {move.position for move in moves}
        assert 0 not in positions
        assert len(positions) == 15

        # All moves should be for player 1 (current player)
        players = {move.player for move in moves}
        assert players == {1}

        # Player 1 can use any shape except where placement rules prevent it
        shapes = {move.shape for move in moves}
        assert len(shapes) > 0  # Should have some legal moves

    def test_legal_moves_respecting_inventory(self):
        """Test that legal moves respect inventory constraints."""
        # Create a game state where player 0 has used all their A pieces
        # Player 0 placed AA, then player 1 placed a, now it's player 0's turn again
        state = State.from_qfen("AA../..aa/..../....")
        inventories = (
            PlayerInventory(
                shape_a=0, shape_b=2, shape_c=2, shape_d=2
            ),  # Used all A pieces
            PlayerInventory(
                shape_a=0, shape_b=2, shape_c=2, shape_d=2
            ),  # Used 1 A piece
        )
        board = QuantikBoard(state, inventories)

        moves = board.get_legal_moves()

        # Player 0's turn - should not have any A moves (shape 0)
        shapes = {move.shape for move in moves}
        assert 0 not in shapes  # No A moves for player 0
        assert shapes.issubset({1, 2, 3})  # Only B, C, D available

        # All moves should be for player 0
        players = {move.player for move in moves}
        assert players == {0}

    def test_legal_moves_with_placement_rules(self):
        """Test legal moves respecting placement rules."""
        # Create position where placement rules restrict moves
        # Player 0: A at (0,0), Player 1: B at (0,1) - now player 0's turn
        state = State.from_qfen("Ab../..../..../....")
        inventories = (
            PlayerInventory(
                shape_a=1, shape_b=2, shape_c=2, shape_d=2
            ),  # Used 1 A piece
            PlayerInventory(
                shape_a=2, shape_b=1, shape_c=2, shape_d=2
            ),  # Used 1 B piece
        )
        board = QuantikBoard(state, inventories)
        moves = board.get_legal_moves()

        # Player 0's turn - should have legal moves but with restrictions
        assert len(moves) > 0  # Should have some legal moves

        # All moves should be for player 0
        players = {move.player for move in moves}
        assert players == {0}

        # Should be able to place some shapes in valid positions
        positions = {move.position for move in moves}
        assert 0 not in positions  # Position 0 is occupied
        assert 1 not in positions  # Position 1 is occupied

    def test_no_legal_moves_stalemate(self):
        """Test detection when no legal moves available."""
        # Create a scenario where a player has still inventory but no legal moves
        state = State.from_qfen("A..C/bbd./CD.A/.adB")
        board = QuantikBoard(state)

        assert board._current_player == 1
        assert board._inventories[board._current_player].total_pieces == 3
        assert board.count_legal_moves() == 0


class TestMoveExecution:
    """Test move execution and undo functionality."""

    def test_play_valid_move(self):
        """Test playing a valid move."""
        board = QuantikBoard.empty()
        move = Move(player=0, shape=0, position=0)  # Place A at position 0

        assert board.play_move(move) is True

        # Check state changed
        assert board.to_qfen() == "A.../..../..../...."
        assert board.current_player == 1
        assert board.move_count == 1
        assert board.last_move == move

        # Check inventory updated
        inv0, inv1 = board.player_inventories
        assert inv0.shape_a == MAX_PIECES_PER_SHAPE - 1
        assert inv1.total_pieces == 4 * MAX_PIECES_PER_SHAPE

    def test_play_invalid_move(self):
        """Test playing an invalid move."""
        board = QuantikBoard.from_qfen("A.../..../..../....")

        # Try to place on occupied square
        invalid_move = Move(player=1, shape=0, position=0)
        assert board.play_move(invalid_move) is False

        # Board should be unchanged
        assert board.to_qfen() == "A.../..../..../...."
        assert board.move_count == 0

    def test_play_move_without_inventory(self):
        """Test playing move without piece in inventory."""
        board = QuantikBoard.from_qfen("Ab../..../..Ac/....")

        # Try to place A piece
        move = Move(player=0, shape=0, position=0)
        assert board.play_move(move) is False

        # Board should be unchanged
        assert board.to_qfen() == "Ab../..../..Ac/...."
        assert board.move_count == 0

    def test_undo_move(self):
        """Test undoing moves."""
        board = QuantikBoard.empty()
        original_qfen = board.to_qfen()

        # Play a move
        move = Move(player=0, shape=0, position=0)
        board.play_move(move)
        assert board.to_qfen() != original_qfen

        # Undo the move
        assert board.undo_move() is True
        assert board.to_qfen() == original_qfen
        assert board.current_player == 0
        assert board.move_count == 0
        assert board.last_move is None

        # Check inventory restored
        inv0, inv1 = board.player_inventories
        assert inv0.total_pieces == 4 * MAX_PIECES_PER_SHAPE

    def test_undo_multiple_moves(self):
        """Test undoing multiple moves."""
        board = QuantikBoard.empty()
        original_qfen = board.to_qfen()

        # Play several moves
        moves = [
            Move(player=0, shape=0, position=0),
            Move(player=1, shape=1, position=1),
            Move(player=0, shape=2, position=2),
        ]

        for move in moves:
            board.play_move(move)

        assert board.move_count == 3

        # Undo all moves
        undone = board.undo_moves(3)
        assert undone == 3
        assert board.to_qfen() == original_qfen
        assert board.move_count == 0

    def test_undo_no_moves(self):
        """Test undoing when no moves to undo."""
        board = QuantikBoard.empty()
        assert board.undo_move() is False
        assert board.undo_moves(5) == 0


class TestGameResultDetection:
    """Test game result and win condition detection."""

    def test_ongoing_game(self):
        """Test ongoing game detection."""
        board = QuantikBoard.from_qfen("A.../..../..../....")
        assert board.get_game_result() == GameResult.ONGOING
        assert not board.is_game_over()

    def test_player_0_win(self):
        """Test player 0 win detection."""
        # Create winning position for player 0 (complete row)
        board = QuantikBoard.from_qfen("ABCD/..../cd../..a.")

        assert board.get_game_result() == GameResult.PLAYER_0_WINS
        assert board.is_game_over()

    def test_player_1_win(self):
        """Test player 1 win detection."""
        # Create winning position for player 1 (complete column)
        board = QuantikBoard.from_qfen("abcd/..../CD../..AB")

        assert board.get_game_result() == GameResult.PLAYER_1_WINS
        assert board.is_game_over()

    def test_stalemate_detection(self):
        """Test stalemate detection."""
        # Player 1 has no legal moves left
        board = QuantikBoard.from_qfen("A..C/bbd./CD.A/.adB")

        assert board.get_game_result() == GameResult.PLAYER_0_WINS
        assert board.is_game_over()


class TestAnalysisFeatures:
    """Test board analysis features."""

    def test_piece_count_analysis(self):
        """Test piece count analysis."""
        board = QuantikBoard.from_qfen("AB../..../..../..ab")
        counts = board.get_piece_counts()

        # Check on-board counts
        assert counts["on_board"]["player_0"][0] == 1  # A
        assert counts["on_board"]["player_0"][1] == 1  # B
        assert counts["on_board"]["player_1"][0] == 1  # a
        assert counts["on_board"]["player_1"][1] == 1  # b

        # Check inventory counts
        assert counts["in_inventory"]["player_0"][0] == MAX_PIECES_PER_SHAPE - 1  # A
        assert counts["in_inventory"]["player_0"][1] == MAX_PIECES_PER_SHAPE - 1  # B
        assert counts["in_inventory"]["player_1"][0] == MAX_PIECES_PER_SHAPE - 1  # a
        assert counts["in_inventory"]["player_1"][1] == MAX_PIECES_PER_SHAPE - 1  # b

    def test_mobility_scoring(self):
        """Test mobility scoring."""
        board = QuantikBoard.empty()

        # Full mobility on empty board
        mobility = board.get_mobility_score(0)
        assert mobility == 64  # 4 shapes × 16 positions

        # Reduced mobility with limited inventory
        limited_board = QuantikBoard.from_qfen("A.../bbd./CD.A/.adB")
        limited_mobility_0 = limited_board.get_mobility_score(0)
        assert limited_mobility_0 == 10
        assert limited_board.get_legal_moves() == [
            Move(player=0, shape=1, position=2),
            Move(player=0, shape=1, position=3),
            Move(player=0, shape=1, position=10),
            Move(player=0, shape=2, position=1),
            Move(player=0, shape=2, position=2),
            Move(player=0, shape=2, position=3),
            Move(player=0, shape=2, position=7),
            Move(player=0, shape=2, position=10),
            Move(player=0, shape=2, position=12),
            Move(player=0, shape=3, position=1),
        ]

    def test_board_copy(self):
        """Test board copying."""
        original = QuantikBoard.from_qfen("Ab../..../..../....")
        copy = original.copy()

        # Should be equal but independent
        assert copy.to_qfen() == original.to_qfen()
        assert copy.player_inventories == original.player_inventories

        # Modify copy
        move = Move(player=0, shape=2, position=2)
        copy.play_move(move)

        # Original should be unchanged
        assert copy.to_qfen() != original.to_qfen()
        assert copy.to_qfen() == "AbC./..../..../...."
        assert original.to_qfen() == "Ab../..../..../...."


class TestStringRepresentation:
    """Test string representation and formatting."""

    def test_str_representation(self):
        """Test string representation."""
        board = QuantikBoard.from_qfen("A.../..../..../....")
        str_repr = str(board)

        assert "QFEN: A.../..../..../...." in str_repr
        assert "Current player:" in str_repr
        assert "Move count:" in str_repr
        assert "inventory:" in str_repr

    def test_repr_representation(self):
        """Test repr representation."""
        board = QuantikBoard.from_qfen("Ab../..../..../....")
        repr_str = repr(board)

        assert repr_str == "QuantikBoard('Ab../..../..../....')"


class TestQFENCompatibility:
    """Test QFEN parsing and serialization compatibility."""

    @pytest.mark.parametrize(
        "qfen",
        [
            "..../..../..../....",  # Empty board
            "A.../..../..../....",  # Single piece
            "AB../..ba/..../....",  # Mixed players
            "ABcd/..../..../....",  # Winning row
            "A.bC/..../d..B/...a",  # Complex position
        ],
    )
    def test_qfen_roundtrip(self, qfen):
        """Test QFEN parsing and serialization roundtrip."""
        board = QuantikBoard.from_qfen(qfen)
        assert board.to_qfen() == qfen

    def test_qfen_validation(self):
        """Test QFEN validation."""
        # Valid QFEN should parse without validation
        board = QuantikBoard.from_qfen("A.../..../..../....", validate=False)
        assert board.to_qfen() == "A.../..../..../...."

        # Invalid QFEN should raise with validation
        with pytest.raises(Exception):
            QuantikBoard.from_qfen("AAAAA/..../..../..../....", validate=True)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    # TODO: validation not implemented yet
    def test_move_on_finished_game(self):
        """Test attempting moves on finished game."""
        # Create winning position
        board = QuantikBoard.from_qfen("ABcd/..../..../....")
        assert board.is_game_over()

        move = Move(player=0, shape=0, position=5)
        with pytest.raises(ValueError, match="Game is already over"):
            board.play_move(move)

    def test_large_undo_count(self):
        """Test undoing more moves than available."""
        board = QuantikBoard.empty()

        # Play 2 moves
        board.play_move(Move(player=0, shape=0, position=0))
        board.play_move(Move(player=1, shape=1, position=1))

        # Try to undo 10 moves
        undone = board.undo_moves(10)
        assert undone == 2  # Only 2 moves were actually undone
        assert board.move_count == 0
