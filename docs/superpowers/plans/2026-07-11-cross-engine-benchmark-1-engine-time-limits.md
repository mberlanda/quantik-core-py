# Benchmark Part 1: `time_limit_s` for MCTS and Beam Search — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional wall-clock `time_limit_s` to `MCTSConfig` and
`BeamSearchConfig` so the fixed-resource benchmark family (part 4) can give
every engine the same per-move budget — `MinimaxConfig` already has one.

**Architecture:** MCTS checks a `time.monotonic()` deadline at the END of
each iteration (so at least one iteration always completes). Beam search
checks the deadline at the TOP of each depth level after depth 1 (so at
least one level always completes); the limit is therefore level-granular —
a wide level can overshoot, which is fine because the harness reports
actual measured wall time, not the configured cap.

**Tech Stack:** Python 3, stdlib `time`, pytest.

## Global Constraints

- This is a **library change** (`src/quantik_core/`): full
  `./dev-check.sh` (pytest+coverage ≥90%, black, flake8, mypy, build,
  twine) must pass before the final commit.
- Default behavior must be unchanged: `time_limit_s=None` (the default)
  must produce byte-identical behavior to today.
- Env setup + formatting + commit trailer: see "Shared conventions" in
  `2026-07-11-cross-engine-benchmark-0-INDEX.md`.

---

### Task 1: `MCTSConfig.time_limit_s`

**Files:**
- Modify: `src/quantik_core/mcts.py`
- Test: `tests/test_mcts.py` (append a new test class)

**Interfaces:**
- Consumes: existing `MCTSConfig`, `MCTSEngine.search`.
- Produces: `MCTSConfig(time_limit_s: Optional[float] = None)`;
  `MCTSEngine.search` stops iterating once the deadline passes (≥1
  iteration guaranteed); `MCTSEngine.__init__` raises `ValueError` for
  `time_limit_s <= 0`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mcts.py`:

```python
class TestMCTSTimeLimit:
    """Optional wall-clock budget on MCTSEngine.search."""

    _QFEN = ".ba./..CC/DcbD/cA.A"  # fast near-endgame anchor, P1 to move

    def test_time_limit_stops_before_max_iterations(self):
        from quantik_core.mcts import MCTSConfig, MCTSEngine

        engine = MCTSEngine(
            MCTSConfig(max_iterations=10_000_000, time_limit_s=0.05, random_seed=0)
        )
        state = State.from_qfen(self._QFEN)
        move, _ = engine.search(state)
        assert engine.iterations_performed < 10_000_000
        assert move in generate_legal_moves_list(state.bb)

    def test_time_limit_always_runs_at_least_one_iteration(self):
        from quantik_core.mcts import MCTSConfig, MCTSEngine

        engine = MCTSEngine(
            MCTSConfig(max_iterations=100, time_limit_s=1e-9, random_seed=0)
        )
        engine.search(State.from_qfen(self._QFEN))
        assert engine.iterations_performed >= 1

    def test_no_time_limit_runs_all_iterations(self):
        from quantik_core.mcts import MCTSConfig, MCTSEngine

        engine = MCTSEngine(MCTSConfig(max_iterations=50, random_seed=0))
        engine.search(State.from_qfen(self._QFEN))
        assert engine.iterations_performed == 50

    def test_non_positive_time_limit_rejected(self):
        from quantik_core.mcts import MCTSConfig, MCTSEngine

        with pytest.raises(ValueError):
            MCTSEngine(MCTSConfig(time_limit_s=0.0))
        with pytest.raises(ValueError):
            MCTSEngine(MCTSConfig(time_limit_s=-1.0))
```

`tests/test_mcts.py` already imports `pytest`, `State`, and
`generate_legal_moves_list` near the top — check with
`grep -n "^import\|^from" tests/test_mcts.py` and add any missing import
next to the existing ones rather than inside the class.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_mcts.py::TestMCTSTimeLimit -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument
'time_limit_s'` (dataclass rejects the unknown field).

- [ ] **Step 3: Implement**

In `src/quantik_core/mcts.py`:

3a. Add `import time` to the imports at the top (next to `import math`).

3b. In `MCTSConfig`, after the `random_seed` field, add:

```python
    # Optional wall-clock budget for `search`, in seconds. Checked at the
    # END of each iteration, so at least one iteration always completes.
    # None (default) => iteration count is the only stop condition.
    time_limit_s: Optional[float] = None
```

3c. In `MCTSEngine.__init__`, right after the existing
`rollout_epsilon` validation block, add:

```python
        if config.time_limit_s is not None and config.time_limit_s <= 0:
            raise ValueError(
                f"time_limit_s must be positive, got {config.time_limit_s}"
            )
```

3d. In `MCTSEngine.search`, replace the iteration loop. The current code is:

```python
        # Perform MCTS iterations
        for _ in range(self.config.max_iterations):
```

and the loop body ends with:

```python
            self.iterations_performed += 1
```

Replace with (deadline computed before the loop; check after the
increment, i.e. at the end of each completed iteration):

```python
        deadline = (
            time.monotonic() + self.config.time_limit_s
            if self.config.time_limit_s is not None
            else None
        )

        # Perform MCTS iterations
        for _ in range(self.config.max_iterations):
```

and at the end of the loop body:

```python
            self.iterations_performed += 1

            if deadline is not None and time.monotonic() >= deadline:
                break
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_mcts.py -v`
Expected: ALL PASS (the whole file, not just the new class — the default
path must be unchanged).

- [ ] **Step 5: Update docs**

