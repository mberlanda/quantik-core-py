from quantik_core import State
from quantik_core.plugins.endgame import has_winning_line


class TestEndgameUtility:
    """Test endgame utility functions."""

    def test_no_win_empty_board(self):
        """Test that empty board has no winning line."""
        state = State.empty()
        assert not has_winning_line(state)

    def test_no_win_partial_games(self):
        """Test various partial games with no complete lines."""
        # Scattered pieces
        state = State.from_qfen("A.b./..c./D.../..a.")
        assert not has_winning_line(state)

        # Almost complete row (missing one shape)
        state = State.from_qfen("ABB./..../..../....")
        assert not has_winning_line(state)

        # Almost complete column (missing one shape)
        state = State.from_qfen("A.../A.../C.../....")
        assert not has_winning_line(state)

        # Almost complete zone (missing one shape)
        state = State.from_qfen("AB../A.../..../....")
        assert not has_winning_line(state)

    def test_rows_win(self):
        """Test explicit row wins with AbCd combinations."""
        row_wins = [
            "AbCd/..../..../....",  # row 0
            "..../AbCd/..../....",  # row 1
            "..../..../AbCd/....",  # row 2
            "..../..../..../AbCd",  # row 3
            # Different permutations of the same win
            "ABCD/..../..../....",  # row 0 - all Player 0
            "abcd/..../..../....",  # row 0 - all Player 1
            "aBcD/..../..../....",  # row 0 - mixed
            "CdAb/..../..../....",  # row 0 - different order
            "DcbA/..../..../....",  # row 0 - reverse order
            "..../DCBA/..../....",  # row 1
            "..../dcba/..../....",  # row 1 - all Player 1
            "..../DcBa/..../....",  # row 1 - mixed
            "..../..../BaDc/....",  # row 2
            "..../..../bAdC/....",  # row 2 - mixed
            "..../..../..../CaBd",  # row 3
            "..../..../..../cabd",  # row 3 - all Player 1
        ]

        for qfen in row_wins:
            state = State.from_qfen(qfen)
            assert has_winning_line(state), f"Row should win: {qfen}"

    def test_columns_win(self):
        """Test explicit column wins with AbCd combinations."""
        column_wins = [
            "A.../b.../C.../d...",  # column 0
            ".A../.b../.C../.d..",  # column 1
            "..A./..b./..C./..d.",  # column 2
            "...A/...b/...C/...d",  # column 3
            # Different permutations
            "A.../B.../C.../D...",  # column 0 - all Player 0
            "a.../b.../c.../d...",  # column 0 - all Player 1
            "D.../c.../B.../a...",  # column 0 - mixed reverse
            "C.../a.../D.../b...",  # column 0 - different order
            ".D../.c../.B../.a..",  # column 1
            ".d../.C../.b../.A..",  # column 1 - mixed
            "..B./..a./..D./..c.",  # column 2
            "..b./..A./..d./..C.",  # column 2 - mixed
            "...C/...a/...D/...b",  # column 3
            "...c/...A/...d/...B",  # column 3 - mixed
        ]

        for qfen in column_wins:
            state = State.from_qfen(qfen)
            assert has_winning_line(state), f"Column should win: {qfen}"

    def test_zones_win(self):
        """Test explicit 2x2 zone wins with AbCd combinations."""
        zone_wins = [
            # Top-left zone (positions 0,1,4,5)
            "Ab../Cd../..../....",  # zone 0
            "AB../CD../..../....",  # zone 0 - all Player 0
            "ab../cd../..../....",  # zone 0 - all Player 1
            "Ca../Db../..../....",  # zone 0 - different order
            "dc../ba../..../....",  # zone 0 - reverse
            # Top-right zone (positions 2,3,6,7)
            "..Ab/..Cd/..../....",  # zone 1
            "..AB/..CD/..../....",  # zone 1 - all Player 0
            "..ab/..cd/..../....",  # zone 1 - all Player 1
            "..Ca/..Db/..../....",  # zone 1 - different order
            "..dc/..ba/..../....",  # zone 1 - reverse
            # Bottom-left zone (positions 8,9,12,13)
            "..../..../Ab../Cd..",  # zone 2
            "..../..../AB../CD..",  # zone 2 - all Player 0
            "..../..../ab../cd..",  # zone 2 - all Player 1
            "..../..../Ca../Db..",  # zone 2 - different order
            "..../..../dc../ba..",  # zone 2 - reverse
            # Bottom-right zone (positions 10,11,14,15)
            "..../..../..Ab/..Cd",  # zone 3
            "..../..../..AB/..CD",  # zone 3 - all Player 0
            "..../..../..ab/..cd",  # zone 3 - all Player 1
            "..../..../..Ca/..Db",  # zone 3 - different order
            "..../..../..dc/..ba",  # zone 3 - reverse
        ]

        for qfen in zone_wins:
            state = State.from_qfen(qfen)
            assert has_winning_line(state), f"Zone should win: {qfen}"

    def test_no_win_invalid_patterns(self):
        """Test patterns that should NOT be winning."""

        invalid_patterns = [
            # Diagonal patterns (not valid wins)
            "A.../bC../..d./....",  # Main diagonal A-b-C-d
            "...A/.Cb./d.../....",  # Anti-diagonal A-C-b-d
            "A..b/..../.C.d/....",  # Scattered diagonal
            "D.../aC../..b./...A",  # Full diagonal with all 4 shapes
            # Central 2x2 (positions 1,2,5,6 - not a valid zone)
            ".AB./.Cd./..../....",  # Central top 2x2
            ".Ab./.cD./..../....",  # Central top 2x2 mixed
            "..../..AB/..Cd/....",  # Central bottom 2x2
            ".ABC/.Dd./..../....",  # Central overlap with extra pieces
            # Other invalid 2x2 combinations
            "A.b./.C.d/..../....",  # Positions 0,2,4,6 (not adjacent)
            "A..b/..../.C.d/....",  # Positions 0,3,8,11 (diagonal-like)
            ".A.b/..../.C.d/....",  # Positions 1,3,9,11
            # L-shapes and irregular patterns
            "ABC./.D../..../....",  # L-shape top-left
            "AB../C.../D.../....",  # Vertical L
            # "ABCD/A.../..../....",  # Row + extra piece - valid
            "A.C./.B../..D./....",  # Scattered irregular
            "AB../..../CD../....",  # Two separate 1x2 blocks
            # Invalid line patterns
            # "AA../BB../CC../DD..",  # Same shapes in different rows - valid column
            # "A.A./B.B./C.C./D.D.",  # Same shapes in different columns - valid column
            "AB../AB../..../....",  # Repeated pattern in zone
            # Almost-valid patterns (missing shapes)
            "ABC./..../..../....",  # Row missing D
            "A.../B.../C.../....",  # Column missing D
            "AB../C.../..../....",  # Zone missing D
            # Too many pieces but wrong pattern - fails qfen deserialization
            # "ABCDA/..../..../...",  # 5 pieces in row
            # "AABBCC/..../..../....",  # 6 pieces but duplicates
        ]

        for qfen in invalid_patterns:
            state = State.from_qfen(qfen)
            assert not has_winning_line(
                state
            ), f"Invalid pattern should not win: {qfen}"

    def test_no_win_incomplete_lines(self):
        """Test lines that are incomplete (missing shapes or have duplicates)."""

        incomplete_patterns = [
            # Rows missing one shape
            "ABC./..../..../....",  # Row 0 missing D
            "ABD./..../..../....",  # Row 0 missing C
            "ACD./..../..../....",  # Row 0 missing B
            "BCD./..../..../....",  # Row 0 missing A
            "..../ABC./..../....",  # Row 1 missing D
            "..../..../ABC./....",  # Row 2 missing D
            "..../..../..../ABC.",  # Row 3 missing D
            # Columns missing one shape
            "A.../B.../C.../....",  # Column 0 missing D
            ".A../.B../.C../....",  # Column 1 missing D
            "..A./..B./..C./....",  # Column 2 missing D
            "...A/...B/...C/....",  # Column 3 missing D
            # Zones missing one shape
            "AB../C.../..../....",  # Zone 0 missing D
            "..AB/..C./..../....",  # Zone 1 missing D
            "..../..../AB../C...",  # Zone 2 missing D
            "..../..../.AB./.C..",  # Zone 3 missing D
            # Lines with duplicate shapes
            "AABC/..../..../....",  # Row with duplicate A
            "ABBC/..../..../....",  # Row with duplicate B
            "ABCC/..../..../....",  # Row with duplicate C
            "ABDD/..../..../....",  # Row with duplicate D
            "AAAA/..../..../....",  # Row with all same shape
            "BBBB/..../..../....",  # Row with all same shape B
            # Column duplicates
            "A.../A.../B.../C...",  # Column 0 with duplicate A
            "A.../B.../B.../C...",  # Column 0 with duplicate B
            # Zone duplicates
            "AA../BC../..../....",  # Zone 0 with duplicate A
            "AB../AC../..../....",  # Zone 0 with duplicate A
        ]

        for qfen in incomplete_patterns:
            state = State.from_qfen(qfen)
            assert not has_winning_line(
                state
            ), f"Incomplete line should not win: {qfen}"

    def test_win_player_combinations(self):
        """Test various player (case) combinations that should win."""

        valid_combinations = [
            # All Player 0 (uppercase)
            "ABCD/..../..../....",  # Row 0
            "A.../B.../C.../D...",  # Column 0
            "AB../CD../..../....",  # Zone 0
            # All Player 1 (lowercase)
            "abcd/..../..../....",  # Row 0
            "a.../b.../c.../d...",  # Column 0
            "ab../cd../..../....",  # Zone 0
            # Mixed combinations
            "AbCd/..../..../....",  # Row 0 - alternating
            "aBcD/..../..../....",  # Row 0 - alternating (different)
            "ABcd/..../..../....",  # Row 0 - first half P0, second P1
            "abCD/..../..../....",  # Row 0 - first half P1, second P0
            "AcBd/..../..../....",  # Row 0 - mixed pattern
            "bDaC/..../..../....",  # Row 0 - different mixed pattern
            # Mixed in columns
            "A.../b.../C.../d...",  # Column 0 - alternating
            "a.../B.../c.../D...",  # Column 0 - alternating (different)
            # Mixed in zones
            "Ab../cD../..../....",  # Zone 0 - mixed
            "aB../Cd../..../....",  # Zone 0 - different mixed
        ]

        for qfen in valid_combinations:
            state = State.from_qfen(qfen)
            assert has_winning_line(
                state
            ), f"Valid player combination should win: {qfen}"

    def test_multiple_winning_lines(self):
        """Test cases where multiple lines have all 4 shapes."""

        # Row 0 and Column 0 both win
        state = State.from_qfen("ABCD/B.../C.../D...")
        assert has_winning_line(state)

        # Row 0 and Zone 0 both win
        state = State.from_qfen("ABCD/AB../..../....")
        assert has_winning_line(state)

        # All rows win (extreme case)
        state = State.from_qfen("ABCD/abcd/DCBA/dcba")
        assert has_winning_line(state)
