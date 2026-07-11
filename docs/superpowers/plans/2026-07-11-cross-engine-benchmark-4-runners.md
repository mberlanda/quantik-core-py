# Benchmark Part 4: Agreement, Head-to-Head, Stability Runners — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** The three measurement runners over the shared dataset:
move-agreement vs the exact reference (plus computational-cost
aggregation), paired side-balanced head-to-head games, and across-seed
stability aggregation for stochastic engines.

**Architecture:** `run_agreement` produces one raw observation row per
(adapter, position, seed) — the single source of truth that BOTH the
agreement/cost tables and the stability table aggregate from (stochastic
engines are never re-run separately for stability). `run_head_to_head`
plays each sampled position twice per seed, once with each engine as the
side to move, crediting the actual engine/color mapping. All aggregation
functions are pure (list-of-dicts in, list-of-dicts out) so part 5 can
serialize everything as JSON.

**Tech Stack:** Python 3 stdlib, parts 2–3 (`benchmarks.dataset`,
`benchmarks.reference`, `benchmarks.adapters`, `benchmarks.metrics`).

## Global Constraints

- Prerequisites: parts 2 and 3 merged.
- The same ordered seed list is used for every stochastic adapter; a
  deterministic adapter runs each position exactly once.
- A row's `hit` is `True` iff the move is in the COMPLETE optimal set;
  `None` (excluded from agreement) when the position has no exact
  reference. Never compare one stochastic run against the deterministic
  reference — stability aggregates per-seed agreement first.
- Quantik has no draws; head-to-head aggregates still carry a `draws: 0`
  field so the report table matches the brief's required shape.
- Env setup + commit trailer: see "Shared conventions" in
  `2026-07-11-cross-engine-benchmark-0-INDEX.md`.

---

### Task 1: `benchmarks/agreement.py`

**Files:**
- Create: `benchmarks/agreement.py`
- Test: `tests/test_benchmark_agreement.py`

**Interfaces:**
- Consumes: `EngineAdapter.select`, dataset payload dicts, reference dicts,
  `benchmarks.metrics`.
- Produces (used by part 5):
  - `run_agreement(adapters, payload, seeds, track_memory=False) -> List[dict]`
    — rows are `MoveObservation.to_dict()` plus `phase` and `hit`
    (True/False/None).
  - `aggregate_agreement(rows) -> List[dict]` — per (engine, config_label,
    phase): `n`, `hits`, `agreement`, `ci95_low`, `ci95_high`.
  - `aggregate_cost(rows) -> List[dict]` — per (engine, config_label):
    `n`, `median_time_s`, `p95_time_s`, `median_nodes`,
    `peak_memory_bytes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_agreement.py`:

```python
"""Tests for benchmarks.agreement: raw observation rows + aggregations."""

import pytest

from quantik_core import State
from quantik_core.move import generate_legal_moves_list

from benchmarks import reference
from benchmarks.adapters import MinimaxAdapter, RandomAdapter
from benchmarks.agreement import aggregate_agreement, aggregate_cost, run_agreement

ANCHOR = ".ba./..CC/DcbD/cA.A"


@pytest.fixture(scope="module")
def payload():
    """One exactly-solved anchor position + one reference-less position."""
    bb = State.from_qfen(ANCHOR).bb
    solved = {
        "id": "p0000",
        "qfen": ANCHOR,
        "phase": "late_mid",
        "pieces": 8,
        "side_to_move": 1,
        "legal_moves": len(generate_legal_moves_list(bb)),
        "reference": reference.solve_position(bb, budget_s=30.0),
    }
    heuristic = {
        "id": "p0001",
        "qfen": "Ab../..../..../....",
        "phase": "opening",
        "pieces": 2,
        "side_to_move": 0,
        "legal_moves": len(
            generate_legal_moves_list(State.from_qfen("Ab../..../..../....").bb)
        ),
        "reference": None,
    }
    return {"positions": [solved, heuristic]}


class TestRunAgreement:
    def test_row_counts_and_seed_scheduling(self, payload):
        rows = run_agreement(
            [MinimaxAdapter(max_depth=2), RandomAdapter()],
            payload,
            seeds=[0, 1, 2],
        )
        # 2 positions x (1 deterministic run + 3 stochastic runs) = 8 rows.
        assert len(rows) == 8
        random_seeds = sorted(
            r["seed"] for r in rows if r["engine"] == "random" and
            r["position_id"] == "p0000"
        )
        assert random_seeds == [0, 1, 2]

    def test_hit_semantics(self, payload):
        # time_limit_s caps the depth-16 search on the OPENING position --
        # without it, iterative deepening would attempt a full open-game
        # solve (intractable). The anchor still solves exactly within 2s.
        rows = run_agreement(
            [MinimaxAdapter(max_depth=16, time_limit_s=2.0)], payload, seeds=[0]
        )
        by_position = {r["position_id"]: r for r in rows}
        # Full-depth minimax must pick an optimal move on the solved anchor.
        assert by_position["p0000"]["hit"] is True
        # No exact reference => hit is None, not False.
        assert by_position["p0001"]["hit"] is None
        assert by_position["p0000"]["phase"] == "late_mid"


class TestAggregations:
    def test_aggregate_agreement_excludes_unsolved(self, payload):
        # See test_hit_semantics: the time cap keeps the opening position
        # from triggering an intractable full solve.
        rows = run_agreement(
            [MinimaxAdapter(max_depth=16, time_limit_s=2.0)], payload, seeds=[0]
        )
        agg = aggregate_agreement(rows)
        assert len(agg) == 1  # only the solved late_mid position counts
        entry = agg[0]
        assert (entry["engine"], entry["phase"]) == ("minimax", "late_mid")
        assert entry["n"] == 1 and entry["hits"] == 1
        assert entry["agreement"] == 1.0
        assert 0.0 <= entry["ci95_low"] <= entry["ci95_high"] <= 1.0

    def test_aggregate_cost_shapes(self, payload):
        rows = run_agreement(
            [MinimaxAdapter(max_depth=2), RandomAdapter()], payload, seeds=[0, 1]
        )
        agg = {(e["engine"]): e for e in aggregate_cost(rows)}
        assert agg["minimax"]["median_nodes"] is not None
        assert agg["minimax"]["median_time_s"] >= 0.0
        assert agg["minimax"]["p95_time_s"] >= agg["minimax"]["median_time_s"]
        # RandomAdapter reports no nodes; the aggregate must tolerate that.
        assert agg["random"]["median_nodes"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_agreement.py -v`
Expected: FAIL — `ModuleNotFoundError` on `benchmarks.agreement`.

- [ ] **Step 3: Implement**

Create `benchmarks/agreement.py`:

```python
"""Move-agreement vs the exact reference + computational-cost aggregation.

`run_agreement` produces the benchmark's raw per-move observation rows --
the single source of truth that the agreement, cost, AND stability tables
are all aggregated from. Engines are never re-run per table.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from quantik_core import State

from benchmarks.metrics import median, percentile, wilson_ci


def run_agreement(
    adapters,
    payload: dict,
    seeds: Sequence[int],
    track_memory: bool = False,
) -> List[dict]:
    """One row per (adapter, position, seed-run).

    Stochastic adapters run once per seed in `seeds` -- the SAME ordered
    seed list for every adapter -- while deterministic adapters run each
    position exactly once (with seeds[0] recorded for traceability).
    Row = MoveObservation.to_dict() + `phase` + `hit`, where `hit` is True
    iff the move belongs to the COMPLETE optimal set, and None when the
    position has no exact reference (heuristic-only positions never count
    toward exact agreement).
    """
    if not seeds:
        raise ValueError("seeds must be a non-empty ordered list")
    rows: List[dict] = []
    for pos in payload["positions"]:
        bb = State.from_qfen(pos["qfen"]).bb
        ref = pos.get("reference")
        optimal = set(ref["optimal_moves"]) if ref else None
        for adapter in adapters:
            adapter_seeds = list(seeds) if adapter.stochastic else [seeds[0]]
            for seed in adapter_seeds:
                _, obs = adapter.select(
                    bb, pos["id"], seed=seed, track_memory=track_memory
                )
                row = obs.to_dict()
                row["phase"] = pos["phase"]
                row["hit"] = (obs.move in optimal) if optimal is not None else None
                rows.append(row)
    return rows


def aggregate_agreement(rows: List[dict]) -> List[dict]:
    """Exact move agreement per (engine, config_label, phase).

    Only rows with an exact reference (`hit` is not None) contribute. The
    95% CI is a Wilson interval; for stochastic engines the n counts
    position x seed runs, so seeds contribute to the same cell (the
    stability table separates the across-seed spread).
    """
    groups: Dict[Tuple[str, str, str], List[dict]] = {}
    for row in rows:
        if row["hit"] is None:
            continue
        key = (row["engine"], row["config_label"], row["phase"])
        groups.setdefault(key, []).append(row)
    out: List[dict] = []
    for (engine, label, phase), grp in sorted(groups.items()):
        hits = sum(1 for r in grp if r["hit"])
        n = len(grp)
        lo, hi = wilson_ci(hits, n)
        out.append(
            {
                "engine": engine,
                "config_label": label,
                "phase": phase,
                "n": n,
                "hits": hits,
                "agreement": hits / n,
                "ci95_low": lo,
                "ci95_high": hi,
            }
        )
    return out


def aggregate_cost(rows: List[dict]) -> List[dict]:
    """Computational cost per (engine, config_label), from MEASURED work."""
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for row in rows:
        groups.setdefault((row["engine"], row["config_label"]), []).append(row)
    out: List[dict] = []
    for (engine, label), grp in sorted(groups.items()):
        walls = [r["wall_time_s"] for r in grp]
        nodes = [float(r["nodes"]) for r in grp if r["nodes"] is not None]
        peaks = [
            r["peak_memory_bytes"]
            for r in grp
            if r["peak_memory_bytes"] is not None
        ]
        out.append(
            {
                "engine": engine,
                "config_label": label,
                "n": len(grp),
                "median_time_s": median(walls),
                "p95_time_s": percentile(walls, 95.0),
                "median_nodes": median(nodes) if nodes else None,
                "peak_memory_bytes": max(peaks) if peaks else None,
            }
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_agreement.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m black benchmarks tests
git add benchmarks/agreement.py tests/test_benchmark_agreement.py
git commit -m "feat(benchmarks): agreement runner + agreement/cost aggregation"
```

---

### Task 2: `benchmarks/head_to_head.py`

**Files:**
- Create: `benchmarks/head_to_head.py`
- Test: `tests/test_benchmark_h2h.py`

**Interfaces:**
- Consumes: `EngineAdapter.select` (returns `(Move, MoveObservation)`),
  `quantik_core` game utilities.
- Produces (used by part 5):
  - `play_game(mover, responder, bb, seed) -> Tuple[str, int]` — winner
    adapter name + plies played.
  - `run_head_to_head(adapter_a, adapter_b, positions, seeds) -> List[dict]`
    — records with keys `position_id`, `phase`, `mover`, `responder`,
    `winner`, `plies`, `seed`.
  - `aggregate_head_to_head(records, name_a, name_b) -> dict` — keys
    `engine_a`, `engine_b`, `games`, `paired_positions`, `a_wins`,
    `b_wins`, `draws` (always 0), `a_win_rate`, `a_win_rate_ci95`
    (two-element list, Wilson), `a_wins_as_mover`, `b_wins_as_mover`,
    `by_phase`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_h2h.py`:

```python
"""Tests for benchmarks.head_to_head: paired, side-balanced games.

Carries forward the old examples/cross_engine_benchmark.py::play_from
regression guarantees: the engine credited with a win must be bound to
whichever color is ACTUALLY to move at the sampled position, for both
parities."""

from quantik_core import State
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
)
from quantik_core.move import generate_legal_moves_list

from benchmarks.adapters import MinimaxAdapter, RandomAdapter
from benchmarks.head_to_head import (
    aggregate_head_to_head,
    play_game,
    run_head_to_head,
)

ANCHOR = ".ba./..CC/DcbD/cA.A"  # P1 to move, immediate win available
P0_ANCHOR = "AbC./d.../..../...."  # P0 to move, immediate win (D at pos 3)


