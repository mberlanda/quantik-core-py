# Benchmark Part 5: Result Bundles, Markdown Report, CLI, Docs, Artifact — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tie parts 1–4 into a reproducible product: self-describing JSON
result bundles (environment + config + raw observations + aggregates),
auto-generated Markdown tables, a CLI-configurable entry point at
`examples/cross_engine_benchmark.py` (issue #24's required knobs), docs,
and the committed versioned dataset artifact `benchmarks/positions-v1.json`.

**Architecture:** `benchmarks/bundle.py` collects environment metadata and
assembles the bundle; `benchmarks/report.py` renders Markdown FROM the
bundle (tables are never maintained by hand). The CLI has three
subcommands — `dataset` (generate artifact once), `run` (preflight →
agreement → head-to-head → aggregate → bundle), `report` (bundle → md).
The old module-level helpers in `examples/cross_engine_benchmark.py` are
replaced; their regression tests were already re-homed by parts 2 and 4.

**Tech Stack:** Python 3 stdlib (`argparse`, `json`, `platform`,
`subprocess`), parts 1–4.

## Global Constraints

- Prerequisites: parts 1–4 merged.
- Final gate: `./dev-check.sh` fully green (this part touches
  `tests/test_examples_demos.py`, which IS in the coverage-scoped suite run).
- The recommended reproduction command (from the consistency brief) must
  work verbatim:
  ```bash
  python examples/cross_engine_benchmark.py run \
    --dataset benchmarks/positions-v1.json \
    --time-limit 1.0 --seeds 30 \
    --output benchmarks/results/$(git rev-parse --short HEAD).json
  ```
- Issue #24 required CLI minimum: MCTS `max_iterations`/`max_depth`/
  `exploration_weight`; minimax `max_depth`/`time_limit_s`; beam
  `beam_width`; plus seeds/counts/paths.
- Env setup + commit trailer: see "Shared conventions" in
  `2026-07-11-cross-engine-benchmark-0-INDEX.md`.

---

### Task 1: `benchmarks/bundle.py` + `benchmarks/report.py`

**Files:**
- Create: `benchmarks/bundle.py`
- Create: `benchmarks/report.py`
- Test: `tests/test_benchmark_bundle.py`

**Interfaces:**
- Consumes: aggregation outputs from part 4 (list-of-dicts shapes), the
  dataset payload from part 2.
- Produces (used by the CLI):
  - `bundle.SCHEMA_VERSION = 1`
  - `bundle.collect_environment() -> dict` — keys `quantik_core_version`,
    `git_sha`, `python_version`, `platform`, `processor`, `cpu_count`,
    `total_memory_bytes` (None where not available).
  - `bundle.make_bundle(*, config, dataset_payload, observations,
    head_to_head, aggregates) -> dict`
  - `bundle.save_bundle(bundle_dict, path) -> None` (creates parent dirs).
  - `report.render_markdown(bundle_dict) -> str` — the four required
    tables (agreement, cost, head-to-head, stability) + phase breakdowns
    + interpretation guardrails.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_bundle.py`:

```python
"""Tests for benchmarks.bundle and benchmarks.report."""

import json

from benchmarks import bundle, report


def _synthetic_bundle():
    dataset_payload = {
        "schema_version": 1,
        "generator": "benchmarks.dataset.generate/v1",
        "seed": 7,
        "requested": {"late_mid": 1},
        "checksum": "cafe" * 16,
        "positions": [
            {"id": "p0000", "qfen": ".ba./..CC/DcbD/cA.A", "phase": "late_mid",
             "pieces": 8, "side_to_move": 1, "legal_moves": 10,
             "reference": None}
        ],
    }
    observations = [
        {"engine": "minimax", "config_label": "minimax(d=16)",
         "position_id": "p0000", "move": "1:3:5", "wall_time_s": 0.01,
         "cpu_time_s": 0.01, "root_legal_moves": 10, "exact": True,
         "seed": 0, "nodes": 42, "iterations": None, "depth_reached": 8,
         "score": 9990.0, "peak_memory_bytes": None, "extra": {},
         "phase": "late_mid", "hit": True}
    ]
    aggregates = {
        "agreement": [
            {"engine": "minimax", "config_label": "minimax(d=16)",
             "phase": "late_mid", "n": 1, "hits": 1, "agreement": 1.0,
             "ci95_low": 0.207, "ci95_high": 1.0}
        ],
        "cost": [
            {"engine": "minimax", "config_label": "minimax(d=16)",
             "n": 1, "median_time_s": 0.01, "p95_time_s": 0.01,
             "median_nodes": 42.0, "peak_memory_bytes": None}
        ],
        "stability": [
            {"engine": "minimax", "config_label": "minimax(d=16)",
             "seeds": 1, "move_consistency": 1.0, "agreement_mean": 1.0,
             "agreement_std": 0.0}
        ],
    }
    head_to_head = {
        "records": [
            {"position_id": "p0000", "phase": "late_mid", "mover": "minimax",
             "responder": "random", "winner": "minimax", "plies": 1, "seed": 0}
        ],
        "aggregates": [
            {"engine_a": "minimax", "engine_b": "random", "games": 2,
             "paired_positions": 1, "a_wins": 2, "b_wins": 0, "draws": 0,
             "a_win_rate": 1.0, "a_win_rate_ci95": [0.342, 1.0],
             "a_wins_as_mover": 1, "b_wins_as_mover": 0,
             "by_phase": {"late_mid": {"games": 2, "a_wins": 2, "b_wins": 0}}}
        ],
    }
    config = {"family": "fixed", "time_limit": 1.0, "engine_seeds": [0]}
    return bundle.make_bundle(
        config=config,
        dataset_payload=dataset_payload,
        observations=observations,
        head_to_head=head_to_head,
        aggregates=aggregates,
    )


class TestEnvironment:
    def test_required_keys_present(self):
        env = bundle.collect_environment()
        for key in (
            "quantik_core_version", "git_sha", "python_version",
            "platform", "processor", "cpu_count", "total_memory_bytes",
        ):
            assert key in env
        assert env["python_version"].count(".") >= 1


class TestBundle:
    def test_bundle_is_self_describing_and_json_serializable(self):
        result = _synthetic_bundle()
        assert result["schema_version"] == bundle.SCHEMA_VERSION
        assert result["dataset"]["checksum"] == "cafe" * 16
        assert result["dataset"]["positions"] == 1
        assert result["dataset"]["phases"] == {"late_mid": 1}
        assert result["observations"]
        json.dumps(result)  # must not raise

    def test_save_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "results" / "nested" / "run.json"
        bundle.save_bundle(_synthetic_bundle(), target)
        assert json.loads(target.read_text())["schema_version"] == 1


class TestReport:
    def test_contains_all_four_tables_and_metadata(self):
        md = report.render_markdown(_synthetic_bundle())
        for heading in (
            "## Exact move agreement",
            "## Computational cost",
            "## Head-to-head (paired, side-balanced)",
            "## Stability across seeds",
            "## Interpretation guardrails",
        ):
            assert heading in md
        assert "cafe" in md  # dataset checksum surfaced
        assert "minimax" in md
        assert "| Draws |" in md or "Draws" in md

    def test_none_values_render_as_dash_not_none(self):
        md = report.render_markdown(_synthetic_bundle())
        assert "None" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_bundle.py -v`
Expected: FAIL — `ImportError` on `benchmarks.bundle`.

- [ ] **Step 3: Implement `benchmarks/bundle.py`**

```python
"""Reproducible result bundles: every run is saved with the environment,
configuration, dataset identity, raw per-move observations, and aggregate
statistics needed to reproduce or re-analyze it later.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

import quantik_core

SCHEMA_VERSION = 1


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _total_memory_bytes() -> Optional[int]:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def collect_environment() -> dict:
    """Host + software fingerprint stored in every bundle."""
    return {
        "quantik_core_version": quantik_core.__version__,
        "git_sha": _git_sha(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "total_memory_bytes": _total_memory_bytes(),
    }


def make_bundle(
    *,
    config: dict,
    dataset_payload: dict,
    observations: list,
    head_to_head: dict,
    aggregates: dict,
) -> dict:
    """Assemble the self-describing result bundle (JSON-serializable)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "environment": collect_environment(),
        "config": config,
        "dataset": {
            "checksum": dataset_payload.get("checksum"),
            "generator": dataset_payload["generator"],
            "seed": dataset_payload["seed"],
            "schema_version": dataset_payload["schema_version"],
            "positions": len(dataset_payload["positions"]),
            "phases": dict(
                Counter(p["phase"] for p in dataset_payload["positions"])
            ),
        },
        "observations": observations,
        "head_to_head": head_to_head,
        "aggregates": aggregates,
    }


