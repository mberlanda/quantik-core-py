# Benchmark Part 3: Engine Adapters, Stats Helpers, Correctness Preflight — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** A uniform adapter layer that runs any engine on a position and
records *effective work* (wall/CPU time, nodes, iterations, depth, memory —
brief §4), small statistics helpers (Wilson CI, percentiles), and a
correctness preflight that fails the benchmark early on invariant
violations (brief §7).

**Architecture:** `benchmarks/adapters.py` wraps each engine behind
`EngineAdapter.select(bb, position_id, seed, track_memory) ->
(Move, MoveObservation)`; the base class does the timing, legality check,
and mutation check so every engine is measured identically. A fresh engine
is constructed per call (mandatory: `MCTSEngine.__init__` seeds the GLOBAL
`random` module). `benchmarks/metrics.py` is pure stdlib math.
`benchmarks/correctness.py` runs the invariant checks over dataset
positions and returns a list of failures.

**Tech Stack:** Python 3 stdlib (`time`, `tracemalloc`, `random`, `math`,
`dataclasses`), `quantik_core`, parts 1–2 (`time_limit_s` configs,
`benchmarks.reference.move_key`).

## Global Constraints

- Prerequisites: parts 1 and 2 are merged (uses
  `MCTSConfig.time_limit_s`, `BeamSearchConfig.time_limit_s`,
  `benchmarks.reference`).
- Same packaging rules as part 2: `benchmarks/` is outside the coverage
  scope but flake8-checked; tests fast (< ~60s per file).
- Configuration values are not comparable across engines — adapters must
  record MEASURED work per move, not just configuration.
- Env setup + commit trailer: see "Shared conventions" in
  `2026-07-11-cross-engine-benchmark-0-INDEX.md`.

---

### Task 1: `benchmarks/metrics.py`

**Files:**
- Create: `benchmarks/metrics.py`
- Test: `tests/test_benchmark_metrics.py`

**Interfaces:**
- Consumes: nothing project-specific.
- Produces (used by part 4):
  - `wilson_ci(hits: int, n: int, z: float = 1.96) -> Tuple[float, float]`
  - `mean_std(xs: Sequence[float]) -> Tuple[float, float]` (sample std, ddof=1)
  - `percentile(xs: Sequence[float], p: float) -> float` (linear interp)
  - `median(xs: Sequence[float]) -> float`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_metrics.py`:

```python
"""Tests for benchmarks.metrics (pure-stdlib statistics helpers)."""

import pytest

from benchmarks.metrics import mean_std, median, percentile, wilson_ci


class TestWilsonCI:
    def test_empty_sample(self):
        assert wilson_ci(0, 0) == (0.0, 0.0)

    def test_half_hits_is_centered_and_bounded(self):
        lo, hi = wilson_ci(20, 40)
        assert 0.0 < lo < 0.5 < hi < 1.0
        assert lo == pytest.approx(0.352, abs=0.005)
        assert hi == pytest.approx(0.648, abs=0.005)

    def test_extremes_stay_in_unit_interval(self):
        lo_all, hi_all = wilson_ci(10, 10)
        lo_none, hi_none = wilson_ci(0, 10)
        assert 0.0 <= lo_none and hi_all <= 1.0
        assert hi_none > 0.0 and lo_all < 1.0  # never a degenerate [1,1]/[0,0]

    def test_interval_narrows_with_n(self):
        lo_small, hi_small = wilson_ci(5, 10)
        lo_big, hi_big = wilson_ci(500, 1000)
        assert (hi_big - lo_big) < (hi_small - lo_small)


class TestMeanStd:
    def test_empty(self):
        assert mean_std([]) == (0.0, 0.0)

    def test_single_value_has_zero_std(self):
        assert mean_std([3.0]) == (3.0, 0.0)

    def test_known_sample(self):
        mean, std = mean_std([1.0, 2.0, 3.0, 4.0])
        assert mean == pytest.approx(2.5)
        assert std == pytest.approx(1.29099, abs=1e-4)  # ddof=1


class TestPercentile:
    def test_empty(self):
        assert percentile([], 95.0) == 0.0

    def test_median_of_odd_and_even(self):
        assert median([3.0, 1.0, 2.0]) == 2.0
        assert median([1.0, 2.0, 3.0, 4.0]) == 2.5

    def test_p95_interpolates(self):
        xs = [float(i) for i in range(1, 101)]
        assert percentile(xs, 95.0) == pytest.approx(95.05)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError` on `benchmarks.metrics`.

- [ ] **Step 3: Implement**

Create `benchmarks/metrics.py`:

```python
"""Pure-stdlib statistics helpers for the benchmark (no numpy/scipy)."""