In `docs/MCTS.md`, find the `MCTSConfig` configuration section (grep for
`max_iterations`) and add one row/bullet in the same style as its
neighbors:

> `time_limit_s` (default `None`) — optional wall-clock budget in seconds
> for `search()`; checked at the end of each iteration, so at least one
> iteration always completes. `None` keeps the pure iteration-count
> behavior.

- [ ] **Step 6: Commit**

```bash
.venv/bin/python -m black src tests
git add src/quantik_core/mcts.py tests/test_mcts.py docs/MCTS.md
git commit -m "feat(mcts): optional wall-clock time_limit_s on MCTSConfig"
```

---

### Task 2: `BeamSearchConfig.time_limit_s`

**Files:**
- Modify: `src/quantik_core/beam_search.py`
- Test: `tests/test_beam_search.py` (append a new test class)

**Interfaces:**
- Consumes: existing `BeamSearchConfig`, `BeamSearchEngine.search`.
- Produces: `BeamSearchConfig(time_limit_s: Optional[float] = None)`;
  `BeamSearchEngine.search` stops deepening once the deadline passes
  (depth 1 always completes); `BeamSearchEngine.__init__` raises
  `ValueError` for `time_limit_s <= 0`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_beam_search.py`:

```python
class TestBeamSearchTimeLimit:
    """Optional wall-clock budget on BeamSearchEngine.search."""

    def test_time_limit_stops_deepening_early(self):
        from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine

        # Empty board + wide beam: a full 16-ply search takes many seconds,
        # so a tiny budget must stop well short of max_depth.
        engine = BeamSearchEngine(
            BeamSearchConfig(
                beam_width=64, max_depth=16, time_limit_s=0.05, random_seed=0
            )
        )
        result = engine.search(State.empty())
        assert 1 <= result.max_depth_reached < 16

    def test_depth_one_always_completes(self):
        from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine

        engine = BeamSearchEngine(
            BeamSearchConfig(
                beam_width=4, max_depth=16, time_limit_s=1e-9, random_seed=0
            )
        )
        result = engine.search(State.empty())
        assert result.max_depth_reached >= 1
        assert result.best_leaf is not None

    def test_no_time_limit_behavior_unchanged(self):
        from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine

        engine = BeamSearchEngine(
            BeamSearchConfig(beam_width=4, max_depth=3, random_seed=0)
        )
        result = engine.search(State.empty())
        assert result.max_depth_reached == 3

    def test_non_positive_time_limit_rejected(self):
        from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine

        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(time_limit_s=0.0))
        with pytest.raises(ValueError):
            BeamSearchEngine(BeamSearchConfig(time_limit_s=-0.5))
```

As in Task 1, reuse the file's existing `pytest`/`State` imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_beam_search.py::TestBeamSearchTimeLimit -v`
Expected: FAIL — unexpected keyword argument `time_limit_s`.

- [ ] **Step 3: Implement**

In `src/quantik_core/beam_search.py`:

3a. Add `import time` next to the existing `import random` at the top.

3b. In `BeamSearchConfig`, after the `rollout_schedule` field, add:

```python
    # Optional wall-clock budget for `search`, in seconds. Checked between
    # depth levels (after each completed level), so depth 1 always
    # completes and a wide level can overshoot the budget — callers that
    # need honest numbers should measure actual elapsed time themselves.
    time_limit_s: Optional[float] = None
```

3c. In `BeamSearchEngine.__init__`, after the `rollout_schedule`
validation block, add:

```python
        if config.time_limit_s is not None and config.time_limit_s <= 0:
            raise ValueError(
                f"time_limit_s must be positive, got {config.time_limit_s}"
            )
```

3d. In `BeamSearchEngine.search`, the current depth loop starts:

```python
        for depth in range(1, self.config.max_depth + 1):
            if not frontier:
                break
```

Compute the deadline just before the loop and add the check right after
the frontier check:

```python
        deadline = (
            time.monotonic() + self.config.time_limit_s
            if self.config.time_limit_s is not None
            else None
        )

        for depth in range(1, self.config.max_depth + 1):
            if not frontier:
                break
            if depth > 1 and deadline is not None and time.monotonic() >= deadline:
                break
```

Note: `reached_terminal` is computed as `not frontier`, which stays
correct — a time-limited stop leaves a non-empty frontier, so
`reached_terminal` is `False`, as it should be.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_beam_search.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Update docs**

In `docs/BEAM_SEARCH.md`, find the `BeamSearchConfig` section (grep for
`beam_width`) and add, in the same style:

> `time_limit_s` (default `None`) — optional wall-clock budget in seconds
> for `search()`; checked between depth levels (depth 1 always completes),
> so a wide level can overshoot the cap. `None` keeps depth/width as the
> only stop conditions.

- [ ] **Step 6: Full gate and commit**

Run: `./dev-check.sh`
Expected: all checks pass, coverage ≥ 90%.

```bash
.venv/bin/python -m black src tests
git add src/quantik_core/beam_search.py tests/test_beam_search.py docs/BEAM_SEARCH.md
git commit -m "feat(beam): optional wall-clock time_limit_s on BeamSearchConfig"
```

---

## Self-review checklist (run yourself before moving to part 2)

- [ ] `MCTSConfig(time_limit_s=None)` and `BeamSearchConfig(time_limit_s=None)`
      reproduce today's behavior exactly (no new time calls on the None path
      besides one comparison).
- [ ] Both engines guarantee minimum work (1 iteration / depth 1).
- [ ] `./dev-check.sh` green.
