# Benchmark Checkpoints And Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long cross-engine benchmark runs durable by writing resumable checkpoints before adding reusable selection-result caching.

**Architecture:** Phase 1 adds an append-only checkpoint store beside the final JSON bundle. Agreement observations and head-to-head game records are streamed to JSONL as each unit completes; a small manifest records config, dataset identity, status, and completed counts. Final bundle/report generation can consume either the legacy monolithic JSON bundle or a checkpoint directory. Phase 2 adds an optional selection cache keyed by engine/config/position/seed so repeated benchmark invocations can skip identical move-selection calls.

**Tech Stack:** Python stdlib only (`json`, `pathlib`, `os.replace`, dataclasses/typing as needed), existing `benchmarks.*` modules, existing CLI in `examples/cross_engine_benchmark.py`, pytest.

---

## Why This Is Immediate

The current benchmark writes `benchmarks/results/<run>.json` only after all agreement rows and all head-to-head games finish. Two longer runs were interrupted or aborted after many minutes and produced no artifact. The first durability fix is checkpointing, not caching: checkpointing prevents losing completed work; caching is useful only after completed units have stable keys and resumable storage.

## File Structure

- Create `benchmarks/checkpoint.py`
  - Owns JSONL append/read helpers.
  - Owns stable key generation for agreement observations and head-to-head records.
  - Owns manifest creation/update.
  - Rehydrates a checkpoint directory into the same bundle shape expected by `benchmarks.report.render_markdown`.
- Modify `benchmarks/agreement.py`
  - Add an iterator form that can skip completed observation keys and yield rows one at a time.
  - Keep `run_agreement()` as the legacy list-returning wrapper.
- Modify `benchmarks/head_to_head.py`
  - Add an iterator form that can skip completed game keys and yield records one at a time.
  - Keep `run_head_to_head()` as the legacy list-returning wrapper.
- Modify `examples/cross_engine_benchmark.py`
  - Add `run --checkpoint-dir`, `run --resume`, and `run --checkpoint-every`.
  - Stream rows/games into checkpoints when `--checkpoint-dir` is present.
  - Save the final bundle as before at `--output`.
  - Allow `report --input <checkpoint-dir>` in addition to `report --input <bundle.json>`.
- Modify `benchmarks/report.py` only if needed to tolerate checkpoint-rehydrated bundles. Prefer keeping it unchanged.
- Modify `docs/BENCHMARKS.md`
  - Document long-run checkpoint usage and resume behavior.
- Add `tests/test_benchmark_checkpoint.py`
  - Unit coverage for manifest, JSONL append/read, stable keys, and bundle rehydration.
- Modify `tests/test_benchmark_agreement.py`
  - Coverage for skip/resume behavior in the iterator.
- Modify `tests/test_benchmark_h2h.py`
  - Coverage for skip/resume behavior in the iterator.
- Modify `tests/test_examples_demos.py`
  - CLI smoke coverage for checkpointed run and `report --input <checkpoint-dir>`.

## Phase 1: Checkpoint And Resume

### Task 1: Add Checkpoint Store

**Files:**
- Create: `benchmarks/checkpoint.py`
- Test: `tests/test_benchmark_checkpoint.py`

- [x] **Step 1: Write failing tests for JSONL append/read and stable keys**

Add `tests/test_benchmark_checkpoint.py`:

```python
"""Tests for resumable benchmark checkpoint storage."""

import json

from benchmarks import checkpoint


def test_jsonl_append_and_load_roundtrip(tmp_path):
    path = tmp_path / "rows.jsonl"

    checkpoint.append_jsonl(path, {"b": 2, "a": 1})
    checkpoint.append_jsonl(path, {"a": 3, "b": 4})

    assert checkpoint.load_jsonl(path) == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]


def test_load_jsonl_missing_file_returns_empty_list(tmp_path):
    assert checkpoint.load_jsonl(tmp_path / "missing.jsonl") == []


def test_observation_key_is_stable_and_specific():
    row = {
        "position_id": "p0008",
        "engine": "mcts",
        "config_label": "mcts(it=5000,d=16,c=1.414)",
        "seed": 7,
    }

    assert checkpoint.observation_key(row) == (
        "p0008",
        "mcts",
        "mcts(it=5000,d=16,c=1.414)",
        7,
    )


def test_h2h_key_is_stable_and_specific():
    row = {
        "position_id": "p0008",
        "phase": "late_mid",
        "mover": "beam",
        "responder": "mcts",
        "seed": 11,
    }

    assert checkpoint.h2h_key(row) == ("p0008", "beam", "mcts", 11)
```