from __future__ import annotations

import math
from typing import Sequence, Tuple


def wilson_ci(hits: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because agreement rates sit
    near 0 or 1 for strong/weak engines, where the naive interval breaks.
    Returns (0.0, 0.0) for an empty sample.
    """
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def mean_std(xs: Sequence[float]) -> Tuple[float, float]:
    """Mean and sample standard deviation (ddof=1); std is 0.0 for n < 2."""
    n = len(xs)
    if n == 0:
        return (0.0, 0.0)
    mean = sum(xs) / n
    if n < 2:
        return (mean, 0.0)
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return (mean, math.sqrt(var))


def percentile(xs: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile, p in [0, 100]; 0.0 for empty input."""
    if not xs:
        return 0.0
    ordered = sorted(xs)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return ordered[int(k)]
    return ordered[lo] * (hi - k) + ordered[hi] * (k - lo)


def median(xs: Sequence[float]) -> float:
    """Convenience wrapper: the 50th percentile."""
    return percentile(xs, 50.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_metrics.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m black benchmarks tests
git add benchmarks/metrics.py tests/test_benchmark_metrics.py
git commit -m "feat(benchmarks): Wilson CI, mean/std, percentile helpers"
```

---

### Task 2: `benchmarks/adapters.py`

**Files:**
- Create: `benchmarks/adapters.py`
- Test: `tests/test_benchmark_adapters.py`

**Interfaces:**
- Consumes: `benchmarks.reference.move_key`; engine configs incl. part 1's
  `time_limit_s`.
- Produces (used by part 4 and the CLI):
  - `MoveObservation` dataclass — fields `engine`, `config_label`,
    `position_id`, `move` (move-key string), `wall_time_s`, `cpu_time_s`,
    `root_legal_moves`, `exact`, `seed`, `nodes`, `iterations`,
    `depth_reached`, `score`, `peak_memory_bytes`, `extra`
    (Dict[str, float]); method `to_dict()`.
  - `EngineAdapter` base — attrs `name: str`, `stochastic: bool`,
    `config_label: str`; method
    `select(bb, position_id, seed=None, track_memory=False) -> Tuple[Move, MoveObservation]`
    which raises `ValueError` on a terminal input, an illegal returned
    move, or input mutation.
  - `MinimaxAdapter(max_depth=16, time_limit_s=None)` — `stochastic=False`,
    sets `exact` iff completed depth ≥ remaining plies, verifies
    `best_move == pv[0]`.
  - `MCTSAdapter(max_iterations=1500, max_depth=16,
    exploration_weight=1.414, time_limit_s=None)` — `stochastic=True`.
  - `BeamAdapter(beam_width=64, max_depth=16, time_limit_s=None)` —
    `stochastic=True`.
  - `RandomAdapter()` — `stochastic=True`.
  - `fixed_time_adapters(time_limit_s, beam_width=256) -> List[EngineAdapter]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_adapters.py`:

```python
"""Tests for benchmarks.adapters: uniform measurement + invariants."""

import pytest

from quantik_core import State, apply_move
from quantik_core.move import Move, generate_legal_moves_list

from benchmarks.adapters import (
    BeamAdapter,
    MCTSAdapter,
    MinimaxAdapter,
    RandomAdapter,
    fixed_time_adapters,
)
from benchmarks.reference import parse_move_key

# 8 pieces, P1 to move, immediate mate available (see part-2 plan).
ANCHOR = ".ba./..CC/DcbD/cA.A"


def _anchor_bb():
    return State.from_qfen(ANCHOR).bb


def _fast_adapters():
    return [
        MinimaxAdapter(max_depth=2),
        MCTSAdapter(max_iterations=50),
        BeamAdapter(beam_width=4, max_depth=4),
        RandomAdapter(),
    ]


class TestSelectContract:
    @pytest.mark.parametrize("adapter", _fast_adapters(), ids=lambda a: a.name)
    def test_returns_legal_move_and_sane_observation(self, adapter):
        bb = _anchor_bb()
        move, obs = adapter.select(bb, "anchor", seed=0)
        legal = generate_legal_moves_list(bb)
        assert move in legal
        assert obs.engine == adapter.name
        assert obs.position_id == "anchor"
        assert obs.move == f"{move.player}:{move.shape}:{move.position}"
        assert obs.wall_time_s >= 0.0 and obs.cpu_time_s >= 0.0
        assert obs.root_legal_moves == len(legal)
        assert obs.to_dict()["engine"] == adapter.name

    @pytest.mark.parametrize("adapter", _fast_adapters(), ids=lambda a: a.name)
    def test_rejects_terminal_input(self, adapter):
        bb = _anchor_bb()
        mate = Move(player=1, shape=3, position=5)
        terminal = apply_move(bb, mate)
        with pytest.raises(ValueError, match="terminal"):
            adapter.select(terminal, "won", seed=0)

    def test_track_memory_populates_peak(self):
        _, obs = MinimaxAdapter(max_depth=2).select(
            _anchor_bb(), "anchor", track_memory=True
        )
        assert obs.peak_memory_bytes is not None and obs.peak_memory_bytes > 0


class TestMinimaxAdapter:
    def test_full_depth_solve_is_exact_and_optimal(self):
        move, obs = MinimaxAdapter(max_depth=16).select(_anchor_bb(), "anchor")
        assert obs.exact  # completed depth >= 16 - 8 remaining plies
        assert obs.nodes and obs.nodes > 0
        assert obs.depth_reached is not None
        # The anchor has an immediate mate; the exact engine must win now.
        child = apply_move(_anchor_bb(), move)
        from quantik_core.game_utils import has_winning_line

        assert has_winning_line(child) or not generate_legal_moves_list(child)

    def test_depth_limited_search_is_not_exact_on_open_board(self):
        _, obs = MinimaxAdapter(max_depth=2).select(
            State.from_qfen("Ab../..../..../....").bb, "open"
        )
        assert not obs.exact  # depth 2 < 14 remaining plies

    def test_is_deterministic(self):
        assert MinimaxAdapter.stochastic is False


class TestStochasticAdapters:
    @pytest.mark.parametrize(
        "adapter_factory",
        [
            lambda: MCTSAdapter(max_iterations=50),
            lambda: BeamAdapter(beam_width=4, max_depth=4),
            lambda: RandomAdapter(),
        ],
        ids=["mcts", "beam", "random"],
    )
    def test_same_seed_same_move(self, adapter_factory):
        adapter = adapter_factory()
        assert adapter.stochastic is True
        bb = _anchor_bb()
        _, first = adapter.select(bb, "anchor", seed=123)
        _, second = adapter.select(bb, "anchor", seed=123)
        assert first.move == second.move

    def test_mcts_records_iterations(self):
        _, obs = MCTSAdapter(max_iterations=50).select(_anchor_bb(), "anchor", seed=0)
        assert obs.iterations == 50
        assert obs.nodes and obs.nodes > 0

    def test_beam_records_depth_and_extra_stats(self):
        _, obs = BeamAdapter(beam_width=4, max_depth=4).select(
            _anchor_bb(), "anchor", seed=0
        )
        assert obs.depth_reached is not None and obs.depth_reached >= 1
        assert "candidates_generated" in obs.extra


class TestFixedTimeFamily:
    def test_equal_budget_adapters(self):
        adapters = fixed_time_adapters(0.05, beam_width=4)
        assert [a.name for a in adapters] == ["minimax", "mcts", "beam"]
        for adapter in adapters:
            assert "t=0.05" in adapter.config_label
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError` on `benchmarks.adapters`.

- [ ] **Step 3: Implement**

Create `benchmarks/adapters.py`:

```python
"""Uniform engine adapters: run any engine on a position and record the
EFFECTIVE work done (measured wall/CPU time, nodes, iterations, depth,
optional peak memory) -- configuration values alone are not comparable
across engines.

Every adapter constructs a FRESH engine per `select` call. This is not an
optimization choice: `MCTSEngine.__init__` seeds the global `random`
module, so reusing an engine (or sharing one across calls) would break
seed-level reproducibility.
"""

from __future__ import annotations

import random
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from quantik_core import State
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine
from quantik_core.game_utils import count_total_pieces, has_winning_line
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import Move, generate_legal_moves_list

from benchmarks.reference import move_key


def _label(name: str, **params) -> str:
    """Compact config label, omitting unset (None) parameters -- keeps
    'None' out of generated report tables."""
    inner = ",".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{name}({inner})" if inner else name


@dataclass
class MoveObservation:
    """Effective work measured for one move selection."""

    engine: str
    config_label: str
    position_id: str
    move: str  # move_key string, "player:shape:position"
    wall_time_s: float
    cpu_time_s: float
    root_legal_moves: int
    exact: bool
    seed: Optional[int] = None
    nodes: Optional[int] = None
    iterations: Optional[int] = None
    depth_reached: Optional[int] = None
    score: Optional[float] = None
    peak_memory_bytes: Optional[int] = None
    extra: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class EngineAdapter:
    """Times an engine call, validates its move, emits a MoveObservation.

    Subclasses implement `_select(bb, seed) -> (Move, metrics_dict)` where
    metrics_dict may carry `exact`, `nodes`, `iterations`, `depth_reached`,
    `score`; any remaining keys land in `MoveObservation.extra` and must be
    floats.
    """

    name = "base"
    stochastic = False  # True if a different seed can change the move

    def __init__(self, config_label: str) -> None:
        self.config_label = config_label

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        raise NotImplementedError

    def select(
        self,
        bb,
        position_id: str,
        seed: Optional[int] = None,
        track_memory: bool = False,
    ) -> Tuple[Move, MoveObservation]:
        legal = generate_legal_moves_list(bb)
        if has_winning_line(bb) or not legal:
            raise ValueError(
                f"{self.name}: cannot select a move from a terminal state"
            )
        bb_before = bb
        if track_memory:
            tracemalloc.start()
        wall0 = time.perf_counter()
        cpu0 = time.process_time()
        try:
            move, metrics = self._select(bb, seed)
        finally:
            if track_memory:
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
        wall = time.perf_counter() - wall0
        cpu = time.process_time() - cpu0
        if not track_memory:
            peak = None
        if bb != bb_before:
            raise ValueError(f"{self.name}: engine mutated its input state")
        if move not in legal:
            raise ValueError(f"{self.name}: returned illegal move {move}")
        observation = MoveObservation(
            engine=self.name,
            config_label=self.config_label,
            position_id=position_id,
            move=move_key(move),
            wall_time_s=wall,
            cpu_time_s=cpu,
            root_legal_moves=len(legal),
            seed=seed,
            peak_memory_bytes=peak,
            exact=bool(metrics.pop("exact", False)),
            nodes=metrics.pop("nodes", None),
            iterations=metrics.pop("iterations", None),
            depth_reached=metrics.pop("depth_reached", None),
            score=metrics.pop("score", None),
            extra=metrics,
        )
        return move, observation


class MinimaxAdapter(EngineAdapter):
    """Alpha-beta iterative deepening; the only adapter that can be exact.

    `exact` iff the last COMPLETED depth >= remaining plies (16 - pieces):
    such a search evaluated only true terminal leaves (see part-2 plan).
    Also enforces the PV invariant: best_move must equal pv[0].
    """

    name = "minimax"
    stochastic = False

    def __init__(
        self, max_depth: int = 16, time_limit_s: Optional[float] = None
    ) -> None:
        super().__init__(_label("minimax", d=max_depth, t=time_limit_s))
        self.max_depth = max_depth
        self.time_limit_s = time_limit_s

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        engine = MinimaxEngine(
            MinimaxConfig(max_depth=self.max_depth, time_limit_s=self.time_limit_s)
        )
        result = engine.search(State(bb))
        if result.pv and result.pv[0] != result.best_move:
            raise ValueError("minimax: best_move inconsistent with reported PV")
        pieces = sum(count_total_pieces(bb))
        return result.best_move, {
            "exact": result.depth_reached >= 16 - pieces,
            "nodes": result.nodes,
            "depth_reached": result.depth_reached,
            "score": result.score,
        }


class MCTSAdapter(EngineAdapter):
    """UCT Monte Carlo tree search; never exact."""

    name = "mcts"
    stochastic = True

    def __init__(
        self,
        max_iterations: int = 1500,
        max_depth: int = 16,
        exploration_weight: float = 1.414,
        time_limit_s: Optional[float] = None,
    ) -> None:
        super().__init__(
            _label(
                "mcts",
                it=max_iterations,
                d=max_depth,
                c=exploration_weight,
                t=time_limit_s,
            )
        )
        self.max_iterations = max_iterations
        self.max_depth = max_depth
        self.exploration_weight = exploration_weight
        self.time_limit_s = time_limit_s

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        engine = MCTSEngine(
            MCTSConfig(
                max_iterations=self.max_iterations,
                max_depth=self.max_depth,
                exploration_weight=self.exploration_weight,
                time_limit_s=self.time_limit_s,
                random_seed=seed,
            )
        )
        move, win_probability = engine.search(State(bb))
        stats = engine.get_statistics()
        return move, {
            "exact": False,
            "iterations": stats["iterations"],
            "nodes": stats["nodes_created"],
            "score": win_probability,
        }


class BeamAdapter(EngineAdapter):
    """Level-by-level beam search; never exact (pruned branches are lost
    even when every kept line reached a terminal)."""

    name = "beam"
    stochastic = True

    def __init__(
        self,
        beam_width: int = 64,
        max_depth: int = 16,
        time_limit_s: Optional[float] = None,
    ) -> None:
        super().__init__(_label("beam", w=beam_width, d=max_depth, t=time_limit_s))
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.time_limit_s = time_limit_s

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        engine = BeamSearchEngine(
            BeamSearchConfig(
                beam_width=self.beam_width,
                max_depth=self.max_depth,
                time_limit_s=self.time_limit_s,
                random_seed=seed,
            )
        )
        result = engine.search(State(bb))
        if result.best_leaf is not None and result.best_leaf.moves:
            move = result.best_leaf.moves[0]
        else:
            move = result.ranked_root_moves()[0].move
        score: Optional[float] = None
        if result.best_leaf is not None:
            score = result.best_leaf.value
            if result.root_player == 1:
                score = -score  # report from the root player's perspective
        stats = result.stats
        return move, {
            "exact": False,
            "nodes": stats.get("nodes_inserted"),
            "depth_reached": result.max_depth_reached,
            "score": score,
            "candidates_generated": float(stats.get("candidates_generated", 0)),
            "nodes_pruned": float(stats.get("nodes_pruned", 0)),
            "rollouts": float(stats.get("rollouts", 0)),
        }


class RandomAdapter(EngineAdapter):
    """Uniform random baseline with its own local RNG."""

    name = "random"
    stochastic = True

    def __init__(self) -> None:
        super().__init__("random")

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        rng = random.Random(seed)
        return rng.choice(generate_legal_moves_list(bb)), {"exact": False}


def fixed_time_adapters(
    time_limit_s: float, beam_width: int = 256
) -> List[EngineAdapter]:
    """The fixed-resource family: the same wall-clock budget per move.

    MCTS gets an effectively unbounded iteration cap so the clock is the
    binding constraint. Beam search honors its deadline only BETWEEN depth
    levels, so a wide level can overshoot the cap -- the honest comparison
    number is each observation's measured wall_time_s, never the
    configured limit.
    """
    return [
        MinimaxAdapter(max_depth=16, time_limit_s=time_limit_s),
        MCTSAdapter(
            max_iterations=10_000_000, max_depth=16, time_limit_s=time_limit_s
        ),
        BeamAdapter(beam_width=beam_width, max_depth=16, time_limit_s=time_limit_s),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_adapters.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
.venv/bin/python -m black benchmarks tests
git add benchmarks/adapters.py tests/test_benchmark_adapters.py
git commit -m "feat(benchmarks): uniform engine adapters with effective-work metrics"
```

---

### Task 3: `benchmarks/correctness.py`

**Files:**
- Create: `benchmarks/correctness.py`
- Test: `tests/test_benchmark_correctness.py`

**Interfaces:**
- Consumes: `EngineAdapter.select` (raises on illegal move / mutation /
  terminal input), `benchmarks.reference.parse_move_key`, dataset position
  dicts.
- Produces (used by the CLI in part 5):
  - `run_preflight(adapters, positions, sample=3, seed=0) -> List[str]` —
    empty list means all invariants hold; the CLI must refuse to benchmark
    otherwise.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_benchmark_correctness.py`:

```python
"""Tests for benchmarks.correctness: the benchmark must fail early on
invariant violations, before any timing is trusted."""

from quantik_core import State, apply_move
from quantik_core.move import Move, generate_legal_moves_list

from benchmarks.adapters import EngineAdapter, MinimaxAdapter, RandomAdapter
from benchmarks.correctness import run_preflight

ANCHOR = ".ba./..CC/DcbD/cA.A"


def _position(qfen, pos_id="p0000"):
    bb = State.from_qfen(qfen).bb
    from quantik_core.game_utils import count_total_pieces

    p0, p1 = count_total_pieces(bb)
    return {
        "id": pos_id,
        "qfen": qfen,
        "phase": "late_mid",
        "pieces": p0 + p1,
        "side_to_move": (p0 + p1) % 2,
        "legal_moves": len(generate_legal_moves_list(bb)),
        "reference": None,
    }


class _FlipFlopAdapter(EngineAdapter):
    """Deliberately non-deterministic: alternates between two legal moves."""

    name = "flipflop"
    stochastic = True

    def __init__(self):
        super().__init__("flipflop")
        self._calls = 0

    def _select(self, bb, seed):
        moves = sorted(
            generate_legal_moves_list(bb), key=lambda m: (m.shape, m.position)
        )
        self._calls += 1
        return moves[self._calls % 2], {}


class TestPreflight:
    def test_passes_for_well_behaved_adapters(self):
        failures = run_preflight(
            [MinimaxAdapter(max_depth=2), RandomAdapter()],
            [_position(ANCHOR)],
        )
        assert failures == []

    def test_flags_terminal_dataset_position(self):
        bb = State.from_qfen(ANCHOR).bb
        won = apply_move(bb, Move(player=1, shape=3, position=5))
        bad = _position(State(won).to_qfen(), pos_id="pbad")
        failures = run_preflight([RandomAdapter()], [bad])
        assert any("terminal" in f for f in failures)

    def test_flags_nondeterminism_under_identical_seed(self):
        failures = run_preflight([_FlipFlopAdapter()], [_position(ANCHOR)])
        assert any("non-deterministic" in f for f in failures)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_benchmark_correctness.py -v`
Expected: FAIL — `ModuleNotFoundError` on `benchmarks.correctness`.

- [ ] **Step 3: Implement**

Create `benchmarks/correctness.py`:

```python
"""Correctness preflight: benchmarking begins only after these invariants
pass. A benchmark of a broken engine measures nothing.

Covered invariants (consistency brief section 7):
- every dataset position is valid and non-terminal (terminal-state and
  no-move handling is a correctness test, not a benchmark sample);
- each adapter returns a legal move without raising
  (`EngineAdapter.select` itself raises on an illegal move, a mutated
  input state, or a terminal input -- those surface here as failures);
- the selected move belongs to the recorded side to move;
- identical settings + identical seed => identical move (stochastic
  engines must be reproducible);
- minimax's best_move == pv[0] is enforced inside `MinimaxAdapter`.
"""

from __future__ import annotations

from typing import List, Sequence

from quantik_core import State
from quantik_core.game_utils import has_winning_line
from quantik_core.move import generate_legal_moves_list

from benchmarks.reference import parse_move_key


def run_preflight(
    adapters, positions: Sequence[dict], sample: int = 3, seed: int = 0
) -> List[str]:
    """Return human-readable invariant failures; empty list == all good.

    Every position is checked for non-terminality; adapter behavior is
    probed on the first `sample` positions (each adapter runs twice per
    probe position to verify seed-level determinism).
    """
    failures: List[str] = []
    for pos in positions:
        bb = State.from_qfen(pos["qfen"]).bb
        if has_winning_line(bb) or not generate_legal_moves_list(bb):
            failures.append(f"dataset: position {pos['id']} is terminal")
    probe = list(positions)[:sample]
    for adapter in adapters:
        for pos in probe:
            bb = State.from_qfen(pos["qfen"]).bb
            try:
                _, first = adapter.select(bb, pos["id"], seed=seed)
            except Exception as exc:  # noqa: B902 -- preflight reports, not raises
                failures.append(f"{adapter.name} on {pos['id']}: {exc}")
                continue
            mover, _, _ = parse_move_key(first.move)
            if mover != pos["side_to_move"]:
                failures.append(
                    f"{adapter.name} on {pos['id']}: moved for player "
                    f"{mover}, but side to move is {pos['side_to_move']}"
                )
            _, second = adapter.select(bb, pos["id"], seed=seed)
            if second.move != first.move:
                failures.append(
                    f"{adapter.name} on {pos['id']}: non-deterministic under "
                    f"identical settings and seed "
                    f"({first.move} vs {second.move})"
                )
    return failures
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_benchmark_correctness.py tests/test_benchmark_adapters.py tests/test_benchmark_metrics.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Lint gate and commit**

```bash
.venv/bin/python -m black benchmarks tests
.venv/bin/python -m flake8 benchmarks --count
git add benchmarks/correctness.py tests/test_benchmark_correctness.py
git commit -m "feat(benchmarks): correctness preflight that fails the run early"
```

---

## Self-review checklist

- [ ] Every adapter constructs a fresh engine per `select` (grep: no
      engine instance stored on `self`).
- [ ] `fixed_time_adapters` gives all three engines the SAME
      `time_limit_s` and documents beam's level-granular overshoot.
- [ ] `select` raises (never silently continues) on: terminal input,
      illegal move, mutated input.
- [ ] All part-3 test files pass together in < ~60s.
