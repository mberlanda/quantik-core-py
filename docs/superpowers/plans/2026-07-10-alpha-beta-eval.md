# Classical Alpha-Beta Search with Handcrafted Evaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic alpha-beta minimax engine with a *fitted* handcrafted evaluation function to `quantik-core`, plus a solver-backed weight-tuning pipeline, benchmarks, and docs.

**Architecture:** A pure, linear-in-features evaluation (`evaluation.py`) scores non-terminal leaves; a negamax/alpha-beta engine (`minimax.py`) with iterative deepening and a `canonical_key()`-keyed transposition table drives search and doubles as the exact solver. A `tuning/` pipeline labels solver-solved positions and fits the eval weights by logistic regression. Examples, benchmarks, docs, and a dated research note complete it.

**Tech Stack:** Python 3.12+, numpy (already a dependency), pytest, hypothesis. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-07-10-alpha-beta-eval-design.md` (authoritative — read it).

## Global Constraints

- Python `>=3.12`. No new runtime dependencies (numpy, psutil, zstandard only). Fit uses numpy alone — no scikit-learn.
- Follow the existing `*Config` dataclass + `*Engine` class pattern (`mcts.py`, `beam_search.py`).
- Bitboards are 8-tuples of `int` (`Bitboard`); `State(bb).bb` returns the tuple; `State(bb).canonical_key()` returns 18 bytes.
- Win detection for search uses `has_winning_line(bb)` (NOT `check_game_winner`) — a winning line means the *previous* mover won.
- Symmetry group is D4 × S4 = 192, **no color/player swap**. Eval must be symmetry-invariant.
- TDD: failing test first. Quality gates before every commit-heavy task boundary: `./auto-lint.sh` then `./dev-check.sh`. Coverage ≥ 90%.
- Commit messages end with the repo's Co-Authored-By trailer.
- Player 0 shapes are uppercase in QFEN; player 1 lowercase.

---

## File Structure

- `src/quantik_core/evaluation.py` — `EvalConfig`, `FEATURE_NAMES`, `features(bb, player) -> np.ndarray`, `evaluate(bb, player, cfg) -> float`, `count_legal_moves(bb, player) -> int`.
- `src/quantik_core/minimax.py` — `MinimaxConfig`, `MinimaxResult`, `MinimaxEngine`, `Bound` enum.
- `tuning/build_dataset.py` — sample + solve + dedup → `tuning/dataset.npz`.
- `tuning/fit_weights.py` — logistic-regression fit → `tuning/weights.json` + metrics.
- `tuning/weights.json` — fitted weights (checked in).
- `examples/minimax_demo.py`, `examples/minimax_benchmark.py`.
- `tests/test_evaluation.py`, `tests/test_minimax.py`, `tests/test_tuning.py`.
- `docs/MINIMAX.md`; update `docs/EXAMPLES.md`, `README.md`, `src/quantik_core/__init__.py`.
- `docs/research/2026-07-10-alpha-beta-eval-vs-mcts.md` (docs agent).

---

## Task 1: Evaluation features & scoring

**Files:**
- Create: `src/quantik_core/evaluation.py`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: `quantik_core.commons.WIN_MASKS`, `quantik_core.game_utils.count_pieces_by_shape`, `quantik_core.move.generate_legal_moves_list`, `quantik_core.game_utils.get_current_player_from_counts`, `has_winning_line`.
- Produces:
  - `FEATURE_NAMES: list[str]` = `["threat_own","threat_opp","threat_shared","mobility_diff","build_two","build_one"]`
  - `features(bb: Bitboard, player: int) -> np.ndarray` (shape `(6,)`, float64)
  - `evaluate(bb: Bitboard, player: int, cfg: EvalConfig = EvalConfig()) -> float`
  - `count_legal_moves(bb: Bitboard, player: int) -> int`
  - `EvalConfig` dataclass: `weights: np.ndarray` (shape `(6,)`), `win: float = 10_000.0`; classmethod `EvalConfig.load(path=None)` returning seeded defaults if no file. Seeded weights: `[100, -100, 20, 3, 2, 0]`.

**Feature semantics (implement exactly):** for each of the 12 `WIN_MASKS`, compute `present = {s in 0..3 : (bb[s] | bb[s+4]) & mask}`, `occupied = popcount(union_all_shapes & mask)`. A line is *dead* if `len(present) < occupied` (a shape repeats). For a live line (`len(present) == occupied`):
- `occupied==3` → live threat, missing shape `m = the one shape not in present`, empty cell `q` = the empty position in mask. `player` can complete iff it still holds a copy of `m` (its count < 2) AND placing `m` at `q` is legal for `player` (opponent has no shape-`m` bit on any `WIN_MASKS` line through `q`). Compute completability for both players → increment `threat_own`/`threat_opp`/`threat_shared`. `threat_shared` is signed `+1` if side-to-move == player else `-1`.
- `occupied==2` → `build_two += sign`; `occupied==1` → `build_one += sign`, where `sign = +1` if side-to-move==player else `-1`.
- `mobility_diff = count_legal_moves(bb, player) - count_legal_moves(bb, 1-player)`.

Side-to-move comes from `get_current_player_from_counts(sum(p0), sum(p1))`.

- [ ] **Step 1: Write failing tests**

```python
import numpy as np
import pytest
from quantik_core import State
from quantik_core.evaluation import (
    EvalConfig, FEATURE_NAMES, features, evaluate, count_legal_moves,
)

