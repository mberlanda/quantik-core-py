"""Exact game-theoretic references for benchmark positions."""

from __future__ import annotations

import time
from typing import Iterable, Optional, Tuple

import quantik_core
from quantik_core import State, apply_move
from quantik_core.game_utils import count_total_pieces, has_winning_line
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import Move, generate_legal_moves_list

_IMMEDIATE_WIN = float("inf")


def move_key(move: Move) -> str:
    """Return a stable string identifier for a move."""
    return f"{move.player}:{move.shape}:{move.position}"


def parse_move_key(key: str) -> Tuple[int, int, int]:
    """Parse a move key into ``(player, shape, position)``."""
    player, shape, position = key.split(":")
    return int(player), int(shape), int(position)


def _remaining_plies(bb) -> int:
    return 16 - sum(count_total_pieces(bb))


def _score_child(
    child_bb, remaining_budget: float
) -> Optional[tuple[float, int, list[str]]]:
    engine = MinimaxEngine(MinimaxConfig(max_depth=16, time_limit_s=remaining_budget))
    result = engine.search(State(child_bb))
    if result.depth_reached < _remaining_plies(child_bb):
        return None
    return -result.score, result.nodes, [move_key(move) for move in result.pv]


def solve_position(bb, budget_s: float) -> Optional[dict]:
    """Return an exact reference for ``bb``, or ``None`` on budget cutoff."""
    started_at = time.monotonic()
    deadline = started_at + budget_s
    legal_moves = generate_legal_moves_list(bb)
    if not legal_moves:
        return None

    scored: dict[str, float] = {}
    pvs: dict[str, list[str]] = {}
    nodes = 0

    for move in legal_moves:
        key = move_key(move)
        child_bb = apply_move(bb, move)

        if has_winning_line(child_bb) or not generate_legal_moves_list(child_bb):
            scored[key] = _IMMEDIATE_WIN
            pvs[key] = [key]
            continue

        remaining_budget = deadline - time.monotonic()
        if remaining_budget <= 0:
            return None

        child_score = _score_child(child_bb, remaining_budget)
        if child_score is None:
            return None

        score, child_nodes, child_pv = child_score
        scored[key] = score
        pvs[key] = [key, *child_pv]
        nodes += child_nodes

    best_score = max(scored.values())
    optimal_moves = sorted(key for key, score in scored.items() if score == best_score)

    return {
        "solved": True,
        "no_cutoff": True,
        "value": 1 if best_score > 0 else -1,
        "optimal_moves": optimal_moves,
        "pv": pvs[optimal_moves[0]],
        "nodes": nodes,
        "solve_time_s": round(time.monotonic() - started_at, 6),
        "solver": (
            "MinimaxEngine(max_depth=16, time_limit_s=remaining_budget) "
            f"quantik-core {quantik_core.__version__}"
        ),
    }


def augment_with_references(
    payload: dict,
    budget_s: float,
    skip_phases: Iterable[str] = ("opening",),
) -> dict:
    """Fill reference fields in-place and return ``payload``."""
    skipped = set(skip_phases)

    for position in payload["positions"]:
        if position["phase"] in skipped:
            position["reference"] = None
            continue

        bb = State.from_qfen(position["qfen"]).bb
        position["reference"] = solve_position(bb, budget_s)

    return payload
