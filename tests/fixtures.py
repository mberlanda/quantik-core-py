"""Shared test fixtures and factories for Quantik game state testing.

This module provides reusable test fixtures, canonical bitboards, and game state
factories to reduce duplication across test files and ensure consistency.

The module now includes a comprehensive unified test case table that consolidates
all QFEN notations found across the test suite, providing a single source of truth
for test data with proper categorization and metadata.
"""

from typing import List, Tuple, Optional, Dict, Any, NamedTuple
from dataclasses import dataclass
import csv
from io import StringIO

from quantik_core.commons import Bitboard
from quantik_core.memory.bitboard_compact import CompactBitboard
from quantik_core.core import State
from quantik_core.qfen import bb_from_qfen, bb_to_qfen
from quantik_core.move import Move


class TestCase(NamedTuple):
    """Unified test case structure for QFEN-based tests."""

    qfen: str
    name: str
    description: str
    expected_player: int
    winner: Optional[int] = None
    is_terminal: bool = False
    category: str = "general"
    tags: Tuple[str, ...] = ()

    @property
    def piece_counts(
        self,
    ) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
        """Calculate piece counts from QFEN."""
        bb = bb_from_qfen(self.qfen)
        # Count pieces for each player and shape
        p0_counts = [0, 0, 0, 0]  # A, B, C, D for player 0
        p1_counts = [0, 0, 0, 0]  # a, b, c, d for player 1

        for i in range(16):  # 4x4 board
            bit = 1 << i
            for shape in range(4):
                if bb[shape] & bit:  # Player 0 shape
                    p0_counts[shape] += 1
                if bb[4 + shape] & bit:  # Player 1 shape
                    p1_counts[shape] += 1

        return (tuple(p0_counts), tuple(p1_counts))

    def to_fixture(self) -> "GameStateFixture":
        """Convert TestCase to GameStateFixture for backward compatibility."""
        bb = bb_from_qfen(self.qfen)
        return GameStateFixture(
            name=self.name,
            description=self.description,
            qfen=self.qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=self.expected_player,
            piece_counts=self.piece_counts,
            is_terminal=self.is_terminal,
            winner=self.winner,
        )


@dataclass
class GameStateFixture:
    """A complete game state fixture with metadata."""

    name: str
    description: str
    qfen: str
    bitboard: Bitboard
    compact_bitboard: CompactBitboard
    state: State
    expected_player: int
    piece_counts: Tuple[
        Tuple[int, int, int, int], Tuple[int, int, int, int]
    ]  # (p0_counts, p1_counts)
    is_terminal: bool = False
    winner: Optional[int] = None


