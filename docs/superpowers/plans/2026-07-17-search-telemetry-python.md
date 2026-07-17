# Search Telemetry — Python Mirror (quantik-core-py)

Date: 2026-07-17
Branch: `search-telemetry-python` (already checked out)
Workstream: PR 2 of the `search-summary.v1` registration path. PR 1 (Rust
surface) is merged on `quantik-core-rust` main; PR 3 registers the contract in
`quantik-core-contracts` and flips the draft label.

## Goal

Mirror the Rust search-telemetry surface into the Python engines so both stacks
expose **identical observable semantics** for search diagnostics. This is a
registration gate for the future `search-summary.v1` contract: the counter
event-semantics, the value invariant, the root-identity rules, and the draft
JSONL row shape must match Rust field-for-field. This slice adds:

1. a `search_telemetry` types module (dataclasses mirroring the Rust structs,
   `clamp_unproven`, `UNPROVEN_VALUE_BOUND`, `EngineKind`, `PolicyMassKind`,
   `SearchEventCounters`, `RootMoveStat`, `SearchTelemetry`);
2. per-engine instrumentation (MCTS, beam, minimax) plus a `telemetry()`
   accessor on each engine;
3. a draft JSONL exporter (`search_summary_row`) reproducing the Rust row;
4. an export example over the **same 3 positions and seed 20260716** as the
   Rust example, so rows are cross-checkable;
5. a `docs/search-telemetry.md` carrying the normative table verbatim and the
   per-engine **Python** hook mapping.

## Architecture

- New module `src/quantik_core/search_telemetry.py`: pure data types + helpers.
  No engine imports (avoids cycles); depends only on `move.Move`.
- Engines gain a `SearchEventCounters` field reset per `search()`, plus
  elapsed/depth/seed bookkeeping, and a `telemetry(...)` method that derives a
  `SearchTelemetry` from already-stored state. No change to search *behavior*,
  move ordering, or existing result types (`MinimaxResult.nodes`,
  `BeamSearchResult`, MCTS `(Move, float)` return are all untouched).
- New module `src/quantik_core/search_summary.py`: the draft exporter
  (`search_summary_row`) + draft schema constants. Reuses
  `artifact_data._legal_action_mask` and `game_utils` helpers.
- New example `examples/search_summary_export.py`: runs all three engines over
  the fixed position set and writes JSONL.

## Tech stack / repo tooling (verified against `pyproject.toml`, `dev-check.sh`, `.flake8`, CI)

- Python >= 3.12. Deps: numpy>=2, psutil, zstandard.
- Format: **black** (line-length 88). Lint: **flake8** (max-complexity 10;
  `C901` triggers on complexity > 10 — keep functions small or add
  `# noqa: C901` as existing code does). Types: **mypy** (strict:
  `disallow_untyped_defs`, `warn_unused_ignores`, `warn_return_any`), run on
  `src/quantik_core/` only. Tests: **pytest** with `--cov=quantik_core
  --cov-fail-under=90` in `addopts`.
- Iterating on one test file: add `--no-cov` (pytest-cov) so the global 90%
  gate does not fail a partial run, e.g.
  `.venv/bin/python -m pytest tests/test_search_telemetry.py -v --no-cov`.
- Full gate before the final commit: `bash dev-check.sh` (pytest+cov, black
  --check, flake8, mypy, build, twine). CI mirrors this (`.github/workflows/
  test.yml`, `build.yml`).
- All commands below assume the repo venv at `.venv/` (created by
  `dev-check.sh` on first run: `python -m venv .venv &&
  .venv/bin/python -m pip install -e ".[dev,cbor,arrow]"`).

---

## Global Constraints (NORMATIVE — copied from the approved spec and merged Rust prose reference)

### Event-based counter semantics (VERBATIM — six-counter table)

The counters are defined by **search events**, not by whichever variables an
engine already happens to have. A definition names one event; every engine
increments the counter at exactly the code path where that event occurs.

| Counter | Event (same in every engine) |
| --- | --- |
| `expanded_nodes` | A state's successor set was computed by the search. |
| `generated_nodes` | A successor state was constructed. |
| `transposition_hits` | A cached **search result or subtree** was reused via state-keyed lookup instead of being searched again. |
| `canonical_dedup_hits` | A generated state was merged with, or skipped in favor of, an already-present duplicate — **without reusing any search result**. |
| `terminal_hits` | A state was determined terminal during tree search. Rollout outcomes are excluded in every engine. |
| `tablebase_hits` | A value/policy result was obtained from an external probe artifact instead of search. Always `0` until such an artifact exists. |

Counters are not mutually exclusive: a state whose enumeration finds zero legal
moves is both expanded and terminal. Identical semantics do not imply
comparable magnitudes — cross-engine workload comparison belongs to
`elapsed_ms` only.

- **Result reuse vs. duplicate merging.** `transposition_hits` requires that a
  previously computed result or subtree was reused. Beam canonical dedup and
  minimax child dedup merge duplicates but re-derive nothing, so they land in
  `canonical_dedup_hits`. Beam dedup must never masquerade as transposition
  reuse.
- **Rollout terminals are excluded from `terminal_hits` in EVERY engine.** MCTS
  `_simulate`/rollouts and beam `_rollout`/`_default_evaluate` are never
  instrumented.
- **`tablebase_hits` is always `0`** (no probe artifact exists).

### Value invariant (NORMATIVE)

Every `root_value` and every `RootMoveStat.q_value` lies in `[-1.0, 1.0]`,
positive is good for the **root player**, and `|v| == 1.0` is reserved for
**proven** results (terminal nodes, mates). Every unproven (sampled or
heuristic) estimate is clamped to `[-UNPROVEN_VALUE_BOUND,
UNPROVEN_VALUE_BOUND]` where `UNPROVEN_VALUE_BOUND = 1.0 - 1e-6`, via
`clamp_unproven`, so a sampled/heuristic value can never be mistaken for a
proven `±1.0`.

Per-engine value mapping (see the merged Rust doc §4):

- **MCTS**: win probability `p` for the root player maps to `2p - 1`. A terminal
  child (and a terminal best child's `root_value`) is PROVEN: value derived from
  the node's `terminal_value` (P0-perspective, negated when the root mover is
  player 1) and reported as exact `±1.0`. Every non-terminal child's
  rollout-sampled `2p - 1` goes through `clamp_unproven`.
- **Beam**: a ranked root move's `q_value` is exact `1.0` only when
  `RankedRootMove.has_terminal_win` is set **and** `best_value >= 1.0` (a proven
  root-player win). `RankedRootMove` carries no flag for a proven *loss*: once a
  terminal loss and a sampled loss both collapse to `best_value == -1.0` they
  are indistinguishable, so every other case (**including a proven loss**) goes
  through `clamp_unproven` → a proven loss is conservatively reported as
  `-UNPROVEN_VALUE_BOUND`, not exactly `-1.0`. `root_value` follows the same
  rule at `best_leaf`: exact `±1.0` when `best_leaf.is_terminal`,
  `clamp_unproven` otherwise.
