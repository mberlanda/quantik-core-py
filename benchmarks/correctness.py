"""Correctness preflight for benchmark inputs and adapters."""

from __future__ import annotations

from typing import List, Sequence

from quantik_core import State
from quantik_core.game_utils import has_winning_line
from quantik_core.move import generate_legal_moves_list

from benchmarks.reference import parse_move_key


def _probe_adapter(adapter, position: dict, seed: int) -> List[str]:
    failures: List[str] = []
    bb = State.from_qfen(position["qfen"]).bb
    try:
        _, first = adapter.select(bb, position["id"], seed=seed)
    except Exception as exc:  # benchmark preflight reports all failures
        return [f"{adapter.name} on {position['id']}: {exc}"]

    mover, _, _ = parse_move_key(first.move)
    if mover != position["side_to_move"]:
        failures.append(
            f"{adapter.name} on {position['id']}: moved for player {mover}, "
            f"but side to move is {position['side_to_move']}"
        )

    try:
        _, second = adapter.select(bb, position["id"], seed=seed)
    except Exception as exc:  # benchmark preflight reports all failures
        failures.append(
            f"{adapter.name} on {position['id']} reproducibility check: {exc}"
        )
        return failures

    if second.move != first.move:
        failures.append(
            f"{adapter.name} on {position['id']}: non-deterministic under "
            f"identical settings and seed ({first.move} vs {second.move})"
        )
    return failures


def run_preflight(
    adapters, positions: Sequence[dict], sample: int = 3, seed: int = 0
) -> List[str]:
    """Return human-readable invariant failures; an empty list means all good."""
    failures: List[str] = []

    for position in positions:
        bb = State.from_qfen(position["qfen"]).bb
        if has_winning_line(bb) or not generate_legal_moves_list(bb):
            failures.append(f"dataset: position {position['id']} is terminal")

    for adapter in adapters:
        for position in list(positions)[:sample]:
            failures.extend(_probe_adapter(adapter, position, seed))

    return failures
