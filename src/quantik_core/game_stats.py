#!/usr/bin/env python
"""Game statistics and symmetry analysis for Quantik with comprehensive game tree analysis."""

from typing import Dict, Tuple, List, Optional, NamedTuple, cast, Protocol
from dataclasses import dataclass

from quantik_core.plugins.validation import bb_check_game_winner, WinStatus

from quantik_core import Bitboard, apply_move, SymmetryHandler, generate_legal_moves
from quantik_core.qfen import bb_from_qfen


class StatsProtocol(Protocol):
    """Protocol defining the interface for statistics objects."""

    @property
    def total_legal_moves(self) -> int:
        """Total number of legal moves."""
        ...

    @property
    def unique_canonical_states(self) -> int:
        """Number of unique canonical states."""
        ...


class StatsCalculationMixin:
    """Mixin providing common statistical calculations."""

    @property
    def reduction_factor(self) -> float:
        """Calculate reduction factor."""
        self_stats = cast(StatsProtocol, self)
        return (
            self_stats.total_legal_moves / self_stats.unique_canonical_states
            if self_stats.unique_canonical_states > 0
            else 0
        )

    @property
    def space_savings_percent(self) -> float:
        """Calculate space savings percentage."""
        self_stats = cast(StatsProtocol, self)
        if self_stats.total_legal_moves == 0:
            return 0
        return (
            (self_stats.total_legal_moves - self_stats.unique_canonical_states)
            / self_stats.total_legal_moves
            * 100
        )


@dataclass
class GameStats(StatsCalculationMixin):
    """Statistics for a game state at a specific depth."""

    depth: int
    total_legal_moves: int
    unique_canonical_states: int
    player_0_wins: int
    player_1_wins: int
    ongoing_games: int


@dataclass
class CumulativeStats(StatsCalculationMixin):
    """Cumulative statistics across all depths."""

    total_legal_moves: int = 0
    unique_canonical_states: int = 0
    player_0_wins: int = 0
    player_1_wins: int = 0
    ongoing_games: int = 0


class CanonicalState(NamedTuple):
    """Represents a canonical game state with its multiplicity."""

    canonical_bb: Tuple[int, ...]
    representative_bb: Tuple[int, ...]  # A valid representative of this canonical class
    multiplicity: int  # How many original states map to this canonical state
    player_turn: int
    depth: int