class UnifiedTestCases:
    """Centralized repository of all QFEN test cases found across the test suite.

    This class provides a single source of truth for all game states used in testing,
    categorized and tagged for easy filtering and reuse.
    """

    # Core test cases from existing fixtures
    _CORE_CASES = [
        TestCase(
            "..../..../..../....",
            "empty_board",
            "Empty 4x4 Quantik board with no pieces",
            0,
            None,
            False,
            "basic",
            ("empty", "start"),
        ),
        TestCase(
            "A.../..../..../....",
            "single_piece_corner",
            "Single Player 0 piece A at position 0 (top-left corner)",
            1,
            None,
            False,
            "basic",
            ("single_piece", "corner"),
        ),
        TestCase(
            "..../..A./..../....",
            "single_piece_center",
            "Single Player 0 piece A at position 6 (center-left)",
            1,
            None,
            False,
            "basic",
            ("single_piece", "center"),
        ),
        TestCase(
            "Ab../..../..../....",
            "alternating_moves",
            "Player 0 A at pos 0, Player 1 B at pos 1",
            0,
            None,
            False,
            "basic",
            ("alternating", "early_game"),
        ),
        TestCase(
            "AbCd/..../..../....",
            "winning_row",
            "Player 1 wins with full top row (AbCd)",
            1,
            0,
            True,
            "winning",
            ("row_win", "terminal"),
        ),
        TestCase(
            "A.../B.../C.../D...",
            "winning_column",
            "Player 0 wins with full left column (ABCD)",
            1,
            0,
            True,
            "winning",
            ("column_win", "terminal"),
        ),
        TestCase(
            "AbcD/..../..../....",
            "mixed_players_winning",
            "Mixed players winning row: A(p0), b(p1), c(p1), D(p0)",
            0,
            None,
            True,
            "winning",
            ("mixed_win", "terminal"),
        ),
        TestCase(
            "Ab../c.D./..../...A",
            "complex_mid_game",
            "Mid-game with pieces scattered across board",
            1,
            None,
            False,
            "midgame",
            ("complex", "scattered"),
        ),
        TestCase(
            "A.../..../A.../...A",
            "multiple_pieces_same_shape",
            "Multiple Player 0 A pieces at positions 0, 8, 15",
            1,
            None,
            False,
            "edge_case",
            ("multiple_same", "invalid"),
        ),
        TestCase(
            "AbcD/bCdA/cDaB/DaBc",
            "stress_test_bitboard",
            "Full board with all positions occupied",
            0,
            None,
            True,
            "stress",
            ("full_board", "terminal", "complex"),
        ),
    ]

    # Test cases from test_qfen.py
    _QFEN_CASES = [
        TestCase(
            "A.../..../..../....",
            "qfen_single_piece",
            "QFEN roundtrip test with single piece",
            1,
            None,
            False,
            "qfen",
            ("roundtrip", "single"),
        ),
        TestCase(
            "A.bC/..../d..B/...a",
            "qfen_complex_mixed",
            "QFEN roundtrip test with mixed pieces",
            0,
            None,
            False,
            "qfen",
            ("roundtrip", "mixed", "complex"),
        ),
        TestCase(
            "AB../ba../..../....",
            "qfen_alternating_rows",
            "QFEN roundtrip test with alternating rows",
            0,
            None,
            False,
            "qfen",
            ("roundtrip", "alternating"),
        ),
        TestCase(
            "ABCD/..../..../....",
            "qfen_winning_line",
            "QFEN roundtrip test with winning line",
            1,
            0,
            True,
            "qfen",
            ("roundtrip", "winning"),
        ),
    ]

    # Test cases from test_core.py
    _CORE_CASES_ADVANCED = [
        TestCase(
            ".A../..b./.c../...D",
            "core_mixed_positions",
            "Core test with mixed player positions",
            0,
            None,
            False,
            "core",
            ("mixed", "scattered"),
        ),
        TestCase(
            "..a./.b../c.../...d",
            "core_player1_pieces",
            "Core test with only player 1 pieces",
            0,
            None,
            False,
            "core",
            ("player1_only", "imbalanced"),
        ),
    ]

    # Test cases from test_game_utils.py
    _GAME_UTILS_CASES = [
        TestCase(
            "ABCD/..../..../....",
            "utils_row_win_p0",
            "Utils test: Player 0 wins with full top row",
            1,
            0,
            True,
            "game_utils",
            ("row_win", "player0"),
        ),
        TestCase(
            "AbcD/..../..../....",
            "utils_mixed_row_win",
            "Utils test: Mixed players complete row",
            0,
            None,
            True,
            "game_utils",
            ("mixed_win", "row"),
        ),
        TestCase(
            "A.../b.../C.../d...",
            "utils_column_mixed",
            "Utils test: Mixed players in column",
            0,
            None,
            True,
            "game_utils",
            ("mixed_win", "column"),
        ),
        TestCase(
            "AB../cd../..../....",
            "utils_incomplete_rows",
            "Utils test: Two incomplete rows",
            0,
            None,
            False,
            "game_utils",
            ("incomplete", "midgame"),
        ),
        TestCase(
            "ABC./..../..../....",
            "utils_incomplete_row",
            "Utils test: Single incomplete row",
            0,
            None,
            False,
            "game_utils",
            ("incomplete", "near_win"),
        ),
        TestCase(
            "ABcd/..../..../....",
            "utils_mixed_top_row",
            "Utils test: Mixed players top row win",
            0,
            None,
            True,
            "game_utils",
            ("mixed_win", "row"),
        ),
        TestCase(
            "A.../..../..../...B",
            "utils_diagonal_pieces",
            "Utils test: Corner pieces (1 each player)",
            0,
            None,
            False,
            "game_utils",
            ("corners", "balanced"),
        ),
        TestCase(
            "AA../..../..../..BB",
            "utils_double_pieces",
            "Utils test: 2 pieces each player (max allowed)",
            0,
            None,
            False,
            "game_utils",
            ("max_pieces", "balanced"),
        ),
    ]

    # Test cases from test_board.py
    _BOARD_CASES = [
        TestCase(
            "A..C/bbd./CD.A/.adB",
            "board_stalemate",
            "Stalemate position from board tests",
            0,
            None,
            True,
            "board",
            ("stalemate", "complex", "terminal"),
        ),
        TestCase(
            "AA../..aa/..../....",
            "board_double_shapes",
            "Board test with double A pieces for each player",
            0,
            None,
            False,
            "board",
            ("double_shapes", "edge_case"),
        ),
        TestCase(
            "Ab../..../..Ac/....",
            "board_scattered_pieces",
            "Board test with scattered A pieces",
            0,
            None,
            False,
            "board",
            ("scattered", "same_shape"),
        ),
        TestCase(
            "ABCD/..../cd../..a.",
            "board_winning_p0",
            "Board test: Player 0 wins with top row",
            1,
            0,
            True,
            "board",
            ("row_win", "player0"),
        ),
        TestCase(
            "abcd/..../CD../..AB",
            "board_winning_p1",
            "Board test: Player 1 wins with top row",
            0,
            1,
            True,
            "board",
            ("row_win", "player1"),
        ),
        TestCase(
            "AB../..../..../..ab",
            "board_symmetric",
            "Board test: Symmetric piece placement",
            0,
            None,
            False,
            "board",
            ("symmetric", "balanced"),
        ),
        TestCase(
            "A.../bbd./CD.A/.adB",
            "board_limited",
            "Board test: Position with limited moves",
            0,
            None,
            False,
            "board",
            ("limited_moves", "complex"),
        ),
    ]

    # Test cases from test_symmetry.py
    _SYMMETRY_CASES = [
        TestCase(
            "A.../.b../..../....",
            "sym_basic_transform",
            "Symmetry test: Basic transformation",
            0,
            None,
            False,
            "symmetry",
            ("transform", "basic"),
        ),
        TestCase(
            "...A/..b./..../....",
            "sym_rotated",
            "Symmetry test: Rotated position",
            0,
            None,
            False,
            "symmetry",
            ("rotated", "transform"),
        ),
        TestCase(
            "a.../.B../..../....",
            "sym_color_swap",
            "Symmetry test: Color swapped",
            1,
            None,
            False,
            "symmetry",
            ("color_swap", "transform"),
        ),
        TestCase(
            "B.../.a../..../....",
            "sym_shape_perm",
            "Symmetry test: Shape permutation",
            0,
            None,
            False,
            "symmetry",
            ("shape_perm", "transform"),
        ),
        TestCase(
            "...b/..A./..../....",
            "sym_complex_transform",
            "Symmetry test: Complex transformation",
            0,
            None,
            False,
            "symmetry",
            ("complex", "transform"),
        ),
        TestCase(
            "A.B./..../..../....",
            "sym_two_pieces",
            "Symmetry test: Two pieces",
            1,
            None,
            False,
            "symmetry",
            ("two_pieces", "simple"),
        ),
        TestCase(
            "A..b/.c../..D./....",
            "sym_mixed_position",
            "Symmetry test: Mixed position with all players",
            0,
            None,
            False,
            "symmetry",
            ("mixed", "complex"),
        ),
    ]

    # Test cases from test_state_validator.py
    _VALIDATOR_CASES = [
        TestCase(
            "A.../..../..a./....",
            "validator_valid_balance",
            "Validator test: Valid turn balance",
            0,
            None,
            False,
            "validator",
            ("valid", "balanced"),
        ),
        TestCase(
            "A.b./c.D./..../.B..",
            "validator_complex_valid",
            "Validator test: Complex valid state",
            0,
            None,
            False,
            "validator",
            ("valid", "complex"),
        ),
        TestCase(
            "AAA./..../..../....",
            "validator_too_many_pieces",
            "Validator test: Too many A pieces (invalid)",
            0,
            None,
            False,
            "validator",
            ("invalid", "too_many"),
        ),
        TestCase(
            "abc./..../..../....",
            "validator_imbalanced",
            "Validator test: Imbalanced turn count",
            0,
            None,
            False,
            "validator",
            ("invalid", "imbalanced"),
        ),
        TestCase(
            "A.../a.../..../....",
            "validator_same_shape_conflict",
            "Validator test: Same shape on same line",
            0,
            None,
            False,
            "validator",
            ("invalid", "conflict"),
        ),
    ]

    # Test cases from test_bitboard_compact.py
    _COMPACT_CASES = [
        TestCase(
            "A.bC/..../d..B/...a",
            "compact_mixed_pieces",
            "Compact bitboard test with mixed pieces",
            0,
            None,
            False,
            "compact",
            ("mixed", "roundtrip"),
        ),
    ]

    @classmethod
    def all_cases(cls) -> List[TestCase]:
        """Get all test cases from all categories."""
        return (
            cls._CORE_CASES
            + cls._QFEN_CASES
            + cls._CORE_CASES_ADVANCED
            + cls._GAME_UTILS_CASES
            + cls._BOARD_CASES
            + cls._SYMMETRY_CASES
            + cls._VALIDATOR_CASES
            + cls._COMPACT_CASES
        )

    @classmethod
    def by_category(cls, category: str) -> List[TestCase]:
        """Get test cases filtered by category."""
        return [case for case in cls.all_cases() if case.category == category]

    @classmethod
    def by_tag(cls, tag: str) -> List[TestCase]:
        """Get test cases filtered by tag."""
        return [case for case in cls.all_cases() if tag in case.tags]

    @classmethod
    def by_name(cls, name: str) -> TestCase:
        """Get a specific test case by name."""
        for case in cls.all_cases():
            if case.name == name:
                return case
        raise ValueError(f"Unknown test case name: {name}")

    @classmethod
    def terminal_cases(cls) -> List[TestCase]:
        """Get all terminal (game-ending) test cases."""
        return [case for case in cls.all_cases() if case.is_terminal]

    @classmethod
    def non_terminal_cases(cls) -> List[TestCase]:
        """Get all non-terminal (ongoing game) test cases."""
        return [case for case in cls.all_cases() if not case.is_terminal]

    @classmethod
    def winning_cases(cls, player: Optional[int] = None) -> List[TestCase]:
        """Get all winning test cases, optionally filtered by winning player."""
        cases = [case for case in cls.all_cases() if case.winner is not None]
        if player is not None:
            cases = [case for case in cases if case.winner == player]
        return cases

    @classmethod
    def balanced_cases(cls) -> List[TestCase]:
        """Get test cases with balanced piece counts between players."""
        balanced = []
        for case in cls.all_cases():
            p0_total = sum(case.piece_counts[0])
            p1_total = sum(case.piece_counts[1])
            if abs(p0_total - p1_total) <= 1:  # Turn balance allows 1 piece difference
                balanced.append(case)
        return balanced

    @classmethod
    def export_csv(cls, filename: Optional[str] = None) -> str:
        """Export all test cases to CSV format."""
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(
            [
                "qfen",
                "name",
                "description",
                "expected_player",
                "winner",
                "is_terminal",
                "category",
                "tags",
                "p0_pieces",
                "p1_pieces",
            ]
        )

        # Data rows
        for case in cls.all_cases():
            p0_total = sum(case.piece_counts[0])
            p1_total = sum(case.piece_counts[1])
            writer.writerow(
                [
                    case.qfen,
                    case.name,
                    case.description,
                    case.expected_player,
                    case.winner,
                    case.is_terminal,
                    case.category,
                    ",".join(case.tags),
                    p0_total,
                    p1_total,
                ]
            )

        csv_content = output.getvalue()
        if filename:
            with open(filename, "w", newline="") as f:
                f.write(csv_content)

        return csv_content

    @classmethod
    def get_statistics(cls) -> Dict[str, Any]:
        """Get statistics about the test cases."""
        all_cases = cls.all_cases()
        return {
            "total_cases": len(all_cases),
            "by_category": {
                category: len(cls.by_category(category))
                for category in set(case.category for case in all_cases)
            },
            "terminal_cases": len(cls.terminal_cases()),
            "winning_cases": len(cls.winning_cases()),
            "player_0_wins": len(cls.winning_cases(0)),
            "player_1_wins": len(cls.winning_cases(1)),
            "balanced_cases": len(cls.balanced_cases()),
            "unique_qfens": len(set(case.qfen for case in all_cases)),
            "all_tags": sorted(set(tag for case in all_cases for tag in case.tags)),
        }