def _bb(qfen): return State.from_qfen(qfen).bb

def test_feature_names_order():
    assert FEATURE_NAMES == ["threat_own","threat_opp","threat_shared",
                             "mobility_diff","build_two","build_one"]

def test_dead_line_scores_zero_threat():
    # Row 0 has shape A twice (A at 0, A-lower at 1) -> can never be 4-distinct
    f = features(_bb("Aa../..../..../...."), player=0)
    # no live 3-threats anywhere
    assert f[0] == 0 and f[1] == 0

def test_three_distinct_line_is_live_threat():
    # Row 0: A b C . -> 3 distinct shapes, missing D at pos 3
    f = features(_bb("AbC./..../..../...."), player=0)
    assert f[0] + f[1] + abs(f[2]) >= 1  # a threat is detected

def test_evaluate_is_dot_product():
    cfg = EvalConfig()
    bb = _bb("AbC./..../d..B/...a")
    assert evaluate(bb, 0, cfg) == pytest.approx(float(cfg.weights @ features(bb, 0)))

def _all_192_variants(bb):
    # VERIFIED API: D4 x S4 = 192, no color swap (canonical_key excludes color swap).
    from quantik_core.symmetry import SymmetryHandler as SH
    out = []
    for d4 in range(8):
        g = [SH.permute16(bb[i], d4) for i in range(8)]  # g[0:4]=P0 shapes, g[4:8]=P1
        for perm in SH.ALL_SHAPE_PERMS:
            out.append(tuple(g[c * 4 + perm[s]] for c in range(2) for s in range(4)))
    return out  # 192 boards (with duplicates for symmetric positions)

def test_symmetry_invariance():
    bb = _bb("AbC./..../d..B/...a")
    base = evaluate(bb, 0)
    for variant in _all_192_variants(bb):
        assert evaluate(variant, 0) == pytest.approx(base)

def test_perspective_relationship():
    # threat_own/opp swap and mobility negates when perspective flips
    bb = _bb("AbC./..../d..B/...a")
    f0, f1 = features(bb, 0), features(bb, 1)
    assert f0[0] == f1[1] and f0[1] == f1[0]
    assert f0[3] == -f1[3]