class SymmetryTable:
    """Comprehensive symmetry analysis table for Quantik game."""

    def __init__(self) -> None:
        self.stats_by_depth: Dict[int, GameStats] = {}
        self.cumulative_stats = CumulativeStats()
        self.canonical_states: Dict[Tuple[int, ...], CanonicalState] = {}
        self.state_queue: List[CanonicalState] = []

    def analyze_game_tree(self, max_depth: int = 16) -> None:
        """Analyze the complete game tree up to max_depth."""
        # Initialize with empty board
        empty_bb = bb_from_qfen("..../..../..../....")
        canonical_empty, _ = SymmetryHandler.find_canonical_form(empty_bb)
        canonical_key = tuple(canonical_empty)

        # Start with the empty state (depth 0, player 0's turn)
        initial_state = CanonicalState(
            canonical_bb=canonical_key,
            representative_bb=canonical_key,  # Empty board is its own representative
            multiplicity=1,
            player_turn=0,
            depth=0,
        )

        self.canonical_states[canonical_key] = initial_state
        self.state_queue = [initial_state]

        # Process each depth level
        for depth in range(1, max_depth + 1):
            print(f"Processing depth {depth}...")
            depth_stats = self._process_depth(depth)
            self.stats_by_depth[depth] = depth_stats

            # Update cumulative stats
            self.cumulative_stats.total_legal_moves += depth_stats.total_legal_moves
            self.cumulative_stats.unique_canonical_states += (
                depth_stats.unique_canonical_states
            )
            self.cumulative_stats.player_0_wins += depth_stats.player_0_wins
            self.cumulative_stats.player_1_wins += depth_stats.player_1_wins
            self.cumulative_stats.ongoing_games += depth_stats.ongoing_games

            # If no ongoing games, we've reached the end
            if depth_stats.ongoing_games == 0:
                print(f"Game tree analysis complete at depth {depth}")
                break

    def _process_depth(self, target_depth: int) -> GameStats:
        """Process all states at a specific depth."""
        new_states: Dict[Tuple[int, ...], CanonicalState] = {}
        total_legal_moves = 0
        player_0_wins = 0
        player_1_wins = 0
        ongoing_games = 0

        # Process all states from previous depth
        current_queue = [
            state for state in self.state_queue if state.depth == target_depth - 1
        ]
        self.state_queue = [
            state for state in self.state_queue if state.depth != target_depth - 1
        ]

        for parent_state in current_queue:
            # Use the representative bitboard instead of reconstructing from canonical
            parent_bb = cast(Bitboard, parent_state.representative_bb)

            # Generate all legal moves
            current_player, moves_by_shape = generate_legal_moves(parent_bb)
            legal_moves = [
                move for move_list in moves_by_shape.values() for move in move_list
            ]

            if not legal_moves:
                if (current_player + 2) % 2 == 0:
                    player_1_wins += parent_state.multiplicity
                else:
                    player_0_wins += parent_state.multiplicity

            # Track moves for this parent state
            moves_count = len(legal_moves) * parent_state.multiplicity
            total_legal_moves += moves_count

            # Process each legal move
            for move in legal_moves:
                new_bb = apply_move(parent_bb, move)
                if bb_check_game_winner(new_bb) != WinStatus.NO_WIN:
                    if move.player == 0:
                        player_0_wins += parent_state.multiplicity
                    else:
                        player_1_wins += parent_state.multiplicity
                    continue

                # Find canonical form of the new state
                canonical_bb, transformation = SymmetryHandler.find_canonical_form(
                    new_bb
                )
                canonical_key = tuple(canonical_bb)

                # Determine next player (accounting for potential color swap in canonical form)
                next_player = (1 + parent_state.player_turn) % 2
                if transformation.color_swap:
                    # If colors were swapped in canonical form, adjust the player turn
                    next_player = 1 - next_player

                # Add or update canonical state
                if canonical_key in new_states:
                    # Increase multiplicity for existing canonical state
                    existing_state = new_states[canonical_key]
                    new_states[canonical_key] = CanonicalState(
                        canonical_bb=canonical_key,
                        representative_bb=existing_state.representative_bb,  # Keep first representative
                        multiplicity=existing_state.multiplicity
                        + parent_state.multiplicity,
                        player_turn=next_player,
                        depth=target_depth,
                    )
                else:
                    # Create new canonical state using the current new_bb as representative
                    new_states[canonical_key] = CanonicalState(
                        canonical_bb=canonical_key,
                        representative_bb=tuple(
                            new_bb
                        ),  # Store original as representative
                        multiplicity=parent_state.multiplicity,
                        player_turn=next_player,
                        depth=target_depth,
                    )

        # Update canonical states and queue for next iteration
        self.canonical_states.update(new_states)
        self.state_queue.extend(new_states.values())
        ongoing_games = sum(state.multiplicity for state in new_states.values())

        return GameStats(
            depth=target_depth,
            total_legal_moves=total_legal_moves,
            unique_canonical_states=len(new_states),
            player_0_wins=player_0_wins,
            player_1_wins=player_1_wins,
            ongoing_games=ongoing_games,
        )

    def _canonical_to_bitboard(self, canonical_tuple: Tuple[int, ...]) -> Bitboard:
        """Convert canonical tuple back to Bitboard."""
        return cast(Bitboard, canonical_tuple)

    def generate_table(self, use_header: bool = False) -> str:
        """Generate a formatted table of statistics."""
        lines = []
        if use_header:
            lines.append("# Quantik Game Tree Analysis with Symmetry Reduction\n")

        # Depth-wise analysis
        lines.append("## Depth-wise Analysis")
        lines.append(
            "| Depth | Total Legal Moves | Unique Canonical | P0 Wins | P1 Wins | Ongoing | Reduction Factor | Space Savings |"
        )
        lines.append(
            "|-------|-------------------|------------------|---------|---------|---------|------------------|---------------|"
        )

        for depth in sorted(self.stats_by_depth.keys()):
            stats = self.stats_by_depth[depth]
            lines.append(
                f"| {depth:5d} | {stats.total_legal_moves:17,d} | "
                f"{stats.unique_canonical_states:16,d} | "
                f"{stats.player_0_wins:7,d} | {stats.player_1_wins:7,d} | "
                f"{stats.ongoing_games:7,d} | {stats.reduction_factor:15.2f}x | "
                f"{stats.space_savings_percent:12.1f}% |"
            )

        # Cumulative analysis
        lines.append("\n## Cumulative Analysis")
        lines.append("| Metric | Value |")
        lines.append("|--------|--------|")
        lines.append(
            f"| Total Legal Moves | {self.cumulative_stats.total_legal_moves:,} |"
        )
        lines.append(
            f"| Unique Canonical States | {self.cumulative_stats.unique_canonical_states:,} |"
        )
        lines.append(f"| Player 0 Wins | {self.cumulative_stats.player_0_wins:,} |")
        lines.append(f"| Player 1 Wins | {self.cumulative_stats.player_1_wins:,} |")
        lines.append(f"| Ongoing Games | {self.cumulative_stats.ongoing_games:,} |")
        lines.append(
            f"| Overall Reduction Factor | {self.cumulative_stats.reduction_factor:.2f}x |"
        )
        lines.append(
            f"| Overall Space Savings | {self.cumulative_stats.space_savings_percent:.1f}% |"
        )

        return "\n".join(lines)

    def get_stats_at_depth(self, depth: int) -> Optional[GameStats]:
        """Get statistics for a specific depth."""
        return self.stats_by_depth.get(depth)

    def get_cumulative_stats(self) -> CumulativeStats:
        """Get cumulative statistics."""
        return self.cumulative_stats


def analyze_symmetry_reduction(
    max_depth: int = 16, output_file: Optional[str] = None
) -> SymmetryTable:
    """
    Perform comprehensive symmetry reduction analysis.

    Args:
        max_depth: Maximum depth to analyze
        output_file: Optional file to save the analysis table

    Returns:
        SymmetryTable with complete analysis
    """
    print("Starting symmetry reduction analysis...")
    table = SymmetryTable()
    table.analyze_game_tree(max_depth)

    # Generate and optionally save table
    table_content = table.generate_table()

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(table_content)
        print(f"Analysis saved to {output_file}")

    print("Analysis complete!")
    return table


if __name__ == "__main__":
    # Example usage
    import os

    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "GAME_TREE_ANALYSIS.md",
    )

    table = analyze_symmetry_reduction(max_depth=8, output_file=output_path)
    print(table.generate_table(use_header=True))