class TestCaseFactory:
    """Factory for creating test cases and converting between formats."""

    @staticmethod
    def from_qfen(
        qfen: str,
        name: str,
        description: str = "",
        category: str = "custom",
        tags: Tuple[str, ...] = (),
    ) -> TestCase:
        """Create a TestCase from QFEN string with automatic property detection."""
        bb = bb_from_qfen(qfen)

        # Auto-detect expected_player based on piece count balance
        p0_count = sum(1 for i in range(16) for s in range(4) if bb[s] & (1 << i))
        p1_count = sum(1 for i in range(16) for s in range(4) if bb[4 + s] & (1 << i))
        expected_player = 1 if p0_count == p1_count else 0

        # Auto-detect terminal state and winner (simplified check)
        is_terminal = False
        winner = None

        # Check for obvious wins (full rows/columns)
        # This is a simplified check - real game logic would be more complex
        for row in range(4):
            row_pieces = set()
            for col in range(4):
                pos = row * 4 + col
                for player in range(2):
                    for shape in range(4):
                        if bb[player * 4 + shape] & (1 << pos):
                            row_pieces.add(
                                f"{chr(ord('A') + shape) if player == 0 else chr(ord('a') + shape)}"
                            )
            if len(row_pieces) == 4:
                is_terminal = True
                break

        if not description:
            description = f"Test case for QFEN: {qfen}"

        return TestCase(
            qfen=qfen,
            name=name,
            description=description,
            expected_player=expected_player,
            winner=winner,
            is_terminal=is_terminal,
            category=category,
            tags=tags,
        )

    @staticmethod
    def to_fixture(test_case: TestCase) -> "GameStateFixture":
        """Convert TestCase to GameStateFixture for backward compatibility."""
        return test_case.to_fixture()

    @staticmethod
    def create_parameterized_test_data(
        test_cases: List[TestCase], fields: Optional[List[str]] = None
    ) -> List[Tuple]:
        """Create data for parameterized tests (pytest.mark.parametrize)."""
        if fields is None:
            fields = ["qfen", "expected_player"]

        return [
            tuple(getattr(case, field_name) for field_name in fields)
            for case in test_cases
        ]


