#!/usr/bin/env python3
"""Cross-engine benchmark CLI (GH issue #24).

Compares MinimaxEngine, MCTSEngine, BeamSearchEngine, and a random-mover
baseline on a shared, versioned, checksummed position dataset.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from pathlib import Path

# `benchmarks/` lives at the repo root. Running this file directly puts only
# `examples/` on sys.path[0], so add the repo root explicitly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks import dataset as ds  # noqa: E402
from benchmarks import reference  # noqa: E402
from benchmarks.adapters import (  # noqa: E402
    BeamAdapter,
    MCTSAdapter,
    MinimaxAdapter,
    RandomAdapter,
    fixed_time_adapters,
)
from benchmarks.agreement import (  # noqa: E402
    aggregate_agreement,
    aggregate_cost,
    run_agreement,
)
from benchmarks.bundle import make_bundle, save_bundle  # noqa: E402
from benchmarks.correctness import run_preflight  # noqa: E402
from benchmarks.head_to_head import (  # noqa: E402
    aggregate_head_to_head,
    run_head_to_head,
)
from benchmarks.report import render_markdown  # noqa: E402
from benchmarks.stability import aggregate_stability  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="cross_engine_benchmark",
        description="Reproducible cross-engine benchmark (docs/BENCHMARKS.md)",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    dataset = subcommands.add_parser(
        "dataset", help="generate the shared position artifact"
    )
    dataset.add_argument("--opening", type=int, default=8)
    dataset.add_argument("--early-mid", type=int, default=8)
    dataset.add_argument("--late-mid", type=int, default=12)
    dataset.add_argument("--endgame", type=int, default=8)
    dataset.add_argument("--seed", type=int, default=20260711)
    dataset.add_argument(
        "--solve-budget",
        type=float,
        default=30.0,
        help="max wall-clock seconds to exactly solve each position",
    )
    dataset.add_argument("--output", default="benchmarks/positions-v1.json")

    run = subcommands.add_parser("run", help="run a benchmark family")
    run.add_argument("--dataset", required=True)
    run.add_argument("--family", choices=("fixed", "native"), default="fixed")
    run.add_argument(
        "--time-limit",
        type=float,
        default=1.0,
        help="fixed family: wall-clock budget per move, seconds",
    )
    run.add_argument("--seeds", type=int, default=10)
    run.add_argument("--seed-base", type=int, default=0)
    run.add_argument("--minimax-depth", type=int, default=6)
    run.add_argument("--minimax-time", type=float, default=0.2)
    run.add_argument("--mcts-iterations", type=int, default=1500)
    run.add_argument("--mcts-depth", type=int, default=16)
    run.add_argument("--mcts-exploration", type=float, default=1.414)
    run.add_argument("--beam-width", type=int, default=64)
    run.add_argument("--beam-depth", type=int, default=16)
    run.add_argument("--h2h-positions", type=int, default=8)
    run.add_argument("--h2h-seeds", type=int, default=1)
    run.add_argument("--skip-h2h", action="store_true")
    run.add_argument("--track-memory", action="store_true")
    run.add_argument("--output", required=True)

    report = subcommands.add_parser("report", help="render a bundle to Markdown")
    report.add_argument("--input", required=True)
    report.add_argument("--output", default=None, help="default: <input>.md")

    return parser


def _build_adapters(args) -> list:
    if args.family == "fixed":
        adapters = fixed_time_adapters(args.time_limit, beam_width=args.beam_width)
    else:
        adapters = [
            MinimaxAdapter(
                max_depth=args.minimax_depth,
                time_limit_s=args.minimax_time,
            ),
            MCTSAdapter(
                max_iterations=args.mcts_iterations,
                max_depth=args.mcts_depth,
                exploration_weight=args.mcts_exploration,
            ),
            BeamAdapter(beam_width=args.beam_width, max_depth=args.beam_depth),
        ]
    return [*adapters, RandomAdapter()]


def _h2h_positions(payload: dict, count: int) -> list:
    """Pick positions round-robin across phase buckets."""
    by_phase: dict[str, list[dict]] = {}
    for position in payload["positions"]:
        by_phase.setdefault(position["phase"], []).append(position)

    picked = []
    while len(picked) < count and any(by_phase.values()):
        for phase in sorted(by_phase):
            if by_phase[phase] and len(picked) < count:
                picked.append(by_phase[phase].pop(0))
    return picked


def cmd_dataset(args) -> int:
    requested = {
        "opening": args.opening,
        "early_mid": args.early_mid,
        "late_mid": args.late_mid,
        "endgame": args.endgame,
    }
    payload = ds.generate(requested, seed=args.seed)
    reference.augment_with_references(payload, budget_s=args.solve_budget)
    digest = ds.save(payload, args.output)

    solved = sum(1 for position in payload["positions"] if position["reference"])
    print(
        f"dataset: {len(payload['positions'])} positions "
        f"({solved} with exact references) -> {args.output}"
    )
    print(f"checksum: {digest}")
    for phase in ds.PHASES:
        positions = [p for p in payload["positions"] if p["phase"] == phase]
        phase_solved = sum(1 for p in positions if p["reference"])
        print(f"  {phase:9s}: {len(positions)} positions, {phase_solved} solved")
    return 0


def cmd_run(args) -> int:
    payload = ds.load(args.dataset)
    adapters = _build_adapters(args)
    failures = run_preflight(adapters, payload["positions"])
    if failures:
        print("PREFLIGHT FAILED - benchmark aborted:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    seeds = [args.seed_base + i for i in range(args.seeds)]
    rows = run_agreement(
        adapters,
        payload,
        seeds,
        track_memory=args.track_memory,
    )

    head_to_head = {"records": [], "aggregates": []}
    if not args.skip_h2h:
        positions = _h2h_positions(payload, args.h2h_positions)
        h2h_seeds = [args.seed_base + i for i in range(args.h2h_seeds)]
        for adapter_a, adapter_b in itertools.combinations(adapters, 2):
            records = run_head_to_head(adapter_a, adapter_b, positions, h2h_seeds)
            head_to_head["records"].extend(records)
            head_to_head["aggregates"].append(
                aggregate_head_to_head(records, adapter_a.name, adapter_b.name)
            )

    config = dict(vars(args))
    config["engine_seeds"] = seeds
    result = make_bundle(
        config=config,
        dataset_payload=payload,
        observations=rows,
        head_to_head=head_to_head,
        aggregates={
            "agreement": aggregate_agreement(rows),
            "cost": aggregate_cost(rows),
            "stability": aggregate_stability(rows),
        },
    )
    save_bundle(result, args.output)
    print(
        f"bundle: {len(rows)} observations, "
        f"{len(head_to_head['records'])} games -> {args.output}"
    )
    return 0


def cmd_report(args) -> int:
    result = json.loads(Path(args.input).read_text())
    output = args.output or str(Path(args.input).with_suffix(".md"))
    Path(output).write_text(render_markdown(result))
    print(f"report -> {output}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"dataset": cmd_dataset, "run": cmd_run, "report": cmd_report}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
