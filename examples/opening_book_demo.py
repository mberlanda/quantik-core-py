#!/usr/bin/env python3
"""
Opening Book Database Demo for Quantik

Demonstrates:
1. Building an opening book from game tree analysis
2. Querying positions by depth
3. Lookup of best moves for positions
4. Export and statistics
5. Canonical deduplication in action
"""

import time
import tempfile
from pathlib import Path

from quantik_core import State, Move, generate_legal_moves, apply_move
from quantik_core.opening_book import (
    OpeningBookDatabase,
    OpeningBookConfig,
    OpeningBookEntry,
)
from quantik_core.game_utils import check_game_winner, WinStatus


def explore_positions(
    bb: tuple, depth: int, max_depth: int, positions: dict
) -> None:
    """
    Recursively explore positions and collect statistics.

    Args:
        bb: Current bitboard
        depth: Current depth
        max_depth: Maximum depth to explore
        positions: Dictionary to store position data
    """
    if depth > max_depth:
        return

    # Create state and get canonical key
    state = State(bb)
    canonical_key = state.canonical_key()

    # Check if already visited at this depth
    if (canonical_key, depth) in positions:
        positions[(canonical_key, depth)]["visit_count"] += 1
        return

    # Check for game end
    winner = check_game_winner(bb)
    if winner != WinStatus.NO_WIN:
        # Terminal position
        if winner == WinStatus.PLAYER_0_WINS:
            win_p0, win_p1, draws = 1, 0, 0
            eval_score = 1.0
        elif winner == WinStatus.PLAYER_1_WINS:
            win_p0, win_p1, draws = 0, 1, 0
            eval_score = -1.0
        else:
            win_p0, win_p1, draws = 0, 0, 1
            eval_score = 0.0

        positions[(canonical_key, depth)] = {
            "state": state,
            "depth": depth,
            "visit_count": 1,
            "win_count_p0": win_p0,
            "win_count_p1": win_p1,
            "draw_count": draws,
            "best_moves": [],
            "evaluation": eval_score,
        }
        return

    # Generate legal moves
    current_player, moves_by_shape = generate_legal_moves(bb)
    all_moves = []
    for shape_moves in moves_by_shape.values():
        all_moves.extend(shape_moves)

    if not all_moves:
        # Stalemate
        positions[(canonical_key, depth)] = {
            "state": state,
            "depth": depth,
            "visit_count": 1,
            "win_count_p0": 0,
            "win_count_p1": 0,
            "draw_count": 1,
            "best_moves": [],
            "evaluation": 0.0,
        }
        return

    # Initialize position data
    positions[(canonical_key, depth)] = {
        "state": state,
        "depth": depth,
        "visit_count": 1,
        "win_count_p0": 0,
        "win_count_p1": 0,
        "draw_count": 0,
        "best_moves": all_moves[:3],  # Store top 3 moves
        "evaluation": 0.0,
    }

    # Explore children
    for move in all_moves:
        new_bb = apply_move(bb, move)
        explore_positions(new_bb, depth + 1, max_depth, positions)


def demo_build_opening_book():
    """Demonstrate building an opening book."""
    print("=" * 80)
    print("DEMO 1: Building Opening Book from Game Tree")
    print("=" * 80)

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = OpeningBookConfig(database_path=db_path)
        db = OpeningBookDatabase(config)

        print(f"\nDatabase created: {db_path}")
        print("Exploring game tree up to depth 4...")

        # Explore positions
        start_time = time.time()
        positions = {}
        initial_state = State.from_qfen("..../..../..../....")
        initial_bb = initial_state.bb
        explore_positions(initial_bb, depth=0, max_depth=4, positions=positions)
        exploration_time = time.time() - start_time

        print(f"Exploration complete in {exploration_time:.2f}s")
        print(f"Unique positions found: {len(positions):,}")

        # Add positions to database
        print("\nPopulating opening book...")
        start_time = time.time()

        for (canonical_key, depth), data in positions.items():
            db.add_position(
                state=data["state"],
                evaluation=data["evaluation"],
                visit_count=data["visit_count"],
                win_count_p0=data["win_count_p0"],
                win_count_p1=data["win_count_p1"],
                draw_count=data["draw_count"],
                best_moves=data["best_moves"],
                depth=depth,
            )

        db_time = time.time() - start_time

        print(f"Database populated in {db_time:.2f}s")

        # Show statistics
        stats = db.get_statistics()
        print(f"\nOpening Book Statistics:")
        print(f"  Total positions: {stats['total_positions']:,}")
        print(f"  Unique depths: {stats['unique_depths']}")
        print(f"  Total visits: {stats['total_visits']:,}")
        print(f"  Max depth: {stats['max_depth']}")
        print(
            f"  Database size: {stats['file_size_bytes']:,} bytes ({stats['file_size_bytes'] / 1024:.1f} KB)"
        )

        # Show positions by depth
        depth_counts = db.get_positions_by_depth()
        print(f"\nPositions by depth:")
        for depth in sorted(depth_counts.keys()):
            print(f"  Depth {depth}: {depth_counts[depth]:,} positions")

        db.close()

    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