- [x] **Step 2: Run tests and verify they fail**

Run: `rtk .venv/bin/python -m pytest tests/test_benchmark_checkpoint.py -v --no-cov`

Expected: import failure because `benchmarks.checkpoint` does not exist.

- [x] **Step 3: Implement JSONL helpers and key functions**

Create `benchmarks/checkpoint.py`:

```python
"""Append-only checkpoint storage for long benchmark runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Tuple


MANIFEST = "manifest.json"
OBSERVATIONS = "observations.jsonl"
H2H_RECORDS = "h2h.jsonl"


def append_jsonl(path, row: dict) -> None:
    """Append one JSON object as one sorted-key JSONL row."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


def load_jsonl(path) -> list[dict]:
    """Load JSONL rows; a missing file means no checkpointed rows yet."""
    source = Path(path)
    if not source.exists():
        return []
    rows = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_number}: invalid checkpoint JSON") from exc
    return rows


def observation_key(row: dict) -> Tuple[str, str, str, int | None]:
    """Return the resume identity for one agreement observation row."""
    return (
        row["position_id"],
        row["engine"],
        row["config_label"],
        row.get("seed"),
    )


def h2h_key(row: dict) -> Tuple[str, str, str, int]:
    """Return the resume identity for one head-to-head game record."""
    return (
        row["position_id"],
        row["mover"],
        row["responder"],
        row["seed"],
    )


def key_set(rows: Iterable[dict], key_func) -> set[tuple]:
    """Return stable resume keys for already checkpointed rows."""
    return {key_func(row) for row in rows}
```

- [x] **Step 4: Run tests and verify they pass**

Run: `rtk .venv/bin/python -m pytest tests/test_benchmark_checkpoint.py -v --no-cov`

Expected: all tests pass.

### Task 2: Add Manifest And Bundle Rehydration

**Files:**
- Modify: `benchmarks/checkpoint.py`
- Modify: `tests/test_benchmark_checkpoint.py`

- [x] **Step 1: Write failing tests for manifest lifecycle and bundle rehydration**

Append to `tests/test_benchmark_checkpoint.py`:

```python
from benchmarks import agreement, bundle, head_to_head, stability


def _dataset_payload():
    return {
        "schema_version": 1,
        "generator": "benchmarks.dataset.generate/v1",
        "seed": 20260711,
        "requested": {"late_mid": 1},
        "checksum": "abc123",
        "positions": [
            {
                "id": "p0008",
                "qfen": ".ba./..CC/DcbD/cA.A",
                "phase": "late_mid",
                "pieces": 8,
                "side_to_move": 1,
                "legal_moves": 10,
                "reference": {
                    "value": 1,
                    "optimal_moves": ["1:3:5"],
                    "solver": "test",
                    "depth": 8,
                },
            }
        ],
    }


def _observation():
    return {
        "engine": "minimax",
        "config_label": "minimax(d=16)",
        "position_id": "p0008",
        "move": "1:3:5",
        "wall_time_s": 0.01,
        "cpu_time_s": 0.01,
        "root_legal_moves": 10,
        "exact": True,
        "seed": 0,
        "nodes": 10,
        "iterations": None,
        "depth_reached": 8,
        "score": 9990.0,
        "peak_memory_bytes": None,
        "extra": {},
        "phase": "late_mid",
        "hit": True,
    }


def _h2h_record():
    return {
        "position_id": "p0008",
        "phase": "late_mid",
        "mover": "minimax",
        "responder": "random",
        "winner": "minimax",
        "plies": 1,
        "seed": 0,
    }


def test_manifest_write_update_and_load(tmp_path):
    root = tmp_path / "checkpoint"
    payload = _dataset_payload()
    config = {"family": "native", "engine_seeds": [0], "skip_h2h": False}

    checkpoint.write_manifest(
        root,
        config=config,
        dataset_payload=payload,
        h2h_pairs=[["minimax", "random"]],
        status="running",
        observations=0,
        h2h_records=0,
    )
    loaded = checkpoint.load_manifest(root)

    assert loaded["status"] == "running"
    assert loaded["dataset"]["checksum"] == "abc123"
    assert loaded["h2h_pairs"] == [["minimax", "random"]]

    checkpoint.update_manifest_counts(root, status="complete", observations=1, h2h_records=1)
    updated = checkpoint.load_manifest(root)
    assert updated["status"] == "complete"
    assert updated["counts"] == {"observations": 1, "h2h_records": 1}


def test_bundle_from_checkpoint_matches_report_shape(tmp_path):
    root = tmp_path / "checkpoint"
    payload = _dataset_payload()
    config = {"family": "native", "engine_seeds": [0], "skip_h2h": False}
    checkpoint.write_manifest(
        root,
        config=config,
        dataset_payload=payload,
        h2h_pairs=[["minimax", "random"]],
        status="complete",
        observations=1,
        h2h_records=1,
    )
    checkpoint.append_jsonl(root / checkpoint.OBSERVATIONS, _observation())
    checkpoint.append_jsonl(root / checkpoint.H2H_RECORDS, _h2h_record())

    result = checkpoint.bundle_from_checkpoint(root)

    assert result["observations"] == [_observation()]
    assert result["head_to_head"]["records"] == [_h2h_record()]
    assert result["head_to_head"]["aggregates"][0]["engine_a"] == "minimax"
    assert result["aggregates"]["agreement"][0]["hits"] == 1
    assert result["aggregates"]["stability"][0]["move_consistency"] == 1.0
```

