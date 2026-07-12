"""Agreement and cost aggregation for benchmark move selections."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Sequence, Tuple

from quantik_core import State

from benchmarks.metrics import median, percentile, wilson_ci


def _agreement_tasks(adapters, payload: dict, seeds: Sequence[int], skip_keys):
    skipped = set(skip_keys or ())
    for position in payload["positions"]:
        for adapter in adapters:
            adapter_seeds = seeds if adapter.stochastic else [seeds[0]]
            for seed in adapter_seeds:
                key = (position["id"], adapter.name, adapter.config_label, seed)
                if key not in skipped:
                    yield adapter, position, seed


def _select_agreement_row(task, track_memory: bool = False) -> dict:
    adapter, position, seed = task
    bb = State.from_qfen(position["qfen"]).bb
    reference = position.get("reference")
    optimal_moves = set(reference["optimal_moves"]) if reference else None
    _, observation = adapter.select(
        bb,
        position["id"],
        seed=seed,
        track_memory=track_memory,
    )
    row = observation.to_dict()
    row["phase"] = position["phase"]
    row["hit"] = (
        observation.move in optimal_moves if optimal_moves is not None else None
    )
    return row


def _select_agreement_row_with_memory(task) -> dict:
    return _select_agreement_row(task, track_memory=True)


def iter_agreement(
    adapters,
    payload: dict,
    seeds: Sequence[int],
    track_memory: bool = False,
    skip_keys=None,
    workers: int = 1,
):
    """Yield one move-observation row per adapter, position, and seed run."""
    if not seeds:
        raise ValueError("seeds must be a non-empty ordered list")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    tasks = list(_agreement_tasks(adapters, payload, seeds, skip_keys))
    if not tasks:
        return
    if workers == 1:
        for task in tasks:
            yield _select_agreement_row(task, track_memory=track_memory)
        return

    worker_func = (
        _select_agreement_row_with_memory if track_memory else _select_agreement_row
    )
    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(worker_func, tasks)


def run_agreement(
    adapters,
    payload: dict,
    seeds: Sequence[int],
    track_memory: bool = False,
    workers: int = 1,
) -> List[dict]:
    """Return one move-observation row per adapter, position, and seed run."""
    return list(
        iter_agreement(
            adapters,
            payload,
            seeds,
            track_memory=track_memory,
            workers=workers,
        )
    )


def aggregate_agreement(rows: List[dict]) -> List[dict]:
    """Aggregate exact-reference agreement by engine, config label, and phase."""
    groups: Dict[Tuple[str, str, str], List[dict]] = {}
    for row in rows:
        if row["hit"] is None:
            continue
        key = (row["engine"], row["config_label"], row["phase"])
        groups.setdefault(key, []).append(row)

    aggregates: List[dict] = []
    for (engine, config_label, phase), group in sorted(groups.items()):
        n = len(group)
        hits = sum(1 for row in group if row["hit"])
        ci95_low, ci95_high = wilson_ci(hits, n)
        aggregates.append(
            {
                "engine": engine,
                "config_label": config_label,
                "phase": phase,
                "n": n,
                "hits": hits,
                "agreement": hits / n,
                "ci95_low": ci95_low,
                "ci95_high": ci95_high,
            }
        )

    return aggregates


def aggregate_cost(rows: List[dict]) -> List[dict]:
    """Aggregate measured selection cost by engine and config label."""
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for row in rows:
        key = (row["engine"], row["config_label"])
        groups.setdefault(key, []).append(row)

    aggregates: List[dict] = []
    for (engine, config_label), group in sorted(groups.items()):
        wall_times = [row["wall_time_s"] for row in group]
        nodes = [row["nodes"] for row in group if row["nodes"] is not None]
        peak_memory = [
            row["peak_memory_bytes"]
            for row in group
            if row["peak_memory_bytes"] is not None
        ]
        aggregates.append(
            {
                "engine": engine,
                "config_label": config_label,
                "n": len(group),
                "median_time_s": median(wall_times),
                "p95_time_s": percentile(wall_times, 95.0),
                "median_nodes": median(nodes) if nodes else None,
                "peak_memory_bytes": max(peak_memory) if peak_memory else None,
            }
        )

    return aggregates