```

- [ ] **Step 2: Run tests, verify they fail** — `.venv/bin/pytest tests/test_evaluation.py -x` → ImportError/fail.

  NOTE: variant enumeration uses the VERIFIED API `SymmetryHandler.permute16(val, d4_idx)` + `SymmetryHandler.ALL_SHAPE_PERMS` (24 perms). Confirmed: `canonical_key()` covers D4×S4=192 with NO color swap, so eval invariance is over these 192 only.

- [ ] **Step 3: Implement `evaluation.py`** per the feature semantics above. Keep `features` pure and allocation-light. `count_legal_moves` = `len(generate_legal_moves_list(bb))`.

- [ ] **Step 4: Run tests, verify pass** — `.venv/bin/pytest tests/test_evaluation.py -v`.

- [ ] **Step 5: Lint + commit** — `./auto-lint.sh`; `git add src/quantik_core/evaluation.py tests/test_evaluation.py`; commit `feat(eval): add fitted-linear evaluation features and scoring`.

---

## Task 2: Minimax engine (negamax + alpha-beta + terminal + eval cutoff)

**Files:**
- Create: `src/quantik_core/minimax.py`
- Test: `tests/test_minimax.py`

**Interfaces:**
- Consumes: `evaluation.evaluate`, `EvalConfig`; `generate_legal_moves_list`, `apply_move`; `has_winning_line`; `State`.
- Produces:
  - `class Bound(IntEnum): EXACT=0; LOWER=1; UPPER=2`
  - `MinimaxConfig` dataclass: `max_depth:int=16`, `time_limit_s:float|None=None`, `use_alpha_beta:bool=True`, `use_transposition_table:bool=True`, `dedup_children:bool=True`, `eval_config:EvalConfig=field(default_factory=EvalConfig)`, `random_seed:int|None=None`.
  - `MinimaxResult` dataclass: `best_move:Move`, `score:float`, `depth_reached:int`, `nodes:int`, `pv:list[Move]`, `elapsed:float`.
  - `class MinimaxEngine: __init__(self, config); search(self, state:State) -> MinimaxResult; solve(self, state:State) -> MinimaxResult` (solve = search with max_depth=16, no time limit).

**Negamax core:** value from side-to-move perspective. At a node: if `has_winning_line(bb)` → previous mover won → return `-(win - ply)`. Else `moves = generate_legal_moves_list(bb)`; if empty → side-to-move loses → `-(win - ply)`. If `depth == 0` → return `evaluate(bb, side_to_move, eval_config)`. Else recurse `-negamax(child, depth-1, -beta, -alpha, ply+1)`, applying alpha-beta when `use_alpha_beta`. `win - ply` uses `ply` so shallower mates score higher.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from quantik_core import State
from quantik_core.minimax import MinimaxEngine, MinimaxConfig

def cfg(**kw): return MinimaxConfig(**kw)

def test_finds_mate_in_one():
    # Row 0 = A b C . ; player 0 to move can place D at pos 3 to complete 4 distinct
    e = MinimaxEngine(cfg(max_depth=2))
    r = e.search(State.from_qfen("AbC./..../..../...."))
    assert r.best_move.position == 3 and r.best_move.shape == 3  # D at pos 3
    assert r.score >= 9000  # near-win magnitude

def test_blocks_opponent_mate_in_one():
    # Opponent (to move) threatens; engine as side-to-move must not hand a mate.
    # Construct a position where exactly one move avoids immediate loss; assert engine picks it.
    # (Implementer: build via QFEN + verify with a full-depth solve in the test.)
    ...

def test_alpha_beta_equals_plain_minimax():
    s = State.from_qfen("A.../..../..../....")
    v_ab = MinimaxEngine(cfg(max_depth=4, use_alpha_beta=True,
                             use_transposition_table=False)).search(s).score
    v_plain = MinimaxEngine(cfg(max_depth=4, use_alpha_beta=False,
                                use_transposition_table=False)).search(s).score
    assert v_ab == pytest.approx(v_plain)

def test_tt_equals_no_tt():
    s = State.from_qfen("A.../..../..../....")
    v_tt = MinimaxEngine(cfg(max_depth=6, use_transposition_table=True)).search(s).score
    v_no = MinimaxEngine(cfg(max_depth=6, use_transposition_table=False)).search(s).score
    assert v_tt == pytest.approx(v_no)

def test_iterative_deepening_matches_fixed_depth():
    s = State.from_qfen("A.../..../..../....")
    # ID to depth 4 should agree in value with a direct depth-4 search
    v_id = MinimaxEngine(cfg(max_depth=4)).search(s).score
    assert v_id == pytest.approx(
        MinimaxEngine(cfg(max_depth=4, use_transposition_table=False,
                          use_alpha_beta=False)).search(s).score)
```

- [ ] **Step 2: Run, verify fail.** Fill in `test_blocks_opponent_mate_in_one` with a concrete QFEN whose unique safe move is verified by a `max_depth=16` solve inside the test (assert the engine's move equals the solver's move and score > -9000).

- [ ] **Step 3: Implement** negamax + alpha-beta + eval cutoff (no ID/TT yet). Terminal via `has_winning_line`. Deterministic tie-break: among equal-score moves pick the lowest `(shape, position)` unless `random_seed` set. Get side-to-move from the move list / piece counts.

- [ ] **Step 4: Add iterative deepening + PV.** Deepen 1..max_depth (or until `time_limit_s`); seed ordering with prior PV; record `pv`, `depth_reached`, `nodes`, `elapsed`.

