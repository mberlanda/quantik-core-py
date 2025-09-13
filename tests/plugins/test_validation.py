from quantik_core import State
from quantik_core.plugins.validation import (
    WinStatus,
    check_game_winner,
    is_game_over,
)


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