def _position(qfen, pos_id, phase="late_mid"):
    bb = State.from_qfen(qfen).bb
    p0, p1 = count_total_pieces(bb)
    return {
        "id": pos_id,
        "qfen": qfen,
        "phase": phase,
        "pieces": p0 + p1,
        "side_to_move": get_current_player_from_counts(p0, p1),
        "legal_moves": len(generate_legal_moves_list(bb)),
        "reference": None,
    }


class TestPlayGame:
    def test_credits_mover_when_p1_to_move(self):
        bb = State.from_qfen(ANCHOR).bb
        assert get_current_player_from_counts(*count_total_pieces(bb)) == 1
        winner, plies = play_game(
            MinimaxAdapter(max_depth=16), RandomAdapter(), bb, seed=0
        )
        assert winner == "minimax"
        assert plies == 1  # immediate mate

    def test_credits_mover_when_p0_to_move(self):
        bb = State.from_qfen(P0_ANCHOR).bb
        assert get_current_player_from_counts(*count_total_pieces(bb)) == 0
        winner, _ = play_game(
            MinimaxAdapter(max_depth=16), RandomAdapter(), bb, seed=0
        )
        assert winner == "minimax"


class TestRunHeadToHead:
    def test_paired_side_balanced_records(self):
        positions = [_position(ANCHOR, "p0000")]
        records = run_head_to_head(
            MinimaxAdapter(max_depth=16), RandomAdapter(), positions, seeds=[0, 1]
        )
        # 1 position x 2 seeds x 2 orientations = 4 games.
        assert len(records) == 4
        for seed in (0, 1):
            movers = sorted(r["mover"] for r in records if r["seed"] == seed)
            assert movers == ["minimax", "random"]  # both orientations played

    def test_aggregate_shape_and_draws_impossible(self):
        positions = [_position(ANCHOR, "p0000")]
        records = run_head_to_head(
            MinimaxAdapter(max_depth=16), RandomAdapter(), positions, seeds=[0]
        )
        agg = aggregate_head_to_head(records, "minimax", "random")
        assert agg["games"] == 2
        assert agg["paired_positions"] == 1
        assert agg["a_wins"] + agg["b_wins"] == agg["games"]
        assert agg["draws"] == 0
        assert agg["a_win_rate"] == agg["a_wins"] / agg["games"]
        lo, hi = agg["a_win_rate_ci95"]
        assert 0.0 <= lo <= agg["a_win_rate"] <= hi <= 1.0
        assert "late_mid" in agg["by_phase"]
        # The exact engine wins at least the game it moves first in.
        assert agg["a_wins_as_mover"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_h2h.py -v`
Expected: FAIL — `ModuleNotFoundError` on `benchmarks.head_to_head`.

- [ ] **Step 3: Implement**

Create `benchmarks/head_to_head.py`:

```python
"""Paired, side-balanced head-to-head games from shared positions.

For every sampled position and seed, TWO games are played: engine A as
the side already to move, then engine B as the side to move -- so
first-move advantage is controlled per position pair. Results are
attributed to the actual engine/color mapping: sampled positions can have
EITHER color to move, so engine names bind to whichever color moves next,
never a hard-coded player 0.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from quantik_core import State, apply_move
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
    has_winning_line,
)
from quantik_core.move import generate_legal_moves_list

from benchmarks.metrics import wilson_ci


def play_game(mover, responder, bb, seed: int) -> Tuple[str, int]:
    """Play out from `bb`; `mover` is the side ALREADY to move there.

    Both terminal conditions -- a completed line, or no legal moves --
    lose for the side whose turn it currently is (the same convention as
    MinimaxEngine._negamax). Quantik cannot draw. Returns
    (winner adapter name, plies played from bb).
    """
    p0, p1 = count_total_pieces(bb)
    turn = get_current_player_from_counts(p0, p1)
    engines = {turn: mover, 1 - turn: responder}
    plies = 0
    while True:
        if has_winning_line(bb) or not generate_legal_moves_list(bb):
            return engines[1 - turn].name, plies
        move, _ = engines[turn].select(bb, position_id="h2h", seed=seed)
        bb = apply_move(bb, move)
        turn ^= 1
        plies += 1


def run_head_to_head(
    adapter_a, adapter_b, positions: Sequence[dict], seeds: Sequence[int]
) -> List[dict]:
    """Both orientations per (position, seed), same wall-clock settings."""
    records: List[dict] = []
    for pos in positions:
        bb = State.from_qfen(pos["qfen"]).bb
        for seed in seeds:
            for mover, responder in ((adapter_a, adapter_b), (adapter_b, adapter_a)):
                winner, plies = play_game(mover, responder, bb, seed)
                records.append(
                    {
                        "position_id": pos["id"],
                        "phase": pos["phase"],
                        "mover": mover.name,
                        "responder": responder.name,
                        "winner": winner,
                        "plies": plies,
                        "seed": seed,
                    }
                )
    return records


def aggregate_head_to_head(records: List[dict], name_a: str, name_b: str) -> dict:
    """Totals, as-mover splits, and per-phase splits for one engine pair.

    `draws` is always 0 -- Quantik has no draws -- but the field is kept
    so the report table matches the brief's required shape.
    """

    def wins(rows: List[dict], name: str) -> int:
        return sum(1 for r in rows if r["winner"] == name)

    by_phase: Dict[str, List[dict]] = {}
    for record in records:
        by_phase.setdefault(record["phase"], []).append(record)
    a_wins = wins(records, name_a)
    ci_low, ci_high = wilson_ci(a_wins, len(records))
    return {
        "engine_a": name_a,
        "engine_b": name_b,
        "games": len(records),
        "paired_positions": len(
            {(r["position_id"], r["seed"]) for r in records}
        ),
        "a_wins": a_wins,
        "b_wins": wins(records, name_b),
        "draws": 0,
        "a_win_rate": a_wins / len(records) if records else 0.0,
        "a_win_rate_ci95": [ci_low, ci_high],
        "a_wins_as_mover": wins(
            [r for r in records if r["mover"] == name_a], name_a
        ),
        "b_wins_as_mover": wins(
            [r for r in records if r["mover"] == name_b], name_b
        ),
        "by_phase": {
            phase: {
                "games": len(rows),
                "a_wins": wins(rows, name_a),
                "b_wins": wins(rows, name_b),
            }
            for phase, rows in sorted(by_phase.items())
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_h2h.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m black benchmarks tests
git add benchmarks/head_to_head.py tests/test_benchmark_h2h.py
git commit -m "feat(benchmarks): paired side-balanced head-to-head runner"
```

---

### Task 3: `benchmarks/stability.py`

**Files:**
- Create: `benchmarks/stability.py`
- Test: `tests/test_benchmark_stability.py`

**Interfaces:**
- Consumes: agreement rows from `run_agreement` (fields `engine`,
  `config_label`, `position_id`, `move`, `seed`, `hit`).
- Produces (used by part 5):
  - `aggregate_stability(rows) -> List[dict]` — per (engine,
    config_label): `seeds`, `move_consistency`, `agreement_mean`,
    `agreement_std`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_stability.py`:

```python
"""Tests for benchmarks.stability. Uses synthetic rows so the arithmetic
is verified exactly, without running any engine."""

import pytest

from benchmarks.stability import aggregate_stability


def _row(engine, position_id, seed, move, hit):
    return {
        "engine": engine,
        "config_label": engine,
        "position_id": position_id,
        "seed": seed,
        "move": move,
        "hit": hit,
    }


class TestAggregateStability:
    def test_known_arithmetic(self):
        rows = [
            # position p1: modal move chosen by 2 of 3 seeds
            _row("fake", "p1", 0, "1:0:0", True),
            _row("fake", "p1", 1, "1:0:0", True),
            _row("fake", "p1", 2, "1:0:1", False),
            # position p2: perfectly consistent, always optimal
            _row("fake", "p2", 0, "1:2:3", True),
            _row("fake", "p2", 1, "1:2:3", True),
            _row("fake", "p2", 2, "1:2:3", True),
        ]
        (entry,) = aggregate_stability(rows)
        assert entry["engine"] == "fake"
        assert entry["seeds"] == 3
        # mean of (2/3, 3/3)
        assert entry["move_consistency"] == pytest.approx(5 / 6)
        # per-seed agreement: 1.0, 1.0, 0.5
        assert entry["agreement_mean"] == pytest.approx(5 / 6)
        assert entry["agreement_std"] == pytest.approx(0.28868, abs=1e-4)

    def test_unsolved_positions_do_not_count_toward_agreement(self):
        rows = [
            _row("fake", "p1", 0, "1:0:0", None),
            _row("fake", "p1", 1, "1:0:0", None),
        ]
        (entry,) = aggregate_stability(rows)
        assert entry["move_consistency"] == 1.0
        assert entry["agreement_mean"] == 0.0  # no solved positions at all
        assert entry["agreement_std"] == 0.0

    def test_deterministic_engine_single_seed(self):
        rows = [_row("minimax", "p1", 0, "1:0:0", True)]
        (entry,) = aggregate_stability(rows)
        assert entry["seeds"] == 1
        assert entry["move_consistency"] == 1.0
        assert entry["agreement_std"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_stability.py -v`
Expected: FAIL — `ModuleNotFoundError` on `benchmarks.stability`.

- [ ] **Step 3: Implement**

Create `benchmarks/stability.py`:

```python
"""Across-seed stability of stochastic engines.

Aggregates the SAME raw rows produced by `benchmarks.agreement
.run_agreement` -- engines are not re-run. Never compares one stochastic
run against the deterministic reference: agreement is computed per seed
first, then summarized as mean/std across seeds.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

from benchmarks.metrics import mean_std


def aggregate_stability(rows: List[dict]) -> List[dict]:
    """Per (engine, config_label): seed count, move consistency, and the
    across-seed agreement mean/std.

    Move consistency: for each position, the fraction of that engine's
    seed runs choosing the modal move; averaged over positions. 1.0 means
    the seed never changes the move. Agreement mean/std: per-seed
    agreement over exactly-solved positions only (`hit` not None),
    aggregated across seeds.
    """
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for row in rows:
        groups.setdefault((row["engine"], row["config_label"]), []).append(row)
    out: List[dict] = []
    for (engine, label), grp in sorted(groups.items()):
        seeds = sorted({r["seed"] for r in grp})
        moves_by_position: Dict[str, List[str]] = {}
        for r in grp:
            moves_by_position.setdefault(r["position_id"], []).append(r["move"])
        consistency_mean, _ = mean_std(
            [
                Counter(moves).most_common(1)[0][1] / len(moves)
                for moves in moves_by_position.values()
            ]
        )
        per_seed_agreement: List[float] = []
        for seed in seeds:
            solved = [r for r in grp if r["seed"] == seed and r["hit"] is not None]
            if solved:
                per_seed_agreement.append(
                    sum(1 for r in solved if r["hit"]) / len(solved)
                )
        agreement_mean, agreement_std = mean_std(per_seed_agreement)
        out.append(
            {
                "engine": engine,
                "config_label": label,
                "seeds": len(seeds),
                "move_consistency": consistency_mean,
                "agreement_mean": agreement_mean,
                "agreement_std": agreement_std,
            }
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_stability.py tests/test_benchmark_agreement.py tests/test_benchmark_h2h.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Lint gate and commit**

```bash
.venv/bin/python -m black benchmarks tests
.venv/bin/python -m flake8 benchmarks --count
git add benchmarks/stability.py tests/test_benchmark_stability.py
git commit -m "feat(benchmarks): across-seed stability aggregation"
```

---

## Self-review checklist

- [ ] Stability aggregates the agreement rows — no engine re-runs anywhere
      in `stability.py` (it imports nothing from `quantik_core`).
- [ ] Head-to-head: every (position, seed) yields exactly two records with
      swapped mover/responder; winner is an adapter NAME, never "P0"/"P1".
- [ ] `hit=None` rows are excluded from agreement and from per-seed
      agreement, but still count toward move consistency.
- [ ] All part-4 test files pass together in < ~60s.