- [ ] **Step 5: Add transposition table.** Dict keyed `state.canonical_key()` → `(depth, value, Bound, )`. On probe: if stored depth ≥ remaining depth, use EXACT directly, tighten alpha/beta for LOWER/UPPER, cutoff if `alpha>=beta`. Store after search with correct bound. Add optional `dedup_children` (collapse sibling moves with equal `canonical_key()` of resulting state; keep one representative; at root keep a concrete move). Value cached, NOT move.

- [ ] **Step 6: Run all tests, verify pass** — `.venv/bin/pytest tests/test_minimax.py -v`.

- [ ] **Step 7: Lint + commit** — `./auto-lint.sh`; commit `feat(minimax): negamax alpha-beta engine with ID + transposition table`.

---

## Task 3: Solve correctness anchor

**Files:** Modify: `tests/test_minimax.py`

**Interfaces:** Consumes `MinimaxEngine.solve`.

- [ ] **Step 1: Write the solve test** (may be marked `@pytest.mark.slow` if long):

```python
def test_full_solve_first_player_result():
    # Quantik is a known first-player (P0) win with perfect play.
    r = MinimaxEngine(MinimaxConfig(max_depth=16)).solve(State.empty())
    assert r.score > 0        # side-to-move (P0) wins
    assert len(r.pv) >= 1
```

- [ ] **Step 2: Run it.** If it is too slow (> ~30s), keep `dedup_children=True` + TT; if still slow, mark `slow` and document runtime. Record nodes/time for the research note.

- [ ] **Step 3: Commit** — `test(minimax): full-depth solve confirms first-player win`.

---

## Task 4: Tuning pipeline (dataset + fit)

**Files:**
- Create: `tuning/build_dataset.py`, `tuning/fit_weights.py`, `tuning/weights.json`
- Test: `tests/test_tuning.py`

**Interfaces:**
- `build_dataset.py`: functions `sample_states(n, max_plies, seed) -> list[State]` (random legal playouts, stop before terminal, dedup by `canonical_key()`), `label_state(state) -> int` (solver value sign via `MinimaxEngine.solve`; `+1/0/-1` for side-to-move), `main()` writing `tuning/dataset.npz` with arrays `X` (N×6 from `features(bb, stm)`) and `y` (N,).
- `fit_weights.py`: `fit(X, y, seed) -> np.ndarray` (logistic regression, numpy gradient descent, deterministic), `sign_accuracy(w, X, y) -> float`, `main()` writing `tuning/weights.json` = `{"weights": [...], "win": 10000, "sign_accuracy": ...}` and printing seeded-vs-fitted accuracy.
- `EvalConfig.load()` reads `tuning/weights.json` if present.

- [ ] **Step 1: Write failing tests**

```python
import numpy as np
from quantik_core.evaluation import features, EvalConfig
from quantik_core import State

def test_features_match_evaluate_dot():
    from quantik_core.evaluation import evaluate
    bb = State.from_qfen("AbC./..../d..B/...a").bb
    cfg = EvalConfig()
    assert evaluate(bb, 0, cfg) == float(cfg.weights @ features(bb, 0))

def test_fit_is_reproducible():
    from tuning.fit_weights import fit
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 6)); y = (X[:,0] - X[:,1] > 0).astype(int)
    w1 = fit(X, y, seed=42); w2 = fit(X, y, seed=42)
    assert np.allclose(w1, w2)

def test_fit_separates_simple_signal():
    from tuning.fit_weights import fit, sign_accuracy
    rng = np.random.default_rng(1)
    X = rng.normal(size=(500, 6)); y = (X[:,0] - X[:,1] > 0).astype(int)
    w = fit(X, y, seed=0)
    assert sign_accuracy(w, X, y) > 0.9
```

- [ ] **Step 2: Run, verify fail.** Ensure `tuning/` is importable in tests (add `conftest.py` path insert or a `tuning/__init__.py`; check how `examples` are imported in `tests/test_examples_demos.py`).

- [ ] **Step 3: Implement** `fit_weights.py` (logistic regression, L2 reg, fixed iterations, deterministic) and `build_dataset.py`.

- [ ] **Step 4: Generate real artifacts.** Run `.venv/bin/python tuning/build_dataset.py` then `.venv/bin/python tuning/fit_weights.py`; commit `tuning/weights.json` (and note dataset size/accuracy for the research note). Keep dataset small enough to build in < ~2 min; do NOT commit large `.npz` (add to `.gitignore`).

