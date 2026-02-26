#!/usr/bin/env python3
"""
Endgame Puzzle Generator for Quantik

Generates tactical puzzles by:
1. Exploring game trees from empty board or specified positions
2. Using dropout rate to control branching factor at deeper levels
3. Applying deterministic seeds for reproducible puzzle sets
4. Identifying positions where one player can force a win in N moves
5. Outputting puzzles in QFEN notation with metadata

Puzzle types:
- "Win in N": Positions where the player to move can force a win in N moves
- "Tactical": Interesting positions with multiple winning lines
"""

import random
import time
from typing import Dict, List, NamedTuple, Optional, Set
from collections import defaultdict
from dataclasses import dataclass

from quantik_core import (
    State,
    Move,
    generate_legal_moves,
    apply_move,
)
from quantik_core.game_utils import check_game_winner, WinStatus


@dataclass
class PuzzleConfig:
    """Configuration for puzzle generation."""

    seed: int = 42  # Deterministic seed for reproducibility
    max_depth: int = 8  # Maximum search depth
    dropout_depth: int = 5  # Depth at which to start dropout
    dropout_rate: float = 0.7  # Fraction of moves to drop after dropout_depth
    min_puzzle_depth: int = 3  # Minimum depth to consider a position as puzzle
    max_puzzles: int = 100  # Maximum number of puzzles to generate
    player_filter: Optional[int] = None  # Filter for specific player (0 or 1)


class Puzzle(NamedTuple):
    """Represents a tactical puzzle position."""

    qfen: str
    player_to_move: int
    moves_to_win: int
    total_positions: int  # Positions explored from this puzzle
    winning_moves: List[Move]  # First moves that lead to forced win


class PuzzleStats(NamedTuple):
    """Statistics for puzzle generation run."""

    total_positions_explored: int
    puzzles_found: int
    generation_time: float
    positions_by_depth: Dict[int, int]


