# Benchmark Part 2: Shared Dataset + Exact References — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new root-level `benchmarks/` package providing (a) a versioned,
checksummed, phase-bucketed dataset of shared benchmark positions and (b)
exact game-theoretic references (value + the COMPLETE set of optimal moves)
computed once and stored inside the dataset artifact.

**Architecture:** `benchmarks/dataset.py` samples valid non-terminal
positions by random playout into four phase buckets, dedups them globally
by `canonical_key()`, and serializes to JSON with a sha256 checksum.
`benchmarks/reference.py` solves each non-opening position exactly with the
full-depth `MinimaxEngine` under a per-position wall-clock budget; a
position is either solved with **no cutoff** (proven by completed
iterative-deepening depth ≥ remaining plies) or gets no reference at all —
never a depth-limited result labeled "exact".

**Tech Stack:** Python 3 stdlib (`json`, `hashlib`, `random`, `time`),
`quantik_core`, pytest. No new dependencies.

## Global Constraints

- `benchmarks/` mirrors the existing root-level `tuning/` package: it is
  NOT part of the built wheel and NOT in the `--cov=quantik_core` scope,
  but flake8 runs on it (`flake8 .`) and its tests run in the suite — keep
  code black-formatted and tests fast (< ~60s per file).
- Prerequisite: Part 1 merged (this part uses
  `MinimaxConfig.time_limit_s`, which already exists today, so part 2 is
  actually independent — but keep the execution order anyway).
- Dataset invariants (from the consistency brief): valid non-terminal
  positions only; player to move recorded; generated once, stored as a
  versioned artifact with seed, generator id, and checksum; canonical-key
  dedup; phase buckets opening 0–4 / early_mid 5–7 / late_mid 8–11 /
  endgame 12–16 pieces.
- Env setup + commit trailer: see "Shared conventions" in
  `2026-07-11-cross-engine-benchmark-0-INDEX.md`.

---

### Task 1: `benchmarks/dataset.py`

**Files:**
- Create: `benchmarks/__init__.py`
- Create: `benchmarks/dataset.py`
- Test: `tests/test_benchmark_dataset.py`

**Interfaces:**
- Consumes: `quantik_core` (`State`, `apply_move`,
  `generate_legal_moves_list`, `has_winning_line`, `count_total_pieces`,
  `get_current_player_from_counts`).
- Produces (used by parts 3–5):
  - `PHASES: Dict[str, Tuple[int, int]]` and `phase_of(pieces: int) -> str`
  - `generate(requested: Dict[str, int], seed: int) -> dict` — payload dict
    with keys `schema_version`, `generator`, `seed`, `requested`,
    `positions` (list of dicts with keys `id`, `qfen`, `phase`, `pieces`,
    `side_to_move`, `legal_moves`, `reference` (None until part 2 task 2)).
  - `checksum(payload: dict) -> str`, `save(payload, path) -> str`,
    `load(path) -> dict` (raises `ValueError` on checksum mismatch).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_dataset.py`:

```python
"""Tests for benchmarks.dataset: phase buckets, sampling, artifact I/O."""

import json

import pytest

from quantik_core import State
from quantik_core.game_utils import has_winning_line
from quantik_core.move import generate_legal_moves_list

from benchmarks import dataset


class TestPhases:
    @pytest.mark.parametrize(
        "pieces,expected",
        [
            (0, "opening"),
            (4, "opening"),
            (5, "early_mid"),
            (7, "early_mid"),
            (8, "late_mid"),
            (11, "late_mid"),
            (12, "endgame"),
            (16, "endgame"),
        ],
    )
    def test_phase_of(self, pieces, expected):
        assert dataset.phase_of(pieces) == expected

    def test_phase_of_rejects_out_of_range(self):
        with pytest.raises(ValueError):
            dataset.phase_of(17)