- [ ] **Step 5: Run tests, lint, commit** — `feat(tuning): solver-labeled dataset + logistic-regression weight fit`.

---

## Task 5: Examples & benchmarks

**Files:** Create `examples/minimax_demo.py`, `examples/minimax_benchmark.py`; Modify `tests/test_examples_demos.py` (smoke).

**Interfaces:** Consumes `MinimaxEngine`, `MCTSEngine`. Reuse `format_move`/`print_board` conventions from `examples/mcts_demo.py`.

- [ ] **Step 1:** `minimax_demo.py` — analyze a tactical QFEN, print best move + PV + ID trace; a tiny minimax-vs-random and minimax-vs-MCTS match. Guard heavy work under `if __name__ == "__main__"`.
- [ ] **Step 2:** `minimax_benchmark.py` — the 3 benchmark categories (strength table; nodes/sec + prune ratio with ab/TT on-off + depth@time; solve stats; eval sign-accuracy & move-agreement seeded-vs-fitted). Print a compact report.
- [ ] **Step 3:** Add a smoke test importing both demos (pattern from `tests/test_examples_demos.py`) so coverage/CI exercises them cheaply.
- [ ] **Step 4:** Run `.venv/bin/python examples/minimax_benchmark.py`; capture numbers for the research note.
- [ ] **Step 5:** Lint + commit — `feat(examples): minimax demo + benchmark harness`.

---

## Task 6: Public API & library docs

**Files:** Modify `src/quantik_core/__init__.py`, `docs/EXAMPLES.md`, `README.md`; Create `docs/MINIMAX.md`; Modify `tests/test_public_api.py` / `tests/test_import_contracts.py`.

- [ ] **Step 1:** Export `MinimaxEngine, MinimaxConfig, MinimaxResult, evaluate, EvalConfig` at TOP LEVEL in `__init__.py` `__all__`. (Note: `MCTSEngine`/`BeamSearchEngine` are module-only, imported via `quantik_core.mcts`; we deliberately surface the new engine top-level as the headline classical-search API. Keep `from quantik_core.minimax import MinimaxEngine` working too.)
- [ ] **Step 2:** Update import-contract/public-api tests to cover the new names.
- [ ] **Step 3:** Write `docs/MINIMAX.md` mirroring `docs/MCTS.md` structure (overview, config, usage, TT/ID notes, tuning, benchmarks). Add entries to `docs/EXAMPLES.md` and the README examples table.
- [ ] **Step 4:** Run `./dev-check.sh` (full gate, coverage ≥ 90%). Fix gaps.
- [ ] **Step 5:** Commit — `feat(api): export minimax + evaluation; docs and MINIMAX.md`.

---

## Task 7: Research design note (documentation agent)

**Files:** Create `docs/research/2026-07-10-alpha-beta-eval-vs-mcts.md`.

- [ ] **Step 1:** Write a standalone, clearly-explanatory design note (NOT rewriting earlier dated papers): the evaluation heuristic & feature vector; the oracle-backed fitting methodology + resulting fitted weights and sign-accuracy/move-agreement; alpha-beta/ID/TT machinery; the symmetry-soundness argument (D4×S4, no color swap) for the TT; and the measured benchmarks from Tasks 3–5. Anchor combinatorial claims to `GAME_TREE_ANALYSIS.md` where relevant.
- [ ] **Step 2:** Commit — `docs(research): alpha-beta + fitted eval vs MCTS design note`.

---

## Self-Review notes (author)

- Spec coverage: §4 eval → T1; §4.6 tuning → T4; §5 engine/TT/ID → T2; solve §7.3 → T3; benchmarks §7 → T3/T5; tests §8 → T1–T4; API/docs §6/§9 → T6; research §9 → T7. Covered.
- Known adjustable points the implementer MUST verify against real APIs (called out inline): the symmetry-variant enumeration method in `symmetry.py`; how `examples`/`tuning` modules are made importable in tests; whether `MCTSEngine` is a top-level export. These are verification steps, not placeholders.
- Type consistency: `features` returns `(6,)` float64 everywhere; `EvalConfig.weights` is `(6,)`; `evaluate == weights @ features`; `MinimaxResult` fields consistent across tasks.