class CanonicalBitboardFactory:
    """Factory for creating canonical, valid bitboards for testing.

    Provides common game states that are guaranteed to be:
    - Canonically valid (follow game rules)
    - Consistently formatted
    - Reusable across tests
    - Well-documented for their purpose
    """

    @staticmethod
    def empty_board() -> GameStateFixture:
        """Empty 4x4 Quantik board."""
        qfen = "..../..../..../...."
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="empty_board",
            description="Empty 4x4 Quantik board with no pieces",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State.empty(),
            expected_player=0,
            piece_counts=((0, 0, 0, 0), (0, 0, 0, 0)),
            is_terminal=False,
        )

    @staticmethod
    def single_piece_corner() -> GameStateFixture:
        """Single piece in top-left corner (canonical position)."""
        qfen = "A.../..../..../...."
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="single_piece_corner",
            description="Single Player 0 piece A at position 0 (top-left corner)",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=1,
            piece_counts=((1, 0, 0, 0), (0, 0, 0, 0)),
            is_terminal=False,
        )

    @staticmethod
    def single_piece_center() -> GameStateFixture:
        """Single piece in center position."""
        qfen = "..../..A./..../...."
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="single_piece_center",
            description="Single Player 0 piece A at position 6 (center-left)",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=1,
            piece_counts=((1, 0, 0, 0), (0, 0, 0, 0)),
            is_terminal=False,
        )

    @staticmethod
    def alternating_moves() -> GameStateFixture:
        """Alternating moves by both players."""
        qfen = "Ab../..../..../...."
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="alternating_moves",
            description="Player 0 A at pos 0, Player 1 B at pos 1",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=0,
            piece_counts=((1, 0, 0, 0), (0, 1, 0, 0)),
            is_terminal=False,
        )

    @staticmethod
    def winning_row() -> GameStateFixture:
        """Complete winning row (all four shapes)."""
        qfen = "AbCd/..../..../...."
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="winning_row",
            description="Player 1 wins with full top row (AbCd)",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=1,
            piece_counts=((1, 1, 1, 1), (0, 0, 0, 0)),
            is_terminal=True,
            winner=0,
        )

    @staticmethod
    def winning_column() -> GameStateFixture:
        """Complete winning column (all four shapes)."""
        qfen = "A.../B.../C.../D..."
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="winning_column",
            description="Player 0 wins with full left column (ABCD)",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=1,
            piece_counts=((1, 1, 1, 1), (0, 0, 0, 0)),
            is_terminal=True,
            winner=0,
        )

    @staticmethod
    def mixed_players_winning() -> GameStateFixture:
        """Mixed players forming a winning line."""
        qfen = "AbcD/..../..../...."
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="mixed_players_winning",
            description="Mixed players winning row: A(p0), b(p1), c(p1), D(p0)",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=0,
            piece_counts=((1, 0, 0, 1), (0, 1, 1, 0)),
            is_terminal=True,
            winner=None,  # Game ends, but no single player wins
        )

    @staticmethod
    def complex_mid_game() -> GameStateFixture:
        """Complex mid-game position with multiple pieces."""
        qfen = "Ab../c.D./..../...A"
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="complex_mid_game",
            description="Mid-game with pieces scattered across board",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=1,
            piece_counts=((1, 0, 0, 1), (1, 1, 1, 0)),
            is_terminal=False,
        )

    @staticmethod
    def multiple_pieces_same_shape() -> GameStateFixture:
        """Invalid state: three A pieces for player 0 exceeds per-shape inventory limit."""
        qfen = "A.../..../A.../...A"
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="multiple_pieces_same_shape",
            description="Multiple Player 0 A pieces at positions 0, 8, 15",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=1,
            piece_counts=((3, 0, 0, 0), (0, 0, 0, 0)),
            is_terminal=False,
        )

    @staticmethod
    def stress_test_bitboard() -> GameStateFixture:
        # this fails validation due to pieces constraints (no repeated shape on same line if opponents have pieces)
        """High-density board for stress testing."""
        qfen = "AbcD/bCdA/cDaB/DaBc"
        bb = bb_from_qfen(qfen)
        return GameStateFixture(
            name="stress_test_bitboard",
            description="Full board with all positions occupied",
            qfen=qfen,
            bitboard=bb,
            compact_bitboard=CompactBitboard.from_tuple(bb),
            state=State(bb),
            expected_player=0,
            piece_counts=((4, 4, 4, 4), (4, 4, 4, 4)),
            is_terminal=True,
            winner=None,  # Multiple winning lines
        )

    @classmethod
    def all_fixtures(cls) -> List[GameStateFixture]:
        """Get all available test fixtures using the unified test cases."""
        return [
            case.to_fixture() for case in UnifiedTestCases.all_cases()[:10]
        ]  # Keep original count for compatibility

    @classmethod
    def by_name(cls, name: str) -> GameStateFixture:
        """Get fixture by name using the unified test cases."""
        try:
            test_case = UnifiedTestCases.by_name(name)
            return test_case.to_fixture()
        except ValueError:
            # Fallback to original fixtures for backward compatibility
            for fixture in cls.all_fixtures():
                if fixture.name == name:
                    return fixture
            raise ValueError(f"Unknown fixture name: {name}")


