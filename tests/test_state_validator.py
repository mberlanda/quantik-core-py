"""
Comprehensive unit tests for state validation.

Tests all validation scenarios including:
- Position validation (row/column/zone conflicts)
- Piece count validation (max 2 per shape per player)
- Turn balance validation (proper alternating turns)
- Game state validation (comprehensive checks)
"""

import pytest

from quantik_core.core import State
from quantik_core.state_validator import (
    ValidationError,
    ValidationResult,
    validate_piece_counts,
    validate_turn_balance,
    validate_position_placement,
    validate_game_state,
    get_current_player,
    validate_player_turn,
    count_pieces_by_shape,
)


class TestPieceCountValidation:
    """Test validation of piece counts per shape per player."""

    def test_valid_piece_counts(self):
        """Test that valid piece counts pass validation."""
        # Empty board
        state = State.from_qfen("..../..../..../....", validate=False)
        assert validate_piece_counts(state) == ValidationResult.OK

        # One piece per shape
        state = State.from_qfen("ABCD/abcd/..../....", validate=False)
        assert validate_piece_counts(state) == ValidationResult.OK

        # Two pieces per shape (maximum allowed)
        state = State.from_qfen("ABCD/abcd/ABCD/abcd", validate=False)
        assert validate_piece_counts(state) == ValidationResult.OK

    def test_exceeded_piece_counts(self):
        """Test that exceeded piece counts fail validation."""
        # Three A pieces for player 0 (exceeds max of 2)
        state = State.from_qfen("AAA./..../..../....", validate=False)
        assert validate_piece_counts(state) == ValidationResult.SHAPE_COUNT_EXCEEDED

        # Three a pieces for player 1 (exceeds max of 2)
        state = State.from_qfen("aaa./..../..../....", validate=False)
        assert validate_piece_counts(state) == ValidationResult.SHAPE_COUNT_EXCEEDED


class TestTurnBalanceValidation:
    """Test validation of turn balance and current player determination."""

    def test_valid_turn_balance(self):
        """Test valid turn balance scenarios."""
        # Empty board - Player 0's turn
        state = State.from_qfen("..../..../..../....", validate=False)
        player, result = validate_turn_balance(state)
        assert result == ValidationResult.OK
        assert player == 0

        # One piece placed by Player 0 - Player 1's turn
        state = State.from_qfen("A.../..../..../....", validate=False)
        player, result = validate_turn_balance(state)
        assert result == ValidationResult.OK
        assert player == 1

        # Equal pieces - Player 0's turn
        state = State.from_qfen("A.../a.../..../....", validate=False)
        player, result = validate_turn_balance(state)
        assert result == ValidationResult.OK
        assert player == 0

    def test_invalid_turn_balance(self):
        """Test invalid turn balance scenarios."""
        # Player 1 has more pieces (impossible since Player 0 goes first)
        state = State.from_qfen("a.../ab../..../....", validate=False)
        player, result = validate_turn_balance(state)
        assert result == ValidationResult.TURN_BALANCE_INVALID
        assert player is None

        # Difference of more than 1 piece
        state = State.from_qfen("ABC./a.../..../....", validate=False)
        player, result = validate_turn_balance(state)
        assert result == ValidationResult.TURN_BALANCE_INVALID
        assert player is None