def demo_query_positions():
    """Demonstrate querying positions from opening book."""
    print(f"\n{'='*80}")
    print("DEMO 2: Querying Positions from Opening Book")
    print("=" * 80)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = OpeningBookConfig(database_path=db_path)
        db = OpeningBookDatabase(config)

        # Build small opening book
        print("\nBuilding opening book (depth 3)...")
        positions = {}
        initial_state = State.from_qfen("..../..../..../....")
        initial_bb = initial_state.bb
        explore_positions(initial_bb, depth=0, max_depth=3, positions=positions)

        for (canonical_key, depth), data in positions.items():
            db.add_position(
                state=data["state"],
                evaluation=data["evaluation"],
                visit_count=data["visit_count"],
                win_count_p0=data["win_count_p0"],
                win_count_p1=data["win_count_p1"],
                draw_count=data["draw_count"],
                best_moves=data["best_moves"],
                depth=depth,
            )

        # Query specific position
        print("\nQuerying specific position...")
        state = State.from_qfen("A.../..../..../....")
        entry = db.get_position(state)

        if entry:
            print(f"Position found: {entry.qfen}")
            print(f"  Depth: {entry.depth}")
            print(f"  Evaluation: {entry.evaluation:.3f}")
            print(f"  Visit count: {entry.visit_count}")
            print(f"  P0 wins: {entry.win_count_p0}, P1 wins: {entry.win_count_p1}")
            print(f"  Best moves ({len(entry.best_moves)}):")
            for i, (shape, position) in enumerate(entry.best_moves, 1):
                shape_name = chr(ord("A") + shape)
                row, col = position // 4, position % 4
                print(f"    {i}. {shape_name} at ({row}, {col})")
        else:
            print("Position not found in opening book")

        # Query by depth
        print(f"\nQuerying positions at depth 2 (top 5)...")
        entries = db.query_by_depth(depth=2, limit=5)
        print(f"Found {len(entries)} positions at depth 2")

        for i, entry in enumerate(entries, 1):
            win_rate = (
                entry.win_count_p0 / entry.visit_count if entry.visit_count > 0 else 0
            )
            print(f"\n{i}. {entry.qfen}")
            print(
                f"   Visits: {entry.visit_count}, Win rate (P0): {win_rate:.1%}, Eval: {entry.evaluation:.3f}"
            )

        db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


def demo_canonical_deduplication():
    """Demonstrate canonical deduplication."""
    print(f"\n{'='*80}")
    print("DEMO 3: Canonical Position Deduplication")
    print("=" * 80)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = OpeningBookConfig(database_path=db_path)
        db = OpeningBookDatabase(config)

        # Create several symmetric positions
        test_positions = [
            "A.../..../..../....",  # A at top-left corner
            "...A/..../..../....",  # A at top-right corner (D4 rotation)
            "..../..../..../A...",  # A at bottom-left corner (D4 rotation)
            "..../..../..../...A",  # A at bottom-right corner (D4 rotation)
        ]

        print("\nAdding potentially symmetric positions...")
        canonical_keys = set()

        for qfen in test_positions:
            state = State.from_qfen(qfen)
            canonical_key = state.canonical_key()
            canonical_keys.add(canonical_key)

            print(f"\nPosition: {qfen}")
            print(f"  Canonical key: {canonical_key.hex()[:16]}...")

            db.add_position(
                state=state,
                evaluation=0.5,
                visit_count=100,
                win_count_p0=50,
                win_count_p1=50,
                draw_count=0,
                best_moves=[Move(player=0, shape=1, position=1)],
                depth=1,
            )

        stats = db.get_statistics()
        print(f"\nResults:")
        print(f"  Input positions: {len(test_positions)}")
        print(f"  Unique canonical forms: {len(canonical_keys)}")
        print(f"  Stored in database: {stats['total_positions']}")
        print(
            f"  Space savings: {(1 - stats['total_positions'] / len(test_positions)) * 100:.1f}%"
        )

        db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