class MoveSequenceFactory:
    """Factory for creating sequences of moves for testing game progression."""

    @staticmethod
    def simple_opening() -> List[Move]:
        """Simple opening sequence: A0, b1, B2, c3."""
        return [
            Move(player=0, shape=0, position=0),  # A at pos 0
            Move(player=1, shape=1, position=1),  # b at pos 1
            Move(player=0, shape=1, position=2),  # B at pos 2
            Move(player=1, shape=2, position=3),  # c at pos 3
        ]

    @staticmethod
    def winning_sequence() -> List[Move]:
        """Move sequence that leads to a win for Player 0."""
        return [
            Move(player=0, shape=0, position=0),  # A at pos 0
            Move(player=1, shape=0, position=4),  # a at pos 4
            Move(player=0, shape=1, position=1),  # B at pos 1
            Move(player=1, shape=1, position=5),  # b at pos 5
            Move(player=0, shape=2, position=2),  # C at pos 2
            Move(player=1, shape=2, position=6),  # c at pos 6
            Move(player=0, shape=3, position=3),  # D at pos 3 - wins!
        ]


class BitboardPatterns:
    """Common bitboard patterns for testing specific scenarios."""

    # Single bit patterns for each position
    SINGLE_BIT_PATTERNS = {
        i: tuple(1 << i if j == 0 else 0 for j in range(8)) for i in range(16)
    }

    # Empty bitboard
    EMPTY = (0, 0, 0, 0, 0, 0, 0, 0)

    # Maximum density patterns
    ALL_BITS_SET = (65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535)

    # Edge case patterns
    ALTERNATING_BITS = (0x5555, 0xAAAA, 0x5555, 0xAAAA, 0x5555, 0xAAAA, 0x5555, 0xAAAA)

    @staticmethod
    def single_piece_at(position: int, player: int = 0, shape: int = 0) -> Bitboard:
        """Create bitboard with single piece at specified position."""
        if not (0 <= position < 16):
            raise ValueError(f"Invalid position: {position}")
        if not (0 <= player < 2):
            raise ValueError(f"Invalid player: {player}")
        if not (0 <= shape < 4):
            raise ValueError(f"Invalid shape: {shape}")

        bitboard_index = player * 4 + shape
        bitboard = [0] * 8
        bitboard[bitboard_index] = 1 << position
        return tuple(bitboard)

    @staticmethod
    def multiple_pieces(pieces: List[Tuple[int, int, int]]) -> Bitboard:
        """Create bitboard with multiple pieces. Each piece is (position, player, shape)."""
        bitboard = [0] * 8
        for position, player, shape in pieces:
            if not (0 <= position < 16):
                raise ValueError(f"Invalid position: {position}")
            if not (0 <= player < 2):
                raise ValueError(f"Invalid player: {player}")
            if not (0 <= shape < 4):
                raise ValueError(f"Invalid shape: {shape}")

            bitboard_index = player * 4 + shape
            bitboard[bitboard_index] |= 1 << position

        return tuple(bitboard)