class TestGenerate:
    def test_positions_are_valid_nonterminal_and_deduped(self):
        payload = dataset.generate({"late_mid": 3, "endgame": 2}, seed=42)
        keys = set()
        for pos in payload["positions"]:
            bb = State.from_qfen(pos["qfen"]).bb
            assert not has_winning_line(bb)
            assert generate_legal_moves_list(bb)
            assert pos["phase"] == dataset.phase_of(pos["pieces"])
            assert pos["legal_moves"] == len(generate_legal_moves_list(bb))
            # One ply == one piece, so parity gives the side to move.
            assert pos["side_to_move"] == pos["pieces"] % 2
            keys.add(State.from_qfen(pos["qfen"]).bb)
        assert len(keys) == len(payload["positions"])

    def test_ids_are_sequential_and_unique(self):
        payload = dataset.generate({"late_mid": 3}, seed=7)
        assert [p["id"] for p in payload["positions"]] == [
            f"p{i:04d}" for i in range(len(payload["positions"]))
        ]

    def test_deterministic_for_same_seed(self):
        a = dataset.generate({"opening": 2, "late_mid": 2}, seed=5)
        b = dataset.generate({"opening": 2, "late_mid": 2}, seed=5)
        assert a == b

    def test_rejects_unknown_phase(self):
        with pytest.raises(ValueError):
            dataset.generate({"midgame": 3}, seed=1)


