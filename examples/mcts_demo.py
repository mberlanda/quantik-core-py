#!/usr/bin/env python3
"""
Monte Carlo Tree Search (MCTS) Demo for Quantik

Demonstrates:
1. Basic MCTS search from empty board
2. Tactical position analysis
3. Comparison of different exploration parameters
4. Performance benchmarking
5. Search tree visualization
"""

import time
from typing import List, Tuple
from dataclasses import dataclass

from quantik_core import State, Move, apply_move
from quantik_core.mcts import MCTSEngine, MCTSConfig
from quantik_core.game_utils import check_game_winner, WinStatus
from quantik_core.qfen import bb_to_qfen


@dataclass
class SearchResult:
    """Results from an MCTS search."""

    move: Move
    win_probability: float
    iterations: int
    nodes_created: int
    search_time: float
    memory_usage: int


def format_move(move: Move) -> str:
    """Format move for display."""
    shape_name = chr(ord("A") + move.shape)
    row = move.position // 4
    col = move.position % 4
    return f"{shape_name} at ({row}, {col}) [pos {move.position}]"


def print_board(state: State):
    """Print board in a readable format."""
    qfen = state.to_qfen()
    rows = qfen.split("/")

    print("\n  0 1 2 3")
    for i, row in enumerate(rows):
        print(f"{i} ", end="")
        for cell in row:
            if cell == ".":
                print(". ", end="")
            else:
                print(f"{cell} ", end="")
        print()
    print()


def perform_search(
    state: State, config: MCTSConfig, description: str
) -> SearchResult:
    """Perform MCTS search and return results."""
    print(f"\n{'='*80}")
    print(f"{description}")
    print(f"{'='*80}")

    print(f"\nPosition: {state.to_qfen()}")
    print_board(state)

    print(f"Search parameters:")
    print(f"  Iterations: {config.max_iterations}")
    print(f"  Exploration weight: {config.exploration_weight}")
    print(f"  Max depth: {config.max_depth}")

    # Perform search
    engine = MCTSEngine(config)
    start_time = time.time()
    move, win_prob = engine.search(state)
    search_time = time.time() - start_time

    # Get statistics
    stats = engine.get_statistics()

    print(f"\nSearch completed in {search_time:.3f} seconds")
    print(f"Iterations performed: {stats['iterations']}")
    print(f"Nodes created: {stats['nodes_created']}")
    print(f"Memory usage: {stats['memory_usage']:,} bytes")
    print(f"Iterations/second: {stats['iterations'] / search_time:.0f}")

    print(f"\nBest move: {format_move(move)}")
    print(f"Win probability (P0): {win_prob:.2%}")

    # Show top moves if available
    print(f"\nMove evaluation:")
    root_id = engine.root_id
    children = engine.tree.get_children(root_id)

    if children:
        # Get move statistics
        move_stats = []
        for child_id in children:
            child = engine.tree.get_node(child_id)
            if child.visit_count > 0:
                win_rate = child.win_count_p0 / child.visit_count
                move_stats.append((child_id, child.visit_count, win_rate))

        # Sort by visits
        move_stats.sort(key=lambda x: x[1], reverse=True)

        print(f"  {'Move':<20} {'Visits':<10} {'Win Rate':<12} {'Selection %'}")
        total_visits = sum(stat[1] for stat in move_stats)

        for child_id, visits, win_rate in move_stats[:5]:
            child_state = engine.tree.get_state(child_id)
            # Find the move that leads to this state
            from quantik_core import generate_legal_moves

            _, moves_by_shape = generate_legal_moves(state.bb)
            all_moves = []
            for shape_moves in moves_by_shape.values():
                all_moves.extend(shape_moves)

            for m in all_moves:
                test_bb = apply_move(state.bb, m)
                test_state = State(test_bb)
                if test_state.canonical_key() == child_state.canonical_key():
                    selection_pct = (visits / total_visits) * 100
                    print(
                        f"  {format_move(m):<20} {visits:<10} {win_rate:>10.2%} {selection_pct:>11.1f}%"
                    )
                    break

    return SearchResult(
        move=move,
        win_probability=win_prob,
        iterations=stats["iterations"],
        nodes_created=stats["nodes_created"],
        search_time=search_time,
        memory_usage=stats["memory_usage"],
    )


def demo_basic_search():
    """Demonstrate basic MCTS search."""
    config = MCTSConfig(max_iterations=1000, random_seed=42, exploration_weight=1.414)

    state = State.from_qfen("..../..../..../....")
    perform_search(state, config, "DEMO 1: Basic MCTS Search from Empty Board")


def demo_tactical_position():
    """Demonstrate MCTS on tactical position."""
    config = MCTSConfig(max_iterations=2000, random_seed=42, exploration_weight=1.414)

    # Position where Player 0 can win soon
    state = State.from_qfen("AB../..../..../....")
    perform_search(
        state, config, "DEMO 2: Tactical Position Analysis (Near Win for P0)"
    )