def demo_export():
    """Demonstrate exporting opening book."""
    print(f"\n{'='*80}")
    print("DEMO 4: Exporting Opening Book")
    print("=" * 80)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    export_path = tempfile.mktemp(suffix=".txt")

    try:
        config = OpeningBookConfig(database_path=db_path)
        db = OpeningBookDatabase(config)

        # Build opening book
        print("\nBuilding opening book (depth 3)...")
        positions = {}
        initial_state = State.from_qfen("..../..../..../....")
        initial_bb = initial_state.bb
        explore_positions(initial_bb, depth=0, max_depth=3, positions=positions)

        for (canonical_key, depth), data in positions.items():
            db.add_position(
                state=data["state"],
                evaluation=data["evaluation"],
                visit_count=data["visit_count"],
                win_count_p0=data["win_count_p0"],
                win_count_p1=data["win_count_p1"],
                draw_count=data["draw_count"],
                best_moves=data["best_moves"],
                depth=depth,
            )

        print(f"Opening book built with {len(positions)} positions")

        # Export to file
        print(f"\nExporting to {export_path}...")
        db.export_to_file(export_path, depth_limit=2)

        # Show preview
        with open(export_path) as f:
            lines = f.readlines()

        print(f"Export complete! Preview (first 10 lines):")
        for line in lines[:10]:
            print(f"  {line.rstrip()}")

        print(f"\nTotal lines: {len(lines)}")

        db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)
        Path(export_path).unlink(missing_ok=True)


def demo_lookup_best_move():
    """Demonstrate looking up best moves from opening book."""
    print(f"\n{'='*80}")
    print("DEMO 5: Best Move Lookup During Game")
    print("=" * 80)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = OpeningBookConfig(database_path=db_path)
        db = OpeningBookDatabase(config)

        # Build opening book
        print("\nBuilding opening book (depth 4)...")
        positions = {}
        initial_state = State.from_qfen("..../..../..../....")
        initial_bb = initial_state.bb
        explore_positions(initial_bb, depth=0, max_depth=4, positions=positions)

        for (canonical_key, depth), data in positions.items():
            db.add_position(
                state=data["state"],
                evaluation=data["evaluation"],
                visit_count=data["visit_count"],
                win_count_p0=data["win_count_p0"],
                win_count_p1=data["win_count_p1"],
                draw_count=data["draw_count"],
                best_moves=data["best_moves"],
                depth=depth,
            )

        print(f"Opening book ready with {len(positions)} positions")

        # Simulate game with opening book lookups
        print("\nSimulating game with opening book assistance...")
        state = State.from_qfen("..../..../..../....")
        depth = 0

        while depth < 3:
            # Check opening book
            entry = db.get_position(state)

            if entry and entry.best_moves:
                shape, position = entry.best_moves[0]

                current_player, _ = generate_legal_moves(state.bb)
                move = Move(player=current_player, shape=shape, position=position)

                shape_name = chr(ord("A") + shape)
                row, col = position // 4, position % 4
                win_rate = (
                    entry.win_count_p0 / entry.visit_count
                    if entry.visit_count > 0
                    else 0.5
                )

                print(f"\nMove {depth + 1}:")
                print(f"  Position: {state.to_qfen()}")
                print(f"  Book move: {shape_name} at ({row}, {col})")
                print(f"  Evaluation: {entry.evaluation:.3f}")
                print(f"  Win rate (P0): {win_rate:.1%}")
                print(f"  Based on {entry.visit_count} games")

                # Apply move
                new_bb = apply_move(state.bb, move)
                state = State(new_bb)
                depth += 1
            else:
                print(f"\nPosition not in opening book at depth {depth}")
                break

        db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


def main():
    """Run all demonstrations."""
    print("QUANTIK OPENING BOOK DEMONSTRATION")
    print("=" * 80)
    print()
    print("This demo showcases the opening book database:")
    print("- Building from game tree analysis")
    print("- Efficient position queries")
    print("- Canonical deduplication")
    print("- Export functionality")
    print("- Best move lookup")
    print()

    demo_build_opening_book()
    demo_query_positions()
    demo_canonical_deduplication()
    demo_export()
    demo_lookup_best_move()

    print(f"\n{'='*80}")
    print("ALL DEMONSTRATIONS COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
