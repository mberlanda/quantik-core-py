"""Across-seed stability of benchmark move selections.

Aggregates the same raw rows produced by benchmarks.agreement.run_agreement;
engines are not re-run here.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

from benchmarks.metrics import mean_std


def aggregate_stability(rows: List[dict]) -> List[dict]:
    """Aggregate move consistency and per-seed agreement by engine config."""
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for row in rows:
        groups.setdefault((row["engine"], row["config_label"]), []).append(row)

    aggregates: List[dict] = []
    for (engine, config_label), group in sorted(groups.items()):
        seeds = sorted({row["seed"] for row in group})

        moves_by_position: Dict[str, List[str]] = {}
        for row in group:
            moves_by_position.setdefault(row["position_id"], []).append(row["move"])
        consistency_values = [
            Counter(moves).most_common(1)[0][1] / len(moves)
            for moves in moves_by_position.values()
        ]
        move_consistency, _ = mean_std(consistency_values)

        per_seed_agreement: List[float] = []
        for seed in seeds:
            solved = [
                row for row in group if row["seed"] == seed and row["hit"] is not None
            ]
            if solved:
                per_seed_agreement.append(
                    sum(1 for row in solved if row["hit"]) / len(solved)
                )
        agreement_mean, agreement_std = mean_std(per_seed_agreement)

        aggregates.append(
            {
                "engine": engine,
                "config_label": config_label,
                "seeds": len(seeds),
                "move_consistency": move_consistency,
                "agreement_mean": agreement_mean,
                "agreement_std": agreement_std,
            }
        )

    return aggregates
