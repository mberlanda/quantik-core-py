from quantik_core import State
from quantik_core.plugins.validation import (
    ValidationResult,
    WinStatus,
    count_pieces_by_shape,
    get_current_player,
    validate_player_turn,
    check_game_winner,
    is_game_over,
)


class TestStateValidation:
    def test_count_pieces_by_shape_when_board_empty(self):
        state = State.empty()
        player0_counts, player1_counts = count_pieces_by_shape(state)
        assert player0_counts == [0, 0, 0, 0]
        assert player1_counts == [0, 0, 0, 0]

    def test_count_pieces_by_shape_when_board_has_shapes(self):
        state = State.from_qfen("A.../.ad./..B./...B")
        player0_counts, player1_counts = count_pieces_by_shape(state)
        assert player0_counts == [1, 2, 0, 0]
        assert player1_counts == [1, 0, 0, 1]


class TestCurrentPlayerDetection:
    """Test whose turn it is based on piece counts."""

    def test_empty_board_player0_turn(self):
        """Empty board should be player 0's turn."""
        state = State.empty()
        player, result = get_current_player(state)
        assert result == ValidationResult.OK
        assert player == 0

    def test_equal_pieces_player0_turn(self):
        """Equal pieces should be player 0's turn."""
        state = State.from_qfen("A.../a.../..../....")
        player, result = get_current_player(state)
        assert result == ValidationResult.OK
        assert player == 0

    def test_one_extra_piece_player1_turn(self):
        """One extra piece for player 0 should be player 1's turn."""
        state = State.from_qfen("A.../..../..../....")
        player, result = get_current_player(state)
        assert result == ValidationResult.OK
        assert player == 1

    def test_one_extra_piece_player0_turn(self):
        """One extra piece for player 1 should be invalid."""
        state = State.from_qfen("A.../a.../a.../....")
        player, result = get_current_player(state)
        assert result == ValidationResult.TURN_BALANCE_INVALID
        assert player is None


class TestPlayerTurnValidation:
    """Test validate_player_turn function."""

    def test_validate_invalid_player_id(self):
        """Test validation with invalid player ID."""
        state = State.empty()
        result = validate_player_turn(state, 2)
        assert result == ValidationResult.INVALID_PLAYER

        result = validate_player_turn(state, -1)
        assert result == ValidationResult.INVALID_PLAYER

    def test_validate_correct_turn_player0_empty_board(self):
        """Test validation when it's correctly player 0's turn on empty board."""
        state = State.empty()
        result = validate_player_turn(state, 0)
        assert result == ValidationResult.OK

    def test_validate_wrong_turn_player1_empty_board(self):
        """Test validation when expecting player 1 but it's player 0's turn."""
        state = State.empty()
        result = validate_player_turn(state, 1)
        assert result == ValidationResult.NOT_PLAYER_TURN

    def test_validate_correct_turn_player1(self):
        """Test validation when it's correctly player 1's turn."""
        # Player 0 has one piece, so it's player 1's turn
        state = State.from_qfen("A.../..../..../....")
        result = validate_player_turn(state, 1)
        assert result == ValidationResult.OK

    def test_validate_wrong_turn_player0_when_player1_should_move(self):
        """Test validation when expecting player 0 but it's player 1's turn."""
        # Player 0 has one piece, so it's player 1's turn
        state = State.from_qfen("A.../..../..../....")
        result = validate_player_turn(state, 0)
        assert result == ValidationResult.NOT_PLAYER_TURN

    def test_validate_turn_with_invalid_state(self):
        """Test validation when the game state itself is invalid (turn balance)."""
        # Player 1 has more pieces than player 0, which is invalid
        state = State.from_qfen("A.../a.../a.../....")
        result = validate_player_turn(state, 0)
        assert result == ValidationResult.TURN_BALANCE_INVALID

        result = validate_player_turn(state, 1)
        assert result == ValidationResult.TURN_BALANCE_INVALID


class TestGameWinnerDetection:
    """Test game winner detection using endgame utility."""

    def test_no_winner_empty_board(self):
        """Test that empty board has no winner."""
        state = State.empty()
        assert check_game_winner(state) == WinStatus.NO_WIN
        assert not is_game_over(state)

    def test_no_winner_partial_game(self):
        """Test that partial game has no winner."""
        state = State.from_qfen("A.b./..c./D.../..a.")
        assert check_game_winner(state) == WinStatus.NO_WIN
        assert not is_game_over(state)

    def test_player_0_wins_more_pieces(self):
        """Test Player 0 wins when they have more pieces."""
        # Player 0 has 3 pieces, Player 1 has 1 piece
        state = State.from_qfen("ABCd/..../..../....")
        assert check_game_winner(state) == WinStatus.PLAYER_0_WINS
        assert is_game_over(state)

    def test_player_1_wins_more_pieces(self):
        """Test Player 1 wins when they have more pieces."""
        # Player 1 has 3 pieces, Player 0 has 1 piece
        state = State.from_qfen("Abcd/a.../..../....")
        assert check_game_winner(state) == WinStatus.PLAYER_1_WINS
        assert is_game_over(state)

    def test_player_0_wins_equal_pieces(self):
        """Test Player 0 wins when pieces are equal (they made the winning move)."""
        # Both players have 2 pieces - Player 0 wins by default
        state = State.from_qfen("AbCd/..../..../....")
        assert check_game_winner(state) == WinStatus.PLAYER_0_WINS
        assert is_game_over(state)

    def test_mixed_win_combinations(self):
        """Test various mixed player winning combinations."""
        # Row win with different combinations
        state = State.from_qfen("aBcD/a.../..../....")
        assert check_game_winner(state) == WinStatus.PLAYER_1_WINS

        # Column win
        state = State.from_qfen("A.../b.../C.../d...")
        assert check_game_winner(state) == WinStatus.PLAYER_0_WINS

        # Zone win
        state = State.from_qfen("Ab../Cd../..../....")
        assert check_game_winner(state) == WinStatus.PLAYER_0_WINS