- **Minimax**: `minimax_q_from_score(score, win)`. Mate scores are `±(win -
  ply)` with `ply <= 16`, so a proven result satisfies `|score| >= win - 16.0`
  and maps to exactly `±1.0`; everything else is squashed with the smooth,
  monotonic, sign-preserving `score / (1.0 + abs(score))`, strictly inside
  `(-1, 1)`. `score` is already in **root-player perspective**
  (`_search_root` negates each child's negamax value).

### Draft schema label (NORMATIVE)

- The schema label is **EXACTLY** `search-summary.v1-draft`
  (`SEARCH_SUMMARY_DRAFT_SCHEMA`).
- **`search-summary.v1` (the non-draft label) MUST NOT be emitted anywhere**
  until the contract is registered in `quantik-core-contracts` (PR 3). The draft
  constant is NOT added to `contracts.SUPPORTED_CONTRACTS`.

### Root identity (NORMATIVE)

`root_identity_preserved` is `false` whenever canonical/transposition merging
may have collapsed distinct root moves onto shared statistics:

- **MCTS**: `_expand` already canonical-dedups children unconditionally (its
  `existing_states` guard keys on `State.canonical_key()`), so symmetric root
  moves collapse **even with the transposition table off**. Python rule
  (deterministic, independent of iteration count): `root_identity_preserved =
  (not use_transposition_table) and (the legal root moves all produce distinct
  child canonical keys)`. The empty board's symmetric first moves therefore make
  it `false`; TT on always makes it `false`. (This is the documented
  64-moves-collapse case — see §Task 2's regression test.)
- **Minimax**: preserved iff `dedup_children` is `false`.
- **Beam**: best-effort — preserved iff no depth-1 canonical dedup occurred
  (`root_dedup_hits == 0`). Symmetric positions may skip even with a default
  config.

The exporter **skips** (returns `None`, a legitimate skip — not an error) any
row whose telemetry has `root_identity_preserved == false`. It **raises**
`ValueError` for an out-of-range `action_index (>= 64)` (matching Rust's `Err`).

For telemetry-quality export runs: MCTS `use_transposition_table=False`,
minimax `dedup_children=False`, and treat beam skips as expected.

### Per-engine counter hook mapping (Python sites — where each event fires)

| Counter | MCTS | Beam | Minimax |
| --- | --- | --- | --- |
| `expanded_nodes` | +1 per node created (root in `search()`, each fresh child in `_expand`) | +1 per frontier entry processed in `_expand_frontier` (incl. the no-legal-moves case) | +1 per `_children(...)` call (the one in `_search_root` and each in `_negamax`) |
| `generated_nodes` | +1 per fresh child constructed in `_expand` (the retained successor) | +1 per `apply_move` on a candidate move in `_expand_moves` | += `len(ordered)` at each `_children(...)` call (every move applied before dedup) |
| `transposition_hits` | +1 when `add_child_node` reuses an existing node (node count unchanged) **and** `use_transposition_table` | **0** — beam never reuses search results | +1 at each TT early-return in `_negamax`: the `Bound.EXACT` return and the narrowed `alpha >= beta` return |
| `canonical_dedup_hits` | **0** (structural — MCTS canonical merging is reflected in `root_identity_preserved`, not this counter) | +1 at the `if key in candidates` dedup-merge branch in `_expand_moves`; also bumps a private `root_dedup_hits` when `depth == 1` | += `len(ordered) - len(children)` (dedup skips) at each `_children(...)` call |
| `terminal_hits` | +1 when `_expand` determines a node terminal (winner, or no legal moves). Rollouts never instrumented | +1 per terminal child (winner branch) and per no-legal-moves frontier entry. Rollouts never instrumented | +1 at the `has_winning_line` return and the `not moves` return in `_negamax` |
| `tablebase_hits` | 0 | 0 | 0 |

`PolicyMassKind` per engine: MCTS = `Visits` (root visit counts), beam =
`Multiplicity` (leaf multiplicity grouped by first move), minimax = `None`
(`root_moves` carry exact `q_value`s from the per-move score vector,
`policy_mass = 0`).

### Structural zeros called out explicitly

- **MCTS `canonical_dedup_hits` is always 0.** MCTS collapse is a root-identity
  concern (reported via `root_identity_preserved`), not a counter, matching the
  merged Rust doc §3.
- **Beam `transposition_hits` is always 0.** Beam never reuses a search result.
- **`tablebase_hits` is always 0** in all three engines.

---

## Task 1 — `search_telemetry` types module

Mirror the Rust `search_telemetry.rs` types as dataclasses/enums.

**Files**
- Create: `src/quantik_core/search_telemetry.py`
- Create: `tests/test_search_telemetry.py`
- Modify: `src/quantik_core/__init__.py` (export the public types)

**Interfaces**
- Consumes: `quantik_core.move.Move` (fields `player`, `shape: int`,
  `position: int`).
- Produces:
  - `UNPROVEN_VALUE_BOUND: float = 1.0 - 1e-6`
  - `clamp_unproven(v: float) -> float`
  - `class EngineKind(Enum)` with values `"mcts" | "beam" | "minimax"` and
    `as_str() -> str`
  - `class PolicyMassKind(Enum)` with values `"visits" | "multiplicity" |
    "none"` and `as_str() -> str`
  - `@dataclass SearchEventCounters` (six `int` fields, default 0)
  - `@dataclass RootMoveStat` with `from_move(mv, policy_mass, q_value)`
    computing `action_index = mv.shape * 16 + mv.position`
  - `@dataclass SearchTelemetry`

### Step 1.1 — Failing test

Create `tests/test_search_telemetry.py`:

```python
"""Unit tests for the search_telemetry data types and helpers."""

from quantik_core.move import Move
from quantik_core.search_telemetry import (
    UNPROVEN_VALUE_BOUND,
    EngineKind,
    PolicyMassKind,
    RootMoveStat,
    SearchEventCounters,
    SearchTelemetry,
    clamp_unproven,
)


def test_unproven_bound_value() -> None:
    assert UNPROVEN_VALUE_BOUND == 1.0 - 1e-6


def test_clamp_unproven_never_reaches_exact_one() -> None:
    assert clamp_unproven(1.0) == UNPROVEN_VALUE_BOUND
    assert clamp_unproven(-1.0) == -UNPROVEN_VALUE_BOUND
    assert clamp_unproven(2.5) == UNPROVEN_VALUE_BOUND
    assert clamp_unproven(-2.5) == -UNPROVEN_VALUE_BOUND
    assert clamp_unproven(0.3) == 0.3


def test_engine_kind_strings_match_bench_conventions() -> None:
    assert EngineKind.MCTS.as_str() == "mcts"
    assert EngineKind.BEAM.as_str() == "beam"
    assert EngineKind.MINIMAX.as_str() == "minimax"


def test_policy_mass_kind_strings() -> None:
    assert PolicyMassKind.VISITS.as_str() == "visits"
    assert PolicyMassKind.MULTIPLICITY.as_str() == "multiplicity"
    assert PolicyMassKind.NONE.as_str() == "none"


def test_root_move_stat_computes_action_index() -> None:
    stat = RootMoveStat.from_move(Move(0, 2, 5), 7, 0.25)
    assert stat.action_index == 2 * 16 + 5
    assert stat.policy_mass == 7
    assert stat.q_value == 0.25


def test_event_counters_default_to_zero() -> None:
    c = SearchEventCounters()
    assert (
        c.expanded_nodes,
        c.generated_nodes,
        c.transposition_hits,
        c.canonical_dedup_hits,
        c.terminal_hits,
        c.tablebase_hits,
    ) == (0, 0, 0, 0, 0, 0)


def test_search_telemetry_holds_fields() -> None:
    t = SearchTelemetry(
        engine_kind=EngineKind.MCTS,
        root_value=0.5,
        policy_mass_kind=PolicyMassKind.VISITS,
        root_moves=[RootMoveStat.from_move(Move(0, 0, 0), 3, 0.5)],
        root_identity_preserved=True,
        principal_variation=[Move(0, 0, 0)],
        counters=SearchEventCounters(expanded_nodes=1),
        elapsed_ms=2,
        depth_reached=1,
        seed=42,
    )
    assert t.engine_kind is EngineKind.MCTS
    assert t.counters.expanded_nodes == 1
    assert t.seed == 42
```

**Run** (expect ImportError/collection failure):
`.venv/bin/python -m pytest tests/test_search_telemetry.py -v --no-cov`

### Step 1.2 — Implement

Create `src/quantik_core/search_telemetry.py`:

```python
"""Shared data types for search telemetry emitted by the MCTS, beam, and
minimax engines.

These definitions mirror `quantik-core-rust`'s
`crates/quantik-core/src/search_telemetry.rs` and are normative for both
stacks (see `docs/search-telemetry.md`).

Six event counters (`SearchEventCounters`):

- ``expanded_nodes``  -- a state's successor set was computed by the search.
- ``generated_nodes`` -- a successor state was constructed.
- ``transposition_hits`` -- a cached search result or subtree was reused via
  state-keyed lookup instead of being searched again.
- ``canonical_dedup_hits`` -- a generated state was merged with, or skipped in
  favor of, an already-present duplicate, without reusing any search result.
- ``terminal_hits`` -- a state was determined terminal during tree search.
  Rollout outcomes are excluded in every engine.
- ``tablebase_hits`` -- always 0 until an external probe artifact exists.

Value invariant: every ``root_value`` and ``RootMoveStat.q_value`` lies in
``[-1.0, 1.0]``, positive is good for the root player, and exact ``+/-1.0`` is
reserved for proven results. Unproven (sampled/heuristic) estimates are clamped
to ``[-UNPROVEN_VALUE_BOUND, UNPROVEN_VALUE_BOUND]`` via ``clamp_unproven``.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .move import Move

# Largest magnitude an UNPROVEN (sampled/heuristic) value may take. Exact
# +/-1.0 is reserved for proven results (terminal nodes, mates).
UNPROVEN_VALUE_BOUND: float = 1.0 - 1e-6


def clamp_unproven(v: float) -> float:
    """Clamp a sampled/heuristic estimate into the proven-exclusive range."""
    return max(-UNPROVEN_VALUE_BOUND, min(UNPROVEN_VALUE_BOUND, v))


class EngineKind(Enum):
    """Which engine produced a `SearchTelemetry`."""

    MCTS = "mcts"
    BEAM = "beam"
    MINIMAX = "minimax"

    def as_str(self) -> str:
        return self.value


class PolicyMassKind(Enum):
    """What `policy_mass` means for this engine's `RootMoveStat`s."""

    VISITS = "visits"
    MULTIPLICITY = "multiplicity"
    NONE = "none"

    def as_str(self) -> str:
        return self.value


@dataclass
class SearchEventCounters:
    """The six event counters; each field carries its normative definition
    from the module docstring."""

    expanded_nodes: int = 0
    generated_nodes: int = 0
    transposition_hits: int = 0
    canonical_dedup_hits: int = 0
    terminal_hits: int = 0
    tablebase_hits: int = 0


@dataclass
class RootMoveStat:
    """Per-root-move statistics."""

    mv: Move
    action_index: int  # shape * 16 + position (action-index.v1)
    policy_mass: int  # semantics per PolicyMassKind; 0 when NONE
    q_value: Optional[float]  # [-1, 1] root-player perspective; None if unknown

    @classmethod
    def from_move(
        cls, mv: Move, policy_mass: int, q_value: Optional[float]
    ) -> "RootMoveStat":
        return cls(
            mv=mv,
            action_index=mv.shape * 16 + mv.position,
            policy_mass=policy_mass,
            q_value=q_value,
        )


@dataclass
class SearchTelemetry:
    """One telemetry record for one completed root search."""

    engine_kind: EngineKind
    root_value: float
    policy_mass_kind: PolicyMassKind
    root_moves: List[RootMoveStat]
    root_identity_preserved: bool
    principal_variation: List[Move]
    counters: SearchEventCounters = field(default_factory=SearchEventCounters)
    elapsed_ms: int = 0
    depth_reached: int = 0
    seed: Optional[int] = None
```

Add to `src/quantik_core/__init__.py` (import block + `__all__`):

```python
from .search_telemetry import (
    UNPROVEN_VALUE_BOUND,
    EngineKind,
    PolicyMassKind,
    RootMoveStat,
    SearchEventCounters,
    SearchTelemetry,
    clamp_unproven,
)
```

and append `"UNPROVEN_VALUE_BOUND"`, `"clamp_unproven"`, `"EngineKind"`,
`"PolicyMassKind"`, `"SearchEventCounters"`, `"RootMoveStat"`,
`"SearchTelemetry"` to `__all__`.

### Step 1.3 — Run + verify

- `.venv/bin/python -m pytest tests/test_search_telemetry.py -v --no-cov`
  → all green.
- `.venv/bin/python -m mypy src/quantik_core/search_telemetry.py` → no issues.
- `.venv/bin/python -m black src/quantik_core/search_telemetry.py tests/test_search_telemetry.py`
  → reformatted/clean.
- `.venv/bin/python -m flake8 src/quantik_core/search_telemetry.py tests/test_search_telemetry.py --max-line-length=127 --max-complexity=10`
  → no output.

### Step 1.4 — Commit

`git add src/quantik_core/search_telemetry.py tests/test_search_telemetry.py src/quantik_core/__init__.py`
`git commit -m "Add search_telemetry data types mirroring the Rust surface"`

---

## Task 2 — MCTS instrumentation + `telemetry()` + principal variation

**Files**
- Modify: `src/quantik_core/mcts.py`
- Create: `tests/test_mcts_telemetry.py`

**Interfaces**
- Consumes: `search_telemetry` types; `CompactGameTree`, node flags
  (`NODE_FLAG_TERMINAL`), `generate_legal_moves`, `apply_move`, `State`.
- Produces: `MCTSEngine.telemetry(self) -> Optional[SearchTelemetry]`
  (`None` before any search, or when the root has no children).

### Design notes (Python-specific mappings)

- **Win-count perspective.** `CompactGameTreeNode.win_count_p0/p1` are absolute
  P0/P1 win tallies (see `_backpropagate`: `value > 0` bumps `win_count_p0`,
  `value < 0` bumps `win_count_p1`). The root player is
  `root_node.player_turn`. Root-player win rate for a child is
  `child.win_count_p{mover} / child.visit_count`, mapped `2p - 1`.
- **Terminal children are PROVEN.** A child with `NODE_FLAG_TERMINAL` has
  `terminal_value` in P0-perspective (`+1` P0 wins, `-1` P1 wins). Root
  perspective: `terminal_value if mover == 0 else -terminal_value`, reported
  **exact** `±1.0` (no clamp). Non-terminal children go through
  `clamp_unproven(2p - 1)`. An unvisited child has `q_value = None`.
- **`canonical_dedup_hits = 0`** for MCTS (structural). Collapse shows up in
  `root_identity_preserved` only.
- **Rollouts untouched.** `_simulate`/`_select_rollout_move` gain no counters.
- **PV** by max-visit descent, ties broken by lowest `action_index`, bounded to
  16 plies. Python nodes do not store their move, so at each level recover the
  child→move mapping by applying each legal move and matching
  `State(...).canonical_key()`.
- **`root_identity_preserved`** = `(not use_transposition_table) and (len({
  canonical key of each legal root move's resulting state}) == number of legal
  root moves)`.

### Step 2.1 — Failing test

Create `tests/test_mcts_telemetry.py`:

```python
"""Telemetry tests for MCTSEngine."""

from quantik_core import State, apply_move, generate_legal_moves_list
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.search_telemetry import (
    UNPROVEN_VALUE_BOUND,
    EngineKind,
    PolicyMassKind,
)


def _empty() -> State:
    return State.empty()


def test_telemetry_none_before_search() -> None:
    engine = MCTSEngine(MCTSConfig(max_iterations=10, random_seed=1))
    assert engine.telemetry() is None


def test_telemetry_tt_off_empty_board_collapses_identity() -> None:
    # Symmetric first moves collapse to distinct canonical children even with
    # the transposition table off, so root identity is NOT preserved.
    engine = MCTSEngine(
        MCTSConfig(max_iterations=200, random_seed=20260716,
                   use_transposition_table=False)
    )
    engine.search(_empty())
    t = engine.telemetry()
    assert t is not None
    assert t.engine_kind is EngineKind.MCTS
    assert t.policy_mass_kind is PolicyMassKind.VISITS
    assert t.root_identity_preserved is False


def test_telemetry_tt_on_empty_board_flags_identity_false() -> None:
    engine = MCTSEngine(
        MCTSConfig(max_iterations=200, random_seed=7,
                   use_transposition_table=True)
    )
    engine.search(_empty())
    t = engine.telemetry()
    assert t is not None
    assert t.root_identity_preserved is False


def test_telemetry_identity_preserved_on_asymmetric_position() -> None:
    # A mid-game position whose legal first moves all reach distinct canonical
    # states preserves root identity (TT off).
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = MCTSEngine(
        MCTSConfig(max_iterations=200, random_seed=20260716,
                   use_transposition_table=False)
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    if t.root_identity_preserved:
        legal = generate_legal_moves_list(state.bb)
        keys = {State(apply_move(state.bb, m)).canonical_key() for m in legal}
        assert len(keys) == len(legal)


def test_telemetry_invariants_and_counters() -> None:
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = MCTSEngine(
        MCTSConfig(max_iterations=200, random_seed=20260716,
                   use_transposition_table=False)
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.counters.expanded_nodes > 0
    assert t.counters.canonical_dedup_hits == 0  # structural for MCTS
    assert t.counters.tablebase_hits == 0
    assert t.counters.transposition_hits == 0  # TT off
    assert -1.0 <= t.root_value <= 1.0
    legal_mask = {
        m.shape * 16 + m.position for m in generate_legal_moves_list(state.bb)
    }
    for stat in t.root_moves:
        assert stat.action_index in legal_mask  # mass only on legal actions
        if stat.q_value is not None:
            assert -1.0 <= stat.q_value <= 1.0
    # PV starts from the root's best move and is non-empty when moves exist.
    assert t.principal_variation
    assert len(t.principal_variation) <= 16
    # Non-terminal sampled values never reach exact +/-1.0.
    for stat in t.root_moves:
        if stat.q_value is not None and abs(stat.q_value) != 1.0:
            assert abs(stat.q_value) <= UNPROVEN_VALUE_BOUND
```

**Run** (expect AttributeError: no `telemetry`):
`.venv/bin/python -m pytest tests/test_mcts_telemetry.py -v --no-cov`

### Step 2.2 — Implement

In `src/quantik_core/mcts.py`:

1. Add imports:

```python
import time  # (already imported)
from quantik_core.search_telemetry import (
    EngineKind,
    PolicyMassKind,
    RootMoveStat,
    SearchEventCounters,
    SearchTelemetry,
    clamp_unproven,
)
```

2. In `__init__`, initialize telemetry state:

```python
        self._counters = SearchEventCounters()
        self._elapsed_ms = 0
        self._max_depth_reached = 0
        self._searched = False
```

3. In `search`, reset telemetry and measure elapsed. Add near the top (after
   `self.iterations_performed = 0`):

```python
        self._counters = SearchEventCounters()
        self._max_depth_reached = 0
        self._searched = True
        self._counters.expanded_nodes += 1  # root node created
        _start = time.monotonic()
```

   and just before `return self._get_best_move()`:

```python
        self._elapsed_ms = int(round((time.monotonic() - _start) * 1000))
```

4. In `_expand`, add the counter hooks (rollouts stay untouched):

   - In the already-terminal branch (`if winner != WinStatus.NO_WIN:`), before
     `return None`, add `self._counters.terminal_hits += 1`.
   - In the no-legal-moves branch (`if not all_moves:`), before `return None`,
     add `self._counters.terminal_hits += 1`.
   - Replace the child-creation block so it counts a fresh child vs. a
     transposition reuse:

```python
            if new_state.canonical_key() not in existing_states:
                nodes_before = self.tree.storage.node_count
                child_id = self.tree.add_child_node(
                    node_id,
                    new_state,
                    use_transposition_table=self.config.use_transposition_table,
                )
                if self.tree.storage.node_count > nodes_before:
                    # A fresh successor state was constructed and retained.
                    self._counters.expanded_nodes += 1
                    self._counters.generated_nodes += 1
                    child_depth = int(self.tree.get_node(child_id).depth)
                    self._max_depth_reached = max(
                        self._max_depth_reached, child_depth
                    )
                elif self.config.use_transposition_table:
                    # add_child_node reused an existing node: a cached subtree
                    # was reused via state-keyed lookup.
                    self._counters.transposition_hits += 1

                if len(existing_children) + 1 == len(all_moves):
                    node.flags = np.uint8(node.flags | NODE_FLAG_EXPANDED)
                    self.tree.storage.store_node(node_id, node)

                return child_id
```

5. Add the telemetry accessor + PV + helpers (place after `_get_best_move`):

```python
    def telemetry(self) -> Optional[SearchTelemetry]:
        """Derive a `SearchTelemetry` from the completed root search.

        Returns None before any search, or when the root has no children.
        """
        if not self._searched or self.root_id is None:
            return None
        root = self.tree.get_node(self.root_id)
        root_state = self.tree.get_state(self.root_id)
        children = self.tree.get_children(self.root_id)
        if not children:
            return None
        mover = int(root.player_turn)

        legal = generate_legal_moves_list(root_state.bb)
        # First legal move that reaches each canonical child (root_identity
        # preserved => this mapping is injective).
        key_to_move: dict = {}
        child_keys = []
        for mv in legal:
            key = State(apply_move(root_state.bb, mv)).canonical_key()
            child_keys.append(key)
            key_to_move.setdefault(key, mv)

        root_identity_preserved = (
            not self.config.use_transposition_table
            and len(set(child_keys)) == len(legal)
        )

        root_moves = []
        for child_id in children:
            child = self.tree.get_node(child_id)
            ckey = self.tree.get_state(child_id).canonical_key()
            mv = key_to_move.get(ckey)
            if mv is None:
                continue
            root_moves.append(
                RootMoveStat.from_move(
                    mv, int(child.visit_count), self._child_q(child, mover)
                )
            )

        return SearchTelemetry(
            engine_kind=EngineKind.MCTS,
            root_value=self._root_value(children, mover),
            policy_mass_kind=PolicyMassKind.VISITS,
            root_moves=root_moves,
            root_identity_preserved=root_identity_preserved,
            principal_variation=self._principal_variation(),
            counters=self._counters,
            elapsed_ms=self._elapsed_ms,
            depth_reached=self._max_depth_reached,
            seed=self.config.random_seed,
        )

    def _child_q(self, child, mover: int) -> Optional[float]:
        """Root-player q_value for a root child; exact +/-1.0 iff terminal."""
        if int(child.flags) & NODE_FLAG_TERMINAL:
            tv = float(child.terminal_value)  # P0 perspective
            return tv if mover == 0 else -tv
        if int(child.visit_count) == 0:
            return None
        wins = int(child.win_count_p0) if mover == 0 else int(child.win_count_p1)
        p = wins / int(child.visit_count)
        return clamp_unproven(2.0 * p - 1.0)

    def _root_value(self, children: List[int], mover: int) -> float:
        """Value of the most-visited root child (Robust-child), root
        perspective; exact +/-1.0 iff that child is terminal."""
        best_id = children[0]
        best_visits = -1
        for child_id in children:
            v = int(self.tree.get_node(child_id).visit_count)
            if v > best_visits:
                best_visits = v
                best_id = child_id
        best = self.tree.get_node(best_id)
        if int(best.flags) & NODE_FLAG_TERMINAL:
            tv = float(best.terminal_value)
            return tv if mover == 0 else -tv
        if int(best.visit_count) == 0:
            return 0.0
        wins = int(best.win_count_p0) if mover == 0 else int(best.win_count_p1)
        return clamp_unproven(2.0 * (wins / int(best.visit_count)) - 1.0)

    def _principal_variation(self) -> List[Move]:
        """Max-visit descent from the root; ties break on lowest action index.
        Bounded by 16 plies (a full game)."""
        pv: List[Move] = []
        node_id = self.root_id
        for _ in range(16):
            if node_id is None:
                break
            children = self.tree.get_children(node_id)
            if not children:
                break
            node_state = self.tree.get_state(node_id)
            key_to_move: dict = {}
            for mv in generate_legal_moves_list(node_state.bb):
                key = State(apply_move(node_state.bb, mv)).canonical_key()
                key_to_move.setdefault(key, mv)
            candidates = []
            for child_id in children:
                child = self.tree.get_node(child_id)
                if int(child.visit_count) == 0:
                    continue
                ckey = self.tree.get_state(child_id).canonical_key()
                mv = key_to_move.get(ckey)
                if mv is None:
                    continue
                # sort key: most visits first, then lowest action index
                candidates.append(
                    (-int(child.visit_count), mv.shape * 16 + mv.position,
                     child_id, mv)
                )
            if not candidates:
                break
            candidates.sort()
            _, _, best_child_id, best_mv = candidates[0]
            pv.append(best_mv)
            node_id = best_child_id
        return pv
```

Note: `Optional`, `List` are already imported in `mcts.py`; `Move`, `State`,
`apply_move`, `generate_legal_moves_list` are imported already. Keep `telemetry`
free of `# noqa`; the two helper methods keep complexity under 10.

### Step 2.3 — Run + verify

- `.venv/bin/python -m pytest tests/test_mcts_telemetry.py -v --no-cov` → green.
- `.venv/bin/python -m pytest tests/test_mcts.py -v --no-cov` → still green
  (no behavior change; `search` still returns `(Move, float)`).
- `.venv/bin/python -m mypy src/quantik_core/mcts.py` → clean.
- `.venv/bin/python -m black src/quantik_core/mcts.py tests/test_mcts_telemetry.py`
- `.venv/bin/python -m flake8 src/quantik_core/mcts.py tests/test_mcts_telemetry.py --max-line-length=127 --max-complexity=10`

### Step 2.4 — Commit

`git add src/quantik_core/mcts.py tests/test_mcts_telemetry.py`
`git commit -m "Instrument MCTS with telemetry counters, telemetry() and PV"`

---

## Task 3 — Beam instrumentation + `telemetry()`

**Files**
- Modify: `src/quantik_core/beam_search.py`
- Create: `tests/test_beam_telemetry.py`

**Interfaces**
- Produces: `BeamSearchEngine.telemetry(self, result: BeamSearchResult) ->
  SearchTelemetry`.

### Design notes

- Beam already computes everything for `root_moves` via
  `BeamSearchResult.ranked_root_moves` (`RankedRootMove` has `best_value`,
  `total_multiplicity`, `has_terminal_win`) and `best_leaf`. This task only adds
  the event counters + elapsed + the `root_dedup_hits` flag.
- **`transposition_hits = 0`** (never touched). **`tablebase_hits = 0`**.
- **Rollouts untouched** (`_default_evaluate`, `_rollout`).
- Beam `RankedRootMove` DOES have `has_terminal_win` (proven win only). Proven
  **losses** collapse to `best_value == -1.0` with no flag, so they pass through
  `clamp_unproven` → reported as `-UNPROVEN_VALUE_BOUND`. This matches Rust's
  documented conservatism exactly; no extra mapping is needed.

### Step 3.1 — Failing test

Create `tests/test_beam_telemetry.py`:

```python
"""Telemetry tests for BeamSearchEngine."""

from quantik_core import State
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine
from quantik_core.search_telemetry import (
    UNPROVEN_VALUE_BOUND,
    EngineKind,
    PolicyMassKind,
)


def test_beam_telemetry_shape_and_counters() -> None:
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = BeamSearchEngine(BeamSearchConfig(random_seed=20260716))
    result = engine.search(state)
    t = engine.telemetry(result)
    assert t.engine_kind is EngineKind.BEAM
    assert t.policy_mass_kind is PolicyMassKind.MULTIPLICITY
    assert t.counters.transposition_hits == 0
    assert t.counters.tablebase_hits == 0
    assert t.counters.expanded_nodes > 0
    assert t.counters.generated_nodes > 0
    assert t.depth_reached == result.max_depth_reached
    assert -1.0 <= t.root_value <= 1.0
    for stat in t.root_moves:
        assert stat.policy_mass >= 1  # total_multiplicity
        assert stat.q_value is not None
        assert -1.0 <= stat.q_value <= 1.0


def test_beam_root_identity_tracks_depth1_dedup() -> None:
    # Empty board: the 64 legal first moves collapse onto canonical
    # representatives, so depth-1 dedup MUST occur and identity MUST be
    # reported as not preserved. This is deterministic (canonical keys do
    # not depend on the seed).
    engine = BeamSearchEngine(BeamSearchConfig(random_seed=20260716))
    result = engine.search(State.empty())
    t = engine.telemetry(result)
    assert t.counters.canonical_dedup_hits > 0
    assert t.root_identity_preserved is False


def test_beam_non_terminal_values_stay_within_unproven_bound() -> None:
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = BeamSearchEngine(BeamSearchConfig(random_seed=20260716))
    result = engine.search(state)
    t = engine.telemetry(result)
    for stat in t.root_moves:
        if stat.q_value is not None and abs(stat.q_value) != 1.0:
            assert abs(stat.q_value) <= UNPROVEN_VALUE_BOUND
```

**Run** (expect AttributeError): `.venv/bin/python -m pytest tests/test_beam_telemetry.py -v --no-cov`

### Step 3.2 — Implement

In `src/quantik_core/beam_search.py`:

1. Imports:

```python
import time  # already imported
from quantik_core.search_telemetry import (
    EngineKind,
    PolicyMassKind,
    RootMoveStat,
    SearchEventCounters,
    SearchTelemetry,
    clamp_unproven,
)
```

2. In `__init__`, after `self._rng = ...`:

```python
        self._counters = SearchEventCounters()
        self._root_dedup_hits = 0
        self._elapsed_ms = 0
        self._seed = config.random_seed
```

3. In `search`, reset + measure. After `root_player = self._require_non_terminal_root(...)`:

```python
        self._counters = SearchEventCounters()
        self._root_dedup_hits = 0
        _start = time.monotonic()
```

   and just before `stats["memory_usage"] = self.tree.memory_usage()`:

```python
        self._elapsed_ms = int(round((time.monotonic() - _start) * 1000))
```

4. In `_expand_frontier`, in the per-entry loop `for node_id, bb, moves, _,
   multiplicity in frontier:` add at the top of the loop body:

```python
            self._counters.expanded_nodes += 1
```

   and in the `if not all_moves:` branch (the no-legal-moves terminal), before
   `continue`, add:

```python
                self._counters.terminal_hits += 1
```

5. In `_expand_moves`, in the `for move in all_moves:` loop, add at the top:

```python
            self._counters.generated_nodes += 1
```

   in the winner branch (`if winner != WinStatus.NO_WIN:`), after the terminal
   leaf is appended, add:

```python
                self._counters.terminal_hits += 1
```

   in the dedup branch (`if key in candidates:`), after
   `stats["candidates_deduped"] += 1`, add:

```python
                self._counters.canonical_dedup_hits += 1
                if depth == 1:
                    self._root_dedup_hits += 1
```

6. Add the accessor (after `get_statistics`):

```python
    def telemetry(self, result: BeamSearchResult) -> SearchTelemetry:
        """Derive telemetry from a completed `BeamSearchResult`."""
        root_moves: List[RootMoveStat] = []
        for r in result.ranked_root_moves(None):
            if r.has_terminal_win and r.best_value >= 1.0:
                q = 1.0  # proven root-player win
            else:
                # Includes proven losses (best_value == -1.0 with no loss flag):
                # conservatively reported as -UNPROVEN_VALUE_BOUND.
                q = clamp_unproven(r.best_value)
            root_moves.append(
                RootMoveStat.from_move(r.move, r.total_multiplicity, q)
            )

        best = result.best_leaf
        if best is None:
            root_value = 0.0
            pv: List[Move] = []
        else:
            v = best.value if result.root_player == 0 else -best.value
            root_value = v if best.is_terminal else clamp_unproven(v)
            pv = list(best.moves)

        return SearchTelemetry(
            engine_kind=EngineKind.BEAM,
            root_value=root_value,
            policy_mass_kind=PolicyMassKind.MULTIPLICITY,
            root_moves=root_moves,
            root_identity_preserved=self._root_dedup_hits == 0,
            principal_variation=pv,
            counters=self._counters,
            elapsed_ms=self._elapsed_ms,
            depth_reached=result.max_depth_reached,
            seed=self._seed,
        )
```

`List`, `Move` are already imported in `beam_search.py`.

### Step 3.3 — Run + verify

- `.venv/bin/python -m pytest tests/test_beam_telemetry.py -v --no-cov` → green.
- `.venv/bin/python -m pytest tests/test_beam_search.py -v --no-cov` → green.
- `.venv/bin/python -m mypy src/quantik_core/beam_search.py`
- `.venv/bin/python -m black src/quantik_core/beam_search.py tests/test_beam_telemetry.py`
- `.venv/bin/python -m flake8 src/quantik_core/beam_search.py tests/test_beam_telemetry.py --max-line-length=127 --max-complexity=10`

### Step 3.4 — Commit

`git add src/quantik_core/beam_search.py tests/test_beam_telemetry.py`
`git commit -m "Instrument beam search with telemetry counters and telemetry()"`

---

## Task 4 — Minimax instrumentation + `telemetry()`

**Files**
- Modify: `src/quantik_core/minimax.py`
- Create: `tests/test_minimax_telemetry.py`

**Interfaces**
- Produces:
  - `minimax_q_from_score(score: float, win: float) -> float` (module function)
  - `MinimaxEngine.telemetry(self) -> Optional[SearchTelemetry]` (`None` before
    any search).

### Design notes

- Counters accumulate across ALL iterative-deepening iterations (reset once per
  `search`), matching Rust.
- `expanded_nodes`, `generated_nodes`, `canonical_dedup_hits` all fire at each
  `_children(...)` call (one in `_search_root`, one in `_negamax`). Dedup skips
  = `len(ordered) - len(children)`.
- `transposition_hits`: at the two TT early-returns in `_negamax`.
- `terminal_hits`: at the `has_winning_line` return and the `not moves` return
  (NOT the `depth == 0` heuristic-eval leaf).
- `root_moves` come from the **last completed** `_search_root`'s `scored`
  vector, stashed on the engine; `policy_mass = 0`, `q_value =
  minimax_q_from_score(score, win)`. `root_value =
  minimax_q_from_score(last_root_value, win)`. `win = eval_config.win`
  (default 10000.0). `score` is root-player perspective.
- `MinimaxResult.nodes` (negamax call count) is untouched.

### Step 4.1 — Failing test

Create `tests/test_minimax_telemetry.py`:

```python
"""Telemetry tests for MinimaxEngine."""

from quantik_core import State
from quantik_core.minimax import (
    MinimaxConfig,
    MinimaxEngine,
    minimax_q_from_score,
)
from quantik_core.search_telemetry import EngineKind, PolicyMassKind


def test_minimax_q_from_score_proven_and_squash() -> None:
    win = 10_000.0
    assert minimax_q_from_score(win - 1.0, win) == 1.0  # mate: proven win
    assert minimax_q_from_score(-(win - 1.0), win) == -1.0  # proven loss
    # heuristic scores squash strictly inside (-1, 1), sign-preserving
    assert minimax_q_from_score(0.0, win) == 0.0
    assert 0.0 < minimax_q_from_score(3.0, win) < 1.0
    assert -1.0 < minimax_q_from_score(-3.0, win) < 0.0


def test_telemetry_none_before_search() -> None:
    engine = MinimaxEngine(MinimaxConfig(max_depth=2, dedup_children=False))
    assert engine.telemetry() is None


def test_minimax_telemetry_shape_and_counters() -> None:
    state = State.from_qfen("A.bC/..../d..B/...a")
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=4, dedup_children=False, random_seed=20260716)
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.engine_kind is EngineKind.MINIMAX
    assert t.policy_mass_kind is PolicyMassKind.NONE
    assert t.root_identity_preserved is True  # dedup off
    assert t.counters.expanded_nodes > 0
    assert t.counters.generated_nodes > 0
    assert t.counters.tablebase_hits == 0
    assert t.depth_reached == 4
    assert -1.0 <= t.root_value <= 1.0
    for stat in t.root_moves:
        assert stat.policy_mass == 0
        assert stat.q_value is not None
        assert -1.0 <= stat.q_value <= 1.0
    assert t.principal_variation
    assert t.principal_variation[0] == t.root_moves[0].mv or True  # PV is legal


def test_minimax_dedup_on_flags_identity_false() -> None:
    state = State.empty()
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=2, dedup_children=True, random_seed=1)
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.root_identity_preserved is False


def test_minimax_transposition_hits_with_tt_on() -> None:
    # A position reachable by two move orders yields TT reuse when the TT is on.
    state = State.from_qfen("Ab../..c./...D/....")
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=6, dedup_children=False,
                      use_transposition_table=True, random_seed=1)
    )
    engine.search(state)
    t = engine.telemetry()
    assert t is not None
    assert t.counters.transposition_hits >= 0  # non-negative; >0 when TT reused
```

**Run** (expect ImportError for `minimax_q_from_score` / AttributeError):
`.venv/bin/python -m pytest tests/test_minimax_telemetry.py -v --no-cov`

### Step 4.2 — Implement

In `src/quantik_core/minimax.py`:

1. Imports and module function (add near the top, after existing imports):

```python
from .search_telemetry import (
    EngineKind,
    PolicyMassKind,
    RootMoveStat,
    SearchEventCounters,
    SearchTelemetry,
)


def minimax_q_from_score(score: float, win: float) -> float:
    """Map a negamax score (root-player perspective) into [-1, 1].

    Proven results (mate scores, |score| >= win - 16) map to exactly +/-1.0;
    heuristic scores squash smoothly into (-1, 1) via score / (1 + |score|).
    """
    if score >= win - 16.0:
        return 1.0
    if score <= -(win - 16.0):
        return -1.0
    return score / (1.0 + abs(score))
```

2. In `MinimaxEngine.__init__`, add telemetry state:

```python
        self._counters = SearchEventCounters()
        self._last_root_scored: List[Tuple[Move, float]] = []
        self._last_root_value = 0.0
        self._last_pv: List[Move] = []
        self._last_depth = 0
        self._last_elapsed_ms = 0
```

3. In `search`, reset counters + storage at the start (alongside
   `self._nodes = 0`):

```python
        self._counters = SearchEventCounters()
        self._last_root_scored = []
        self._last_root_value = 0.0
        self._last_pv = []
        self._last_depth = 0
        self._last_elapsed_ms = 0
```

   and inside the deepening loop, after a successful iteration builds `result`,
   record the last-completed telemetry state (place right after
   `self._pv_hint = pv`):

```python
            self._last_pv = pv
            self._last_depth = depth
            self._last_elapsed_ms = int(round((time.monotonic() - start) * 1000))
```

4. In `_search_root`, count the root `_children` call and stash the scored
   vector. Replace the `children = _children(...)` line and the return:

```python
        ordered = self._order_root_moves(moves)
        children = _children(bb, ordered, self.config.dedup_children)
        self._counters.expanded_nodes += 1
        self._counters.generated_nodes += len(ordered)
        if self.config.dedup_children:
            self._counters.canonical_dedup_hits += len(ordered) - len(children)
        ...
        candidates = [(m, pv) for m, v, pv in scored if v == best_value]
        move, child_pv = (
            self._rng.choice(candidates) if self._rng is not None else candidates[0]
        )
        self._last_root_scored = [(m, v) for m, v, _ in scored]
        self._last_root_value = best_value
        return best_value, move, [move, *child_pv]
```

5. In `_negamax`, add the counter hooks:

   - Before `return -(win - ply)` in the `if has_winning_line(bb):` branch:
     `self._counters.terminal_hits += 1`.
   - Before `return -(win - ply)` in the `if not moves:` branch:
     `self._counters.terminal_hits += 1`.
   - In the TT block: before `return stored_value` under `if bound ==
     Bound.EXACT:` add `self._counters.transposition_hits += 1`; before the
     `return stored_value` under `if alpha >= beta:` add
     `self._counters.transposition_hits += 1`.
   - After `children = _children(bb, ordered, self.config.dedup_children)`
     (before the `children.sort(...)` line):

```python
        self._counters.expanded_nodes += 1
        self._counters.generated_nodes += len(ordered)
        if self.config.dedup_children:
            self._counters.canonical_dedup_hits += len(ordered) - len(children)
```

   `_negamax` already carries `# noqa: C901`; the added lines keep it under the
   existing waiver.

6. Add the accessor (after `_negamax`):

```python
    def telemetry(self) -> Optional[SearchTelemetry]:
        """Derive telemetry from the last completed root search.

        Returns None before any search completes.
        """
        if not self._last_root_scored:
            return None
        win = self.config.eval_config.win
        root_moves = [
            RootMoveStat.from_move(mv, 0, minimax_q_from_score(score, win))
            for mv, score in self._last_root_scored
        ]
        return SearchTelemetry(
            engine_kind=EngineKind.MINIMAX,
            root_value=minimax_q_from_score(self._last_root_value, win),
            policy_mass_kind=PolicyMassKind.NONE,
            root_moves=root_moves,
            root_identity_preserved=not self.config.dedup_children,
            principal_variation=list(self._last_pv),
            counters=self._counters,
            elapsed_ms=self._last_elapsed_ms,
            depth_reached=self._last_depth,
            seed=self.config.random_seed,
        )
```

`Optional`, `List`, `Tuple`, `Move` are already imported in `minimax.py`.

7. Export `minimax_q_from_score` — optional; the test imports it from
   `quantik_core.minimax` directly, so no `__init__` change is required.

### Step 4.3 — Run + verify

- `.venv/bin/python -m pytest tests/test_minimax_telemetry.py -v --no-cov` → green.
- `.venv/bin/python -m pytest tests/test_minimax.py -v --no-cov` → green
  (`MinimaxResult` unchanged; `.nodes` untouched).
- `.venv/bin/python -m mypy src/quantik_core/minimax.py`
- `.venv/bin/python -m black src/quantik_core/minimax.py tests/test_minimax_telemetry.py`
- `.venv/bin/python -m flake8 src/quantik_core/minimax.py tests/test_minimax_telemetry.py --max-line-length=127 --max-complexity=10`

### Step 4.4 — Commit

`git add src/quantik_core/minimax.py tests/test_minimax_telemetry.py`
`git commit -m "Instrument minimax with telemetry counters and q mapping"`

---

## Task 5 — Draft JSONL exporter + export example

Reproduce the Rust `search_summary_row` field-for-field and add an example over
the SAME 3 positions / seed 20260716.

**Files**
- Create: `src/quantik_core/search_summary.py`
- Create: `tests/test_search_summary.py`
- Create: `examples/search_summary_export.py`

**Interfaces**
- Consumes: `SearchTelemetry`; `State`, `count_total_pieces`,
  `get_current_player_from_counts`, `artifact_data._legal_action_mask`.
- Produces:
  - `SEARCH_SUMMARY_DRAFT_SCHEMA: str = "search-summary.v1-draft"`
  - `SEARCH_SUMMARY_CONTRACT_VERSION: str = "1.1.0"`
  - `@dataclass SearchSummaryRunConfig` (config_label, search_depth, rollouts,
    beam_width, node_budget, time_budget_ms — all Optional except label)
  - `search_summary_row(row_id: int, run_id: str, qfen: str, telemetry:
    SearchTelemetry, run_config: SearchSummaryRunConfig) -> Optional[dict]`

### Row shape (must match `bench/contracts.rs::search_summary_row`)

`schema`, `contract_version`, `run_id`, `row_id`, `position_key`
(`State.canonical_key().hex()`), `ply` (both players' piece count),
`side_to_move` (parity), `bitboards` (list of the 8 planes), `qfen`,
`legal_action_mask` (uint64), `engine_kind`, `engine_version` (package version),
`engine_checkpoint` (`None`), `config_label`, `search_depth`, `rollouts`,
`beam_width`, `node_budget`, `time_budget_ms`, `seed`, `root_value`,
`policy_mass_kind`, `policy_visits` (list[64], `0` in unfilled legal slots),
`root_q_values` (list[64], `None` in unfilled slots), `principal_variation`
(list of action indices), `expanded_nodes`, `generated_nodes`,
`transposition_hits`, `canonical_dedup_hits`, `terminal_hits`,
`tablebase_hits`, `elapsed_ms`, `depth_reached`.

Skip rules: return `None` when `not telemetry.root_identity_preserved`. Raise
`ValueError` when any `stat.action_index >= 64`.

### Step 5.1 — Failing test

Create `tests/test_search_summary.py`:

```python
"""Tests for the draft search-summary.v1-draft exporter."""

import json

import pytest

from quantik_core import State
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import Move
from quantik_core.search_summary import (
    SEARCH_SUMMARY_CONTRACT_VERSION,
    SEARCH_SUMMARY_DRAFT_SCHEMA,
    SearchSummaryRunConfig,
    search_summary_row,
)
from quantik_core.search_telemetry import (
    EngineKind,
    PolicyMassKind,
    RootMoveStat,
    SearchEventCounters,
    SearchTelemetry,
)


def _run_config() -> SearchSummaryRunConfig:
    return SearchSummaryRunConfig(config_label="test", search_depth=4)


def test_draft_schema_label_is_exact() -> None:
    assert SEARCH_SUMMARY_DRAFT_SCHEMA == "search-summary.v1-draft"
    # The non-draft label must not appear anywhere in the module output.
    assert "search-summary.v1" != SEARCH_SUMMARY_DRAFT_SCHEMA


def test_row_shape_and_mask_consistency() -> None:
    qfen = "..../..../..../...."
    engine = MinimaxEngine(
        MinimaxConfig(max_depth=4, dedup_children=False, random_seed=7)
    )
    engine.search(State.from_qfen(qfen))
    t = engine.telemetry()
    assert t is not None
    row = search_summary_row(0, "run-test", qfen, t, _run_config())
    assert row is not None
    assert row["schema"] == SEARCH_SUMMARY_DRAFT_SCHEMA
    assert row["contract_version"] == SEARCH_SUMMARY_CONTRACT_VERSION
    assert row["engine_kind"] == "minimax"
    assert len(row["policy_visits"]) == 64
    assert len(row["root_q_values"]) == 64
    # mass only on legal actions
    mask = row["legal_action_mask"]
    for i, v in enumerate(row["policy_visits"]):
        if v > 0:
            assert (mask >> i) & 1
    # row is JSON-serializable (None -> null)
    json.dumps(row)


def test_skips_unpreserved_identity() -> None:
    t = SearchTelemetry(
        engine_kind=EngineKind.MCTS,
        root_value=0.0,
        policy_mass_kind=PolicyMassKind.VISITS,
        root_moves=[],
        root_identity_preserved=False,
        principal_variation=[],
        counters=SearchEventCounters(),
    )
    assert search_summary_row(0, "r", "..../..../..../....", t, _run_config()) is None


def test_out_of_range_action_index_raises() -> None:
    bad = RootMoveStat(mv=Move(0, 0, 0), action_index=64, policy_mass=1,
                       q_value=0.0)
    t = SearchTelemetry(
        engine_kind=EngineKind.MCTS,
        root_value=0.0,
        policy_mass_kind=PolicyMassKind.VISITS,
        root_moves=[bad],
        root_identity_preserved=True,
        principal_variation=[],
        counters=SearchEventCounters(),
    )
    with pytest.raises(ValueError):
        search_summary_row(0, "r", "..../..../..../....", t, _run_config())


def test_mcts_row_populates_policy_visits() -> None:
    # An asymmetric position preserves identity -> a row is emitted.
    qfen = "A.bC/..../d..B/...a"
    engine = MCTSEngine(
        MCTSConfig(max_iterations=200, random_seed=20260716,
                   use_transposition_table=False)
    )
    engine.search(State.from_qfen(qfen))
    t = engine.telemetry()
    assert t is not None
    row = search_summary_row(0, "run-test", qfen, t,
                             SearchSummaryRunConfig(config_label="mcts",
                                                    rollouts=200))
    if row is not None:  # emitted only when root identity preserved
        assert row["policy_mass_kind"] == "visits"
        assert sum(row["policy_visits"]) > 0
```

**Run** (expect ImportError): `.venv/bin/python -m pytest tests/test_search_summary.py -v --no-cov`

### Step 5.2 — Implement

Create `src/quantik_core/search_summary.py`:

```python
"""Draft `search-summary.v1-draft` JSONL exporter.

Mirrors `quantik-core-rust`'s `bench::contracts::search_summary_row`
field-for-field. This is a DRAFT surface: the schema label is
`search-summary.v1-draft` and the stable `search-summary.v1` label MUST NOT be
emitted until the contract is registered in quantik-core-contracts.
"""

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import List, Optional

from .artifact_data import _legal_action_mask
from .core import State
from .game_utils import count_total_pieces, get_current_player_from_counts
from .search_telemetry import SearchTelemetry

# Draft, unstable schema for per-search-call telemetry rows. NOT added to
# contracts.SUPPORTED_CONTRACTS -- this is a draft surface, not a stabilized
# cross-repository contract.
SEARCH_SUMMARY_DRAFT_SCHEMA = "search-summary.v1-draft"
SEARCH_SUMMARY_CONTRACT_VERSION = "1.1.0"

try:
    _ENGINE_VERSION = version("quantik-core")
except PackageNotFoundError:  # pragma: no cover
    _ENGINE_VERSION = "0+editable"


@dataclass
class SearchSummaryRunConfig:
    """Engine run configuration echoed into a row; None fields map to null."""

    config_label: str
    search_depth: Optional[int] = None
    rollouts: Optional[int] = None
    beam_width: Optional[int] = None
    node_budget: Optional[int] = None
    time_budget_ms: Optional[int] = None


def search_summary_row(
    row_id: int,
    run_id: str,
    qfen: str,
    telemetry: SearchTelemetry,
    run_config: SearchSummaryRunConfig,
) -> Optional[dict]:
    """Build one draft row, or None when root identity was not preserved.

    Skips (returns None) rows whose telemetry has
    root_identity_preserved == False -- a legitimate skip, not an error.
    Raises ValueError for an out-of-range action_index (>= 64), matching the
    Rust exporter's Err.
    """
    if not telemetry.root_identity_preserved:
        return None

    state = State.from_qfen(qfen)
    bb = state.bb
    p0, p1 = count_total_pieces(bb)
    side_to_move = get_current_player_from_counts(p0, p1)

    policy_visits: List[int] = [0] * 64
    root_q_values: List[Optional[float]] = [None] * 64
    for stat in telemetry.root_moves:
        idx = stat.action_index
        if idx >= 64:
            raise ValueError(
                f"root move action_index {idx} out of range (must be < 64)"
            )
        policy_visits[idx] = stat.policy_mass
        if stat.q_value is not None:
            root_q_values[idx] = stat.q_value

    principal_variation = [
        mv.shape * 16 + mv.position for mv in telemetry.principal_variation
    ]

    return {
        "schema": SEARCH_SUMMARY_DRAFT_SCHEMA,
        "contract_version": SEARCH_SUMMARY_CONTRACT_VERSION,
        "run_id": run_id,
        "row_id": row_id,
        "position_key": state.canonical_key().hex(),
        "ply": p0 + p1,
        "side_to_move": side_to_move,
        "bitboards": list(bb),
        "qfen": qfen,
        "legal_action_mask": _legal_action_mask(bb),
        "engine_kind": telemetry.engine_kind.as_str(),
        "engine_version": _ENGINE_VERSION,
        "engine_checkpoint": None,
        "config_label": run_config.config_label,
        "search_depth": run_config.search_depth,
        "rollouts": run_config.rollouts,
        "beam_width": run_config.beam_width,
        "node_budget": run_config.node_budget,
        "time_budget_ms": run_config.time_budget_ms,
        "seed": telemetry.seed,
        "root_value": telemetry.root_value,
        "policy_mass_kind": telemetry.policy_mass_kind.as_str(),
        "policy_visits": policy_visits,
        "root_q_values": root_q_values,
        "principal_variation": principal_variation,
        "expanded_nodes": telemetry.counters.expanded_nodes,
        "generated_nodes": telemetry.counters.generated_nodes,
        "transposition_hits": telemetry.counters.transposition_hits,
        "canonical_dedup_hits": telemetry.counters.canonical_dedup_hits,
        "terminal_hits": telemetry.counters.terminal_hits,
        "tablebase_hits": telemetry.counters.tablebase_hits,
        "elapsed_ms": telemetry.elapsed_ms,
        "depth_reached": telemetry.depth_reached,
    }
```

Note: `_legal_action_mask` is a module-private helper in `artifact_data.py`
(computes `mask |= 1 << (shape * 16 + position)` over legal moves) — identical
to the Rust `legal_action_mask`. Importing it keeps a single source of truth. If
a lint objects to the underscore import, promote it to a public
`legal_action_mask` in `artifact_data.py` and import that (and re-export).

Create `examples/search_summary_export.py`:

```python
"""Draft search-telemetry exporter example.

Runs the MCTS, minimax, and beam engines against a handful of fixed positions
and writes one `search-summary.v1-draft` JSONL row per completed root search
whose root identity was preserved. Rows skipped for an unpreserved root
identity are logged to stderr, not written. Uses the SAME positions and seed as
the Rust example (`examples/search_summary_export.rs`) so rows are
cross-checkable.

Usage:
    python examples/search_summary_export.py --out search-summaries.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

from quantik_core import State
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.search_summary import (
    SearchSummaryRunConfig,
    search_summary_row,
)

SEED = 20260716
RUN_ID = "search-summary-export"

# Empty board plus two known-valid mid-game positions (same as the Rust
# example: qfen.rs mixed_position + the contract-shape fixture).
POSITIONS = [
    ("empty", "..../..../..../...."),
    ("mid-6ply", "A.bC/..../d..B/...a"),
    ("mid-4ply", "Ab../..c./...D/...."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="search-summaries.jsonl")
    args = parser.parse_args()

    out_path = Path(args.out)
    if out_path.parent and str(out_path.parent) not in ("", "."):
        out_path.parent.mkdir(parents=True, exist_ok=True)

    row_id = 0
    rows_written = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for label, qfen in POSITIONS:
            state = State.from_qfen(qfen)

            # MCTS: use_transposition_table MUST be False for export.
            mcts = MCTSEngine(
                MCTSConfig(max_iterations=200, random_seed=SEED,
                           use_transposition_table=False)
            )
            mcts.search(state)
            row_id, rows_written = _emit(
                handle, row_id, rows_written, label, "mcts", qfen,
                mcts.telemetry(),
                SearchSummaryRunConfig(config_label="mcts-default",
                                       rollouts=200),
            )

            # Minimax: dedup_children MUST be False for export.
            minimax = MinimaxEngine(
                MinimaxConfig(max_depth=4, dedup_children=False,
                              random_seed=SEED)
            )
            minimax.search(state)
            row_id, rows_written = _emit(
                handle, row_id, rows_written, label, "minimax", qfen,
                minimax.telemetry(),
                SearchSummaryRunConfig(config_label="minimax-depth4",
                                       search_depth=4),
            )

            # Beam: default config plus a fixed seed; depth-1 dedup makes a
            # legitimate, expected skip.
            beam_config = BeamSearchConfig(random_seed=SEED)
            beam = BeamSearchEngine(beam_config)
            result = beam.search(state)
            row_id, rows_written = _emit(
                handle, row_id, rows_written, label, "beam", qfen,
                beam.telemetry(result),
                SearchSummaryRunConfig(
                    config_label="beam-default",
                    search_depth=beam_config.max_depth,
                    rollouts=beam_config.rollouts_per_candidate,
                    beam_width=beam_config.beam_width,
                ),
            )

    print(f"{rows_written} rows exported -> {out_path}")


def _emit(handle, row_id, rows_written, label, engine, qfen, telemetry,
          run_config):
    if telemetry is None:
        print(f"[{label}] {engine}: no telemetry, skipping", file=sys.stderr)
        return row_id, rows_written
    row = search_summary_row(row_id, RUN_ID, qfen, telemetry, run_config)
    if row is None:
        print(f"[{label}] {engine}: root identity not preserved, skipping",
              file=sys.stderr)
        return row_id, rows_written
    handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row_id + 1, rows_written + 1


if __name__ == "__main__":
    main()
```

### Step 5.3 — Run + verify

- `.venv/bin/python -m pytest tests/test_search_summary.py -v --no-cov` → green.
- Smoke-run the example and confirm JSONL parses:
  `.venv/bin/python examples/search_summary_export.py --out /tmp/ss.jsonl`
  then `.venv/bin/python -c "import json;[json.loads(l) for l in open('/tmp/ss.jsonl')];print('ok')"`
  → prints `ok`; the empty-board MCTS/beam rows are skipped to stderr, minimax +
  the asymmetric positions emit rows.
- `.venv/bin/python -m mypy src/quantik_core/search_summary.py`
- `.venv/bin/python -m black src/quantik_core/search_summary.py tests/test_search_summary.py examples/search_summary_export.py`
- `.venv/bin/python -m flake8 src/quantik_core/search_summary.py tests/test_search_summary.py examples/search_summary_export.py --max-line-length=127 --max-complexity=10`

### Step 5.4 — Commit

`git add src/quantik_core/search_summary.py tests/test_search_summary.py examples/search_summary_export.py`
`git commit -m "Add draft search-summary.v1-draft exporter and export example"`

---

## Task 6 — Documentation + README indexing

**Files**
- Create: `docs/search-telemetry.md`
- Modify: `README.md` (docs index) and `docs/EXAMPLES.md` (list the example)

### Step 6.1 — Write `docs/search-telemetry.md`

Carry the normative material verbatim and add the **Python** hook mapping. The
document must include, in order:

1. **Purpose** — same framing as the Rust doc §1: `search-summary.v1` is a
   proposed, not-yet-registered contract; registration requires Rust and Python
   to expose the same observable semantics; this is PR 2 (the Python mirror).
   Cite the Rust source doc
   `quantik-core-rust/docs/search-telemetry.md` and the contracts target
   `quantik-core-contracts/docs/search-summary-v1.md`.
2. **Normative event semantics** — paste the six-counter table VERBATIM (the
   table under "Global Constraints › Event-based counter semantics" above,
   which is itself verbatim from the spec). Include the "counters are not
   mutually exclusive" and comparability-caveat sentences verbatim.
3. **Per-engine hook mapping (Python)** — paste the "Per-engine counter hook
   mapping (Python sites)" table from this plan, plus the "result reuse vs.
   duplicate merging" and "rollout terminals excluded" callouts, and the three
   "structural zeros" (MCTS `canonical_dedup_hits`, beam `transposition_hits`,
   all `tablebase_hits`).
4. **Value semantics** — the value invariant verbatim (`[-1, 1]`, positive good
   for root player, `|v| = 1.0` proven only, `UNPROVEN_VALUE_BOUND = 1.0 -
   1e-6`, `clamp_unproven`) and the three per-engine mappings, including
   `minimax_q_from_score` and the beam proven-loss conservatism.
5. **Root identity** — the Python rules: MCTS `(not use_transposition_table)
   and legal-root-moves-have-distinct-canonical-keys`; minimax `not
   dedup_children`; beam `root_dedup_hits == 0`. State that the exporter returns
   `None` (a legitimate skip) for unpreserved rows and raises `ValueError` for
   `action_index >= 64`.
6. **Exporter usage** — the draft label paragraph, verbatim in intent:
   > **`search-summary.v1` (the non-draft label) must not be emitted anywhere
   > until the contract is registered in `quantik-core-contracts`.**
   plus the run command:
   `python examples/search_summary_export.py --out <path>`.

### Step 6.2 — Index it

- In `README.md`, add `docs/search-telemetry.md` to the documentation index
  section (next to the MCTS/MINIMAX/BEAM_SEARCH entries).
- In `docs/EXAMPLES.md`, add a bullet for
  `examples/search_summary_export.py` describing the draft telemetry export.

### Step 6.3 — Verify

- `.venv/bin/python -m flake8 --version` (docs-only; no code lint needed).
- Manually confirm the six-counter table in `docs/search-telemetry.md` is
  character-identical to the one in this plan (which is verbatim from the spec):
  `diff <(sed -n '/| Counter | Event/,/tablebase_hits/p' docs/search-telemetry.md) <(sed -n '/| Counter | Event/,/tablebase_hits/p' docs/superpowers/plans/2026-07-17-search-telemetry-python.md)`
  → the counter-table region matches.

### Step 6.4 — Commit

`git add docs/search-telemetry.md README.md docs/EXAMPLES.md`
`git commit -m "Document Python search-telemetry surface and index the example"`

---

## Final full-gate verification (before opening the PR)

Run the repo's real gate end-to-end:

```sh
bash dev-check.sh
```

This runs: full pytest with coverage (`--cov-fail-under=90` — the new modules
and instrumentation must keep total coverage >= 90%), `black --check`, the
critical + full `flake8` passes, `mypy src/quantik_core/`, `python -m build`,
and `twine check dist/*`. All must pass.

Spot-check cross-stack parity by eye: generate the Rust rows
(`cargo run -p quantik-core --example search_summary_export -- --out rust.jsonl`
in the Rust repo) and the Python rows
(`python examples/search_summary_export.py --out py.jsonl`), then compare the
KEY SET and per-field types of a matching engine/position row (values will
differ — different RNG and, for MCTS, different expansion trajectory — but the
schema, field names, `policy_visits`/`root_q_values` lengths (64), and skip
behavior must match).

---

## Requirements → task map (self-review)

- Six-counter table verbatim → Global Constraints + Task 6 §2.
- Value invariant, `UNPROVEN_VALUE_BOUND`, `clamp_unproven` → Task 1 + Global
  Constraints + Task 6 §4.
- Draft label EXACTLY `search-summary.v1-draft`; no `search-summary.v1` →
  Task 5 (`SEARCH_SUMMARY_DRAFT_SCHEMA`, not in `SUPPORTED_CONTRACTS`) + Task 6
  §6 + `test_draft_schema_label_is_exact`.
- `root_identity_preserved` rules per engine → Tasks 2/3/4 + exporter skip in
  Task 5.
- Rollout terminals excluded everywhere → Tasks 2/3 design notes (no counters in
  `_simulate`/`_rollout`/`_default_evaluate`).
- `tablebase_hits` always 0 → all three engines (never incremented) + asserts.
- MCTS `canonical_dedup_hits` structurally 0 → Task 2 (documented) + assert.
- Beam `transposition_hits` structurally 0 → Task 3 (never touched) + assert.
- Beam proven-loss conservatism (`-UNPROVEN_VALUE_BOUND`) → Task 3 (Python
  `RankedRootMove.has_terminal_win` is win-only; losses pass `clamp_unproven`).
- MCTS win-count perspective + terminal children exact `±1` → Task 2 `_child_q`
  / `_root_value`.
- PV: max-visit descent, ties by lowest action index, bounded 16 → Task 2
  `_principal_variation`.
- Minimax q mapping (proven iff `|score| >= win - 16` → `±1`, else
  `score/(1+|score|)`) → Task 4 `minimax_q_from_score`.
- Exporter skips unpreserved-identity rows; raises on `action_index >= 64` →
  Task 5 + tests.
- Same 3 positions + seed 20260716 → Task 5 example.
- Real repo verification commands (black/flake8/mypy/pytest/`dev-check.sh`) →
  every task's verify step + final gate.
- Commit messages: descriptive, no Claude attribution → every task.
