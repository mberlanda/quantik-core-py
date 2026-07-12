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
import time
from collections import Counter
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
    iter_agreement,
    run_agreement,
)
from benchmarks.bundle import (  # noqa: E402
    collect_environment,
    make_bundle,
    save_bundle,
)
from benchmarks.checkpoint import (  # noqa: E402
    H2H_RECORDS,
    MANIFEST,
    OBSERVATIONS,
    append_jsonl,
    bundle_from_checkpoint,
    h2h_key,
    key_set,
    load_jsonl,
    load_manifest,
    observation_key,
    validate_resume_manifest,
    update_manifest_counts,
    write_manifest,
)
from benchmarks.correctness import run_preflight  # noqa: E402
from benchmarks.head_to_head import (  # noqa: E402
    aggregate_head_to_head,
    iter_head_to_head,
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
    run.add_argument("--checkpoint-dir", default=None)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--checkpoint-every", type=int, default=1)
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


def _dataset_summary(payload: dict) -> dict:
    positions = payload["positions"]
    phases = Counter(position["phase"] for position in positions)
    return {
        "checksum": payload.get("checksum"),
        "generator": payload["generator"],
        "seed": payload["seed"],
        "schema_version": payload["schema_version"],
        "positions": len(positions),
        "phases": dict(phases),
    }


def _checkpoint_manifest(args, payload: dict, seeds: list[int]) -> dict:
    config = dict(vars(args))
    config["engine_seeds"] = seeds
    return {
        "status": "preflight",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "environment": collect_environment(),
        "config": config,
        "dataset": _dataset_summary(payload),
        "counts": {"observations": 0, "h2h_records": 0},
    }


def _checkpoint_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "manifest": root / MANIFEST,
        "observations": root / OBSERVATIONS,
        "h2h": root / H2H_RECORDS,
    }


def _expected_h2h_records(adapters, positions: list[dict], seeds: list[int]) -> int:
    pair_count = len(list(itertools.combinations(adapters, 2)))
    return pair_count * len(positions) * len(seeds) * 2