class EndgamePuzzleGenerator:
    """
    Generates endgame puzzles by exploring game trees with configurable dropout.

    The generator uses:
    - Deterministic randomization for reproducibility
    - Dropout rate to reduce branching factor and enable deeper search
    - Win detection to identify tactical positions
    - QFEN notation for puzzle representation
    """

    def __init__(self, config: PuzzleConfig):
        """Initialize generator with configuration."""
        self.config = config
        random.seed(config.seed)

        # Statistics tracking
        self.positions_explored = 0
        self.positions_by_depth: Dict[int, int] = defaultdict(int)
        self.puzzles: List[Puzzle] = []
        self.seen_positions: Set[bytes] = set()

    def generate_puzzles(
        self, starting_qfen: str = "..../..../..../...."
    ) -> PuzzleStats:
        """
        Generate puzzles from a starting position.

        Args:
            starting_qfen: Starting position in QFEN notation (default: empty board)

        Returns:
            Statistics about puzzle generation
        """
        print(f"Generating puzzles with seed {self.config.seed}")
        print(f"Max depth: {self.config.max_depth}")
        print(
            f"Dropout: {self.config.dropout_rate} after depth {self.config.dropout_depth}"
        )
        print(f"Starting position: {starting_qfen}\n")

        start_time = time.time()

        # Start exploration from initial position
        starting_state = State.from_qfen(starting_qfen)
        self._explore_position(starting_state.bb, depth=0, move_sequence=[])

        generation_time = time.time() - start_time

        # Create statistics
        stats = PuzzleStats(
            total_positions_explored=self.positions_explored,
            puzzles_found=len(self.puzzles),
            generation_time=generation_time,
            positions_by_depth=dict(self.positions_by_depth),
        )

        return stats

    def _explore_position(
        self, bb: tuple, depth: int, move_sequence: List[Move]
    ) -> Optional[WinStatus]:
        """
        Recursively explore positions to find puzzles.

        Returns:
            WinStatus if position leads to forced win, None otherwise
        """
        # Track statistics
        self.positions_explored += 1
        self.positions_by_depth[depth] += 1

        # Check depth limit
        if depth >= self.config.max_depth:
            return None

        # Check for immediate win
        winner = check_game_winner(bb)
        if winner != WinStatus.NO_WIN:
            return winner

        # Deduplicate positions using canonical form
        state = State(bb)
        canonical_key = state.canonical_key()
        if canonical_key in self.seen_positions:
            return None
        self.seen_positions.add(canonical_key)

        # Generate legal moves
        current_player, moves_by_shape = generate_legal_moves(bb)
        all_moves = []
        for shape_moves in moves_by_shape.values():
            all_moves.extend(shape_moves)

        if not all_moves:
            return None  # No legal moves

        # Apply dropout if configured
        if depth >= self.config.dropout_depth and self.config.dropout_rate > 0:
            # Randomly sample moves based on dropout rate
            keep_count = max(1, int(len(all_moves) * (1 - self.config.dropout_rate)))
            all_moves = random.sample(all_moves, keep_count)

        # Explore each move
        winning_moves = []
        losing_moves = []
        drawn_moves = []

        for move in all_moves:
            new_bb = apply_move(bb, move)
            result = self._explore_position(new_bb, depth + 1, move_sequence + [move])

            if result is None:
                drawn_moves.append(move)
            elif (result == WinStatus.PLAYER_0_WINS and current_player == 0) or (
                result == WinStatus.PLAYER_1_WINS and current_player == 1
            ):
                winning_moves.append(move)
            else:
                losing_moves.append(move)

        # Determine if this is a puzzle position
        if winning_moves and depth >= self.config.min_puzzle_depth:
            # This is a forced win position - a puzzle!
            if (
                self.config.player_filter is None
                or self.config.player_filter == current_player
            ):
                qfen = State(bb).to_qfen()
                moves_to_win = (depth + 1) // 2 + 1  # Approximate moves to win

                puzzle = Puzzle(
                    qfen=qfen,
                    player_to_move=current_player,
                    moves_to_win=moves_to_win,
                    total_positions=1,
                    winning_moves=winning_moves[:3],  # Keep first 3 winning moves
                )

                self.puzzles.append(puzzle)

                if len(self.puzzles) >= self.config.max_puzzles:
                    return (
                        WinStatus.PLAYER_0_WINS
                        if current_player == 0
                        else WinStatus.PLAYER_1_WINS
                    )

        # Return result for parent
        if winning_moves:
            return (
                WinStatus.PLAYER_0_WINS
                if current_player == 0
                else WinStatus.PLAYER_1_WINS
            )
        elif losing_moves and not drawn_moves:
            return (
                WinStatus.PLAYER_1_WINS
                if current_player == 0
                else WinStatus.PLAYER_0_WINS
            )
        else:
            return None

    def get_puzzles(self) -> List[Puzzle]:
        """Get generated puzzles."""
        return self.puzzles

    def print_puzzles(self, max_display: int = 10):
        """Print generated puzzles."""
        print(f"\n{'=' * 80}")
        print(
            f"GENERATED PUZZLES (showing {min(max_display, len(self.puzzles))} of {len(self.puzzles)})"
        )
        print(f"{'=' * 80}\n")

        for idx, puzzle in enumerate(self.puzzles[:max_display], 1):
            print(f"Puzzle #{idx}:")
            print(f"  QFEN: {puzzle.qfen}")
            print(f"  Player to move: {puzzle.player_to_move}")
            print(f"  Approximate moves to win: {puzzle.moves_to_win}")
            print(f"  Winning first moves ({len(puzzle.winning_moves)}):")

            for move in puzzle.winning_moves:
                shape_name = chr(ord("A") + move.shape)
                print(f"    - {shape_name} at position {move.position}")

            print()

    def print_stats(self, stats: PuzzleStats):
        """Print generation statistics."""
        print(f"{'=' * 80}")
        print("GENERATION STATISTICS")
        print(f"{'=' * 80}")
        print(f"Total positions explored: {stats.total_positions_explored:,}")
        print(f"Puzzles found: {stats.puzzles_found}")
        print(f"Generation time: {stats.generation_time:.2f} seconds")
        print(
            f"Positions/second: {stats.total_positions_explored / stats.generation_time:,.0f}"
        )
        print()
        print("Positions by depth:")
        for depth in sorted(stats.positions_by_depth.keys()):
            count = stats.positions_by_depth[depth]
            print(f"  Depth {depth}: {count:,} positions")