- [x] **Step 2: Run tests and verify they fail**

Run: `rtk .venv/bin/python -m pytest tests/test_benchmark_checkpoint.py -v --no-cov`

Expected: missing `write_manifest`, `load_manifest`, `update_manifest_counts`, and `bundle_from_checkpoint`.

- [x] **Step 3: Implement manifest and rehydration**

Extend `benchmarks/checkpoint.py`:

```python
import time
from collections import Counter

from benchmarks.agreement import aggregate_agreement, aggregate_cost
from benchmarks.bundle import SCHEMA_VERSION, collect_environment
from benchmarks.head_to_head import aggregate_head_to_head
from benchmarks.stability import aggregate_stability
```

Add:

```python
def _dataset_summary(dataset_payload: dict) -> dict:
    positions = dataset_payload["positions"]
    phases = Counter(position["phase"] for position in positions)
    return {
        "checksum": dataset_payload.get("checksum"),
        "generator": dataset_payload["generator"],
        "seed": dataset_payload["seed"],
        "schema_version": dataset_payload["schema_version"],
        "positions": len(positions),
        "phases": dict(phases),
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_manifest(
    root,
    *,
    config: dict,
    dataset_payload: dict,
    h2h_pairs: list[list[str]],
    status: str,
    observations: int,
    h2h_records: int,
) -> None:
    """Create or replace the checkpoint manifest."""
    target = Path(root)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "environment": collect_environment(),
        "config": config,
        "dataset": _dataset_summary(dataset_payload),
        "h2h_pairs": h2h_pairs,
        "status": status,
        "counts": {"observations": observations, "h2h_records": h2h_records},
    }
    _write_json_atomic(target / MANIFEST, manifest)


def load_manifest(root) -> dict:
    """Load a checkpoint manifest."""
    path = Path(root) / MANIFEST
    if not path.exists():
        raise FileNotFoundError(f"checkpoint manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def update_manifest_counts(
    root, *, status: str, observations: int, h2h_records: int
) -> None:
    """Update status and completed row counts in an existing manifest."""
    path = Path(root) / MANIFEST
    manifest = load_manifest(root)
    manifest["status"] = status
    manifest["counts"] = {"observations": observations, "h2h_records": h2h_records}
    _write_json_atomic(path, manifest)


def bundle_from_checkpoint(root) -> dict:
    """Rehydrate a checkpoint directory into the normal result bundle shape."""
    target = Path(root)
    manifest = load_manifest(target)
    observations = load_jsonl(target / OBSERVATIONS)
    h2h_records = load_jsonl(target / H2H_RECORDS)
    h2h_aggregates = []
    for engine_a, engine_b in manifest.get("h2h_pairs", []):
        pair_records = [
            row
            for row in h2h_records
            if {row["mover"], row["responder"]} == {engine_a, engine_b}
        ]
        h2h_aggregates.append(aggregate_head_to_head(pair_records, engine_a, engine_b))

    return {
        "schema_version": manifest["schema_version"],
        "started_at": manifest["started_at"],
        "environment": manifest["environment"],
        "config": manifest["config"],
        "dataset": manifest["dataset"],
        "observations": observations,
        "head_to_head": {"records": h2h_records, "aggregates": h2h_aggregates},
        "aggregates": {
            "agreement": aggregate_agreement(observations),
            "cost": aggregate_cost(observations),
            "stability": aggregate_stability(observations),
        },
    }
```