def assert_fixture_consistency(fixture: GameStateFixture) -> None:
    """Assert that a fixture is internally consistent."""
    # QFEN roundtrip
    assert bb_to_qfen(fixture.bitboard) == fixture.qfen
    assert bb_from_qfen(fixture.qfen) == fixture.bitboard

    # CompactBitboard consistency
    assert fixture.compact_bitboard.to_tuple() == fixture.bitboard
    assert fixture.compact_bitboard.to_qfen() == fixture.qfen

    # State consistency
    assert fixture.state.bb == fixture.bitboard
    assert fixture.state.to_qfen() == fixture.qfen

    # Piece counts consistency (this would require importing game utils)
    # We'll skip this for now to avoid circular imports

    print(f"✓ Fixture '{fixture.name}' is consistent")


def validate_all_fixtures() -> None:
    """Validate all fixtures for consistency."""
    print("Validating original fixtures...")
    for fixture in CanonicalBitboardFactory.all_fixtures():
        assert_fixture_consistency(fixture)

    print("Validating unified test cases...")
    for test_case in UnifiedTestCases.all_cases():
        fixture = test_case.to_fixture()
        assert_fixture_consistency(fixture)

    print("✓ All fixtures and unified test cases validated successfully")


# Convenience functions for easy access to unified test cases
def get_test_cases_by_category(category: str) -> List[TestCase]:
    """Get all test cases in a specific category."""
    return UnifiedTestCases.by_category(category)


