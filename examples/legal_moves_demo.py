"""
Example demonstrating legal move generation with Quantik game constraints.

This example shows how to:
1. Generate legal moves for the current player
2. Understand game constraints (max pieces, line conflicts)
3. Validate player turns
4. Analyze moves by shape
"""

from quantik_core.move import (
    generate_legal_moves,
    Move,
    apply_move,
)
from quantik_core.qfen import bb_from_qfen, bb_to_qfen


def demonstrate_legal_moves():
    """Demonstrate legal move generation functionality."""

    print("=== Quantik Legal Move Generation Demo ===\n")

    # 1. Empty board - all moves available
    print("1. Empty board:")
    bb = bb_from_qfen("..../..../..../....", validate=True)
    current_player, moves_by_shape = generate_legal_moves(bb)
    print(f"   Current player: {current_player}")
    print(
        f"   Moves per shape: {[(shape, len(moves)) for shape, moves in moves_by_shape.items()]}"
    )
    print(f"   Total moves: {sum(len(moves) for moves in moves_by_shape.values())}")
    print()

    # 2. After first move - constraints appear
    print("2. After player 0 places A at position 0:")
    bb = bb_from_qfen("A.../..../..../....", validate=True)
    current_player, moves_by_shape = generate_legal_moves(bb)
    print(f"   Current player: {current_player}")
    print(
        f"   A moves for player 1: {len(moves_by_shape[0])} (constraints from row/col/zone)"
    )
    print(
        f"   Other shape moves: B={len(moves_by_shape[1])}, C={len(moves_by_shape[2])}, D={len(moves_by_shape[3])}"
    )

    # Show specific A positions that are forbidden/allowed
    a_positions = sorted([move.position for move in moves_by_shape[0]])
    forbidden_positions = sorted(
        set(range(16)) - set(a_positions) - {0}
    )  # Exclude occupied position 0
    print(f"   Forbidden A positions: {forbidden_positions}")
    print(f"   Allowed A positions: {a_positions}")
    print()

    # 3. Max pieces constraint
    print("3. Max pieces constraint:")
    bb = bb_from_qfen("A.A./b.../..c./....", validate=True)
    current_player, moves_by_shape = generate_legal_moves(bb)
    print(f"   Current player: {current_player}")
    print(
        f"   A moves for player 0: {len(moves_by_shape[0])} (already has 2 A pieces - max reached)"
    )
    print(
        f"   Other moves available: B={len(moves_by_shape[1])}, C={len(moves_by_shape[2])}, D={len(moves_by_shape[3])}"
    )
    print()

    # 4. Player validation
    print("4. Player turn validation:")
    bb = bb_from_qfen("..../..../..../....", validate=True)
    # Try to get moves for wrong player
    wrong_player, no_moves = generate_legal_moves(
        bb, player_id=1
    )  # Player 1 when it's player 0's turn
    print("   Requesting moves for player 1 when it's player 0's turn:")
    print(f"   Result: {[(shape, len(moves)) for shape, moves in no_moves.items()]}")
    print()

    # 5. Game progression example
    print("5. Game progression example:")
    bb = bb_from_qfen("..../..../..../....", validate=True)
    moves_sequence = [
        Move(0, 0, 0),  # Player 0: A at pos 0
        Move(1, 1, 6),  # Player 1: B at pos 6
        Move(0, 2, 10),  # Player 0: C at pos 10
        Move(1, 3, 15),  # Player 1: D at pos 15
    ]

    for i, move in enumerate(moves_sequence):
        print(f"   Before move {i + 1}: {bb_to_qfen(bb)}")

        # Validate the move
        current_player, moves_by_shape = generate_legal_moves(bb)
        is_valid = any(move in shape_moves for shape_moves in moves_by_shape.values())

        print(f"   Move {move} is {'valid' if is_valid else 'INVALID'}")

        if is_valid:
            bb = apply_move(bb, move)
        else:
            print("   Breaking due to invalid move")
            break

    print(f"   Final state: {bb_to_qfen(bb)}")

    # Show remaining legal moves
    final_player, final_moves = generate_legal_moves(bb)
    total_remaining = sum(len(moves) for moves in final_moves.values())
    print(f"   Remaining legal moves for player {final_player}: {total_remaining}")


if __name__ == "__main__":
    demonstrate_legal_moves()
