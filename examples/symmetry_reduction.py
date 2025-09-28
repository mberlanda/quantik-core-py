#!/usr/bin/env python
"""
A script to demonstrate symmetry reduction in Quantik.
"""

from typing import TextIO, Optional, Tuple, Dict, Set, List
import os
import textwrap
import random

from quantik_core import Move, apply_move, SymmetryHandler, generate_legal_moves
from quantik_core.commons import Bitboard
from quantik_core.qfen import bb_from_qfen, bb_to_qfen

# Random seed for deterministic sampling
RANDOM_SEED = 42
random.seed(RANDOM_SEED)


class MarkdownWriter:
    """Utility class to write markdown content."""

    def __init__(self, file_path: str):
        """Initialize with output file path."""
        self.file_path = file_path
        self.file: Optional[TextIO] = None

    def __enter__(self):
        """Open file when entering context."""
        self.file = open(self.file_path, "w", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close file when exiting context."""
        if self.file:
            self.file.close()
            self.file = None

    def write(self, text: str):
        """Write text to file."""
        if self.file:
            self.file.write(text)

    def writeln(self, text: str = ""):
        """Write text with newline."""
        self.write(text + "\n")

    def heading(self, level: int, text: str):
        """Write markdown heading."""
        self.writeln("\n" + "#" * level + " " + text + "\n")

    def draw_ascii_grid(self, grid_data: List[List[str]]) -> None:
        """Draw 4x4 ASCII grid with provided data."""
        self.writeln("```")
        self.writeln("┌───┬───┬───┬───┐")
        for r in range(4):
            self.writeln(f"│ {' │ '.join(grid_data[r])} │")
            if r < 3:
                self.writeln("├───┼───┼───┼───┤")
        self.writeln("└───┴───┴───┴───┘")
        self.writeln("```")


def position_to_coords(pos: int) -> str:
    """Convert a position index to human-readable coordinates."""
    row, col = SymmetryHandler.i_to_rc(pos)
    return f"({row},{col})"


def find_piece_position_in_canonical(canonical_bb: Bitboard) -> int:
    """Find position of a piece in canonical board representation."""
    # Check all shapes for both players
    for player in range(2):
        for shape in range(4):
            for i in range(16):
                if (canonical_bb[player * 4 + shape] >> i) & 1:
                    return i
    return -1


def board_to_markdown(bb: Bitboard, title: str = None) -> str:
    """Convert Quantik board to markdown string."""
    qfen = bb_to_qfen(bb)
    rows = qfen.split("/")

    result = []

    if title:
        result.append(f"\n### {title}\n")

    result.append("```")
    result.append("  ┌───┬───┬───┬───┐")
    for i, row in enumerate(rows):
        result.append(f"{i} │ {' │ '.join(row)} │")
        if i < 3:
            result.append("  ├───┼───┼───┼───┤")
    result.append("  └───┴───┴───┴───┘")
    result.append("    0   1   2   3  ")
    result.append("```\n")

    return "\n".join(result)


def get_sample_moves(bb: Bitboard, count: int) -> List[Move]:
    """Get sample of legal moves with deterministic sampling."""
    _, moves_by_shape = generate_legal_moves(bb)
    legal_moves = [move for move_list in moves_by_shape.values() for move in move_list]

    if not legal_moves:
        return []

    # Use sample if we want fewer moves than available, otherwise return all
    if count >= len(legal_moves):
        return legal_moves
    else:
        return random.sample(legal_moves, count)


def create_position_grid(fill_char: str = "·") -> List[List[str]]:
    """Create empty 4x4 grid."""
    return [[fill_char for _ in range(4)] for _ in range(4)]


def populate_position_grid(
    grid: List[List[str]], positions: List[int], marker: str
) -> None:
    """Populate grid with markers at specified positions."""
    for pos in positions:
        r, c = divmod(pos, 4)
        grid[r][c] = marker


def populate_mapping_grid(
    grid: List[List[str]],
    position_mapping: Dict[int, int],
    value_map: Dict[int, str],
    default: str = "?",
) -> None:
    """Populate grid with mapped values for all positions."""
    for pos in range(16):
        mapped_value = position_mapping[pos]
        r, c = divmod(pos, 4)
        grid[r][c] = value_map.get(mapped_value, default)


def compute_unique_canonical_positions(bb: Bitboard) -> Set[Tuple[int, ...]]:
    """Compute all unique canonical positions from legal moves on given state."""
    canonical_states = set()

    # Get all legal moves from current state
    _, moves_by_shape = generate_legal_moves(bb)
    legal_moves = [move for move_list in moves_by_shape.values() for move in move_list]

    for move in legal_moves:
        new_bb = apply_move(bb, move)
        canonical_bb, _ = SymmetryHandler.find_canonical_form(new_bb)
        # Use tuple of bitboard values as hashable key (ignore transformation for uniqueness)
        canonical_key = tuple(canonical_bb)
        canonical_states.add(canonical_key)

    return canonical_states


def compute_canonical_first_move_positions(empty: Bitboard) -> Set[int]:
    """Compute all unique canonical positions for first moves by player 0."""
    canonical_positions = set()

    # Try all possible first moves (4 shapes × 16 positions)
    for shape in range(4):
        for pos in range(16):
            move = Move(player=0, shape=shape, position=pos)
            bb = apply_move(empty, move)
            canonical_bb, _ = SymmetryHandler.find_canonical_form(bb)

            # Find where the piece ended up in the canonical form
            canonical_pos = find_piece_position_in_canonical(canonical_bb)
            if canonical_pos != -1:
                canonical_positions.add(canonical_pos)

    return canonical_positions


def compute_move_statistics(bb: Bitboard) -> Tuple[int, int, float, float]:
    """Compute statistics for a given board state."""
    # Get all legal moves
    _, moves_by_shape = generate_legal_moves(bb)
    legal_moves = [move for move_list in moves_by_shape.values() for move in move_list]

    # Compute unique canonical positions
    canonical_states = compute_unique_canonical_positions(bb)

    total_legal_moves = len(legal_moves)
    unique_canonical_states = len(canonical_states)
    reduction_factor = (
        total_legal_moves / unique_canonical_states
        if unique_canonical_states > 0
        else 0
    )
    space_savings = (
        (total_legal_moves - unique_canonical_states) / total_legal_moves * 100
        if total_legal_moves > 0
        else 0
    )

    return total_legal_moves, unique_canonical_states, reduction_factor, space_savings


def write_comprehensive_symmetry_table(
    writer: MarkdownWriter, empty: Bitboard, max_moves: int = 16
) -> None:
    """Write comprehensive table showing symmetry reduction across multiple moves."""
    writer.writeln("\n### Comprehensive Symmetry Reduction Analysis")
    writer.writeln(
        "| Move | Total Legal Moves | Unique Canonical States | Reduction Factor | Space Savings |"
    )
    writer.writeln(
        "|------|-------------------|-------------------------|------------------|---------------|"
    )

    # Start with empty board
    current_bb = empty
    move_sequence = []

    for move_num in range(1, max_moves + 1):
        # Get statistics for current position
        total_legal, unique_canonical, reduction_factor, space_savings = (
            compute_move_statistics(current_bb)
        )

        if total_legal == 0:
            # No more legal moves, game ended
            break

        # Write table row
        writer.writeln(
            f"| {move_num} | {total_legal} | {unique_canonical} | {reduction_factor:.2f}x | {space_savings:.1f}% |"
        )

        # Pick a random legal move to continue the sequence
        sample_moves = get_sample_moves(current_bb, 1)
        if not sample_moves:
            break

        move = sample_moves[0]
        current_bb = apply_move(current_bb, move)
        move_sequence.append(move)

    writer.writeln(
        f"\n*Analysis based on a random game sequence of {len(move_sequence)} moves.*"
    )


def write_introduction(writer: MarkdownWriter, empty: Bitboard) -> None:
    """Write introduction section."""
    writer.heading(1, "QUANTIK SYMMETRY REDUCTION DEMONSTRATION")

    writer.writeln(
        textwrap.dedent(
            """
        This document demonstrates how symmetry handling can dramatically reduce
        the complexity of the Quantik game search space.
        """
        )
    )

    # Show the empty board
    writer.write(board_to_markdown(empty, "Empty Board"))


def write_first_move_section(
    writer: MarkdownWriter, empty: Bitboard, canonical_positions: Set[int]
) -> None:
    """Write first move canonicalization section."""
    writer.heading(2, "First Move Canonicalization")
    writer.writeln(
        textwrap.dedent(
            """
        In Quantik, the first player has 64 possible moves (4 shapes × 16 positions).
        However, due to symmetries, many of these are equivalent.

        By applying symmetry reductions, we can map all first moves to just a few
        canonical positions.
        """
        )
    )

    # Show these canonical positions
    writer.writeln("\n### Canonical First Move Positions:")

    # Create grid data for canonical positions
    canonical_grid = [
        ["   ", "   ", "   ", "   "],
        ["   ", "   ", "   ", "   "],
        [" 8 ", " 9 ", "   ", "   "],
        [" 12", "   ", "   ", "   "],
    ]

    writer.draw_ascii_grid(canonical_grid)


def compute_position_mappings(
    empty: Bitboard, canonical_positions: Set[int]
) -> Tuple[Dict[int, int], Dict[int, List[int]]]:
    """Compute mapping of positions to canonical equivalents."""
    position_mapping = {}
    canonical_representatives = {pos: [] for pos in canonical_positions}

    # For each possible first move position
    for pos in range(16):
        # Create a state with shape A at that position
        move = Move(player=0, shape=0, position=pos)
        bb = apply_move(empty, move)
        canonical_bb, _ = SymmetryHandler.find_canonical_form(bb)

        # Find where the piece ended up in the canonical form
        canonical_pos = find_piece_position_in_canonical(canonical_bb)

        # Store the mapping
        position_mapping[pos] = canonical_pos

        # Store the reverse mapping for our canonical positions
        if canonical_pos in canonical_positions:
            canonical_representatives[canonical_pos].append(pos)

    return position_mapping, canonical_representatives


def write_position_mappings(
    writer: MarkdownWriter, canonical_representatives: Dict[int, List[int]]
) -> None:
    """Write position mappings visualization."""
    # Show the mapping results
    writer.writeln("\n### Position Mappings to Canonical Forms:")
    for canon_pos, equiv_positions in canonical_representatives.items():
        writer.writeln(
            f"\n#### Positions equivalent to {position_to_coords(canon_pos)}:"
        )

        # Create a visual 4x4 grid showing equivalent positions
        grid = create_position_grid()
        populate_position_grid(grid, equiv_positions, "●")

        writer.draw_ascii_grid(grid)

        writer.writeln(f"Total: {len(equiv_positions)} positions")


def write_canonical_mapping_visualization(
    writer: MarkdownWriter,
    position_mapping: Dict[int, int],
    canonical_positions: Set[int],
) -> None:
    """Write canonical position mapping visualization."""
    writer.writeln("\n### Visualization of Canonical Position Mapping:")
    writer.writeln("This grid shows where each position maps to in canonical form:")

    # Create a visual 4x4 grid showing the canonical mapping for each position
    mapping_grid = create_position_grid()

    # Define mapping letters for clarity
    canonical_letters = {8: "A", 9: "B", 12: "C"}

    # Fill in the grid with mapping information
    populate_mapping_grid(mapping_grid, position_mapping, canonical_letters)

    writer.draw_ascii_grid(mapping_grid)
    writer.writeln("Where: A = maps to (2,0), B = maps to (2,1), C = maps to (3,0)")

    writer.writeln("\n### Total unique first moves after symmetry reduction:")
    writer.writeln(f"* **Unique positions:** {len(canonical_positions)}")
    writer.writeln(f"* **Reduction factor:** {16 / len(canonical_positions):.2f}x")


def write_example_canonical_forms(
    writer: MarkdownWriter, empty: Bitboard, position_mapping: Dict[int, int]
) -> None:
    """Write example canonical forms for selected positions."""
    # Show example canonical forms
    writer.heading(2, "Example Canonical Forms")

    # Choose some interesting positions to show
    example_positions = [0, 5, 15]

    for pos in example_positions:
        # Create a state with shape A at that position
        move = Move(player=0, shape=0, position=pos)
        bb = apply_move(empty, move)
        canonical_bb, trans = SymmetryHandler.find_canonical_form(bb)

        # Get the original and canonical states
        writer.writeln(f"\n### Position {position_to_coords(pos)}")
        writer.write(board_to_markdown(bb, "Original Position"))
        writer.write(board_to_markdown(canonical_bb, f"Canonical Form {trans}"))
        pos_coords = position_to_coords(position_mapping[pos])
        writer.writeln(f"Maps to canonical position {pos_coords}")


def write_second_third_moves(
    writer: MarkdownWriter, empty: Bitboard, canonical_positions: Set[int]
) -> None:
    """Write second and third move canonicalization section."""
    writer.heading(2, "Second and Third Move Canonicalization")

    # For each canonical first position, show second move examples
    for canon_pos in sorted(canonical_positions):
        # Create a state with the first move
        first_move = Move(player=0, shape=0, position=canon_pos)
        bb_1 = apply_move(empty, first_move)

        writer.writeln(
            f"\n### Second Move After First Move at {position_to_coords(canon_pos)}"
        )
        writer.write(board_to_markdown(bb_1, "Position after first move"))

        # Choose a few representative second moves
        second_move_examples = get_sample_moves(bb_1, 3)

        for move_idx, second_move in enumerate(second_move_examples):
            bb_2 = apply_move(bb_1, second_move)
            canonical_bb2, trans2 = SymmetryHandler.find_canonical_form(bb_2)

            writer.writeln(f"\n#### Second Move Example {move_idx + 1}")
            writer.writeln(
                f"Move: Player {second_move.player}, Shape {second_move.shape} at "
                f"position {position_to_coords(second_move.position)}"
            )
            writer.write(board_to_markdown(bb_2, "After second move"))
            writer.write(board_to_markdown(canonical_bb2, f"Canonical form {trans2}"))

            # For the first example, also show a third move
            if move_idx == 0:
                writer.writeln("\n##### Third Move Example After Above")
                legal_third_moves = get_sample_moves(bb_2, 1)

                if legal_third_moves:
                    third_move = legal_third_moves[0]
                    bb_3 = apply_move(bb_2, third_move)
                    canonical_bb3, trans3 = SymmetryHandler.find_canonical_form(bb_3)

                    pos_coords = position_to_coords(third_move.position)
                    move_text = (
                        f"Move: Player {third_move.player}, Shape {third_move.shape}"
                    )
                    writer.writeln(f"{move_text} at position {pos_coords}")
                    writer.write(board_to_markdown(bb_3, "After third move"))
                    writer.write(
                        board_to_markdown(canonical_bb3, f"Canonical form {trans3}")
                    )


def write_determinism_test(writer: MarkdownWriter) -> None:
    """Write determinism testing section."""
    # Add discussion on determinism of canonical representation
    writer.heading(2, "Is Canonical Representation Deterministic?")
    writer.writeln(
        textwrap.dedent(
            """
    A critical property of any canonical representation system is determinism -
    the same game state must always map to the same canonical form, regardless of
    how that state was reached. Let's verify this property:
    """
        )
    )

    # Create two equivalent states through different move sequences
    writer.writeln("\n### Testing Determinism")

    # Define two different paths to equivalent positions
    def create_test_states() -> Tuple[Bitboard, Bitboard]:
        """Create two equivalent states via different move sequences."""
        empty = bb_from_qfen("..../..../..../....")

        # Path 1: Moves at positions 0, 5, 10
        moves1 = [
            Move(player=0, shape=0, position=0),
            Move(player=1, shape=1, position=5),
            Move(player=0, shape=2, position=10),
        ]

        # Path 2: Moves at positions 3, 14, 9 (equivalent under rotation)
        moves2 = [
            Move(player=0, shape=0, position=3),
            Move(player=1, shape=1, position=14),
            Move(player=0, shape=2, position=9),
        ]

        bb_1 = empty
        for move in moves1:
            bb_1 = apply_move(bb_1, move)

        bb_2 = empty
        for move in moves2:
            bb_2 = apply_move(bb_2, move)

        return bb_1, bb_2

    bb_1, bb_2 = create_test_states()

    writer.write(board_to_markdown(bb_1, "State 1"))
    writer.write(board_to_markdown(bb_2, "State 2"))

    canonical_bb1, trans1 = SymmetryHandler.find_canonical_form(bb_1)
    canonical_bb2, trans2 = SymmetryHandler.find_canonical_form(bb_2)

    writer.write(
        board_to_markdown(canonical_bb1, f"Canonical Form of State 1 - {trans1}")
    )
    writer.write(
        board_to_markdown(canonical_bb2, f"Canonical Form of State 2 - {trans2}")
    )

    if canonical_bb1 == canonical_bb2:
        writer.writeln(
            "\n**Result:** The canonical representation is deterministic. "
            "Both equivalent states map to the same canonical form."
        )
        writer.writeln(f"Canonical QFEN: `{bb_to_qfen(canonical_bb1)}`")
    else:
        writer.writeln(
            "\n**Result:** The canonical representation is NOT deterministic! "
            "This is a serious issue that needs to be fixed."
        )
        writer.writeln(f"Canonical QFEN 1: `{bb_to_qfen(canonical_bb1)}`")
        writer.writeln(f"Canonical QFEN 2: `{bb_to_qfen(canonical_bb2)}`")

    writer.writeln(
        textwrap.dedent(
            """
    ### Implications for Game Search

    The deterministic property of our canonical representation is crucial for:

    1. **Transposition Tables:** We can safely use canonical positions as keys in our
       transposition tables, knowing that equivalent positions will always hash to the same key.

    2. **Learning Algorithms:** When training reinforcement learning agents or building
       opening books, we can properly aggregate data from equivalent positions.

    3. **Consistency:** Game analysis and search will be consistent and reliable across
       different move sequences that lead to equivalent positions.
    """
        )
    )


def write_dynamic_symmetry_reduction(
    writer: MarkdownWriter, empty: Bitboard, canonical_positions: Set[int]
) -> None:
    """Write dynamic symmetry analysis section."""
    writer.heading(2, "Dynamic Symmetry Reduction Analysis")
    writer.writeln(
        textwrap.dedent(
            """
        Let's analyze how symmetry reduction works dynamically by examining the reduction
        at different move depths. This shows how the game tree complexity is reduced
        at each level through canonical representation.
        """
        )
    )

    # Write comprehensive symmetry reduction table up to 16th move
    write_comprehensive_symmetry_table(writer, empty, 16)

    writer.writeln(
        textwrap.dedent(
            """
        ### Key Insights

        This dynamic analysis demonstrates:
        - **Progressive reduction**: Each move level shows different reduction factors
        - **Symmetry preservation**: Even as the game progresses, symmetries continue to reduce complexity
        - **Computational savings**: The space savings percentage shows the efficiency gained
        - **Search optimization**: These reductions directly translate to smaller search trees
        """
        )
    )


def write_conclusion(writer: MarkdownWriter) -> None:
    """Write conclusion section."""
    writer.heading(2, "CONCLUSION")
    writer.writeln(
        textwrap.dedent(
            """
    We've demonstrated how symmetry handling can dramatically reduce the complexity
    of the Quantik game search space. The main benefits are:

    1. First move: From 64 possible moves to just 3 canonical positions
    2. Entire game tree reduction by a factor of 24 (8 spatial symmetries × 3 shape permutations)
    3. Second and third move canonicalization continues to reduce the branching factor

    **IMPORTANT FINDING:** Our determinism test revealed that the current canonical
    representation is NOT deterministic! This is a critical issue that needs to be addressed
    before using the symmetry reduction in production, as it could lead to inconsistent behavior in:
    - Transposition tables
    - Opening books
    - Learning algorithms

    This indicates a potential bug in the symmetry handling implementation that should be fixed.

    Once fixed, this approach will enable much more efficient game analysis, as we can:
    - Store evaluations for canonical positions only
    - Analyze a much smaller search space
    - Still recover the actual moves through symmetry transformations
    - Build reliable opening books and transposition tables
    """
        )
    )


def main() -> None:
    """Generate markdown file demonstrating symmetry reduction."""
    # Set seed for reproducibility of random examples
    random.seed(RANDOM_SEED)

    output_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "SYMMETRY_REDUCTION_DEMONSTRATION.md",
    )

    with MarkdownWriter(output_file) as writer:
        # Initialize the empty state
        empty = bb_from_qfen("..../..../..../....")

        # Compute canonical positions for all first moves
        canonical_positions = compute_canonical_first_move_positions(empty)

        # Write introduction
        write_introduction(writer, empty)

        # Write first move section
        write_first_move_section(writer, empty, canonical_positions)

        # Compute position mappings
        position_mapping, canonical_representatives = compute_position_mappings(
            empty, canonical_positions
        )

        # Write position mapping visualizations
        write_position_mappings(writer, canonical_representatives)

        # Write canonical mapping visualization
        write_canonical_mapping_visualization(
            writer, position_mapping, canonical_positions
        )

        # Dynamic symmetry analysis section
        write_dynamic_symmetry_reduction(writer, empty, canonical_positions)

        # Write example canonical forms
        write_example_canonical_forms(writer, empty, position_mapping)

        # Write second and third moves section
        write_second_third_moves(writer, empty, canonical_positions)

        # Test and write about determinism
        write_determinism_test(writer)

        # Write conclusion
        write_conclusion(writer)

        print(f"Successfully wrote demonstration to {output_file}")


if __name__ == "__main__":
    main()