class TestArtifactIO:
    def test_save_load_roundtrip(self, tmp_path):
        payload = dataset.generate({"late_mid": 2}, seed=9)
        path = tmp_path / "positions.json"
        digest = dataset.save(payload, path)
        loaded = dataset.load(path)
        assert loaded["checksum"] == digest
        assert loaded["positions"] == payload["positions"]
        assert loaded["seed"] == 9

    def test_load_rejects_tampered_file(self, tmp_path):
        payload = dataset.generate({"late_mid": 2}, seed=9)
        path = tmp_path / "positions.json"
        dataset.save(payload, path)
        blob = json.loads(path.read_text())
        blob["positions"][0]["qfen"] = "AbC./..../..../...."
        path.write_text(json.dumps(blob))
        with pytest.raises(ValueError, match="checksum"):
            dataset.load(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_dataset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'benchmarks'`.

- [ ] **Step 3: Implement**

Create `benchmarks/__init__.py`:

```python
"""Cross-engine benchmark harness (GH issue #24).

Root-level tooling package like `tuning/` -- not shipped in the wheel, not
part of the `quantik_core` coverage scope. Entry point:
`examples/cross_engine_benchmark.py`. Methodology: `docs/BENCHMARKS.md`.
"""
```

Create `benchmarks/dataset.py`:

```python
"""Shared, versioned position dataset for the cross-engine benchmark.

Every engine is evaluated on exactly the same positions. The dataset is
generated once (random playouts into phase buckets, globally deduped by
`State.canonical_key()`), then stored as a JSON artifact carrying its
generation seed, generator id, schema version, and a sha256 checksum.
Positions are always valid and NON-terminal, with the player to move
recorded explicitly.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from quantik_core import State, apply_move
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
    has_winning_line,
)
from quantik_core.move import generate_legal_moves_list

SCHEMA_VERSION = 1
GENERATOR = "benchmarks.dataset.generate/v1"

# Phase buckets by pieces placed (== plies from the empty board).
PHASES: Dict[str, Tuple[int, int]] = {
    "opening": (0, 4),
    "early_mid": (5, 7),
    "late_mid": (8, 11),
    "endgame": (12, 16),
}


def phase_of(pieces: int) -> str:
    """Bucket name for a position with `pieces` pieces placed."""
    for name, (lo, hi) in PHASES.items():
        if lo <= pieces <= hi:
            return name
    raise ValueError(f"no phase bucket for {pieces} pieces")


def _random_position(rng: random.Random, plies: int) -> Optional[Tuple[int, ...]]:
    """Random legal playout to exactly `plies` pieces placed.

    Returns None (caller resamples) if the line hits a terminal state --
    a completed winning line, or a side left with no legal reply -- at or
    before the target ply.
    """
    bb: Tuple[int, ...] = State.empty().bb
    for _ in range(plies):
        moves = generate_legal_moves_list(bb)
        if not moves:
            return None
        bb = apply_move(bb, rng.choice(moves))  # type: ignore[assignment]
        if has_winning_line(bb):
            return None
    if not generate_legal_moves_list(bb):
        return None
    return bb


def generate(requested: Dict[str, int], seed: int) -> dict:
    """Sample `requested[phase]` distinct positions per phase bucket.

    Deep phases (especially endgame) have low acceptance rates -- random
    playouts often terminate early -- so after 500 attempts per requested
    position a bucket may come back short; callers should check the
    per-phase counts. A 16-piece non-terminal position cannot exist (a
    full board leaves the mover with no legal move), so sampling targets
    are capped at 15 plies.
    """
    unknown = set(requested) - set(PHASES)
    if unknown:
        raise ValueError(f"unknown phase(s): {sorted(unknown)}")
    rng = random.Random(seed)
    seen: set = set()
    positions: List[dict] = []
    for phase, (lo, hi) in PHASES.items():
        want = requested.get(phase, 0)
        found = 0
        attempts = 0
        while found < want and attempts < want * 500:
            attempts += 1
            plies = rng.randint(lo, min(hi, 15))
            bb = _random_position(rng, plies)
            if bb is None:
                continue
            key = State(bb).canonical_key()
            if key in seen:
                continue
            seen.add(key)
            p0, p1 = count_total_pieces(bb)
            positions.append(
                {
                    "id": f"p{len(positions):04d}",
                    "qfen": State(bb).to_qfen(),
                    "phase": phase,
                    "pieces": p0 + p1,
                    "side_to_move": get_current_player_from_counts(p0, p1),
                    "legal_moves": len(generate_legal_moves_list(bb)),
                    "reference": None,
                }
            )
            found += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "seed": seed,
        "requested": dict(requested),
        "positions": positions,
    }


def checksum(payload: dict) -> str:
    """sha256 over canonical JSON of everything except the checksum field."""
    stripped = {k: v for k, v in payload.items() if k != "checksum"}
    blob = json.dumps(stripped, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def save(payload: dict, path) -> str:
    """Write the artifact with its checksum; returns the checksum."""
    payload = dict(payload)
    payload["checksum"] = checksum(payload)
    Path(path).write_text(json.dumps(payload, indent=1, sort_keys=True))
    return payload["checksum"]


def load(path) -> dict:
    """Read and checksum-verify an artifact; ValueError on mismatch."""
    payload = json.loads(Path(path).read_text())
    expected = payload.get("checksum")
    actual = checksum(payload)
    if expected != actual:
        raise ValueError(
            f"dataset checksum mismatch: file says {expected}, content is {actual}"
        )
    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_dataset.py -v`
Expected: ALL PASS (endgame sampling makes this the slowest test file so
far; it should still finish in well under a minute).

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m black benchmarks tests
git add benchmarks/__init__.py benchmarks/dataset.py tests/test_benchmark_dataset.py
git commit -m "feat(benchmarks): phase-bucketed, checksummed shared position dataset"
```

---

### Task 2: `benchmarks/reference.py`

**Files:**
- Create: `benchmarks/reference.py`
- Test: `tests/test_benchmark_reference.py`

**Interfaces:**
- Consumes: `MinimaxEngine`/`MinimaxConfig` (with `time_limit_s`),
  `benchmarks.dataset.generate` payload shape.
- Produces (used by parts 3–5):
  - `move_key(move: Move) -> str` — `"player:shape:position"`, e.g. `"1:3:5"`.
  - `parse_move_key(key: str) -> Tuple[int, int, int]`.
  - `solve_position(bb, budget_s: float) -> Optional[dict]` — reference
    dict with keys `solved` (True), `no_cutoff` (True), `value` (+1/-1 for
    the side to move), `optimal_moves` (sorted list of move keys — the
    COMPLETE optimal set), `pv` (list of move keys), `nodes`,
    `solve_time_s`, `solver`; or `None` if the budget ran out.
  - `augment_with_references(payload, budget_s, skip_phases=("opening",)) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_reference.py`:

```python
"""Tests for benchmarks.reference: exact values, complete optimal sets,
budget behavior. Carries forward the regression guarantees of the old
examples/cross_engine_benchmark.py::optimal_moves tests."""

import pytest

from quantik_core import State, apply_move
from quantik_core.game_utils import has_winning_line
from quantik_core.move import Move, generate_legal_moves_list

from benchmarks import dataset, reference

# 8 pieces placed, P1 to move, three immediately winning moves (shape=3 at
# pos=5 completes a line; the other two leave P0 with no legal reply).
ANCHOR = ".ba./..CC/DcbD/cA.A"


class TestMoveKey:
    def test_roundtrip(self):
        move = Move(player=1, shape=3, position=5)
        assert reference.move_key(move) == "1:3:5"
        assert reference.parse_move_key("1:3:5") == (1, 3, 5)


class TestSolvePosition:
    def test_finds_the_mate_with_full_optimal_set(self):
        bb = State.from_qfen(ANCHOR).bb
        ref = reference.solve_position(bb, budget_s=30.0)
        assert ref is not None and ref["solved"] and ref["no_cutoff"]
        assert ref["value"] == 1  # side to move wins
        assert "1:3:5" in ref["optimal_moves"]
        # Every optimal move here is immediately terminal: it completes a
        # line or leaves the opponent with zero legal replies. (Regression:
        # terminal children must be scored directly, never solve()d.)
        for key in ref["optimal_moves"]:
            player, shape, position = reference.parse_move_key(key)
            child = apply_move(bb, Move(player=player, shape=shape, position=position))
            assert has_winning_line(child) or not generate_legal_moves_list(child)

    def test_optimal_moves_are_legal_and_sorted(self):
        bb = State.from_qfen(ANCHOR).bb
        ref = reference.solve_position(bb, budget_s=30.0)
        legal = {reference.move_key(m) for m in generate_legal_moves_list(bb)}
        assert set(ref["optimal_moves"]) <= legal
        assert ref["optimal_moves"] == sorted(ref["optimal_moves"])
        assert ref["pv"][0] in ref["optimal_moves"]

    def test_budget_exhaustion_returns_none_not_partial(self):
        # 2 pieces placed: exactly solving any child is intractable in a
        # tiny budget, so the reference must be None, never depth-limited.
        bb = State.from_qfen("Ab../..../..../....").bb
        assert reference.solve_position(bb, budget_s=0.05) is None


class TestAugment:
    def test_opening_skipped_and_solvable_phases_filled(self):
        payload = dataset.generate({"opening": 1, "late_mid": 1}, seed=11)
        reference.augment_with_references(payload, budget_s=15.0)
        by_phase = {p["phase"]: p for p in payload["positions"]}
        assert by_phase["opening"]["reference"] is None
        ref = by_phase["late_mid"]["reference"]
        assert ref is not None and ref["solved"]
        assert ref["value"] in (1, -1)
        assert ref["optimal_moves"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_reference.py -v`
Expected: FAIL — `ImportError: cannot import name 'reference'`.

- [ ] **Step 3: Implement**

Create `benchmarks/reference.py`:

```python
"""Exact game-theoretic references for benchmark positions.

A reference is either COMPLETE and EXACT -- game value plus the full set
of optimal moves, proven with no depth/time cutoff -- or absent. A
depth-limited minimax result is never labeled exact.

Exactness criterion: Quantik never exceeds 16 plies and one ply places one
piece, so a child position with c pieces placed has at most 16 - c plies
remaining. An iterative-deepening search whose last COMPLETED depth is
>= 16 - c evaluated only true terminal leaves, i.e. its value is exact.

An engine scores an agreement hit when its move is IN the optimal set --
`optimal_moves` is the complete set of ties, not one arbitrary pick.
"""

from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional, Tuple

import quantik_core
from quantik_core import State, apply_move
from quantik_core.game_utils import count_total_pieces, has_winning_line
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import Move, generate_legal_moves_list

_WIN = float("inf")


def move_key(move: Move) -> str:
    """Stable string id for a move: 'player:shape:position'."""
    return f"{move.player}:{move.shape}:{move.position}"


def parse_move_key(key: str) -> Tuple[int, int, int]:
    """Inverse of `move_key`: '1:3:5' -> (1, 3, 5)."""
    player, shape, position = (int(part) for part in key.split(":"))
    return player, shape, position


def solve_position(bb, budget_s: float) -> Optional[dict]:
    """Exact value + COMPLETE optimal-move set for `bb`, or None.

    Returns None when `budget_s` (wall-clock) runs out before every child
    is solved without a cutoff. Never returns a partial or depth-limited
    reference.

    A child that is itself terminal -- it completes a line, or leaves the
    opponent with no legal reply -- is a win for the mover and is scored
    +inf directly: `MinimaxEngine.search` raises on no-legal-move states,
    and +inf dominating every finite mate score matches the engine's own
    "prefer the faster win" convention. All non-terminal children are
    scored with the same fresh-root convention (-solve(child)), so the
    argmax is comparable across children.
    """
    start = time.monotonic()
    deadline = start + budget_s
    pieces = sum(count_total_pieces(bb))
    scored: Dict[str, float] = {}
    pvs: Dict[str, List[str]] = {}
    total_nodes = 0
    for move in generate_legal_moves_list(bb):
        key = move_key(move)
        child = apply_move(bb, move)
        if has_winning_line(child) or not generate_legal_moves_list(child):
            scored[key] = _WIN
            pvs[key] = [key]
            continue
        remaining_budget = deadline - time.monotonic()
        if remaining_budget <= 0:
            return None
        engine = MinimaxEngine(
            MinimaxConfig(max_depth=16, time_limit_s=remaining_budget)
        )
        result = engine.search(State(child))
        total_nodes += result.nodes
        if result.depth_reached < 16 - (pieces + 1):
            return None  # cut off before exhausting the child's tree
        scored[key] = -result.score
        pvs[key] = [key, *(move_key(m) for m in result.pv)]
    best = max(scored.values())
    value = 1 if best > 0 else (-1 if best < 0 else 0)
    optimal = sorted(k for k, v in scored.items() if v == best)
    return {
        "solved": True,
        "no_cutoff": True,
        "value": value,
        "optimal_moves": optimal,
        "pv": pvs[optimal[0]],
        "nodes": total_nodes,
        "solve_time_s": round(time.monotonic() - start, 6),
        "solver": (
            f"MinimaxEngine(max_depth=16) quantik-core "
            f"{quantik_core.__version__}"
        ),
    }


def augment_with_references(
    payload: dict, budget_s: float, skip_phases: Iterable[str] = ("opening",)
) -> dict:
    """Fill each position's 'reference' field in place; returns `payload`.

    Positions in `skip_phases` -- by default the opening bucket, where an
    exact solve is intractable in pure Python -- keep reference=None and
    therefore never contribute to exact move-agreement figures (they form
    the separate heuristic benchmark).
    """
    skip = set(skip_phases)
    for pos in payload["positions"]:
        if pos["phase"] in skip:
            pos["reference"] = None
            continue
        bb = State.from_qfen(pos["qfen"]).bb
        pos["reference"] = solve_position(bb, budget_s)
    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_reference.py tests/test_benchmark_dataset.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Lint gate and commit**

```bash
.venv/bin/python -m black benchmarks tests
.venv/bin/python -m flake8 benchmarks tests/test_benchmark_reference.py --count
git add benchmarks/reference.py tests/test_benchmark_reference.py
git commit -m "feat(benchmarks): exact reference solver with complete optimal-move sets"
```

---

## Self-review checklist

- [ ] No position with a `reference` was ever solved with a cutoff
      (`solve_position` returns None instead — grep the module: the only
      `return` paths are `None` or the fully solved dict).
- [ ] `optimal_moves` is the complete tie set, not a single move.
- [ ] Dataset artifact records: schema version, generator id, seed,
      per-position side-to-move, checksum. Opening bucket present but
      reference-less.
- [ ] Both test files pass together and run fast.