- [x] **Step 4: Run tests and verify they pass**

Run: `rtk .venv/bin/python -m pytest tests/test_benchmark_checkpoint.py -v --no-cov`

Expected: all checkpoint tests pass.

### Task 3: Stream Agreement Rows With Resume Skips

**Files:**
- Modify: `benchmarks/agreement.py`
- Modify: `tests/test_benchmark_agreement.py`

- [x] **Step 1: Write failing tests for skip behavior**

Append to `tests/test_benchmark_agreement.py`:

```python
from benchmarks.checkpoint import observation_key


class TestIterAgreement:
    def test_skip_completed_observation_keys(self, payload):
        adapters = [MinimaxAdapter(max_depth=2), RandomAdapter()]
        all_rows = run_agreement(adapters, payload, seeds=[0, 1])
        completed = {observation_key(all_rows[0])}

        resumed = list(
            iter_agreement(adapters, payload, seeds=[0, 1], skip_keys=completed)
        )

        assert len(resumed) == len(all_rows) - 1
        assert observation_key(all_rows[0]) not in {observation_key(row) for row in resumed}
```

Also update the imports at the top:

```python
from benchmarks.agreement import (
    aggregate_agreement,
    aggregate_cost,
    iter_agreement,
    run_agreement,
)
```

- [x] **Step 2: Run test and verify it fails**

Run: `rtk .venv/bin/python -m pytest tests/test_benchmark_agreement.py::TestIterAgreement -v --no-cov`

Expected: import failure for `iter_agreement`.

- [x] **Step 3: Implement iterator and keep wrapper**

In `benchmarks/agreement.py`, add:

```python
def _planned_observation_key(
    *, position_id: str, engine: str, config_label: str, seed: int | None
) -> tuple:
    return (position_id, engine, config_label, seed)
```

Replace `run_agreement()` body with an iterator plus wrapper:

```python
def iter_agreement(
    adapters,
    payload: dict,
    seeds: Sequence[int],
    track_memory: bool = False,
    skip_keys: set[tuple] | None = None,
):
    """Yield one move-observation row at a time, skipping completed keys."""
    if not seeds:
        raise ValueError("seeds must be a non-empty ordered list")

    completed = skip_keys or set()
    for position in payload["positions"]:
        bb = State.from_qfen(position["qfen"]).bb
        reference = position.get("reference")
        optimal_moves = set(reference["optimal_moves"]) if reference else None

        for adapter in adapters:
            adapter_seeds = seeds if adapter.stochastic else [seeds[0]]
            for seed in adapter_seeds:
                planned_key = _planned_observation_key(
                    position_id=position["id"],
                    engine=adapter.name,
                    config_label=adapter.config_label,
                    seed=seed,
                )
                if planned_key in completed:
                    continue
                _, observation = adapter.select(
                    bb,
                    position["id"],
                    seed=seed,
                    track_memory=track_memory,
                )
                row = observation.to_dict()
                row["phase"] = position["phase"]
                row["hit"] = (
                    observation.move in optimal_moves
                    if optimal_moves is not None
                    else None
                )
                yield row


def run_agreement(
    adapters,
    payload: dict,
    seeds: Sequence[int],
    track_memory: bool = False,
) -> List[dict]:
    """Return one move-observation row per adapter, position, and seed run."""
    return list(iter_agreement(adapters, payload, seeds, track_memory=track_memory))
```

- [x] **Step 4: Run tests and verify they pass**

Run: `rtk .venv/bin/python -m pytest tests/test_benchmark_agreement.py -v --no-cov`

Expected: all agreement tests pass.

### Task 4: Stream Head-To-Head Records With Resume Skips

**Files:**
- Modify: `benchmarks/head_to_head.py`
- Modify: `tests/test_benchmark_h2h.py`

- [x] **Step 1: Write failing tests for skip behavior**

Append to `tests/test_benchmark_h2h.py`:

```python
from benchmarks.checkpoint import h2h_key


class TestIterHeadToHead:
    def test_skip_completed_game_keys(self):
        positions = [
            {
                "id": "p0008",
                "qfen": ".ba./..CC/DcbD/cA.A",
                "phase": "late_mid",
            }
        ]
        a = ScriptedAdapter("minimax")
        b = ScriptedAdapter("random")
        all_records = run_head_to_head(a, b, positions, seeds=[0])
        completed = {h2h_key(all_records[0])}

        resumed = list(iter_head_to_head(a, b, positions, seeds=[0], skip_keys=completed))

        assert len(resumed) == len(all_records) - 1
        assert h2h_key(all_records[0]) not in {h2h_key(row) for row in resumed}
```

Also update imports at the top:

```python
from benchmarks.head_to_head import (
    aggregate_head_to_head,
    iter_head_to_head,
    play_game,
    run_head_to_head,
)
```

- [x] **Step 2: Run test and verify it fails**

Run: `rtk .venv/bin/python -m pytest tests/test_benchmark_h2h.py::TestIterHeadToHead -v --no-cov`

Expected: import failure for `iter_head_to_head`.

- [x] **Step 3: Implement iterator and keep wrapper**

In `benchmarks/head_to_head.py`, add:

```python
def _planned_h2h_key(position_id: str, mover: str, responder: str, seed: int) -> tuple:
    return (position_id, mover, responder, seed)
```

Replace `run_head_to_head()` body with:

```python
def iter_head_to_head(
    adapter_a,
    adapter_b,
    positions: Sequence[dict],
    seeds: Sequence[int],
    skip_keys: set[tuple] | None = None,
):
    """Yield side-balanced head-to-head records one game at a time."""
    completed = skip_keys or set()
    for position in positions:
        bb = State.from_qfen(position["qfen"]).bb
        for seed in seeds:
            for mover, responder in ((adapter_a, adapter_b), (adapter_b, adapter_a)):
                planned_key = _planned_h2h_key(
                    position["id"], mover.name, responder.name, seed
                )
                if planned_key in completed:
                    continue
                winner, plies = play_game(mover, responder, bb, seed)
                yield {
                    "position_id": position["id"],
                    "phase": position["phase"],
                    "mover": mover.name,
                    "responder": responder.name,
                    "winner": winner,
                    "plies": plies,
                    "seed": seed,
                }


def run_head_to_head(
    adapter_a, adapter_b, positions: Sequence[dict], seeds: Sequence[int]
) -> List[dict]:
    """Play both engine orientations per position and seed."""
    return list(iter_head_to_head(adapter_a, adapter_b, positions, seeds))
```

- [x] **Step 4: Run tests and verify they pass**

Run: `rtk .venv/bin/python -m pytest tests/test_benchmark_h2h.py -v --no-cov`

Expected: all h2h tests pass.

### Task 5: Add CLI Checkpoint/Resume

**Files:**
- Modify: `examples/cross_engine_benchmark.py`
- Modify: `tests/test_examples_demos.py`

- [x] **Step 1: Write failing CLI tests**

Extend `TestCrossEngineBenchmarkCLI.test_pipeline_end_to_end()` in `tests/test_examples_demos.py`:

After `bundle_path = ...`, add:

```python
checkpoint_dir = tmp_path / "results" / "checkpoint"
checkpoint_report_path = tmp_path / "results" / "checkpoint.md"
```

In the existing `run` command argument list, add:

```python
"--checkpoint-dir",
str(checkpoint_dir),
```

After reading `bundle`, add:

```python
assert (checkpoint_dir / "manifest.json").exists()
assert (checkpoint_dir / "observations.jsonl").exists()
assert (checkpoint_dir / "h2h.jsonl").exists()
manifest = json.loads((checkpoint_dir / "manifest.json").read_text())
assert manifest["status"] == "complete"
assert manifest["counts"]["observations"] == len(bundle["observations"])
assert manifest["counts"]["h2h_records"] == len(bundle["head_to_head"]["records"])
```

After the existing report assertion, add:

```python
assert (
    cross_engine_benchmark.main(
        [
            "report",
            "--input",
            str(checkpoint_dir),
            "--output",
            str(checkpoint_report_path),
        ]
    )
    == 0
)
assert "Exact move agreement" in checkpoint_report_path.read_text()
```

Add a new test:

```python
    def test_checkpoint_resume_skips_existing_rows(
        self, cross_engine_benchmark, tmp_path
    ):
        dataset_path = tmp_path / "positions.json"
        checkpoint_dir = tmp_path / "checkpoint"
        first_bundle = tmp_path / "first.json"
        second_bundle = tmp_path / "second.json"

        assert cross_engine_benchmark.main(
            [
                "dataset",
                "--opening",
                "0",
                "--early-mid",
                "0",
                "--late-mid",
                "1",
                "--endgame",
                "0",
                "--seed",
                "7",
                "--solve-budget",
                "15.0",
                "--output",
                str(dataset_path),
            ]
        ) == 0

        base_args = [
            "run",
            "--dataset",
            str(dataset_path),
            "--family",
            "native",
            "--minimax-depth",
            "2",
            "--mcts-iterations",
            "30",
            "--beam-width",
            "4",
            "--beam-depth",
            "4",
            "--seeds",
            "2",
            "--h2h-positions",
            "1",
            "--h2h-seeds",
            "1",
            "--checkpoint-dir",
            str(checkpoint_dir),
        ]

        assert cross_engine_benchmark.main([*base_args, "--output", str(first_bundle)]) == 0
        first = json.loads(first_bundle.read_text())
        assert cross_engine_benchmark.main(
            [*base_args, "--resume", "--output", str(second_bundle)]
        ) == 0
        second = json.loads(second_bundle.read_text())

        assert second["observations"] == first["observations"]
        assert second["head_to_head"]["records"] == first["head_to_head"]["records"]
```

- [x] **Step 2: Run tests and verify they fail**

Run: `rtk .venv/bin/python -m pytest tests/test_examples_demos.py::TestCrossEngineBenchmarkCLI -v --no-cov`

Expected: parser rejects unknown `--checkpoint-dir` and `--resume`.

- [x] **Step 3: Wire CLI parser**

In `examples/cross_engine_benchmark.py`, add imports:

```python
from benchmarks import checkpoint  # noqa: E402
```

In `build_parser()`, add to the `run` subparser:

```python
run.add_argument("--checkpoint-dir", default=None)
run.add_argument("--resume", action="store_true")
run.add_argument("--checkpoint-every", type=int, default=1)
```

- [x] **Step 4: Implement checkpointed run path**

In `cmd_run(args)`, after `config = dict(vars(args))` logic is available, create config before work:

```python
    seeds = [args.seed_base + i for i in range(args.seeds)]
    config = dict(vars(args))
    config["engine_seeds"] = seeds
```

Replace the current `rows = run_agreement(...)` block with checkpoint-aware streaming:

```python
    checkpoint_root = Path(args.checkpoint_dir) if args.checkpoint_dir else None
    existing_rows = []
    existing_h2h = []
    completed_observations = set()
    completed_h2h = set()
    h2h_pairs = [
        [adapter_a.name, adapter_b.name]
        for adapter_a, adapter_b in itertools.combinations(adapters, 2)
    ]

    if checkpoint_root is not None:
        if args.resume:
            existing_rows = checkpoint.load_jsonl(checkpoint_root / checkpoint.OBSERVATIONS)
            existing_h2h = checkpoint.load_jsonl(checkpoint_root / checkpoint.H2H_RECORDS)
            completed_observations = checkpoint.key_set(
                existing_rows, checkpoint.observation_key
            )
            completed_h2h = checkpoint.key_set(existing_h2h, checkpoint.h2h_key)
        checkpoint.write_manifest(
            checkpoint_root,
            config=config,
            dataset_payload=payload,
            h2h_pairs=h2h_pairs if not args.skip_h2h else [],
            status="running",
            observations=len(existing_rows),
            h2h_records=len(existing_h2h),
        )

    rows = list(existing_rows)
    for row in iter_agreement(
        adapters,
        payload,
        seeds,
        track_memory=args.track_memory,
        skip_keys=completed_observations,
    ):
        rows.append(row)
        if checkpoint_root is not None:
            checkpoint.append_jsonl(checkpoint_root / checkpoint.OBSERVATIONS, row)
            if len(rows) % args.checkpoint_every == 0:
                checkpoint.update_manifest_counts(
                    checkpoint_root,
                    status="running",
                    observations=len(rows),
                    h2h_records=len(existing_h2h),
                )
```

