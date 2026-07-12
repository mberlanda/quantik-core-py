"""Run-size estimates for benchmark planning."""

from __future__ import annotations

import itertools
import json
from typing import Iterable


def estimate_volume(
    *,
    positions: int,
    seeds: int,
    h2h_positions: int,
    h2h_seeds: int,
    engines: Iterable[str],
    deterministic_engines: set[str],
) -> dict:
    """Estimate observation and head-to-head row counts for a benchmark run."""
    if positions < 0:
        raise ValueError("positions must be non-negative")
    if seeds < 1:
        raise ValueError("seeds must be at least 1")
    if h2h_positions < 0:
        raise ValueError("h2h_positions must be non-negative")
    if h2h_seeds < 1:
        raise ValueError("h2h_seeds must be at least 1")

    engine_names = list(engines)
    if len(engine_names) < 2:
        raise ValueError("at least two engines are required for h2h estimates")

    observation_by_engine = {
        engine: positions * (1 if engine in deterministic_engines else seeds)
        for engine in engine_names
    }
    effective_h2h_positions = min(positions, h2h_positions)
    pairs = list(itertools.combinations(engine_names, 2))
    games_per_pair = effective_h2h_positions * h2h_seeds * 2
    games_per_engine_pair_side = effective_h2h_positions * h2h_seeds

    by_engine = {}
    for engine in engine_names:
        opponent_count = len(engine_names) - 1
        by_engine[engine] = {
            "games": games_per_pair * opponent_count,
            "as_mover": games_per_engine_pair_side * opponent_count,
            "as_responder": games_per_engine_pair_side * opponent_count,
        }

    return {
        "inputs": {
            "positions": positions,
            "seeds": seeds,
            "engine_count": len(engine_names),
            "deterministic_engines": sorted(deterministic_engines),
            "stochastic_engines": [
                engine for engine in engine_names if engine not in deterministic_engines
            ],
        },
        "observations": {
            "total": sum(observation_by_engine.values()),
            "by_engine": observation_by_engine,
        },
        "h2h": {
            "requested_positions": h2h_positions,
            "effective_positions": effective_h2h_positions,
            "seeds": h2h_seeds,
            "pair_count": len(pairs),
            "games_per_pair": games_per_pair,
            "total_games": games_per_pair * len(pairs),
            "by_pair": {pair: games_per_pair for pair in pairs},
            "by_engine": by_engine,
        },
    }


def render_text(estimate: dict) -> str:
    """Render a human-readable benchmark volume estimate."""
    inputs = estimate["inputs"]
    observations = estimate["observations"]
    h2h = estimate["h2h"]
    lines = [
        "Benchmark volume estimate",
        f"positions: {inputs['positions']}",
        f"engine seeds: {inputs['seeds']}",
        f"engines: {inputs['engine_count']}",
        "deterministic engines: "
        + _render_engine_list(inputs["deterministic_engines"]),
        "stochastic engines: " + _render_engine_list(inputs["stochastic_engines"]),
        f"observations: {observations['total']}",
        f"h2h games: {h2h['total_games']}",
        "requested h2h positions: "
        f"{h2h['requested_positions']}; effective: {h2h['effective_positions']}",
        f"h2h seeds: {h2h['seeds']}",
        f"engine pairs: {h2h['pair_count']}",
        f"games per engine pair: {h2h['games_per_pair']}",
        "",
        "By engine:",
    ]
    for engine, observation_count in observations["by_engine"].items():
        engine_h2h = h2h["by_engine"][engine]
        lines.append(
            f"- {engine}: {observation_count} observations, "
            f"{engine_h2h['games']} h2h games "
            f"({engine_h2h['as_mover']} as mover, "
            f"{engine_h2h['as_responder']} as responder)"
        )

    lines.append("")
    lines.append("By engine pair:")
    for pair, games in h2h["by_pair"].items():
        lines.append(f"- {pair[0]} vs {pair[1]}: {games} games")
    return "\n".join(lines)


def render_json(estimate: dict) -> str:
    """Render an estimate as JSON, converting tuple pair keys to objects."""
    serializable = dict(estimate)
    h2h = dict(serializable["h2h"])
    h2h["by_pair"] = [
        {"engine_a": pair[0], "engine_b": pair[1], "games": games}
        for pair, games in h2h["by_pair"].items()
    ]
    serializable["h2h"] = h2h
    return json.dumps(serializable, indent=2, sort_keys=True)


def _render_engine_list(engines: list[str]) -> str:
    return ", ".join(engines) if engines else "-"
