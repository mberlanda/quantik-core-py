from quantik_core import State
from quantik_core.plugins.validation import count_pieces_by_shape

class TestStateValidation:
    def test_count_pieces_by_shape_when_board_empty(self):
        state = State.empty()
        player0_counts, player1_counts = count_pieces_by_shape(state)
        assert player0_counts == [0, 0, 0, 0]
        assert player1_counts == [0, 0, 0, 0]

    def test_count_pieces_by_shape_when_board_empty(self):
        state = State.from_qfen('A.../.ad./..B./...B')
        player0_counts, player1_counts = count_pieces_by_shape(state)
        assert player0_counts == [1, 2, 0, 0]
        assert player1_counts == [1, 0, 0, 1]