Replace the head-to-head generation block with:

```python
    head_to_head = {"records": list(existing_h2h), "aggregates": []}
    if not args.skip_h2h:
        positions = _h2h_positions(payload, args.h2h_positions)
        h2h_seeds = [args.seed_base + i for i in range(args.h2h_seeds)]
        for adapter_a, adapter_b in itertools.combinations(adapters, 2):
            pair_records = [
                row
                for row in head_to_head["records"]
                if {row["mover"], row["responder"]} == {adapter_a.name, adapter_b.name}
            ]
            for record in iter_head_to_head(
                adapter_a,
                adapter_b,
                positions,
                h2h_seeds,
                skip_keys=completed_h2h,
            ):
                head_to_head["records"].append(record)
                pair_records.append(record)
                if checkpoint_root is not None:
                    checkpoint.append_jsonl(
                        checkpoint_root / checkpoint.H2H_RECORDS, record
                    )
                    if len(head_to_head["records"]) % args.checkpoint_every == 0:
                        checkpoint.update_manifest_counts(
                            checkpoint_root,
                            status="running",
                            observations=len(rows),
                            h2h_records=len(head_to_head["records"]),
                        )
            head_to_head["aggregates"].append(
                aggregate_head_to_head(pair_records, adapter_a.name, adapter_b.name)
            )
```

After `save_bundle(result, args.output)`, add:

```python
    if checkpoint_root is not None:
        checkpoint.update_manifest_counts(
            checkpoint_root,
            status="complete",
            observations=len(rows),
            h2h_records=len(head_to_head["records"]),
        )
```

Update imports from agreement/head_to_head:

```python
from benchmarks.agreement import (
    aggregate_agreement,
    aggregate_cost,
    iter_agreement,
)
from benchmarks.head_to_head import (
    aggregate_head_to_head,
    iter_head_to_head,
)
```

- [x] **Step 5: Implement `report --input <checkpoint-dir>`**

In `cmd_report(args)`, replace:

```python
    result = json.loads(Path(args.input).read_text())
```

with:

```python
    source = Path(args.input)
    result = (
        checkpoint.bundle_from_checkpoint(source)
        if source.is_dir()
        else json.loads(source.read_text())
    )
```

- [x] **Step 6: Run CLI tests and verify they pass**

Run: `rtk .venv/bin/python -m pytest tests/test_examples_demos.py::TestCrossEngineBenchmarkCLI -v --no-cov`

Expected: all CLI checkpoint tests pass.

### Task 6: Documentation And Focused Verification

**Files:**
- Modify: `docs/BENCHMARKS.md`
- Modify: `docs/superpowers/plans/2026-07-12-benchmark-checkpoints-cache.md`

- [x] **Step 1: Document checkpoint usage**

Add to `docs/BENCHMARKS.md` after "Reproducing A Run":

```markdown
## Long-Run Checkpoints

Long benchmark runs should use a checkpoint directory. Agreement observations
and head-to-head records are appended as JSONL after each completed unit, so an
interrupted run can be inspected or resumed without losing all completed work.

```bash
python examples/cross_engine_benchmark.py run \
  --dataset benchmarks/positions-v1.json \
  --family native \
  --seeds 30 \
  --mcts-iterations 5000 \
  --h2h-positions 12 --h2h-seeds 5 \
  --checkpoint-dir benchmarks/results/native-seeds30.checkpoint \
  --output benchmarks/results/native-seeds30.json

python examples/cross_engine_benchmark.py run \
  --dataset benchmarks/positions-v1.json \
  --family native \
  --seeds 30 \
  --mcts-iterations 5000 \
  --h2h-positions 12 --h2h-seeds 5 \
  --checkpoint-dir benchmarks/results/native-seeds30.checkpoint \
  --resume \
  --output benchmarks/results/native-seeds30.json

python examples/cross_engine_benchmark.py report \
  --input benchmarks/results/native-seeds30.checkpoint
```

Use `--resume` only with the same dataset checksum and run configuration. The
checkpoint key includes position id, engine, configuration label, and seed for
agreement rows; head-to-head keys include position id, mover, responder, and
seed.
```

- [x] **Step 2: Run focused benchmark tests**

Run:

