#!/usr/bin/env python
"""Game statistics and symmetry analysis for Quantik with comprehensive game tree analysis."""

from typing import Dict, Tuple, List, Optional, NamedTuple, cast, Protocol
from dataclasses import dataclass

from quantik_core.plugins.validation import bb_check_game_winner, WinStatus

from quantik_core import (
    Bitboard,
    apply_move,
    SymmetryHandler,
    generate_legal_moves,
    Move,
)
from quantik_core.qfen import bb_from_qfen

# Module constants
DEFAULT_MAX_DEPTH = 12  # limit due heuristic of states with legal moves
MAX_ALLOWED_DEPTH = 16  # limit due to board size and total states
MIN_ALLOWED_DEPTH = 1  # minimum meaningful depth for analysis
INITIAL_PLAYER = 0
EMPTY_BOARD_QFEN = "..../..../..../...."

# Game constants
PLAYER_0 = 0
PLAYER_1 = 1
TOTAL_PLAYERS = 2
PERCENTAGE_MULTIPLIER = 100

# Analysis constants
INITIAL_DEPTH = 0
INITIAL_MULTIPLICITY = 1


class AnalysisError(Exception):
    """Exception raised when game tree analysis fails."""

    pass


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
            * PERCENTAGE_MULTIPLIER
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


@dataclass
class StateProcessingResult:
    """Result of processing a single parent state."""

    total_moves: int
    player_0_wins: int
    player_1_wins: int
    new_states: Dict[Tuple[int, ...], CanonicalState]


@dataclass
class MoveProcessingResult:
    """Result of processing a single move."""

    is_winning_move: bool
    new_state: Optional[CanonicalState]


class DepthStatsAccumulator:
    """Accumulates statistics during depth processing."""

    def __init__(self, target_depth: int) -> None:
        self.target_depth = target_depth
        self.total_legal_moves = 0
        self.player_0_wins = 0
        self.player_1_wins = 0
        self.new_states: Dict[Tuple[int, ...], CanonicalState] = {}

    def add_state_results(self, state_results: "StateProcessingResult") -> None:
        """Add results from processing a single state."""
        self.total_legal_moves += state_results.total_moves
        self.player_0_wins += state_results.player_0_wins
        self.player_1_wins += state_results.player_1_wins

        # Merge new states
        for new_state in state_results.new_states.values():
            self._add_or_update_state(new_state)

    def _add_or_update_state(self, new_state: CanonicalState) -> None:
        """Add a new state or update existing one in the accumulator."""
        canonical_key = new_state.canonical_bb

        if canonical_key in self.new_states:
            existing_state = self.new_states[canonical_key]
            self.new_states[canonical_key] = CanonicalState(
                canonical_bb=canonical_key,
                representative_bb=existing_state.representative_bb,  # Keep first representative
                multiplicity=existing_state.multiplicity + new_state.multiplicity,
                player_turn=new_state.player_turn,
                depth=new_state.depth,
            )
        else:
            self.new_states[canonical_key] = new_state

    def build_game_stats(self) -> GameStats:
        """Build final GameStats from accumulated data."""
        ongoing_games = sum(state.multiplicity for state in self.new_states.values())

        return GameStats(
            depth=self.target_depth,
            total_legal_moves=self.total_legal_moves,
            unique_canonical_states=len(self.new_states),
            player_0_wins=self.player_0_wins,
            player_1_wins=self.player_1_wins,
            ongoing_games=ongoing_games,
        )

    def get_new_states(self) -> Dict[Tuple[int, ...], CanonicalState]:
        """Get the accumulated new states."""
        return self.new_states