def demo_basic_puzzle_generation():
    """Demonstrate basic puzzle generation from empty board."""
    print("=" * 80)
    print("DEMO 1: Basic Puzzle Generation from Empty Board")
    print("=" * 80)

    config = PuzzleConfig(
        seed=42,
        max_depth=6,
        dropout_depth=4,
        dropout_rate=0.6,
        min_puzzle_depth=3,
        max_puzzles=20,
    )

    generator = EndgamePuzzleGenerator(config)
    stats = generator.generate_puzzles()

    generator.print_stats(stats)
    generator.print_puzzles(max_display=5)


def demo_deep_search_with_dropout():
    """Demonstrate deep search with high dropout rate."""
    print("\n" + "=" * 80)
    print("DEMO 2: Deep Search with High Dropout Rate")
    print("=" * 80)

    config = PuzzleConfig(
        seed=123,
        max_depth=8,
        dropout_depth=4,
        dropout_rate=0.8,  # Drop 80% of moves after depth 4
        min_puzzle_depth=4,
        max_puzzles=15,
    )

    generator = EndgamePuzzleGenerator(config)
    stats = generator.generate_puzzles()

    generator.print_stats(stats)
    generator.print_puzzles(max_display=5)


def demo_midgame_puzzle_generation():
    """Demonstrate puzzle generation from a midgame position."""
    print("\n" + "=" * 80)
    print("DEMO 3: Puzzle Generation from Midgame Position")
    print("=" * 80)

    # Start from a specific midgame position
    starting_position = "A.b./..C./d.../...a"

    config = PuzzleConfig(
        seed=456,
        max_depth=7,
        dropout_depth=3,
        dropout_rate=0.5,
        min_puzzle_depth=2,
        max_puzzles=25,
    )

    generator = EndgamePuzzleGenerator(config)
    stats = generator.generate_puzzles(starting_qfen=starting_position)

    generator.print_stats(stats)
    generator.print_puzzles(max_display=5)


def demo_reproducible_seeds():
    """Demonstrate reproducibility with same seed."""
    print("\n" + "=" * 80)
    print("DEMO 4: Reproducibility Test with Same Seed")
    print("=" * 80)

    config = PuzzleConfig(
        seed=999,
        max_depth=5,
        dropout_depth=3,
        dropout_rate=0.7,
        min_puzzle_depth=2,
        max_puzzles=5,
    )

    # Generate puzzles twice with same seed
    print("First run:")
    gen1 = EndgamePuzzleGenerator(config)
    stats1 = gen1.generate_puzzles()
    puzzles1 = [p.qfen for p in gen1.get_puzzles()]

    print("\nSecond run (same seed):")
    gen2 = EndgamePuzzleGenerator(config)
    stats2 = gen2.generate_puzzles()
    puzzles2 = [p.qfen for p in gen2.get_puzzles()]

    print(f"\nPuzzles match: {puzzles1 == puzzles2}")
    print(f"First run puzzles: {len(puzzles1)}")
    print(f"Second run puzzles: {len(puzzles2)}")


def main():
    """Run all demonstrations."""
    print("QUANTIK ENDGAME PUZZLE GENERATOR")
    print("=" * 80)
    print()
    print("This example demonstrates generating tactical puzzles using:")
    print("- Deterministic seeds for reproducible puzzle sets")
    print("- Configurable dropout rates to control search depth")
    print("- Win detection to identify forcing sequences")
    print("- QFEN notation for puzzle representation")
    print()

    # Run demonstrations
    demo_basic_puzzle_generation()
    demo_deep_search_with_dropout()
    demo_midgame_puzzle_generation()
    demo_reproducible_seeds()

    print("\n" + "=" * 80)
    print("ALL DEMONSTRATIONS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