def _print_progress(message: str) -> None:
    print(message, flush=True)


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
    seeds = [args.seed_base + i for i in range(args.seeds)]
    run_config = dict(vars(args))
    run_config["engine_seeds"] = seeds
    adapters = _build_adapters(args)
    h2h_positions = _h2h_positions(payload, args.h2h_positions)
    h2h_seeds = [args.seed_base + i for i in range(args.h2h_seeds)]

    checkpoint_root = Path(args.checkpoint_dir) if args.checkpoint_dir else None
    rows: list[dict]
    head_to_head: dict
    paths = _checkpoint_paths(checkpoint_root) if checkpoint_root is not None else None

    if checkpoint_root is not None and args.resume:
        manifest = load_manifest(paths["manifest"])
        if not manifest:
            print(
                "RESUME FAILED - checkpoint manifest not found: " f"{paths['manifest']}"
            )
            return 1
        existing_rows = load_jsonl(paths["observations"])
        existing_records = load_jsonl(paths["h2h"])
        expected_h2h_records = _expected_h2h_records(adapters, h2h_positions, h2h_seeds)
        if args.skip_h2h and len(existing_records) != expected_h2h_records:
            print(
                "RESUME FAILED - checkpoint h2h records incomplete: "
                f"expected {expected_h2h_records}, found {len(existing_records)}"
            )
            return 1
        try:
            validate_resume_manifest(
                manifest,
                dataset_checksum=payload.get("checksum"),
                config=run_config,
                allow_skip_h2h_mismatch=args.skip_h2h
                and len(existing_records) == expected_h2h_records,
            )
        except ValueError as exc:
            print(f"RESUME FAILED - {exc}")
            return 1

    if checkpoint_root is not None and not args.resume:
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        for path in (paths["observations"], paths["h2h"]):
            path.write_text("", encoding="utf-8")
        write_manifest(paths["manifest"], _checkpoint_manifest(args, payload, seeds))

    _print_progress(
        "preflight: checking "
        f"{len(adapters)} adapters across {min(3, len(payload['positions']))} "
        "sample positions"
    )
    failures = run_preflight(adapters, payload["positions"])
    if failures:
        if paths is not None and (paths["manifest"]).exists():
            update_manifest_counts(
                paths["manifest"],
                observations=len(load_jsonl(paths["observations"])),
                h2h_records=len(load_jsonl(paths["h2h"])),
                status="preflight_failed",
            )
        print("PREFLIGHT FAILED - benchmark aborted:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    _print_progress("preflight: passed")

    if checkpoint_root is None:
        _print_progress(
            f"agreement: running {len(payload['positions'])} positions "
            f"with {len(seeds)} seed(s)"
        )
        rows = run_agreement(
            adapters,
            payload,
            seeds,
            track_memory=args.track_memory,
        )
        head_to_head = {"records": [], "aggregates": []}
        if not args.skip_h2h:
            _print_progress(
                f"h2h: running {len(h2h_positions)} positions with "
                f"{len(h2h_seeds)} seed(s)"
            )
            for adapter_a, adapter_b in itertools.combinations(adapters, 2):
                records = run_head_to_head(
                    adapter_a, adapter_b, h2h_positions, h2h_seeds
                )
                head_to_head["records"].extend(records)
                head_to_head["aggregates"].append(
                    aggregate_head_to_head(records, adapter_a.name, adapter_b.name)
                )
        result = make_bundle(
            config=run_config,
            dataset_payload=payload,
            observations=rows,
            head_to_head=head_to_head,
            aggregates={
                "agreement": aggregate_agreement(rows),
                "cost": aggregate_cost(rows),
                "stability": aggregate_stability(rows),
            },
        )
    else:
        existing_rows = load_jsonl(paths["observations"])
        if args.skip_h2h and not args.resume:
            paths["h2h"].write_text("", encoding="utf-8")
            existing_records = []
        else:
            existing_records = load_jsonl(paths["h2h"])
        rows = list(existing_rows)

        observation_skips = key_set(existing_rows, observation_key)
        h2h_skips = key_set(existing_records, h2h_key)

        update_manifest_counts(
            paths["manifest"],
            observations=len(existing_rows),
            h2h_records=len(existing_records),
            status="running",
        )

        completed_observations = len(existing_rows)
        total_observations = sum(
            len(seeds) if adapter.stochastic else 1 for adapter in adapters
        ) * len(payload["positions"])
        _print_progress(
            f"agreement: {completed_observations}/{total_observations} "
            f"observations complete; checkpoint {paths['observations']}"
        )
        for row in iter_agreement(
            adapters,
            payload,
            seeds,
            track_memory=args.track_memory,
            skip_keys=observation_skips,
        ):
            append_jsonl(paths["observations"], row)
            rows.append(row)
            completed_observations += 1
            if (
                args.checkpoint_every > 0
                and completed_observations % args.checkpoint_every == 0
            ):
                update_manifest_counts(
                    paths["manifest"],
                    observations=completed_observations,
                    h2h_records=len(existing_records),
                    status="running",
                )
                _print_progress(
                    f"agreement: {completed_observations}/{total_observations} "
                    "observations checkpointed"
                )

        completed_h2h = len(existing_records)
        if not args.skip_h2h:
            total_h2h = _expected_h2h_records(adapters, h2h_positions, h2h_seeds)
            _print_progress(
                f"h2h: {completed_h2h}/{total_h2h} games complete; "
                f"checkpoint {paths['h2h']}"
            )
            for adapter_a, adapter_b in itertools.combinations(adapters, 2):
                for record in iter_head_to_head(
                    adapter_a,
                    adapter_b,
                    h2h_positions,
                    h2h_seeds,
                    skip_keys=h2h_skips,
                ):
                    append_jsonl(paths["h2h"], record)
                    completed_h2h += 1
                    if (
                        args.checkpoint_every > 0
                        and completed_h2h % args.checkpoint_every == 0
                    ):
                        update_manifest_counts(
                            paths["manifest"],
                            observations=completed_observations,
                            h2h_records=completed_h2h,
                            status="running",
                        )
                        _print_progress(
                            f"h2h: {completed_h2h}/{total_h2h} games checkpointed"
                        )

        update_manifest_counts(
            paths["manifest"],
            observations=completed_observations,
            h2h_records=completed_h2h,
            status="complete",
        )
        result = bundle_from_checkpoint(paths["root"])

    save_bundle(result, args.output)
    print(
        f"bundle: {len(result['observations'])} observations, "
        f"{len(result['head_to_head']['records'])} games -> {args.output}"
    )
    return 0


def cmd_report(args) -> int:
    input_path = Path(args.input)
    result = (
        bundle_from_checkpoint(input_path)
        if input_path.is_dir()
        else json.loads(input_path.read_text())
    )
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
