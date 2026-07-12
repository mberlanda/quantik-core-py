"""Paired, side-balanced head-to-head games from shared positions.

For every sampled position and seed, two games are played: engine A as
the side already to move, then engine B as the side to move. Results are
attributed to the actual engine/color mapping because sampled positions
can have either color to move.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Sequence, Tuple

from quantik_core import State, apply_move
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
    has_winning_line,
)
from quantik_core.move import generate_legal_moves_list

from benchmarks.metrics import wilson_ci


def play_game(mover, responder, bb, seed: int) -> Tuple[str, int]:
    """Play from bb; mover is the side already to move."""
    p0, p1 = count_total_pieces(bb)
    turn = get_current_player_from_counts(p0, p1)
    engines = {turn: mover, 1 - turn: responder}
    plies = 0

    while True:
        if has_winning_line(bb) or not generate_legal_moves_list(bb):
            return engines[1 - turn].name, plies

        move, _ = engines[turn].select(bb, position_id="h2h", seed=seed)
        bb = apply_move(bb, move)
        turn ^= 1
        plies += 1


def _h2h_tasks(adapter_a, adapter_b, positions: Sequence[dict], seeds, skip_keys):
    skipped = set(skip_keys or ())
    for position in positions:
        for seed in seeds:
            for mover, responder in ((adapter_a, adapter_b), (adapter_b, adapter_a)):
                key = (position["id"], mover.name, responder.name, seed)
                if key not in skipped:
                    yield mover, responder, position, seed


def _play_h2h_record(task) -> dict:
    mover, responder, position, seed = task
    bb = State.from_qfen(position["qfen"]).bb
    winner, plies = play_game(mover, responder, bb, seed)
    return {
        "position_id": position["id"],
        "phase": position["phase"],
        "mover": mover.name,
        "responder": responder.name,
        "winner": winner,
        "plies": plies,
        "seed": seed,
    }


def iter_head_to_head(
    adapter_a,
    adapter_b,
    positions: Sequence[dict],
    seeds: Sequence[int],
    skip_keys=None,
    workers: int = 1,
):
    """Play both engine orientations per position and seed."""
    if workers < 1:
        raise ValueError("workers must be at least 1")

    tasks = list(_h2h_tasks(adapter_a, adapter_b, positions, seeds, skip_keys))
    if not tasks:
        return
    if workers == 1:
        for task in tasks:
            yield _play_h2h_record(task)
        return

    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(_play_h2h_record, tasks)


def run_head_to_head(
    adapter_a,
    adapter_b,
    positions: Sequence[dict],
    seeds: Sequence[int],
    workers: int = 1,
) -> List[dict]:
    """Play both engine orientations per position and seed."""
    return list(
        iter_head_to_head(adapter_a, adapter_b, positions, seeds, workers=workers)
    )


def aggregate_head_to_head(records: List[dict], name_a: str, name_b: str) -> dict:
    """Aggregate totals, as-mover splits, and per-phase splits."""

    def wins(rows: List[dict], name: str) -> int:
        return sum(1 for row in rows if row["winner"] == name)

    by_phase: Dict[str, List[dict]] = {}
    for record in records:
        by_phase.setdefault(record["phase"], []).append(record)

    games = len(records)
    a_wins = wins(records, name_a)
    ci_low, ci_high = wilson_ci(a_wins, games)
    return {
        "engine_a": name_a,
        "engine_b": name_b,
        "games": games,
        "paired_positions": len(
            {(record["position_id"], record["seed"]) for record in records}
        ),
        "a_wins": a_wins,
        "b_wins": wins(records, name_b),
        "draws": 0,
        "a_win_rate": a_wins / games if games else 0.0,
        "a_win_rate_ci95": [ci_low, ci_high],
        "a_wins_as_mover": wins(
            [record for record in records if record["mover"] == name_a], name_a
        ),
        "b_wins_as_mover": wins(
            [record for record in records if record["mover"] == name_b], name_b
        ),
        "by_phase": {
            phase: {
                "games": len(rows),
                "a_wins": wins(rows, name_a),
                "b_wins": wins(rows, name_b),
            }
            for phase, rows in sorted(by_phase.items())
        },
    }