class TableFormatter:
    """Formats game statistics into human-readable tables."""

    @staticmethod
    def format_analysis_table(
        stats_by_depth: Dict[int, GameStats],
        cumulative_stats: CumulativeStats,
        use_header: bool = False,
    ) -> str:
        """Format statistics into a markdown table.

        Args:
            stats_by_depth: Statistics organized by depth
            cumulative_stats: Overall cumulative statistics
            use_header: Whether to include markdown header

        Returns:
            Formatted markdown table string
        """
        lines = []
        if use_header:
            lines.append("# Quantik Game Tree Analysis with Symmetry Reduction\n")

        # Depth-wise analysis
        lines.extend(TableFormatter._format_depth_analysis(stats_by_depth))

        # Cumulative analysis
        lines.extend(TableFormatter._format_cumulative_analysis(cumulative_stats))

        return "\n".join(lines)

    @staticmethod
    def _format_depth_analysis(stats_by_depth: Dict[int, GameStats]) -> List[str]:
        """Format depth-wise analysis section."""
        lines = []
        lines.append("## Depth-wise Analysis")
        lines.append(
            "| Depth | Total Legal Moves | Unique Canonical | P0 Wins | P1 Wins | Ongoing | Reduction Factor | Space Savings |"
        )
        lines.append(
            "|-------|-------------------|------------------|---------|---------|---------|------------------|---------------|"
        )

        for depth in sorted(stats_by_depth.keys()):
            stats = stats_by_depth[depth]
            lines.append(
                f"| {depth:5d} | {stats.total_legal_moves:17,d} | "
                f"{stats.unique_canonical_states:16,d} | "
                f"{stats.player_0_wins:7,d} | {stats.player_1_wins:7,d} | "
                f"{stats.ongoing_games:7,d} | {stats.reduction_factor:15.2f}x | "
                f"{stats.space_savings_percent:12.1f}% |"
            )

        return lines

    @staticmethod
    def _format_cumulative_analysis(cumulative_stats: CumulativeStats) -> List[str]:
        """Format cumulative analysis section."""
        lines = []
        lines.append("\n## Cumulative Analysis")
        lines.append("| Metric | Value |")
        lines.append("|--------|--------|")
        lines.append(f"| Total Legal Moves | {cumulative_stats.total_legal_moves:,} |")
        lines.append(
            f"| Unique Canonical States | {cumulative_stats.unique_canonical_states:,} |"
        )
        lines.append(f"| Player 0 Wins | {cumulative_stats.player_0_wins:,} |")
        lines.append(f"| Player 1 Wins | {cumulative_stats.player_1_wins:,} |")
        lines.append(f"| Ongoing Games | {cumulative_stats.ongoing_games:,} |")
        lines.append(
            f"| Overall Reduction Factor | {cumulative_stats.reduction_factor:.2f}x |"
        )
        lines.append(
            f"| Overall Space Savings | {cumulative_stats.space_savings_percent:.1f}% |"
        )

        return lines


