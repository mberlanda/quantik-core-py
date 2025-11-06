#!/usr/bin/env python3
"""
Quantik Win Probability Analysis

Given an initial QFEN position, compute the final probability of win for each player
with a table summarizing valid moves available at each turn depth.
"""

import time
from typing import Dict, List, NamedTuple
from collections import defaultdict, Counter

from quantik_core import (
    State,
    QuantikBoard,
    Move,
    GameResult,
)


class GameOutcome(NamedTuple):
    """Represents the outcome of a game path."""

    result: GameResult
    depth: int
    move_sequence: List[Move]


class TurnAnalysis(NamedTuple):
    """Analysis data for a specific turn/depth."""

    depth: int
    player_turn: int
    total_positions: int
    valid_moves_available: int
    positions_with_moves: int
    terminal_positions: int
    avg_moves_per_position: float


class WinProbabilityAnalyzer:
    """
    Analyzes win probabilities from a given starting position by exploring
    all possible game continuations up to a specified depth.
    """

    def __init__(self, starting_qfen: str):
        """Initialize analyzer with starting position."""
        self.starting_qfen = starting_qfen
        self.starting_state = State.from_qfen(starting_qfen)
        self.starting_board = QuantikBoard.from_state(self.starting_state)

        # Results storage
        self.game_outcomes: List[GameOutcome] = []
        self.turn_data: Dict[int, TurnAnalysis] = {}
        self.positions_by_depth: Dict[int, List[QuantikBoard]] = defaultdict(list)

    def analyze_win_probabilities(self, max_depth: int = 16) -> Dict[str, any]:
        """
        Analyze win probabilities by exploring all game paths.

        Args:
            max_depth: Maximum depth to explore

        Returns:
            Dictionary with complete analysis results
        """
        print(f"Analyzing win probabilities from: {self.starting_qfen}")
        print(f"Starting player: {self.starting_board.current_player}")
        print(f"Max exploration depth: {max_depth}")

        start_time = time.time()

        # Explore all possible games
        self._explore_all_games(max_depth)

        analysis_time = time.time() - start_time

        # Compile results
        results = self._compile_results(analysis_time)

        return results

    def _explore_all_games(self, max_depth: int):
        """Explore all possible game continuations."""

        def explore_recursive(
            board: QuantikBoard, move_sequence: List[Move], depth: int
        ):
            # Record this position
            self.positions_by_depth[depth].append(board.copy())

            # Check if game is over
            game_result = board.get_game_result()
            if game_result != GameResult.ONGOING:
                outcome = GameOutcome(game_result, depth, move_sequence.copy())
                self.game_outcomes.append(outcome)
                return

            # Check depth limit
            if depth >= max_depth:
                # Treat as ongoing at depth limit
                outcome = GameOutcome(GameResult.ONGOING, depth, move_sequence.copy())
                self.game_outcomes.append(outcome)
                return

            # Get legal moves
            legal_moves = list(board.generate_legal_moves())

            if not legal_moves:
                # No moves available - game ends as ongoing/draw
                outcome = GameOutcome(GameResult.ONGOING, depth, move_sequence.copy())
                self.game_outcomes.append(outcome)
                return

            # Explore each legal move
            for move in legal_moves:
                board_copy = board.copy()
                if board_copy.play_move(move):
                    new_sequence = move_sequence + [move]
                    explore_recursive(board_copy, new_sequence, depth + 1)

        # Start exploration
        print("Exploring all game paths...")
        explore_recursive(self.starting_board, [], 0)
        print(f"Exploration complete. Found {len(self.game_outcomes)} game outcomes.")

        # Analyze turn data
        self._analyze_turn_data()

    def _analyze_turn_data(self):
        """Analyze data for each turn/depth level."""
        print("Analyzing turn data...")

        for depth, positions in self.positions_by_depth.items():
            if not positions:
                continue

            total_positions = len(positions)
            total_moves = 0
            positions_with_moves = 0
            terminal_positions = 0

            # Analyze each position at this depth
            for board in positions:
                if board.get_game_result() != GameResult.ONGOING:
                    terminal_positions += 1
                else:
                    legal_moves = list(board.generate_legal_moves())
                    move_count = len(legal_moves)
                    total_moves += move_count
                    if move_count > 0:
                        positions_with_moves += 1

            # Calculate averages
            avg_moves = (
                total_moves / positions_with_moves if positions_with_moves > 0 else 0.0
            )

            # Determine player turn (assuming starting player alternates)
            player_turn = (self.starting_board.current_player + depth) % 2

            self.turn_data[depth] = TurnAnalysis(
                depth=depth,
                player_turn=player_turn,
                total_positions=total_positions,
                valid_moves_available=total_moves,
                positions_with_moves=positions_with_moves,
                terminal_positions=terminal_positions,
                avg_moves_per_position=avg_moves,
            )

    def _compile_results(self, analysis_time: float) -> Dict[str, any]:
        """Compile comprehensive analysis results."""

        # Count outcomes
        outcome_counts = Counter(outcome.result for outcome in self.game_outcomes)
        total_games = len(self.game_outcomes)

        # Calculate probabilities
        if total_games > 0:
            p0_wins = outcome_counts[GameResult.PLAYER_0_WINS]
            p1_wins = outcome_counts[GameResult.PLAYER_1_WINS]
            ongoing = outcome_counts[GameResult.ONGOING]

            p0_win_prob = p0_wins / total_games
            p1_win_prob = p1_wins / total_games
            ongoing_prob = ongoing / total_games
        else:
            p0_wins = p1_wins = ongoing = 0
            p0_win_prob = p1_win_prob = ongoing_prob = 0.0

        # Compile turn analysis table
        turn_table = []
        for depth in sorted(self.turn_data.keys()):
            turn_info = self.turn_data[depth]
            turn_table.append(
                {
                    "depth": depth,
                    "player_turn": turn_info.player_turn,
                    "total_positions": turn_info.total_positions,
                    "terminal_positions": turn_info.terminal_positions,
                    "ongoing_positions": turn_info.total_positions
                    - turn_info.terminal_positions,
                    "total_valid_moves": turn_info.valid_moves_available,
                    "avg_moves_per_position": turn_info.avg_moves_per_position,
                }
            )

        return {
            "starting_position": self.starting_qfen,
            "starting_player": self.starting_board.current_player,
            "analysis_time": analysis_time,
            "total_game_paths": total_games,
            "win_probabilities": {
                "player_0_win_probability": p0_win_prob,
                "player_1_win_probability": p1_win_prob,
                "ongoing_probability": ongoing_prob,
                "player_0_wins": p0_wins,
                "player_1_wins": p1_wins,
                "ongoing_games": ongoing,
            },
            "turn_analysis_table": turn_table,
        }

    def print_results(self, results: Dict[str, any]):
        """Print formatted analysis results."""

        print(f"\n{'=' * 80}")
        print("QUANTIK WIN PROBABILITY ANALYSIS")
        print(f"{'=' * 80}")

        # Basic info
        print(f"Starting position: {results['starting_position']}")
        print(f"Starting player: {results['starting_player']}")
        print(f"Analysis time: {results['analysis_time']:.2f} seconds")
        print(f"Total game paths explored: {results['total_game_paths']:,}")

        # Win probabilities
        print(f"\n{'=' * 50}")
        print("WIN PROBABILITIES")
        print(f"{'=' * 50}")

        probs = results["win_probabilities"]
        print(
            f"Player 0 win probability: {probs['player_0_win_probability']:.1%} ({probs['player_0_wins']:,} wins)"
        )
        print(
            f"Player 1 win probability: {probs['player_1_win_probability']:.1%} ({probs['player_1_wins']:,} wins)"
        )
        print(
            f"Ongoing/Draw probability: {probs['ongoing_probability']:.1%} ({probs['ongoing_games']:,} games)"
        )

        # Position evaluation
        if probs["player_0_win_probability"] > probs["player_1_win_probability"] + 0.1:
            evaluation = "Strong advantage for Player 0"
        elif (
            probs["player_1_win_probability"] > probs["player_0_win_probability"] + 0.1
        ):
            evaluation = "Strong advantage for Player 1"
        elif (
            abs(probs["player_0_win_probability"] - probs["player_1_win_probability"])
            < 0.05
        ):
            evaluation = "Balanced position"
        elif probs["player_0_win_probability"] > probs["player_1_win_probability"]:
            evaluation = "Slight advantage for Player 0"
        else:
            evaluation = "Slight advantage for Player 1"

        print(f"\nPosition evaluation: {evaluation}")

        # Turn analysis table
        print(f"\n{'=' * 50}")
        print("TURN ANALYSIS TABLE")
        print(f"{'=' * 50}")
        print(
            "| Turn | Player | Total Pos | Terminal | Ongoing | Total Moves | Avg Moves/Pos |"
        )
        print(
            "|------|--------|-----------|----------|---------|-------------|---------------|"
        )

        for turn_info in results["turn_analysis_table"]:
            print(
                f"| {turn_info['depth']:4d} |    {turn_info['player_turn']:1d}   | "
                f"{turn_info['total_positions']:9,d} | {turn_info['terminal_positions']:8,d} | "
                f"{turn_info['ongoing_positions']:7,d} | {turn_info['total_valid_moves']:11,d} | "
                f"{turn_info['avg_moves_per_position']:13.1f} |"
            )


def main():
    """Main analysis function."""

    # Starting position as requested (fixed QFEN format - each rank must be exactly 4 chars)
    starting_qfen = "A.b./.C.D/c.D./...a"

    print("Quantik Win Probability Analysis")
    print(f"Starting position: {starting_qfen}")

    # Create analyzer
    analyzer = WinProbabilityAnalyzer(starting_qfen)

    # Run analysis with reasonable depth limit
    results = analyzer.analyze_win_probabilities(max_depth=12)

    # Print results
    analyzer.print_results(results)

    print(f"\n{'=' * 80}")
    print("ANALYSIS COMPLETE")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