class TestPositionPlacementValidation:
    """Test validation of piece placement according to Quantik rules."""

    def test_valid_placements(self):
        """Test valid piece placements."""
        # Empty board - any placement is valid
        state = State.from_qfen("..../..../..../....", validate=False)
        assert (
            validate_position_placement(state, 0, 0, 0) == ValidationResult.OK
        )  # A at pos 0 for Player 0
        assert (
            validate_position_placement(state, 5, 1, 1) == ValidationResult.OK
        )  # b at pos 5 for Player 1

        # Player 0 has A at position 0 (row 0, col 0, zone 0)
        # Player 1 can place 'a' at position 10 (row 2, col 2, zone 3) - no conflicts
        state = State.from_qfen("A.../..../..../....", validate=False)
        assert (
            validate_position_placement(state, 10, 0, 1) == ValidationResult.OK
        )  # a at pos 10 (different row, col, zone)

        # Same player can place same shape in same row/column/zone
        state = State.from_qfen("A.../..../..../....", validate=False)
        assert (
            validate_position_placement(state, 1, 0, 0) == ValidationResult.OK
        )  # A at pos 1 (same row)

    def test_invalid_placements_position_occupied(self):
        """Test that occupied positions are rejected."""
        state = State.from_qfen("A.../..../..../....", validate=False)
        assert (
            validate_position_placement(state, 0, 1, 0)
            == ValidationResult.PIECE_OVERLAP
        )  # Pos 0 occupied

    def test_invalid_placements_opponent_conflict(self):
        """Test rejection when opponent has same shape in line."""
        # Player 1 has 'a' in row 0, Player 0 cannot place 'A' in same row
        state = State.from_qfen("a.../..../..../....", validate=False)
        assert (
            validate_position_placement(state, 1, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )
        assert (
            validate_position_placement(state, 2, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )
        assert (
            validate_position_placement(state, 3, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )

        # Player 1 has 'a' in column 0, Player 0 cannot place 'A' in same column
        state = State.from_qfen("a.../..../..../....", validate=False)
        assert (
            validate_position_placement(state, 4, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 4 (col 0)
        assert (
            validate_position_placement(state, 8, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 8 (col 0)
        assert (
            validate_position_placement(state, 12, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 12 (col 0)

        # Player 1 has 'a' in zone 0, Player 0 cannot place 'A' in same zone
        state = State.from_qfen("a.../..../..../....", validate=False)
        assert (
            validate_position_placement(state, 1, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 1 (same zone)
        assert (
            validate_position_placement(state, 4, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 4 (same zone)
        assert (
            validate_position_placement(state, 5, 0, 0)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 5 (same zone)

    def test_invalid_parameters(self):
        """Test rejection of invalid parameters."""
        state = State.from_qfen("..../..../..../....", validate=False)

        # Invalid position
        assert (
            validate_position_placement(state, -1, 0, 0)
            == ValidationResult.INVALID_POSITION
        )
        assert (
            validate_position_placement(state, 16, 0, 0)
            == ValidationResult.INVALID_POSITION
        )

        # Invalid shape
        assert (
            validate_position_placement(state, 0, -1, 0)
            == ValidationResult.INVALID_SHAPE
        )
        assert (
            validate_position_placement(state, 0, 4, 0)
            == ValidationResult.INVALID_SHAPE
        )

        # Invalid player
        assert (
            validate_position_placement(state, 0, 0, -1)
            == ValidationResult.INVALID_PLAYER
        )
        assert (
            validate_position_placement(state, 0, 0, 2)
            == ValidationResult.INVALID_PLAYER
        )


class TestGameStateValidation:
    """Test comprehensive game state validation."""

    def test_valid_game_states(self):
        """Test various valid game states."""
        # Empty board
        state = State.from_qfen("..../..../..../....", validate=False)
        assert validate_game_state(state) == ValidationResult.OK

        # Valid game - A and a in different rows, columns, and zones
        state = State.from_qfen("A.../..../..a./....", validate=False)
        assert validate_game_state(state) == ValidationResult.OK

        # Valid complex game where no same shapes conflict
        state = State.from_qfen("A.b./c.D./..../....", validate=False)
        assert validate_game_state(state) == ValidationResult.OK

    def test_invalid_game_states(self):
        """Test various invalid game states."""
        # Too many pieces of same shape
        state = State.from_qfen("AAA./..../..../....", validate=False)
        assert validate_game_state(state) == ValidationResult.SHAPE_COUNT_EXCEEDED

        # Invalid turn balance
        state = State.from_qfen("abc./..../..../....", validate=False)
        assert validate_game_state(state) == ValidationResult.TURN_BALANCE_INVALID

        # Illegal placement - same shape in same column for different players
        state = State.from_qfen("A.../a.../..../....", validate=False)
        assert validate_game_state(state) == ValidationResult.ILLEGAL_PLACEMENT

        # Overlapping pieces (This would need to be constructed manually since QFEN can't represent overlaps)
        bb_with_overlap = list(State.empty().bb)
        bb_with_overlap[0] |= 1  # Player 0 shape A at position 0
        bb_with_overlap[4] |= 1  # Player 1 shape A at position 0 (overlap!)
        state = State(tuple(bb_with_overlap))
        assert validate_game_state(state) == ValidationResult.PIECE_OVERLAP

    def test_validation_with_exceptions(self):
        """Test that validation can raise exceptions when requested."""
        # Valid state should not raise
        state = State.from_qfen("A.../..../..../....", validate=False)
        validate_game_state(state, raise_on_error=True)  # Should not raise

        # Invalid state should raise
        state = State.from_qfen("AAA./..../..../....", validate=False)
        with pytest.raises(ValidationError):
            validate_game_state(state, raise_on_error=True)


class TestPlayerTurnValidation:
    """Test validation of expected player turns."""

    def test_valid_player_turns(self):
        """Test validation of correct player turns."""
        # Empty board - Player 0's turn
        state = State.from_qfen("..../..../..../....", validate=False)
        assert validate_player_turn(state, 0) == ValidationResult.OK

        # Player 0 moved - Player 1's turn
        state = State.from_qfen("A.../..../..../....", validate=False)
        assert validate_player_turn(state, 1) == ValidationResult.OK

    def test_invalid_player_turns(self):
        """Test validation of incorrect player turns."""
        # Empty board - not Player 1's turn
        state = State.from_qfen("..../..../..../....", validate=False)
        assert validate_player_turn(state, 1) == ValidationResult.NOT_PLAYER_TURN

        # Player 0 moved - not Player 0's turn again
        state = State.from_qfen("A.../..../..../....", validate=False)
        assert validate_player_turn(state, 0) == ValidationResult.NOT_PLAYER_TURN

        # Invalid player ID
        state = State.from_qfen("..../..../..../....", validate=False)
        assert validate_player_turn(state, 2) == ValidationResult.INVALID_PLAYER

        # For inconsistent game state
        state = State.from_qfen("A.../..../..A./....", validate=False)
        assert validate_player_turn(state, 0) == ValidationResult.TURN_BALANCE_INVALID


class TestFromQfenValidation:
    """Test that from_qfen properly validates states when requested."""

    def test_valid_qfen_with_validation(self):
        """Test that valid QFEN strings pass validation."""
        # Should not raise
        State.from_qfen("..../..../..../....", validate=True)

        # This should pass - A and a are in different rows, columns, and zones
        State.from_qfen("A.../..../..a./....", validate=True)

    def test_invalid_qfen_with_validation(self):
        """Test that invalid QFEN strings fail validation."""
        with pytest.raises(ValidationError):
            State.from_qfen("AAA./..../..../....", validate=True)  # Too many A pieces

        with pytest.raises(ValidationError):
            State.from_qfen(
                "abc./..../..../....", validate=True
            )  # Invalid turn balance

        # This should fail since A and a are in the same column
        with pytest.raises(ValidationError):
            State.from_qfen("A.../a.../..../....", validate=True)

    def test_qfen_without_validation(self):
        """Test that validation can be disabled."""
        # Should not raise even with invalid state (default behavior)
        state = State.from_qfen("AAA./..../..../....", validate=False)
        assert state is not None

        # Should also not raise when validation is not specified (default is False)
        state = State.from_qfen("AAA./..../..../....")
        assert state is not None

    def test_invalid_characters_in_qfen(self):
        """Test that invalid characters in QFEN are rejected."""
        with pytest.raises(ValueError, match="Invalid character"):
            State.from_qfen("AXX./..../..../....", validate=False)


class TestUtilityFunctions:
    """Test utility functions used by validation."""

    def test_count_pieces_by_shape(self):
        """Test piece counting functionality."""
        state = State.from_qfen("ABab/CDcd/..../....", validate=False)
        player0_counts, player1_counts = count_pieces_by_shape(state)

        assert player0_counts == [1, 1, 1, 1]  # One of each shape for Player 0
        assert player1_counts == [1, 1, 1, 1]  # One of each shape for Player 1

        # Test with unequal counts
        state = State.from_qfen("AABb/..../..../....", validate=False)
        player0_counts, player1_counts = count_pieces_by_shape(state)

        assert player0_counts == [2, 1, 0, 0]  # Two A, one B for Player 0
        assert player1_counts == [0, 1, 0, 0]  # One b for Player 1

    def test_get_current_player(self):
        """Test current player determination."""
        # Empty board
        state = State.from_qfen("..../..../..../....", validate=False)
        player, result = get_current_player(state)
        assert result == ValidationResult.OK
        assert player == 0

        # After Player 0 moves
        state = State.from_qfen("A.../..../..../....", validate=False)
        player, result = get_current_player(state)
        assert result == ValidationResult.OK
        assert player == 1

        # After both players move
        state = State.from_qfen("A.../..../..a./....", validate=False)
        player, result = get_current_player(state)
        assert result == ValidationResult.OK
        assert player == 0


class TestComplexValidationScenarios:
    """Test complex validation scenarios that combine multiple rules."""

    def test_full_game_simulation(self):
        """Test validation throughout a complete game simulation."""
        # Start with empty board
        State.from_qfen("..../..../..../....", validate=True)

        # Player 0 places A at position 0
        State.from_qfen("A.../..../..../....", validate=True)

        # Player 1 places b at position 5 (different row, column, zone from A)
        State.from_qfen("A.../..b./..../....", validate=True)

        # Player 0 places B at position 8 (different row, column, zone from b)
        State.from_qfen("A.../..b./B.../....", validate=True)

        # Continue with more valid moves - a is placed where it doesn't conflict with A
        State.from_qfen("A.../..b./B.../..a.", validate=True)

    def test_zone_conflict_validation(self):
        """Test specific zone conflict scenarios with position placement validation."""
        # Player 0 places A in top-left zone (position 0)
        state = State.from_qfen("A.../..../..../....", validate=False)

        # Player 1 cannot place 'a' anywhere in top-left zone
        assert (
            validate_position_placement(state, 1, 0, 1)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 1
        assert (
            validate_position_placement(state, 4, 0, 1)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 4
        assert (
            validate_position_placement(state, 5, 0, 1)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 5

        # Player 1 cannot place 'a' in same row (position 2, 3)
        assert (
            validate_position_placement(state, 2, 0, 1)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 2 (same row)
        assert (
            validate_position_placement(state, 3, 0, 1)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 3 (same row)

        # Player 1 cannot place 'a' in same column (position 8, 12)
        assert (
            validate_position_placement(state, 8, 0, 1)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 8 (same col)
        assert (
            validate_position_placement(state, 12, 0, 1)
            == ValidationResult.ILLEGAL_PLACEMENT
        )  # pos 12 (same col)

        # But Player 1 can place 'a' in positions that don't conflict
        assert (
            validate_position_placement(state, 10, 0, 1) == ValidationResult.OK
        )  # pos 10 (row 2, col 2, zone 3)

    def test_maximum_pieces_scenario(self):
        """Test scenarios with maximum allowed pieces."""
        # Valid state with pieces placed to avoid conflicts
        State.from_qfen("A.../B.../..a./..b.", validate=True)

        # Cannot add more pieces - 3 A's for player 0
        with pytest.raises(ValidationError):
            State.from_qfen(
                "AAA./..../..../....", validate=True
            )  # Three A pieces for player 0

    def test_overlapping_pieces_validation(self):
        """Test that overlapping pieces are detected."""
        # Create a state with overlapping pieces manually
        bb = list(State.empty().bb)
        bb[0] |= 1  # Player 0 shape A at position 0
        bb[4] |= 1  # Player 1 shape A at position 0 (same position!)
        state = State(tuple(bb))

        # This should fail validation
        assert validate_game_state(state) == ValidationResult.PIECE_OVERLAP

        with pytest.raises(ValidationError):
            validate_game_state(state, raise_on_error=True)