def save_bundle(bundle: dict, path) -> None:
    """Write the bundle as JSON, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle, indent=1))
```

- [ ] **Step 4: Implement `benchmarks/report.py`**

```python
"""Markdown report generation.

Tables are generated FROM the raw result bundle -- never maintained by
hand -- and every table states which benchmark family it belongs to.
"""

from __future__ import annotations

from typing import List


def _fmt(value, spec: str = ".3f") -> str:
    if value is None:
        return "—"
    return format(value, spec)


def _table(headers: List[str], rows: List[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(" --- " for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_markdown(bundle: dict) -> str:  # noqa: C901
    env = bundle["environment"]
    cfg = bundle["config"]
    agg = bundle["aggregates"]
    family = cfg.get("family", "?")
    family_note = (
        "same wall-clock budget per move — a fair practical-latency comparison"
        if family == "fixed"
        else (
            "per-engine native settings — explains scaling behaviour, "
            "NOT a fair head-to-head ranking"
        )
    )

    parts: List[str] = [
        f"# Cross-engine benchmark — `{str(env['git_sha'])[:12]}`",
        "",
        f"- benchmark family: **{family}** ({family_note})",
        (
            f"- dataset: `{bundle['dataset']['checksum']}` — "
            f"{bundle['dataset']['positions']} positions "
            f"{bundle['dataset']['phases']}, generation seed "
            f"{bundle['dataset']['seed']}"
        ),
        f"- engine seeds: `{cfg.get('engine_seeds')}`",
        (
            f"- environment: quantik-core {env['quantik_core_version']}, "
            f"python {env['python_version']}, {env['platform']}, "
            f"{env['cpu_count']} CPUs"
        ),
        f"- started: {bundle['started_at']}",
        "",
        "## Exact move agreement",
        "",
        (
            "A hit = the selected move is in the COMPLETE optimal set proven "
            "by the exact solver with no cutoff. Positions without an exact "
            "reference (opening bucket, unsolved) are excluded. For "
            "stochastic engines, runs = positions × seeds."
        ),
        "",
        _table(
            [
                "Engine", "Configuration", "Phase", "Runs",
                "Optimal selected", "Agreement", "95% CI",
            ],
            [
                [
                    e["engine"], f"`{e['config_label']}`", e["phase"],
                    e["n"], e["hits"], _fmt(e["agreement"]),
                    f"[{_fmt(e['ci95_low'])}, {_fmt(e['ci95_high'])}]",
                ]
                for e in agg["agreement"]
            ],
        ),
        "",
        "## Computational cost",
        "",
        "Measured effective work per move (not configuration values).",
        "",
        _table(
            [
                "Engine", "Configuration", "Moves", "Median time (s)",
                "p95 time (s)", "Median nodes", "Peak memory (bytes)",
            ],
            [
                [
                    e["engine"], f"`{e['config_label']}`", e["n"],
                    _fmt(e["median_time_s"], ".4f"),
                    _fmt(e["p95_time_s"], ".4f"),
                    _fmt(e["median_nodes"], ".0f"),
                    _fmt(e["peak_memory_bytes"], ",.0f"),
                ]
                for e in agg["cost"]
            ],
        ),
        "",
        "## Head-to-head (paired, side-balanced)",
        "",
        (
            "Each (position, seed) is played twice, once with each engine as "
            "the side to move; wins are credited to the actual engine/color "
            "mapping. Quantik cannot draw, so Draws is structurally 0."
        ),
        "",
        _table(
            [
                "Engine A", "Engine B", "Paired positions", "Games",
                "A wins", "B wins", "Draws", "A win rate (95% CI)",
                "A wins as mover", "B wins as mover",
            ],
            [
                [
                    h["engine_a"], h["engine_b"], h["paired_positions"],
                    h["games"], h["a_wins"], h["b_wins"], h["draws"],
                    (
                        f"{_fmt(h['a_win_rate'])} "
                        f"[{_fmt(h['a_win_rate_ci95'][0])}, "
                        f"{_fmt(h['a_win_rate_ci95'][1])}]"
                    ),
                    h["a_wins_as_mover"], h["b_wins_as_mover"],
                ]
                for h in bundle["head_to_head"]["aggregates"]
            ],
        ),
        "",
        "### Head-to-head by phase",
        "",
        _table(
            ["Engine A", "Engine B", "Phase", "Games", "A wins", "B wins"],
            [
                [
                    h["engine_a"], h["engine_b"], phase,
                    split["games"], split["a_wins"], split["b_wins"],
                ]
                for h in bundle["head_to_head"]["aggregates"]
                for phase, split in h["by_phase"].items()
            ],
        ),
        "",
        "## Stability across seeds",
        "",
        (
            "Move consistency = average fraction of seeds choosing the modal "
            "move per position (1.0 = the seed never changes the move). "
            "Agreement mean/std is computed per seed first, then aggregated."
        ),
        "",
        _table(
            [
                "Engine", "Configuration", "Seeds", "Move consistency",
                "Agreement mean", "Agreement std",
            ],
            [
                [
                    e["engine"], f"`{e['config_label']}`", e["seeds"],
                    _fmt(e["move_consistency"]),
                    _fmt(e["agreement_mean"]),
                    _fmt(e["agreement_std"]),
                ]
                for e in agg["stability"]
            ],
        ),
        "",
        "## Interpretation guardrails",
        "",
        (
            "- Minimax buys adversarial certainty when the remaining tree is "
            "small enough; MCTS buys empirical confidence through repeated "
            "sampling; beam search buys bounded, selectively deep "
            "exploration. Hybrid play exploits that these strengths occur in "
            "different game phases."
        ),
        (
            "- No engine is 'universally superior' unless the evidence spans "
            "multiple phases, equivalent budgets, repeated seeds, and "
            "statistically meaningful samples."
        ),
        (
            "- Beam search honors its time limit only between depth levels; "
            "compare MEASURED times above, never configured caps."
        ),
        (
            "- Algorithm-native tables explain scaling; only fixed-resource "
            "tables support fair engine-vs-engine claims."
        ),
        "",
    ]
    return "\n".join(parts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_bundle.py -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
.venv/bin/python -m black benchmarks tests
git add benchmarks/bundle.py benchmarks/report.py tests/test_benchmark_bundle.py
git commit -m "feat(benchmarks): reproducible result bundles + generated Markdown report"
```

---

### Task 2: CLI rewrite of `examples/cross_engine_benchmark.py`

**Files:**
- Rewrite: `examples/cross_engine_benchmark.py` (full replacement)
- Modify: `tests/test_examples_demos.py` — DELETE the module-scoped
  `cross_engine_benchmark` fixture AND the whole `TestCrossEngineBenchmark`
  class (they test module-level helpers that no longer exist; their
  regression guarantees now live in `tests/test_benchmark_reference.py`
  and `tests/test_benchmark_h2h.py`), then add the new fixture + CLI
  class below in the same location.

**Interfaces:**
- Consumes: everything from parts 2–4 + task 1.
- Produces: `build_parser() -> argparse.ArgumentParser`,
  `main(argv=None) -> int` with subcommands `dataset`, `run`, `report`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_examples_demos.py`, replace the deleted fixture + class with:

```python
@pytest.fixture(scope="module")
def cross_engine_benchmark():
    return _load_demo_module("cross_engine_benchmark.py")


class TestCrossEngineBenchmarkCLI:
    """End-to-end smoke of the dataset -> run -> report pipeline with tiny
    settings. The old module-level helpers' regression guarantees now live
    in tests/test_benchmark_reference.py (complete optimal sets, terminal
    children scored directly) and tests/test_benchmark_h2h.py (win credited
    to the actual side to move, both parities)."""

    def test_pipeline_end_to_end(self, cross_engine_benchmark, tmp_path):
        dataset_path = tmp_path / "positions.json"
        bundle_path = tmp_path / "results" / "run.json"
        report_path = tmp_path / "results" / "run.md"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset", "--opening", "0", "--early-mid", "0",
                    "--late-mid", "1", "--endgame", "0", "--seed", "7",
                    "--solve-budget", "15.0", "--output", str(dataset_path),
                ]
            )
            == 0
        )

        assert (
            cross_engine_benchmark.main(
                [
                    "run", "--dataset", str(dataset_path),
                    "--family", "native", "--minimax-depth", "2",
                    "--mcts-iterations", "30", "--beam-width", "4",
                    "--beam-depth", "4", "--seeds", "2",
                    "--h2h-positions", "1", "--h2h-seeds", "1",
                    "--output", str(bundle_path),
                ]
            )
            == 0
        )

        assert (
            cross_engine_benchmark.main(
                ["report", "--input", str(bundle_path), "--output", str(report_path)]
            )
            == 0
        )

        import json

        bundle = json.loads(bundle_path.read_text())
        assert bundle["schema_version"] == 1
        assert bundle["observations"]
        assert bundle["dataset"]["checksum"]
        assert bundle["head_to_head"]["records"]
        md = report_path.read_text()
        for heading in (
            "Exact move agreement", "Computational cost",
            "Head-to-head", "Stability",
        ):
            assert heading in md

    def test_parser_rejects_unknown_family(self, cross_engine_benchmark):
        with pytest.raises(SystemExit):
            cross_engine_benchmark.build_parser().parse_args(
                ["run", "--dataset", "x.json", "--family", "bogus",
                 "--output", "y.json"]
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest "tests/test_examples_demos.py::TestCrossEngineBenchmarkCLI" -v`
Expected: FAIL — the current module has no `main` accepting argv /
no `build_parser`.

- [ ] **Step 3: Implement — replace `examples/cross_engine_benchmark.py` entirely**

```python
#!/usr/bin/env python3
"""Cross-engine benchmark CLI (GH issue #24).

Compares MinimaxEngine, MCTSEngine, BeamSearchEngine, and a random-mover
baseline on a SHARED, versioned, checksummed position dataset, under two
distinct families:

- fixed   : every engine gets the same wall-clock budget per move -- the
            fair practical-latency comparison.
- native  : each engine runs at explicit native settings (depth,
            iterations, beam width) -- explains scaling behaviour, but is
            NOT a fair head-to-head ranking.

Subcommands:
  dataset   Generate the shared position artifact (positions + exact
            references). Run ONCE, commit the artifact.
  run       Correctness preflight, then move-agreement + head-to-head ->
            a reproducible JSON result bundle.
  report    Render a bundle to Markdown tables.

Typical flow:
    python examples/cross_engine_benchmark.py dataset \
        --output benchmarks/positions-v1.json
    python examples/cross_engine_benchmark.py run \
        --dataset benchmarks/positions-v1.json \
        --family fixed --time-limit 1.0 --seeds 10 \
        --output benchmarks/results/fixed-1s.json
    python examples/cross_engine_benchmark.py report \
        --input benchmarks/results/fixed-1s.json

Methodology and metric definitions: docs/BENCHMARKS.md.
"""

import argparse
import itertools
import json
import os
import sys
from pathlib import Path

# `benchmarks/` lives at the repo root, a level above `examples/`. Running
# this file directly puts only `examples/` on sys.path[0], so add the repo
# root explicitly (same pattern the old version used for `tuning/`).
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
    parser = argparse.ArgumentParser(
        prog="cross_engine_benchmark",
        description="Reproducible cross-engine benchmark (docs/BENCHMARKS.md)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ds = sub.add_parser("dataset", help="generate the shared position artifact")
    p_ds.add_argument("--opening", type=int, default=8)
    p_ds.add_argument("--early-mid", type=int, default=8)
    p_ds.add_argument("--late-mid", type=int, default=12)
    p_ds.add_argument("--endgame", type=int, default=8)
    p_ds.add_argument("--seed", type=int, default=20260711)
    p_ds.add_argument(
        "--solve-budget",
        type=float,
        default=30.0,
        help="max wall-clock seconds to exactly solve each position",
    )
    p_ds.add_argument("--output", default="benchmarks/positions-v1.json")

    p_run = sub.add_parser("run", help="run a benchmark family -> JSON bundle")
    p_run.add_argument("--dataset", required=True)
    p_run.add_argument("--family", choices=("fixed", "native"), default="fixed")
    p_run.add_argument(
        "--time-limit",
        type=float,
        default=1.0,
        help="fixed family: wall-clock budget per move, seconds",
    )
    p_run.add_argument(
        "--seeds", type=int, default=10, help="seed count for stochastic engines"
    )
    p_run.add_argument("--seed-base", type=int, default=0)
    # native-family engine knobs (issue #24 required minimum).
    p_run.add_argument("--minimax-depth", type=int, default=6)
    p_run.add_argument("--minimax-time", type=float, default=0.2)
    p_run.add_argument("--mcts-iterations", type=int, default=1500)
    p_run.add_argument("--mcts-depth", type=int, default=16)
    p_run.add_argument("--mcts-exploration", type=float, default=1.414)
    p_run.add_argument("--beam-width", type=int, default=64)
    p_run.add_argument("--beam-depth", type=int, default=16)
    p_run.add_argument("--h2h-positions", type=int, default=8)
    p_run.add_argument("--h2h-seeds", type=int, default=1)
    p_run.add_argument("--skip-h2h", action="store_true")
    p_run.add_argument("--track-memory", action="store_true")
    p_run.add_argument("--output", required=True)

    p_rep = sub.add_parser("report", help="render a bundle to Markdown")
    p_rep.add_argument("--input", required=True)
    p_rep.add_argument("--output", default=None, help="default: <input>.md")
    return parser


def _build_adapters(args):
    if args.family == "fixed":
        engines = fixed_time_adapters(args.time_limit, beam_width=args.beam_width)
    else:
        engines = [
            MinimaxAdapter(
                max_depth=args.minimax_depth, time_limit_s=args.minimax_time
            ),
            MCTSAdapter(
                max_iterations=args.mcts_iterations,
                max_depth=args.mcts_depth,
                exploration_weight=args.mcts_exploration,
            ),
            BeamAdapter(beam_width=args.beam_width, max_depth=args.beam_depth),
        ]
    return engines + [RandomAdapter()]


def _h2h_positions(payload, count):
    """Pick positions round-robin across phase buckets so every phase is
    represented in head-to-head play."""
    by_phase = {}
    for pos in payload["positions"]:
        by_phase.setdefault(pos["phase"], []).append(pos)
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
    solved = sum(1 for p in payload["positions"] if p["reference"])
    print(
        f"dataset: {len(payload['positions'])} positions "
        f"({solved} with exact references) -> {args.output}"
    )
    print(f"checksum: {digest}")
    for phase in ds.PHASES:
        in_phase = [p for p in payload["positions"] if p["phase"] == phase]
        phase_solved = sum(1 for p in in_phase if p["reference"])
        print(f"  {phase:9s}: {len(in_phase)} positions, {phase_solved} solved")
    return 0


def cmd_run(args) -> int:
    payload = ds.load(args.dataset)
    adapters = _build_adapters(args)
    failures = run_preflight(adapters, payload["positions"])
    if failures:
        print("PREFLIGHT FAILED -- benchmark aborted:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    seeds = [args.seed_base + i for i in range(args.seeds)]
    print(
        f"preflight OK; agreement over {len(payload['positions'])} positions, "
        f"seeds {seeds} ..."
    )
    rows = run_agreement(adapters, payload, seeds, track_memory=args.track_memory)
    head_to_head = {"records": [], "aggregates": []}
    if not args.skip_h2h:
        positions = _h2h_positions(payload, args.h2h_positions)
        h2h_seeds = [args.seed_base + i for i in range(args.h2h_seeds)]
        for a, b in itertools.combinations(adapters, 2):
            print(f"head-to-head: {a.name} vs {b.name} ...")
            records = run_head_to_head(a, b, positions, h2h_seeds)
            head_to_head["records"].extend(records)
            head_to_head["aggregates"].append(
                aggregate_head_to_head(records, a.name, b.name)
            )
    aggregates = {
        "agreement": aggregate_agreement(rows),
        "cost": aggregate_cost(rows),
        "stability": aggregate_stability(rows),
    }
    config = dict(vars(args))
    config["engine_seeds"] = seeds
    bundle = make_bundle(
        config=config,
        dataset_payload=payload,
        observations=rows,
        head_to_head=head_to_head,
        aggregates=aggregates,
    )
    save_bundle(bundle, args.output)
    print(
        f"bundle: {len(rows)} observations, "
        f"{len(head_to_head['records'])} games -> {args.output}"
    )
    return 0


def cmd_report(args) -> int:
    bundle = json.loads(Path(args.input).read_text())
    output = args.output or str(Path(args.input).with_suffix(".md"))
    Path(output).write_text(render_markdown(bundle))
    print(f"report -> {output}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"dataset": cmd_dataset, "run": cmd_run, "report": cmd_report}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_examples_demos.py -v`
Expected: ALL PASS (including the untouched other demo classes; the
end-to-end test takes ~15–40s because it exactly solves one late_mid
position and plays 12 tiny head-to-head games).

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m black examples tests
git add examples/cross_engine_benchmark.py tests/test_examples_demos.py
git commit -m "feat(examples): CLI-configurable cross-engine benchmark (dataset/run/report)"
```

---

### Task 3: Documentation

**Files:**
- Create: `docs/BENCHMARKS.md`
- Modify: `docs/EXAMPLES.md` (the `cross_engine_benchmark.py` entry)
- Modify: `CHANGELOG.md`
- Modify: `.gitignore`

- [ ] **Step 1: Create `docs/BENCHMARKS.md`**

```markdown
# Cross-Engine Benchmark Methodology

`examples/cross_engine_benchmark.py` compares `MinimaxEngine`,
`MCTSEngine`, `BeamSearchEngine`, and a uniform-random baseline under
reproducible, methodologically consistent conditions (GH issue #24). It
distinguishes four things a single win-rate or timing figure conflates:

1. **Move quality** — does the engine select an objectively optimal move?
2. **Playing strength** — how do engines perform against one another?
3. **Computational cost** — measured time, nodes, iterations, memory.
4. **Stability** — do stochastic engines behave consistently across seeds?

## Shared dataset

All engines are evaluated on exactly the same positions
(`benchmarks/positions-v1.json`, generated once by the `dataset`
subcommand and committed). The artifact records the generation seed,
generator id, schema version, and a sha256 checksum that `run` verifies on
load. Positions are valid, reachable, NON-terminal, globally deduped by
`State.canonical_key()`, and record the side to move. Phase buckets by
pieces placed (== plies): opening 0–4, early_mid 5–7, late_mid 8–11,
endgame 12–16.

## Exact references

Non-opening positions carry an exact reference: the game value for the
side to move and the COMPLETE set of optimal moves, solved by the
full-depth minimax engine. A reference exists only when every child was
solved with **no cutoff** — proven by the completed iterative-deepening
depth reaching the child's remaining-ply count (Quantik never exceeds 16
plies). Positions that exceed the per-position solve budget, and the whole
opening bucket (exact solving the open game is intractable in pure
Python), have no reference and never contribute to exact move-agreement
figures. An engine scores a hit when its move is IN the optimal set.

## Two benchmark families

- **fixed** (`--family fixed --time-limit T`): every engine gets the same
  wall-clock budget per move (minimax via iterative-deepening deadline,
  MCTS via a per-iteration deadline with an unbounded iteration cap, beam
  via a between-depth-levels deadline). This is the fair
  practical-latency comparison. Caveat: beam checks its deadline only
  between depth levels, so a wide level can overshoot — always compare
  the MEASURED times in the cost table, never configured caps.
- **native** (`--family native` + engine flags): each engine at explicit
  native settings (minimax depth/time, MCTS iterations/depth/exploration,
  beam width/depth). Explains scaling behaviour; NOT a fair head-to-head
  ranking. Every generated table is labeled with its family.

## Stochastic engines

MCTS, beam, and random are seed-sensitive; minimax is deterministic. The
`run` subcommand evaluates stochastic engines across `--seeds N` seeds
(`seed_base + 0..N-1` — the same ordered list for every engine) and the
stability table reports per-position move consistency plus the across-seed
agreement mean/std. Use ≥10 seeds during development, ≥30 for publishable
results. Never compare one stochastic run against the deterministic
reference.

## Head-to-head

Every sampled position is played twice per seed — each engine once as the
side already to move — and results are credited to the actual engine/color
mapping (sampled positions can have either color to move). Quantik has no
draws; the Draws column is structurally 0. Results are reported in total,
by phase, and by role (as mover / as responder).

## Correctness preflight

`run` refuses to benchmark until invariants pass: all dataset positions
non-terminal; every adapter returns a legal move for the correct side
without mutating its input; identical settings + seed reproduce the same
move; minimax's chosen move equals its principal variation head.

## Reproducing a run

Every result bundle embeds: schema version, quantik-core version, git SHA,
python version, OS/processor/memory, full CLI config, dataset checksum and
generation seed, the ordered engine seed list, a start timestamp, all raw
per-move observations, and the aggregate tables. Markdown tables are
generated from the bundle by the `report` subcommand — never edited by
hand.

    python examples/cross_engine_benchmark.py run \
      --dataset benchmarks/positions-v1.json \
      --time-limit 1.0 --seeds 30 \
      --output benchmarks/results/$(git rev-parse --short HEAD).json
    python examples/cross_engine_benchmark.py report \
      --input benchmarks/results/$(git rev-parse --short HEAD).json

`benchmarks/results/` is gitignored; attach reports to PRs/issues instead
of committing them.

## Interpretation guardrails

Minimax buys adversarial certainty when the remaining tree is small
enough; MCTS buys empirical confidence through repeated sampling; beam
search buys bounded, selectively deep exploration; the hybrid player
exploits the fact that these strengths occur in different phases. Claims
that one engine is universally superior require evidence across multiple
phases, equivalent budgets, repeated seeds, and statistically meaningful
samples — an aggregate score alone can hide that one algorithm owns the
opening while another owns solvable endgames.
```

- [ ] **Step 2: Update `docs/EXAMPLES.md`**

Find the existing `cross_engine_benchmark.py` entry and replace its
description with:

> CLI benchmark harness comparing minimax, MCTS, beam search, and a random
> baseline on a shared versioned dataset — `dataset` / `run` / `report`
> subcommands, fixed-resource vs algorithm-native families, exact
> move-agreement, paired head-to-head, and seed-stability tables. See
> `docs/BENCHMARKS.md`.

- [ ] **Step 3: Update `CHANGELOG.md`**

Following the file's existing heading conventions, add under the
unreleased/next section:

```markdown
- feat: cross-engine benchmark harness (#24) — shared checksummed position
  dataset with exact references (`benchmarks/`), CLI
  `examples/cross_engine_benchmark.py` with `dataset`/`run`/`report`
  subcommands, fixed-resource and algorithm-native families, correctness
  preflight, seed-stability and paired head-to-head reporting
  (`docs/BENCHMARKS.md`).
- feat: optional wall-clock `time_limit_s` on `MCTSConfig` and
  `BeamSearchConfig`.
```

- [ ] **Step 4: Update `.gitignore`**

Add (near the other build/output entries):

```
# benchmark result bundles are attached to PRs/issues, not committed
benchmarks/results/
```

- [ ] **Step 5: Commit**

```bash
git add docs/BENCHMARKS.md docs/EXAMPLES.md CHANGELOG.md .gitignore
git commit -m "docs: cross-engine benchmark methodology and CLI reference"
```

---

### Task 4: Generate the committed dataset artifact + smoke run + final gates

- [ ] **Step 1: Generate `benchmarks/positions-v1.json`**

```bash
.venv/bin/python examples/cross_engine_benchmark.py dataset \
    --opening 8 --early-mid 8 --late-mid 12 --endgame 8 \
    --seed 20260711 --solve-budget 30.0 \
    --output benchmarks/positions-v1.json
```

Expected output: `dataset: 36 positions (...) -> benchmarks/positions-v1.json`
plus per-phase counts. Notes: this can take up to ~15–30 minutes (early_mid
positions are the slow solves; some may exceed the budget and stay
reference-less — that is correct behavior, they join the heuristic
bucket). The endgame bucket may come back with fewer than 8 positions
(random playouts often end before 12 plies); that is acceptable, the
printed counts are the record.

- [ ] **Step 2: Smoke-run the full pipeline on the real artifact**

```bash
mkdir -p benchmarks/results
.venv/bin/python examples/cross_engine_benchmark.py run \
    --dataset benchmarks/positions-v1.json \
    --family fixed --time-limit 0.25 --seeds 3 \
    --h2h-positions 4 --h2h-seeds 1 \
    --output benchmarks/results/smoke.json
.venv/bin/python examples/cross_engine_benchmark.py report \
    --input benchmarks/results/smoke.json
```

Expected: preflight OK, a bundle and a Markdown report under
`benchmarks/results/` (gitignored). Eyeball the report: four tables
present, agreement highest for minimax in late_mid/endgame, no `None`
cells. Takes roughly 5–15 minutes.

- [ ] **Step 3: Full gate**

Run: `./dev-check.sh`
Expected: pytest+coverage ≥90%, black, flake8, mypy, build, twine all
green.

- [ ] **Step 4: Commit the artifact**

```bash
git add benchmarks/positions-v1.json
git commit -m "data(benchmarks): shared position dataset v1 (36 positions, exact refs)"
```

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch. The PR should reference
issue #24 and include the smoke report's four tables in its description
(paste from `benchmarks/results/smoke.md`). The issue additionally asks
for a "reasonably thorough" run to be posted as a comment — after the PR
is up, run and post:

```bash
.venv/bin/python examples/cross_engine_benchmark.py run \
    --dataset benchmarks/positions-v1.json \
    --family fixed --time-limit 1.0 --seeds 10 \
    --h2h-positions 8 --h2h-seeds 2 \
    --output benchmarks/results/thorough.json
.venv/bin/python examples/cross_engine_benchmark.py report \
    --input benchmarks/results/thorough.json
```

(Expect this to take on the order of an hour; it can run while the PR is
in review.)

---

## Self-review checklist

- [ ] The brief's recommended command works verbatim (`run` defaults to
      the fixed family, so `--dataset … --time-limit 1.0 --seeds 30
      --output …` is sufficient).
- [ ] Issue #24's five required knobs are all CLI-exposed:
      `--mcts-iterations`, `--mcts-depth`, `--mcts-exploration`,
      `--minimax-depth`, `--minimax-time`, `--beam-width` (plus seeds,
      counts, paths).
- [ ] `report` output is generated purely from the bundle JSON.
- [ ] Old `TestCrossEngineBenchmark` deleted; its guarantees are pinned in
      `tests/test_benchmark_reference.py` and `tests/test_benchmark_h2h.py`.
- [ ] `./dev-check.sh` green; dataset artifact committed; results dir
      gitignored.