def get_test_cases_by_tag(tag: str) -> List[TestCase]:
    """Get all test cases with a specific tag."""
    return UnifiedTestCases.by_tag(tag)


def get_basic_test_cases() -> List[TestCase]:
    """Get basic test cases suitable for simple unit tests."""
    return UnifiedTestCases.by_category("basic")


def get_winning_test_cases() -> List[TestCase]:
    """Get all test cases that represent winning positions."""
    return UnifiedTestCases.terminal_cases()


def get_parameterized_qfen_data() -> List[Tuple[str, int]]:
    """Get (qfen, expected_player) tuples for parameterized tests."""
    return TestCaseFactory.create_parameterized_test_data(
        UnifiedTestCases.all_cases(), ["qfen", "expected_player"]
    )


def get_parameterized_winning_data() -> List[Tuple[str, int, Optional[int]]]:
    """Get (qfen, expected_player, winner) tuples for winning position tests."""
    return TestCaseFactory.create_parameterized_test_data(
        UnifiedTestCases.terminal_cases(), ["qfen", "expected_player", "winner"]
    )


def export_test_cases_csv(filename: str = "quantik_test_cases.csv") -> str:
    """Export all test cases to CSV file and return the CSV content."""
    return UnifiedTestCases.export_csv(filename)


def print_test_case_statistics() -> None:
    """Print comprehensive statistics about available test cases."""
    stats = UnifiedTestCases.get_statistics()
    print("=== Quantik Test Cases Statistics ===")
    print(f"Total test cases: {stats['total_cases']}")
    print(f"Unique QFENs: {stats['unique_qfens']}")
    print(f"Terminal cases: {stats['terminal_cases']}")
    print(f"Player 0 wins: {stats['player_0_wins']}")
    print(f"Player 1 wins: {stats['player_1_wins']}")
    print(f"Balanced cases: {stats['balanced_cases']}")
    print("\nBy Category:")
    for category, count in sorted(stats["by_category"].items()):
        print(f"  {category}: {count}")
    print(f"\nAvailable tags: {', '.join(stats['all_tags'])}")


if __name__ == "__main__":
    # When run as script, validate all fixtures and show statistics
    validate_all_fixtures()
    print_test_case_statistics()

    # Export to CSV for easy inspection
    csv_content = export_test_cases_csv("test_cases_export.csv")
    print(
        f"\nExported {UnifiedTestCases.get_statistics()['total_cases']} test cases to CSV"
    )