class SymmetryTable:
    """Comprehensive symmetry analysis table for Quantik game."""

    def __init__(self) -> None:
        self.stats_by_depth: Dict[int, GameStats] = {}
        self.cumulative_stats = CumulativeStats()
        self.canonical_states: Dict[Tuple[int, ...], CanonicalState] = {}
        self.state_queue: List[CanonicalState] = []

    def analyze_game_tree(self, max_depth: int = DEFAULT_MAX_DEPTH) -> None:
        """Analyze the complete game tree up to max_depth.

        Args:
            max_depth: Maximum depth to analyze (must be between 1 and 16)

        Raises:
            ValueError: If max_depth is invalid
            AnalysisError: If analysis fails during execution
        """
        self._validate_max_depth(max_depth)

        try:
            self._initialize_analysis()
            self._process_depth_levels(max_depth)
        except AnalysisError:
            # Re-raise analysis errors as-is
            raise
        except Exception as e:
            # Wrap unexpected errors
            raise AnalysisError(f"Unexpected error during analysis: {e}") from e

    def _validate_max_depth(self, max_depth: int) -> None:
        """Validate the max_depth parameter."""
        if not isinstance(max_depth, int):
            raise ValueError(
                f"max_depth must be an integer, got {type(max_depth).__name__}"
            )
        if max_depth < MIN_ALLOWED_DEPTH:
            raise ValueError(
                f"max_depth must be at least {MIN_ALLOWED_DEPTH}, got {max_depth}"
            )
        if max_depth > MAX_ALLOWED_DEPTH:
            raise ValueError(
                f"max_depth cannot exceed {MAX_ALLOWED_DEPTH} (memory constraints), got {max_depth}"
            )

    def _initialize_analysis(self) -> None:
        """Initialize the analysis with the empty board state."""
        empty_bb = bb_from_qfen(EMPTY_BOARD_QFEN)
        canonical_empty, _ = SymmetryHandler.find_canonical_form(empty_bb)
        canonical_key = tuple(canonical_empty)

        # Start with the empty state (depth 0, player 0's turn)
        initial_state = CanonicalState(
            canonical_bb=canonical_key,
            representative_bb=canonical_key,  # Empty board is its own representative
            multiplicity=INITIAL_MULTIPLICITY,
            player_turn=INITIAL_PLAYER,
            depth=INITIAL_DEPTH,
        )

        self.canonical_states[canonical_key] = initial_state
        self.state_queue = [initial_state]

    def _process_depth_levels(self, max_depth: int) -> None:
        """Process each depth level in the game tree."""
        for depth in range(1, max_depth + 1):
            print(f"Processing depth {depth}...")

            try:
                depth_stats = self._process_depth(depth)
                self.stats_by_depth[depth] = depth_stats
            except Exception as e:
                raise AnalysisError(f"Analysis failed at depth {depth}: {e}") from e

            self._update_cumulative_stats(depth_stats)

            # If no ongoing games, we've reached the end
            if depth_stats.ongoing_games == 0:
                print(f"Game tree analysis complete at depth {depth}")
                break

    def _update_cumulative_stats(self, depth_stats: GameStats) -> None:
        """Update cumulative statistics with depth results."""
        self.cumulative_stats.total_legal_moves += depth_stats.total_legal_moves
        self.cumulative_stats.unique_canonical_states += (
            depth_stats.unique_canonical_states
        )
        self.cumulative_stats.player_0_wins += depth_stats.player_0_wins
        self.cumulative_stats.player_1_wins += depth_stats.player_1_wins
        self.cumulative_stats.ongoing_games += depth_stats.ongoing_games

    def _process_depth(self, target_depth: int) -> GameStats:
        """Process all states at a specific depth."""
        # Extract states for this depth and update queue
        current_queue = self._extract_states_for_depth(target_depth - 1)

        # Initialize accumulator
        accumulator = DepthStatsAccumulator(target_depth)

        # Process each parent state
        for parent_state in current_queue:
            state_results = self._process_parent_state(parent_state, target_depth)
            accumulator.add_state_results(state_results)

        # Update tracking and return results
        new_states = accumulator.get_new_states()
        self._update_state_tracking(new_states)

        return accumulator.build_game_stats()

    def _extract_states_for_depth(self, depth: int) -> List[CanonicalState]:
        """Extract and remove states for a specific depth from the queue."""
        current_queue = [state for state in self.state_queue if state.depth == depth]
        self.state_queue = [state for state in self.state_queue if state.depth != depth]
        return current_queue

    def _process_parent_state(
        self, parent_state: CanonicalState, target_depth: int
    ) -> "StateProcessingResult":
        """Process a single parent state and return the results."""
        parent_bb = cast(Bitboard, parent_state.representative_bb)

        # Generate legal moves
        current_player, moves_by_shape = generate_legal_moves(parent_bb)
        legal_moves = [
            move for move_list in moves_by_shape.values() for move in move_list
        ]

        # Handle no legal moves case
        if not legal_moves:
            return self._handle_no_legal_moves(current_player, parent_state)

        # Process each legal move
        total_moves = len(legal_moves) * parent_state.multiplicity
        new_states: Dict[Tuple[int, ...], CanonicalState] = {}
        player_0_wins = 0
        player_1_wins = 0

        for move in legal_moves:
            move_result = self._process_move(
                move, parent_bb, parent_state, target_depth
            )

            if move_result.is_winning_move:
                if move.player == PLAYER_0:
                    player_0_wins += parent_state.multiplicity
                else:
                    player_1_wins += parent_state.multiplicity
            elif move_result.new_state:
                self._add_or_update_state(new_states, move_result.new_state)

        return StateProcessingResult(
            total_moves=total_moves,
            player_0_wins=player_0_wins,
            player_1_wins=player_1_wins,
            new_states=new_states,
        )

    def _handle_no_legal_moves(
        self, current_player: int, parent_state: CanonicalState
    ) -> "StateProcessingResult":
        """Handle the case when a state has no legal moves."""
        if (current_player + TOTAL_PLAYERS) % TOTAL_PLAYERS == PLAYER_0:
            return StateProcessingResult(
                total_moves=0,
                player_0_wins=0,
                player_1_wins=parent_state.multiplicity,
                new_states={},
            )
        else:
            return StateProcessingResult(
                total_moves=0,
                player_0_wins=parent_state.multiplicity,
                player_1_wins=0,
                new_states={},
            )

    def _process_move(
        self,
        move: "Move",
        parent_bb: Bitboard,
        parent_state: CanonicalState,
        target_depth: int,
    ) -> "MoveProcessingResult":
        """Process a single move and return the result."""
        new_bb = apply_move(parent_bb, move)

        # Check for winning move
        if bb_check_game_winner(new_bb) != WinStatus.NO_WIN:
            return MoveProcessingResult(is_winning_move=True, new_state=None)

        # Find canonical form
        canonical_bb, transformation = SymmetryHandler.find_canonical_form(new_bb)
        canonical_key = tuple(canonical_bb)

        # Calculate next player
        next_player = (PLAYER_1 + parent_state.player_turn) % TOTAL_PLAYERS
        if transformation.color_swap:
            next_player = PLAYER_1 - next_player

        # Create new canonical state
        new_state = CanonicalState(
            canonical_bb=canonical_key,
            representative_bb=tuple(new_bb),
            multiplicity=parent_state.multiplicity,
            player_turn=next_player,
            depth=target_depth,
        )

        return MoveProcessingResult(is_winning_move=False, new_state=new_state)

    def _add_or_update_state(
        self,
        states_dict: Dict[Tuple[int, ...], CanonicalState],
        new_state: CanonicalState,
    ) -> None:
        """Add a new state or update existing one in the states dictionary."""
        canonical_key = new_state.canonical_bb

        if canonical_key in states_dict:
            existing_state = states_dict[canonical_key]
            states_dict[canonical_key] = CanonicalState(
                canonical_bb=canonical_key,
                representative_bb=existing_state.representative_bb,  # Keep first representative
                multiplicity=existing_state.multiplicity + new_state.multiplicity,
                player_turn=new_state.player_turn,
                depth=new_state.depth,
            )
        else:
            states_dict[canonical_key] = new_state

    def _update_state_tracking(
        self, new_states: Dict[Tuple[int, ...], CanonicalState]
    ) -> None:
        """Update canonical states tracking and queue for next iteration."""
        self.canonical_states.update(new_states)
        self.state_queue.extend(new_states.values())

    def _canonical_to_bitboard(self, canonical_tuple: Tuple[int, ...]) -> Bitboard:
        """Convert canonical tuple back to Bitboard."""
        return cast(Bitboard, canonical_tuple)

    def generate_table(self, use_header: bool = False) -> str:
        """Generate a formatted table of statistics."""
        return TableFormatter.format_analysis_table(
            self.stats_by_depth, self.cumulative_stats, use_header
        )

    def get_stats_at_depth(self, depth: int) -> Optional[GameStats]:
        """Get statistics for a specific depth."""
        return self.stats_by_depth.get(depth)

    def get_cumulative_stats(self) -> CumulativeStats:
        """Get cumulative statistics."""
        return self.cumulative_stats