def demo_exploration_comparison():
    """Compare different exploration parameters."""
    print(f"\n{'='*80}")
    print("DEMO 3: Comparison of Exploration Parameters")
    print(f"{'='*80}")

    state = State.from_qfen("A.../b.../..../....")

    configs = [
        (0.5, "Low exploration (more exploitation)"),
        (1.414, "Standard UCB1 (sqrt(2))"),
        (2.0, "High exploration (more diverse search)"),
    ]

    results = []
    for exploration_weight, description in configs:
        config = MCTSConfig(
            max_iterations=500, random_seed=42, exploration_weight=exploration_weight
        )

        print(f"\n{description} (weight={exploration_weight})")
        print("-" * 40)

        engine = MCTSEngine(config)
        start_time = time.time()
        move, win_prob = engine.search(state)
        search_time = time.time() - start_time

        stats = engine.get_statistics()

        print(f"Best move: {format_move(move)}")
        print(f"Win probability: {win_prob:.2%}")
        print(f"Nodes explored: {stats['nodes_created']}")
        print(f"Search time: {search_time:.3f}s")

        results.append(
            (exploration_weight, move, win_prob, stats["nodes_created"], search_time)
        )

    print(f"\n{'='*80}")
    print("COMPARISON SUMMARY")
    print(f"{'='*80}")
    print(
        f"{'Exploration':<12} {'Move':<20} {'Win Prob':<12} {'Nodes':<10} {'Time (s)'}"
    )
    for weight, move, prob, nodes, stime in results:
        print(
            f"{weight:<12.1f} {format_move(move):<20} {prob:>10.2%} {nodes:>9} {stime:>9.3f}"
        )


def demo_performance_scaling():
    """Demonstrate performance with different iteration counts."""
    print(f"\n{'='*80}")
    print("DEMO 4: Performance Scaling")
    print(f"{'='*80}")

    state = State.from_qfen("..../..../..../....")

    iteration_counts = [100, 500, 1000, 5000]

    print(f"\n{'Iterations':<12} {'Time (s)':<12} {'Iter/s':<12} {'Nodes':<10}")
    print("-" * 50)

    for iterations in iteration_counts:
        config = MCTSConfig(
            max_iterations=iterations, random_seed=42, exploration_weight=1.414
        )

        engine = MCTSEngine(config)
        start_time = time.time()
        engine.search(state)
        search_time = time.time() - start_time

        stats = engine.get_statistics()
        iter_per_sec = iterations / search_time

        print(
            f"{iterations:<12} {search_time:<12.3f} {iter_per_sec:<12.0f} {stats['nodes_created']:<10}"
        )


def demo_game_playout():
    """Demonstrate full game using MCTS."""
    print(f"\n{'='*80}")
    print("DEMO 5: Full Game Playout with MCTS")
    print(f"{'='*80}")

    config = MCTSConfig(max_iterations=500, random_seed=42, exploration_weight=1.414)

    state = State.from_qfen("..../..../..../....")
    move_count = 0
    max_moves = 16

    print("\nPlaying game with MCTS (500 iterations per move)...\n")

    while move_count < max_moves:
        # Check for game end
        winner = check_game_winner(state.bb)
        if winner != WinStatus.NO_WIN:
            print(f"\nGame over after {move_count} moves!")
            if winner == WinStatus.PLAYER_0_WINS:
                print("Player 0 wins!")
            elif winner == WinStatus.PLAYER_1_WINS:
                print("Player 1 wins!")
            else:
                print("Draw!")
            break

        # Determine current player
        from quantik_core import generate_legal_moves

        current_player, _ = generate_legal_moves(state.bb)

        # Perform search
        engine = MCTSEngine(config)
        move, win_prob = engine.search(state)

        move_count += 1
        print(f"Move {move_count} (Player {current_player}):")
        print(f"  Move: {format_move(move)}")
        print(f"  Win probability (P0): {win_prob:.2%}")

        # Apply move
        new_bb = apply_move(state.bb, move)
        state = State(new_bb)
        print(f"  Position: {state.to_qfen()}")
        print()

    print_board(state)


def demo_tree_statistics():
    """Show detailed tree statistics."""
    print(f"\n{'='*80}")
    print("DEMO 6: Tree Statistics and Analysis")
    print(f"{'='*80}")

    config = MCTSConfig(max_iterations=2000, random_seed=42, exploration_weight=1.414)

    state = State.from_qfen("AB../c.../..../....")
    engine = MCTSEngine(config)

    print("\nPerforming search...")
    move, win_prob = engine.search(state)

    stats = engine.get_statistics()
    tree_stats = stats["tree_stats"]

    print(f"\nTree Statistics:")
    print(f"  Total nodes: {tree_stats['node_count']:,}")
    print(f"  Capacity: {tree_stats['capacity']:,}")
    print(f"  Utilization: {tree_stats['utilization_percent']}%")
    print(f"  Memory usage: {stats['memory_usage']:,} bytes")
    print(f"  Bytes per node: {stats['memory_usage'] / tree_stats['node_count']:.1f}")

    print(f"\nSearch Results:")
    print(f"  Best move: {format_move(move)}")
    print(f"  Win probability: {win_prob:.2%}")
    print(f"  Total iterations: {stats['iterations']:,}")

    # Analyze root node
    root = engine.tree.get_node(engine.root_id)
    print(f"\nRoot Node Statistics:")
    print(f"  Visit count: {root.visit_count:,}")
    print(f"  Best value: {root.best_value:.3f}")
    print(f"  P0 wins: {root.win_count_p0:,}")
    print(f"  P1 wins: {root.win_count_p1:,}")


def main():
    """Run all demonstrations."""
    print("QUANTIK MCTS DEMONSTRATION")
    print("=" * 80)
    print()
    print("This demo showcases the Monte Carlo Tree Search implementation:")
    print("- Basic position analysis")
    print("- Tactical position evaluation")
    print("- Exploration parameter tuning")
    print("- Performance characteristics")
    print("- Full game playout")
    print("- Tree statistics")
    print()

    demo_basic_search()
    demo_tactical_position()
    demo_exploration_comparison()
    demo_performance_scaling()
    demo_game_playout()
    demo_tree_statistics()

    print(f"\n{'='*80}")
    print("ALL DEMONSTRATIONS COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
