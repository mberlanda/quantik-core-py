#!/usr/bin/env python3
"""
Quantik Tactical Puzzle Generator with Full Visual Solutions

Generates tactical puzzles from midgame starting positions using the existing
EndgamePuzzleGenerator, then computes complete forced winning sequences via
a minimax solver. Outputs puzzles with step-by-step board visualizations.

Usage:
    python examples/generate_puzzles.py
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from quantik_core import Move, State, apply_move, generate_legal_moves
from quantik_core.game_utils import WinStatus, check_game_winner

sys.path.insert(0, os.path.dirname(__file__))

from endgame_puzzle_generator import (  # noqa: E402
    EndgamePuzzleGenerator,
    Puzzle,
    PuzzleConfig,
)

SHAPE_NAMES = "ABCD"

STARTING_POSITIONS = [
    ("A.../.B../..c./...d", "Diagonal spread (4 pieces)"),
    ("A..d/cB../..C./...b", "Advanced midgame (6 pieces)"),
    ("A.b./.C.d/..../....", "Clustered (4 pieces)"),
]

BOX_WIDTH = 48
SOLVE_TIMEOUT_SECS = 5.0


# ---------------------------------------------------------------------------
# Board rendering helpers
# ---------------------------------------------------------------------------


def qfen_to_grid(qfen: str) -> List[List[str]]:
    return [list(row) for row in qfen.split("/")]


def render_board_lines(qfen: str, indent: str = "  ") -> List[str]:
    grid = qfen_to_grid(qfen)
    lines = [f"{indent}    0   1   2   3"]
    for r in range(4):
        cells = "   ".join(grid[r])
        lines.append(f"{indent} {r}  {cells}")
    return lines


def format_move(move: Move, is_winning: bool = False) -> str:
    shape_ch = SHAPE_NAMES[move.shape]
    if move.player == 1:
        shape_ch = shape_ch.lower()
    row, col = move.position // 4, move.position % 4
    suffix = " \u2014 WIN!" if is_winning else ""
    return f"P{move.player} plays {shape_ch} at ({row},{col}){suffix}"


# ---------------------------------------------------------------------------
# Minimax solver
# ---------------------------------------------------------------------------


def _minimax(  # noqa: C901
    bb: tuple,
    winning_player: int,
    depth_limit: int,
    memo: Dict[tuple, Tuple[int, Optional[Move]]],
    deadline: float,
) -> Tuple[Optional[int], Optional[Move]]:
    """
    Return (distance_in_plies, best_move) for a forced win by *winning_player*,
    or (None, None) when no forced win is found within *depth_limit*.

    Winning player's turns  -> minimise distance.
    Opponent's turns        -> maximise distance (best defence); if any move
                               escapes the forced loss the position is not won.
    """
    winner = check_game_winner(bb)
    if winner != WinStatus.NO_WIN:
        is_ours = (winner == WinStatus.PLAYER_0_WINS and winning_player == 0) or (
            winner == WinStatus.PLAYER_1_WINS and winning_player == 1
        )
        return (0, None) if is_ours else (None, None)

    if depth_limit <= 0 or time.time() > deadline:
        return None, None

    if bb in memo:
        cached_dist, cached_move = memo[bb]
        if cached_dist is not None and cached_dist <= depth_limit:
            return cached_dist, cached_move

    current_player, moves_by_shape = generate_legal_moves(bb)
    all_moves: List[Move] = []
    for shape_moves in moves_by_shape.values():
        all_moves.extend(shape_moves)

    if not all_moves:
        return None, None

    # ---- move ordering: try immediate wins first, skip losing moves ----
    ordered: List[Move] = []
    for m in all_moves:
        nbb = apply_move(bb, m)
        w = check_game_winner(nbb)
        if w != WinStatus.NO_WIN:
            is_ours = (w == WinStatus.PLAYER_0_WINS and winning_player == 0) or (
                w == WinStatus.PLAYER_1_WINS and winning_player == 1
            )
            if is_ours:
                memo[bb] = (1, m)
                return 1, m
            continue
        ordered.append(m)

    if current_player == winning_player:
        best_dist: Optional[int] = None
        best_move: Optional[Move] = None
        for m in ordered:
            nbb = apply_move(bb, m)
            d, _ = _minimax(nbb, winning_player, depth_limit - 1, memo, deadline)
            if d is not None:
                d += 1
                if best_dist is None or d < best_dist:
                    best_dist = d
                    best_move = m
        if best_dist is not None:
            memo[bb] = (best_dist, best_move)
        return best_dist, best_move
    else:
        worst_dist: Optional[int] = None
        worst_move: Optional[Move] = None
        for m in ordered:
            nbb = apply_move(bb, m)
            d, _ = _minimax(nbb, winning_player, depth_limit - 1, memo, deadline)
            if d is None:
                return None, None  # opponent escapes
            d += 1
            if worst_dist is None or d > worst_dist:
                worst_dist = d
                worst_move = m
        if worst_dist is not None:
            memo[bb] = (worst_dist, worst_move)
        return worst_dist, worst_move


def compute_solution_line(
    bb: tuple,
    winning_player: int,
    depth_limit: int = 8,
) -> Optional[List[Tuple[Move, str, bool]]]:
    """
    Compute the full forced winning sequence from *bb*.

    Returns a list of (move, qfen_after, is_terminal) tuples,
    or None if no forced win can be verified.
    """
    memo: Dict[tuple, Tuple[int, Optional[Move]]] = {}
    deadline = time.time() + SOLVE_TIMEOUT_SECS

    dist, first = _minimax(bb, winning_player, depth_limit, memo, deadline)
    if dist is None or first is None:
        return None

    steps: List[Tuple[Move, str, bool]] = []
    current = bb
    remaining = depth_limit

    while remaining > 0:
        w = check_game_winner(current)
        if w != WinStatus.NO_WIN:
            break

        d, best = _minimax(current, winning_player, remaining, memo, deadline)
        if d is None or best is None:
            break

        nbb = apply_move(current, best)
        qfen_after = State(nbb).to_qfen()
        w = check_game_winner(nbb)
        is_final = w != WinStatus.NO_WIN
        steps.append((best, qfen_after, is_final))

        if is_final:
            break
        current = nbb
        remaining -= 1

    if steps and steps[-1][2]:
        return steps
    return None


# ---------------------------------------------------------------------------
# Puzzle box rendering
# ---------------------------------------------------------------------------


def _box_line(text: str) -> str:
    return f"\u2551{text:<{BOX_WIDTH}}\u2551"


def render_puzzle_box(
    num: int,
    puzzle: Puzzle,
    solution: List[Tuple[Move, str, bool]],
) -> str:
    winning_moves = sum(1 for m, _, _ in solution if m.player == puzzle.player_to_move)
    lines: List[str] = []

    # header
    lines.append(f"\u2554{'═' * BOX_WIDTH}\u2557")
    lines.append(
        _box_line(
            f"  PUZZLE #{num}  \u2014  P{puzzle.player_to_move} to win in {winning_moves}"
        )
    )
    lines.append(f"\u2560{'═' * BOX_WIDTH}\u2563")

    # starting board
    lines.append(_box_line(f"  QFEN: {puzzle.qfen}"))
    lines.append(_box_line(""))
    for bl in render_board_lines(puzzle.qfen, indent="  "):
        lines.append(_box_line(bl))

    # solution
    lines.append(f"\u2560{'═' * BOX_WIDTH}\u2563")
    lines.append(_box_line("  SOLUTION:"))
    lines.append(_box_line(""))

    for i, (move, qfen_after, is_final) in enumerate(solution, 1):
        desc = format_move(move, is_final)
        lines.append(_box_line(f"  Move {i}: {desc}"))
        for bl in render_board_lines(qfen_after, indent="    "):
            lines.append(_box_line(bl))
        lines.append(_box_line(""))

    lines.append(f"\u255a{'═' * BOX_WIDTH}\u255d")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Puzzle generation pipeline
# ---------------------------------------------------------------------------


SAMPLES_PER_DIFFICULTY = 8
MAX_VERIFIED = 60

GENERATOR_CONFIGS = [
    {
        "seed": 42,
        "max_depth": 7,
        "dropout_depth": 2,
        "dropout_rate": 0.70,
        "min_puzzle_depth": 1,
        "max_puzzles": 100,
        "max_positions": 200_000,
        "max_time_seconds": 12.0,
    },
    {
        "seed": 123,
        "max_depth": 7,
        "dropout_depth": 2,
        "dropout_rate": 0.85,
        "min_puzzle_depth": 2,
        "max_puzzles": 100,
        "max_positions": 200_000,
        "max_time_seconds": 12.0,
    },
    {
        "seed": 456,
        "max_depth": 6,
        "dropout_depth": 2,
        "dropout_rate": 0.60,
        "min_puzzle_depth": 1,
        "max_puzzles": 100,
        "max_positions": 200_000,
        "max_time_seconds": 12.0,
    },
]


def _sample_diverse(puzzles: List[Puzzle], per_difficulty: int) -> List[Puzzle]:
    """Take up to *per_difficulty* puzzles from each moves_to_win bucket."""
    by_diff: Dict[int, List[Puzzle]] = {}
    for p in puzzles:
        by_diff.setdefault(p.moves_to_win, []).append(p)

    sampled: List[Puzzle] = []
    for diff in sorted(by_diff):
        sampled.extend(by_diff[diff][:per_difficulty])
    return sampled


def generate_raw_puzzles() -> List[Puzzle]:
    """Run EndgamePuzzleGenerator on each starting position with diverse sampling."""
    all_puzzles: List[Puzzle] = []
    seen: set = set()

    for (qfen, label), cfg in zip(STARTING_POSITIONS, GENERATOR_CONFIGS):
        print(f"\n{'─' * 60}")
        print(f"Generating from: {qfen} ({label})")
        print(f"{'─' * 60}")

        config = PuzzleConfig(**cfg)
        gen = EndgamePuzzleGenerator(config)
        gen.generate_puzzles(starting_qfen=qfen)

        raw = [p for p in gen.get_puzzles() if p.winning_moves]
        sampled = _sample_diverse(raw, SAMPLES_PER_DIFFICULTY)
        print(f"  Raw: {len(raw)} -> sampled {len(sampled)} (diverse)")

        for p in sampled:
            if p.qfen not in seen:
                seen.add(p.qfen)
                all_puzzles.append(p)

    return all_puzzles


def solve_puzzles(
    raw: List[Puzzle],
) -> List[Tuple[Puzzle, List[Tuple[Move, str, bool]]]]:
    """Verify each puzzle with minimax and compute the full solution line."""
    solved: List[Tuple[Puzzle, List[Tuple[Move, str, bool]]]] = []

    for i, puzzle in enumerate(raw):
        bb = State.from_qfen(puzzle.qfen).bb
        sol = compute_solution_line(bb, puzzle.player_to_move, depth_limit=8)
        if sol is not None:
            solved.append((puzzle, sol))
        if (i + 1) % 10 == 0 or i == len(raw) - 1:
            print(f"  [{i + 1}/{len(raw)}] verified={len(solved)}")
        if len(solved) >= MAX_VERIFIED:
            print(f"  Reached {MAX_VERIFIED} verified puzzles, stopping.")
            break

    return solved


def curate(
    solved: List[Tuple[Puzzle, List[Tuple[Move, str, bool]]]],
    target: int = 10,
) -> List[Tuple[Puzzle, List[Tuple[Move, str, bool]]]]:
    """Pick a diverse subset preferring different difficulty levels."""
    by_diff: Dict[int, List[Tuple[Puzzle, List[Tuple[Move, str, bool]]]]] = {}
    for puzzle, sol in solved:
        win_count = sum(1 for m, _, _ in sol if m.player == puzzle.player_to_move)
        by_diff.setdefault(win_count, []).append((puzzle, sol))

    result: List[Tuple[Puzzle, List[Tuple[Move, str, bool]]]] = []
    while len(result) < target:
        added = False
        for diff in sorted(by_diff):
            if by_diff[diff] and len(result) < target:
                result.append(by_diff[diff].pop(0))
                added = True
        if not added:
            break
    return result


def save_puzzles(
    puzzles: List[Tuple[Puzzle, List[Tuple[Move, str, bool]]]],
    filepath: str,
) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("QUANTIK TACTICAL PUZZLES\n")
        f.write("=" * 50 + "\n")
        f.write(f"Generated {len(puzzles)} curated puzzles\n\n")
        for i, (puzzle, sol) in enumerate(puzzles, 1):
            f.write(render_puzzle_box(i, puzzle, sol))
            f.write("\n\n")
    print(f"Puzzles saved to {filepath}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    w = BOX_WIDTH
    print(f"\u2554{'═' * w}\u2557")
    print(f"\u2551{'  QUANTIK TACTICAL PUZZLE GENERATOR':<{w}}\u2551")
    print(f"\u2551{'  with Full Visual Solutions':<{w}}\u2551")
    print(f"\u255a{'═' * w}\u255d")
    print()

    # Step 1: generate raw puzzles
    print("STEP 1: Generating candidate puzzles ...")
    raw = generate_raw_puzzles()
    print(f"\nFound {len(raw)} unique candidate puzzles")

    # Step 2: verify with minimax and compute solutions
    print(
        f"\nSTEP 2: Verifying with minimax solver (timeout {SOLVE_TIMEOUT_SECS}s/puzzle) ..."
    )
    solved = solve_puzzles(raw)
    print(f"Verified {len(solved)} puzzles with forced wins")

    if not solved:
        print("No puzzles could be verified. Try adjusting generation parameters.")
        return

    # Step 3: curate diverse set
    curated = curate(solved, target=10)
    print(f"\nSTEP 3: Curated {len(curated)} diverse puzzles")
    print(f"\n{'=' * 60}\n")

    # Display
    for i, (puzzle, sol) in enumerate(curated, 1):
        print(render_puzzle_box(i, puzzle, sol))
        print()

    # Save
    project_root = Path(__file__).resolve().parent.parent
    output_path = project_root / "data" / "puzzles.txt"
    save_puzzles(curated, str(output_path))


if __name__ == "__main__":
    main()