def analyze_symmetry_reduction(
    max_depth: int = DEFAULT_MAX_DEPTH, output_file: Optional[str] = None
) -> SymmetryTable:
    """
    Perform comprehensive symmetry reduction analysis.

    Args:
        max_depth: Maximum depth to analyze (must be between 1 and 16)
        output_file: Optional file to save the analysis table

    Returns:
        SymmetryTable with complete analysis

    Raises:
        ValueError: If max_depth is invalid
        AnalysisError: If analysis fails during execution
        IOError: If output_file cannot be written
    """
    # Input validation
    if not isinstance(max_depth, int):
        raise ValueError(
            f"max_depth must be an integer, got {type(max_depth).__name__}"
        )
    if max_depth < MIN_ALLOWED_DEPTH:
        raise ValueError(
            f"max_depth must be at least {MIN_ALLOWED_DEPTH}, got {max_depth}"
        )
    if max_depth > MAX_ALLOWED_DEPTH:
        raise ValueError(
            f"max_depth cannot exceed {MAX_ALLOWED_DEPTH} (memory constraints), got {max_depth}"
        )
    if output_file is not None and not isinstance(output_file, str):
        raise ValueError(
            f"output_file must be a string or None, got {type(output_file).__name__}"
        )

    print("Starting symmetry reduction analysis...")
    table = SymmetryTable()
    table.analyze_game_tree(max_depth)

    # Generate and optionally save table
    table_content = table.generate_table()

    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(table_content)
            print(f"Analysis saved to {output_file}")
        except IOError as e:
            raise IOError(f"Failed to write analysis to {output_file}: {e}") from e

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
