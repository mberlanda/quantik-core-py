# Python/Rust API Portability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Python package enforce the shared Quantik API and self-play data contracts used by the companion Rust crate.

**Architecture:** Keep core game primitives stable and language-neutral: QFEN, bitboard order, action indexing, and decisive value semantics. Add Python ML-data helpers in a dedicated `quantik_core.ml_data` module so Rust self-play output can be validated and consumed without widening the top-level public API.

**Tech Stack:** Python 3.12+, NumPy, pytest, existing `quantik_core` QFEN/move/state-validator APIs, Rust JSONL self-play output from `quantik-core-rust`.

---

## Context

The Rust plan `2026-07-13-crates-io-packaging-and-ml-data-pipeline.md` makes Rust responsible for compute-heavy MCTS self-play and exports one JSONL row per ply. The Python library should not duplicate that heavy loop. Python should enforce the schema, load the rows, encode tensors, train models, and evaluate those models in the existing benchmark harness.

## File Structure

- Create: `docs/API_PORTABILITY.md` - human-readable Python/Rust shared contracts.
- Create: `src/quantik_core/ml_data.py` - schema validation, JSONL loading, QFEN tensor encoding, policy normalization.
- Create: `tests/fixtures/selfplay_v1.jsonl` - golden JSONL rows matching the Rust exporter schema.
- Create: `tests/test_ml_data.py` - CI enforcement for the schema, tensor encoding, legality checks, and decisive values.
- Modify later: `examples/cross_engine_benchmark.py` - add a trained-model adapter after a real model exists.

## Task 1: Document Cross-Language API Contract

**Files:**
- Create: `docs/API_PORTABILITY.md`

- [x] **Step 1: Define shared state and action conventions**

Add a table documenting board positions `0..15`, shape ids `0..3`, player ids `0..1`, bitboard order, QFEN, and action index `shape * 16 + position`.

- [x] **Step 2: Define Rust self-play row schema**

Document the JSONL fields `game_id`, `ply`, `qfen`, `side_to_move`, `policy`, and `value`, including the rule that `value` is only `+1.0` or `-1.0`.

- [x] **Step 3: Define tensor encoding**

Document the `(9, 4, 4)` tensor layout: eight player/shape planes plus one side-to-move plane.

## Task 2: Add Python ML Data Contract Helpers

**Files:**
- Create: `src/quantik_core/ml_data.py`
- Create: `tests/fixtures/selfplay_v1.jsonl`
- Create: `tests/test_ml_data.py`

- [x] **Step 1: Add golden JSONL fixture**

Create `tests/fixtures/selfplay_v1.jsonl` with valid rows:

```jsonl
{"game_id":0,"ply":0,"qfen":"..../..../..../....","side_to_move":0,"policy":[{"shape":0,"position":0,"visits":3},{"shape":1,"position":5,"visits":1}],"value":1.0}
{"game_id":0,"ply":1,"qfen":"A.../..../..../....","side_to_move":1,"policy":[{"shape":0,"position":10,"visits":2},{"shape":1,"position":1,"visits":6}],"value":-1.0}
```

- [x] **Step 2: Implement schema dataclasses and parser**

Create `PolicyVisit` and `SelfPlayRow`, plus `parse_selfplay_row(record)` that validates qfen, side-to-move, legal policy moves, positive visits, and decisive values.

- [x] **Step 3: Implement tensor and policy encoders**

Create `qfen_to_tensor(qfen, side_to_move)` returning `(9, 4, 4)` and `policy_visits_to_distribution(policy)` returning a 64-slot normalized NumPy vector.

- [x] **Step 4: Add tests**

Test fixture loading, tensor channel placement, policy normalization, zero-value rejection, side-to-move mismatch rejection, and illegal policy rejection.

## Task 3: Cross-Repo Generated Artifact Smoke

**Files:**
- Future modify: `.github/workflows/test.yml`
- Future create: `benchmarks/results/selfplay-smoke.jsonl` or CI artifact download step

- [ ] **Step 1: Wait for Rust Task 6 output**

Do not fabricate a generated artifact. Use output from the Rust exporter command:

```bash
cargo run --release --example selfplay_export -p quantik-core -- --games 5 --iterations 500 --seed 1 --out /tmp/selfplay-smoke.jsonl
```

Expected: a JSONL file with non-empty policy arrays and values only in `{-1.0, 1.0}`.

- [ ] **Step 2: Add Python smoke validation command**

Use the Python loader to validate the generated artifact:

```bash
.venv/bin/python - <<'PY'
from quantik_core.ml_data import load_selfplay_jsonl
rows = load_selfplay_jsonl('/tmp/selfplay-smoke.jsonl')
assert rows
print(f'validated {len(rows)} rows')
PY
```

Expected: no exception and a positive row count.

## Task 4: Python Training Dataset

**Files:**
- Future create: `src/quantik_core/ml_dataset.py`
- Future create: `tests/test_ml_dataset.py`

- [ ] **Step 1: Build on `SelfPlayRow`**

Create a dataset adapter that maps rows to `(tensor, policy_distribution, value)` triples, using `qfen_to_tensor()` and `policy_visits_to_distribution()`.

- [ ] **Step 2: Keep PyTorch optional**

Keep the base loader NumPy-only. Add PyTorch integration behind an optional dependency when the training loop is introduced.

## Self-Review

- Spec coverage: This plan covers the Rust handoff schema, Python tensor encoding, policy normalization, decisive value validation, and future benchmark/model integration.
- Placeholder scan: Future tasks are explicitly blocked on real Rust exporter output; no fake schema or fake model is proposed.
- Type consistency: `PolicyVisit`, `SelfPlayRow`, `qfen_to_tensor`, `policy_visits_to_distribution`, and `load_selfplay_jsonl` are the stable names used throughout.
