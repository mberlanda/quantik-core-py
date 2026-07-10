#!/usr/bin/env python3
"""
Classical alpha-beta minimax demo for Quantik.

Demonstrates:
1. Analyzing a position: best move, score, principal variation, node count.
2. The effect of the fitted vs. seeded evaluation weights on a shallow search.
3. Iterative-deepening trace (value/PV per depth).
4. A tiny tournament: minimax vs. a random mover and vs. MCTS.

Run: python examples/minimax_demo.py
"""

import random
import time
from pathlib import Path
from typing import Callable, Optional

import quantik_core.evaluation as _evaluation_module
from quantik_core import Move, State, apply_move
from quantik_core.evaluation import EvalConfig
from quantik_core.game_utils import check_game_winner, has_winning_line, WinStatus
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import generate_legal_moves_list

# Mirrors EvalConfig.load()'s own default-path resolution, so this demo can
# tell (and say honestly) whether "fitted" actually differs from "seeded" --
# EvalConfig.load() silently falls back to seeded weights when the file is
# absent, which would otherwise make the [2] comparison below misleading.
_WEIGHTS_PATH = (
    Path(_evaluation_module.__file__).resolve().parents[2] / "tuning" / "weights.json"
)


def format_move(move: Move) -> str:
    """Format a move, player-aware (uppercase P0, lowercase P1, per QFEN)."""
    shape_letter = chr(ord("A") + move.shape)
    if move.player == 1:
        shape_letter = shape_letter.lower()
    row, col = move.position // 4, move.position % 4
    return f"{shape_letter} at ({row}, {col}) [pos {move.position}]"


def print_board(state: State) -> None:
    """Print the board from its QFEN in a readable grid."""
    print("\n  0 1 2 3")
    for i, row in enumerate(state.to_qfen().split("/")):
        cells = " ".join(row)
        print(f"{i} {cells}")


def analyze_position(state: State, config: Optional[MinimaxConfig] = None) -> None:
    """Search a position and print the best move, score, PV and node count."""
    engine = MinimaxEngine(config or MinimaxConfig(max_depth=6, time_limit_s=1.0))
    result = engine.search(state)
    print_board(state)
    print(f"  best move : {format_move(result.best_move)}")
    print(f"  score     : {result.score:.1f}")
    print(f"  depth     : {result.depth_reached}   nodes: {result.nodes}")
    pv = " -> ".join(format_move(m) for m in result.pv)
    print(f"  pv        : {pv}")


def iterative_deepening_trace(state: State, max_depth: int = 6) -> None:
    """Print the value and PV found at each successive depth."""
    print("\nIterative-deepening trace:")
    for depth in range(1, max_depth + 1):
        r = MinimaxEngine(MinimaxConfig(max_depth=depth)).search(state)
        pv = " ".join(format_move(m) for m in r.pv)
        print(f"  depth {depth}: score={r.score:8.1f} nodes={r.nodes:6d}  pv: {pv}")


# ----- players (State -> Move) ---------------------------------------------


def random_player(seed: Optional[int] = None) -> Callable[[State], Move]:
    rng = random.Random(seed)
    return lambda s: rng.choice(generate_legal_moves_list(s.bb))


def minimax_player(**config_kwargs) -> Callable[[State], Move]:
    config = MinimaxConfig(**config_kwargs)
    return lambda s: MinimaxEngine(config).search(s).best_move


def mcts_player(**config_kwargs) -> Callable[[State], Move]:
    config = MCTSConfig(**config_kwargs)
    return lambda s: MCTSEngine(config).search(s)[0]


def play_game(
    player0: Callable[[State], Move], player1: Callable[[State], Move]
) -> WinStatus:
    """Play a full game between two selectors; return the winner."""
    bb = State.empty().bb
    players = (player0, player1)
    turn = 0
    while True:
        if has_winning_line(bb):
            return check_game_winner(bb)
        moves = generate_legal_moves_list(bb)
        if not moves:
            # Side to move cannot move: it loses.
            return WinStatus.PLAYER_1_WINS if turn == 0 else WinStatus.PLAYER_0_WINS
        move = players[turn](State(bb))
        bb = apply_move(bb, move)
        turn ^= 1


def _score_series(label: str, results: list, minimax_is_p0: bool) -> None:
    mm_win = WinStatus.PLAYER_0_WINS if minimax_is_p0 else WinStatus.PLAYER_1_WINS
    wins = sum(1 for r in results if r == mm_win)
    print(f"  {label}: minimax won {wins}/{len(results)}")


def mini_tournament(games: int = 6) -> None:
    print(f"\nMini-tournament ({games} games per matchup):")
    mm = dict(max_depth=6, time_limit_s=0.15, eval_config=EvalConfig.load())

    # vs random, minimax as P0 then P1
    res = [play_game(minimax_player(**mm), random_player(seed=g)) for g in range(games)]
    _score_series("vs random (minimax P0)", res, minimax_is_p0=True)
    res = [play_game(random_player(seed=g), minimax_player(**mm)) for g in range(games)]
    _score_series("vs random (minimax P1)", res, minimax_is_p0=False)

    # vs MCTS
    mcts = dict(max_iterations=1500, random_seed=0)
    res = [play_game(minimax_player(**mm), mcts_player(**mcts)) for _ in range(games)]
    _score_series("vs MCTS   (minimax P0)", res, minimax_is_p0=True)


def main() -> None:
    print("=" * 60)
    print("Quantik alpha-beta minimax demo")
    print("=" * 60)

    # A tactical position: side to move (P0) has a live threat to complete.
    tactical = State.from_qfen("AbC./..../..../....")
    print("\n[1] Analyze a tactical position (mate available):")
    analyze_position(tactical, MinimaxConfig(max_depth=2))

    # Seeded vs fitted weights on a quiet mid-game position.
    quiet = State.from_qfen(".D.a/..../..d./.BBd")
    print("\n[2] Seeded vs fitted evaluation (shallow search):")
    if not _WEIGHTS_PATH.exists():
        print(
            f"  note: {_WEIGHTS_PATH} not found -- 'fitted' falls back to seeded "
            "weights (run `python -m tuning.fit_weights` to generate it), so "
            "both rows below will be identical."
        )
    for label, cfg in (("seeded", EvalConfig()), ("fitted", EvalConfig.load())):
        r = MinimaxEngine(MinimaxConfig(max_depth=2, eval_config=cfg)).search(quiet)
        print(f"  {label}: best {format_move(r.best_move)}  score={r.score:.2f}")

    print("\n[3] Iterative deepening on the quiet position:")
    iterative_deepening_trace(quiet, max_depth=5)

    start = time.time()
    mini_tournament(games=6)
    print(f"\n(tournament ran in {time.time() - start:.1f}s)")


if __name__ == "__main__":
    main()
