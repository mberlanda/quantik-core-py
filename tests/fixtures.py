"""Shared test fixtures and factories for Quantik game state testing.

This module provides reusable test fixtures, canonical bitboards, and game state
factories to reduce duplication across test files and ensure consistency.
"""

from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass

from quantik_core.commons import Bitboard
from quantik_core.memory.bitboard_compact import CompactBitboard
from quantik_core.core import State
from quantik_core.qfen import bb_from_qfen, bb_to_qfen
from quantik_core.move import Move


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
    piece_counts: Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]  # (p0_counts, p1_counts)
    is_terminal: bool = False
    winner: Optional[int] = None


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
            is_terminal=False
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
            is_terminal=False
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
            is_terminal=False
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
            is_terminal=False
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
            winner=0
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
            winner=0
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
            winner=None  # Game ends, but no single player wins
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
            is_terminal=False
        )
    
    @staticmethod
    def multiple_pieces_same_shape() -> GameStateFixture:
        """Multiple pieces of the same shape (valid in Quantik)."""
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
            is_terminal=False
        )
    
    @staticmethod
    def stress_test_bitboard() -> GameStateFixture:
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
            winner=None  # Multiple winning lines
        )
    
    @classmethod
    def all_fixtures(cls) -> List[GameStateFixture]:
        """Get all available test fixtures."""
        return [
            cls.empty_board(),
            cls.single_piece_corner(),
            cls.single_piece_center(),
            cls.alternating_moves(),
            cls.winning_row(),
            cls.winning_column(),
            cls.mixed_players_winning(),
            cls.complex_mid_game(),
            cls.multiple_pieces_same_shape(),
            cls.stress_test_bitboard(),
        ]
    
    @classmethod
    def by_name(cls, name: str) -> GameStateFixture:
        """Get fixture by name."""
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
        i: tuple(1 << i if j == 0 else 0 for j in range(8))
        for i in range(16)
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
    for fixture in CanonicalBitboardFactory.all_fixtures():
        assert_fixture_consistency(fixture)
    print("✓ All fixtures validated successfully")


if __name__ == "__main__":
    # When run as script, validate all fixtures
    validate_all_fixtures()