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
    validate_game_state,
)


def _assert_game_state_validation(
    state: "State", expected_player: int, expected_result: ValidationResult
):
    player, result = validate_game_state(state.bb)
    assert player == expected_player
    assert result == expected_result


class TestGameStateValidation:
    """Test comprehensive game state validation."""

    def test_valid_game_states(self):
        """Test various valid game states."""
        # Empty board
        state = State.from_qfen("..../..../..../....", validate=False)
        _assert_game_state_validation(state, 0, ValidationResult.OK)

        # Valid game - A and a in different rows, columns, and zones
        state = State.from_qfen("A.../..../..a./....", validate=False)
        _assert_game_state_validation(state, 0, ValidationResult.OK)

        # Valid complex game where no same shapes conflict
        state = State.from_qfen("A.b./c.D./..../.B..", validate=False)
        _assert_game_state_validation(state, 1, ValidationResult.OK)

    def test_invalid_game_states(self):
        """Test various invalid game states."""
        # Too many pieces of same shape
        state = State.from_qfen("AAA./..../..../....", validate=False)
        _assert_game_state_validation(
            state, None, ValidationResult.SHAPE_COUNT_EXCEEDED
        )

        # Invalid turn balance
        state = State.from_qfen("abc./..../..../....", validate=False)
        _assert_game_state_validation(
            state, None, ValidationResult.TURN_BALANCE_INVALID
        )

        # Illegal placement - same shape in same column for different players
        state = State.from_qfen("A.../a.../..../....", validate=False)
        _assert_game_state_validation(state, None, ValidationResult.ILLEGAL_PLACEMENT)

        # Overlapping pieces (This would need to be constructed manually since QFEN can't represent overlaps)
        bb_with_overlap = list(State.empty().bb)
        bb_with_overlap[0] |= 1  # Player 0 shape A at position 0
        bb_with_overlap[4] |= 1  # Player 1 shape A at position 0 (overlap!)
        state = State(tuple(bb_with_overlap))
        _assert_game_state_validation(state, None, ValidationResult.PIECE_OVERLAP)

    def test_validation_with_exceptions(self):
        """Test that validation can raise exceptions when requested."""
        # Valid state should not raise
        state = State.from_qfen("A.../..../..../....", validate=False)
        validate_game_state(state.bb, raise_on_error=True)  # Should not raise

        # Invalid state should raise
        state = State.from_qfen("AAA./..../..../....", validate=False)
        with pytest.raises(ValidationError):
            validate_game_state(state.bb, raise_on_error=True)


class TestPlayerTurnValidation:
    """Test validation of expected player turns."""

    def test_valid_player_turns(self):
        """Test validation of correct player turns."""
        # Empty board - Player 0's turn
        state = State.from_qfen("..../..../..../....", validate=False)
        _assert_game_state_validation(state, 0, ValidationResult.OK)

        # Player 0 moved - Player 1's turn
        state = State.from_qfen("A.../..../..../....", validate=False)
        _assert_game_state_validation(state, 1, ValidationResult.OK)
        """Test validation of incorrect player turns."""


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
        _assert_game_state_validation(state, None, ValidationResult.PIECE_OVERLAP)

        with pytest.raises(ValidationError):
            validate_game_state(state.bb, raise_on_error=True)
