#!/usr/bin/env python3
"""
Beam Search Demo for Quantik

Demonstrates:
1. Full-depth search from the empty board, reaching a true terminal
2. Tactical position analysis (immediate win found at depth 1)
3. Beam width sweep showing the O(beam_width x depth) memory bound
4. Pluggable custom evaluator
"""

import time

from quantik_core import State, Move, apply_move
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine


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


def demo_full_game_reachability():
    """Demonstrate reaching a true terminal from the empty board."""
    print(f"\n{'=' * 80}")
    print("DEMO 1: Full-Depth Search from Empty Board")
    print(f"{'=' * 80}")

    config = BeamSearchConfig(
        beam_width=4, max_depth=16, rollouts_per_candidate=2, random_seed=42
    )
    engine = BeamSearchEngine(config)
    state = State.from_qfen("..../..../..../....")

    print("\nSearch parameters:")
    print(f"  Beam width: {config.beam_width}")
    print(f"  Max depth: {config.max_depth}")
    print(f"  Rollouts per candidate: {config.rollouts_per_candidate}")

    start_time = time.time()
    result = engine.search(state)
    search_time = time.time() - start_time

    print(f"\nSearch completed in {search_time:.3f} seconds")
    print(f"Reached terminal: {result.reached_terminal}")
    print(f"Max depth reached: {result.max_depth_reached}")
    print(f"Terminal leaves found: {len(result.terminal_leaves)}")
    print(f"Stats: {result.stats}")

    assert result.best_leaf is not None
    print(f"\nBest line for the root player ({len(result.best_leaf.moves)} plies):")
    print(f"  Final value (P0 perspective): {result.best_leaf.value:+.1f}")

    replay_state = state
    for ply, move in enumerate(result.best_leaf.moves, start=1):
        new_bb = apply_move(replay_state.bb, move)
        replay_state = State(new_bb)
        print(f"  Ply {ply}: {format_move(move)}")

    print_board(replay_state)


def demo_tactical_position():
    """Demonstrate beam search finding an immediate win."""
    print(f"\n{'=' * 80}")
    print("DEMO 2: Tactical Position Analysis (Immediate Win)")
    print(f"{'=' * 80}")

    # P0: A at (0,0), B at (0,1); P1: c at (0,2), a at (3,3).
    # Row 0 has shapes A, B, C — P0 wins in one move by placing D at (0,3).
    state = State.from_qfen("ABc./..../..../...a")
    print(f"\nPosition: {state.to_qfen()}")
    print_board(state)

    config = BeamSearchConfig(
        beam_width=4, max_depth=2, rollouts_per_candidate=2, random_seed=1
    )
    engine = BeamSearchEngine(config)
    result = engine.search(state)

    assert result.best_leaf is not None
    print(f"Best move found: {format_move(result.best_leaf.moves[0])}")
    print(f"Terminal: {result.best_leaf.is_terminal}")
    print(f"Value (P0 perspective): {result.best_leaf.value:+.1f}")
    print(f"Depth: {result.best_leaf.depth}")


def demo_beam_width_sweep():
    """Demonstrate the O(beam_width x depth) memory bound."""
    print(f"\n{'=' * 80}")
    print("DEMO 3: Beam Width Sweep (Memory Bound)")
    print(f"{'=' * 80}")

    state = State.from_qfen("..../..../..../....")

    print(f"\n{'Beam Width':<12} {'Nodes Inserted':<16} {'Memory Usage (bytes)'}")
    print("-" * 50)

    for beam_width in (2, 8, 32):
        config = BeamSearchConfig(
            beam_width=beam_width,
            max_depth=6,
            rollouts_per_candidate=2,
            random_seed=7,
            # A small initial capacity makes memory growth visible in this
            # demo; production searches should size this to the expected
            # tree (see BeamSearchConfig.initial_tree_capacity docs).
            initial_tree_capacity=64,
        )
        engine = BeamSearchEngine(config)
        result = engine.search(state)

        print(
            f"{beam_width:<12} {result.stats['nodes_inserted']:<16} "
            f"{result.stats['memory_usage']:,}"
        )

    print("\nNodes inserted grows with beam_width, bounded by beam_width * depth")
    print("plus the number of terminal leaves discovered along the way.")


def demo_custom_evaluator():
    """Demonstrate a pluggable, non-default evaluator."""
    print(f"\n{'=' * 80}")
    print("DEMO 4: Pluggable Custom Evaluator")
    print(f"{'=' * 80}")

    def material_evaluator(state: State) -> float:
        """Toy evaluator: favors player 0 having placed more pieces.

        Not a serious Quantik heuristic (piece count alone says little
        about winning chances) — this only demonstrates that any
        `Callable[[State], float]` can replace the built-in random-rollout
        evaluator.
        """
        bb = state.bb
        p0_pieces = sum(bin(b).count("1") for b in bb[:4])
        p1_pieces = sum(bin(b).count("1") for b in bb[4:])
        return max(-1.0, min(1.0, (p0_pieces - p1_pieces) / 4.0))

    config = BeamSearchConfig(
        beam_width=4, max_depth=4, evaluator=material_evaluator, random_seed=3
    )
    engine = BeamSearchEngine(config)
    state = State.from_qfen("..../..../..../....")

    result = engine.search(state)

    print(f"\nEvaluator calls made: {result.stats['evaluations']}")
    assert result.stats["evaluations"] > 0
    assert result.best_leaf is not None
    print(f"Best line found ({len(result.best_leaf.moves)} plies):")
    for ply, move in enumerate(result.best_leaf.moves, start=1):
        print(f"  Ply {ply}: {format_move(move)}")


def main():
    """Run all demonstrations."""
    print("QUANTIK BEAM SEARCH DEMONSTRATION")
    print("=" * 80)
    print()
    print("This demo showcases the parametrizable beam search engine:")
    print("- Full-depth search reaching a true terminal state")
    print("- Tactical (immediate win) position analysis")
    print("- Beam width sweep and its memory bound")
    print("- Pluggable custom evaluators")
    print()

    demo_full_game_reachability()
    demo_tactical_position()
    demo_beam_width_sweep()
    demo_custom_evaluator()

    print(f"\n{'=' * 80}")
    print("ALL DEMONSTRATIONS COMPLETE")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