```bash
rtk .venv/bin/python -m pytest \
  tests/test_benchmark_checkpoint.py \
  tests/test_benchmark_agreement.py \
  tests/test_benchmark_h2h.py \
  tests/test_benchmark_bundle.py \
  tests/test_examples_demos.py::TestCrossEngineBenchmarkCLI \
  -v --no-cov
```

Expected: all selected tests pass.

- [x] **Step 3: Run `auto-lint.sh` before commit**

Run: `rtk ./auto-lint.sh`

Expected: exit 0.

- [x] **Step 4: Commit checkpoint implementation**

Run:

```bash
rtk git add benchmarks/checkpoint.py benchmarks/agreement.py benchmarks/head_to_head.py examples/cross_engine_benchmark.py tests/test_benchmark_checkpoint.py tests/test_benchmark_agreement.py tests/test_benchmark_h2h.py tests/test_examples_demos.py docs/BENCHMARKS.md docs/superpowers/plans/2026-07-12-benchmark-checkpoints-cache.md
rtk git commit -m "feat(benchmarks): add resumable result checkpoints"
```

Expected: one model-neutral commit.

Actual: checkpoint support was committed across focused follow-up commits,
including preflight-progress fixes after long native runs showed no early
observable output.

## Phase 1b: Parallel Benchmark Workers

Added after checkpointing because the checkpointed agreement-only native run
still projected to multiple hours on constrained hardware. This phase keeps
engine internals unchanged and parallelizes only independent benchmark units.

- [x] Add `workers` support to `benchmarks.agreement.run_agreement()` and
  `iter_agreement()`. `workers=1` preserves the old sequential path;
  `workers>1` uses process workers over independent
  `(position, adapter, seed)` observations.
- [x] Add `workers` support to `benchmarks.head_to_head.run_head_to_head()`
  and `iter_head_to_head()`. Each side-balanced game is an independent task.
- [x] Add CLI `run --workers`, defaulting to `1`.
- [x] Keep checkpoint writes parent-owned. Parallel workers return normal row
  dictionaries; the CLI appends JSONL and updates the manifest.
- [x] Ignore `workers` during resume validation because it changes execution
  scheduling, not benchmark semantics.
- [x] Document worker usage and memory tradeoffs in `docs/BENCHMARKS.md`.
- [x] Run focused tests, `auto-lint.sh`, and `dev-check.sh`; commit and push.
- [x] Add checkpointed `run --resume --skip-agreement` so a completed
  agreement-only checkpoint can run H2H later without recomputing agreement
  observations.

## Phase 2: Selection Cache

Do Phase 2 only after Phase 1 is merged or stable.

### Task 7: Add Optional Selection Cache Store

**Files:**
- Modify: `benchmarks/checkpoint.py` or create `benchmarks/cache.py`
- Modify: `benchmarks/agreement.py`
- Modify: `benchmarks/head_to_head.py`
- Modify: `examples/cross_engine_benchmark.py`
- Test: `tests/test_benchmark_checkpoint.py` or `tests/test_benchmark_cache.py`

Implement cache keys:

```python
def selection_cache_key(*, engine: str, config_label: str, qfen: str, seed: int | None) -> tuple:
    return (engine, config_label, qfen, seed)
```

Rules:

- Cache stores only completed move-selection observations, not partial engine state.
- Cache is opt-in via `run --selection-cache <path>`.
- Cache key must include `environment.git_sha` or `quantik_core_version` in manifest metadata so stale cache provenance is visible.
- Do not silently use cache entries across different `config_label` values.
- For fixed wall-clock configurations, cache is allowed but report must state cached observations were reused because wall-clock search is not perfectly reproducible.

Tests:

- A second run with the same dataset/config/seed should not call a sentinel adapter when a cache hit exists.
- A changed config label should miss the cache.
- Report/bundle should preserve cached observation rows exactly.

## Self-Review Checklist

- [ ] Checkpointed run can be interrupted and still leave `manifest.json`, `observations.jsonl`, and/or `h2h.jsonl`.
- [ ] `--resume` skips completed agreement and h2h keys.
- [ ] Final bundle JSON shape remains backward-compatible for `benchmarks.report.render_markdown`.
- [ ] `report --input <checkpoint-dir>` works without requiring final bundle JSON.
- [ ] Existing non-checkpoint `run` behavior still writes the same monolithic bundle shape.
- [ ] No model-specific commit trailers or commit messages.
- [ ] `auto-lint.sh` runs before commit.
- [ ] `dev-check.sh` runs before push.
