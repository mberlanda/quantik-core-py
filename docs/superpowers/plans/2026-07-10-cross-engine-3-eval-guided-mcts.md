# Cross-Engine Follow-up 3: Eval-Guided MCTS Rollouts

> **For agentic workers:** Execute task-by-task with TDD. This modifies the library module `src/quantik_core/mcts.py`, so the full `./dev-check.sh` coverage gate applies. Read `docs/MCTS.md` and `docs/MINIMAX.md` first. Read the whole of `src/quantik_core/mcts.py` before editing.

**Goal:** Let MCTS use the fitted handcrafted evaluation (`quantik_core.evaluation`) to guide its random playouts instead of pure-random move selection, via an opt-in config option. Default behavior is unchanged (pure random).

**Architecture:** Add two `MCTSConfig` fields (`rollout_eval_config`, `rollout_epsilon`) and one helper method `_select_rollout_move`. In `_simulate`, replace the single random-move pick with a call to that helper. When no eval config is set, the helper falls back to `random.choice`, so existing behavior and tests are preserved exactly.

**Tech Stack:** Python 3.12+, numpy only.

## Global Constraints
- Python `>=3.12`, numpy only. No new deps.
- **Backward compatibility is mandatory:** with `rollout_eval_config=None` (the default), MCTS must behave byte-for-byte as before. Existing `tests/test_mcts.py` must still pass unchanged.
- `./auto-lint.sh` then `./dev-check.sh` (coverage ≥ 90%) before the final commit.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Follow the existing `mcts.py` style (numpy scalar wrapping, docstrings).

## Verified existing internals (in `src/quantik_core/mcts.py`)
- `@dataclass MCTSConfig` has: `exploration_weight`, `max_iterations`, `max_depth`, `random_seed`, `use_transposition_table`. Add fields here.
- `MCTSEngine.__init__(self, config)` seeds `random.seed(config.random_seed)` when set — the module uses the global `random`.
- `_simulate(self, node_id)` runs the playout loop. Inside it:
  ```python
  current_player, moves_by_shape = generate_legal_moves(current_bb)
  all_moves = []
  for shape_moves in moves_by_shape.values():
      all_moves.extend(shape_moves)
  if not all_moves:
      return -1.0 if current_player == 0 else 1.0
  # Pick random move
  move = random.choice(all_moves)
  current_bb = apply_move(current_bb, move)  # type: ignore[assignment]
  depth += 1
  ```
- Existing imports include `random`, `apply_move`, `generate_legal_moves`, `State`.

## Evaluation API (already merged)
- `from quantik_core.evaluation import EvalConfig, evaluate`
- `evaluate(bb, player, cfg) -> float` — higher is better for `player`. Pass `EvalConfig.load()` for fitted weights.

---

## Task 1: Config fields + `_select_rollout_move` helper + wire into `_simulate`

**Files:**
- Modify: `src/quantik_core/mcts.py`
- Test: `tests/test_mcts.py` (append new tests; do not modify existing)

**Interfaces produced:**
- `MCTSConfig.rollout_eval_config: Optional[EvalConfig] = None`
- `MCTSConfig.rollout_epsilon: float = 0.2`
- `MCTSEngine._select_rollout_move(self, bb, current_player, all_moves) -> Move`

- [ ] **Step 1: Write failing tests** (append to `tests/test_mcts.py`):

```python
def test_rollout_move_defaults_to_random_when_no_eval():
    # With no eval config, the helper must just pick from the legal moves.
    from quantik_core import State
    from quantik_core.mcts import MCTSEngine, MCTSConfig
    from quantik_core.move import generate_legal_moves_list
    engine = MCTSEngine(MCTSConfig(max_iterations=1, random_seed=0))
    bb = State.from_qfen("A.../..../..../....").bb
    legal = generate_legal_moves_list(bb)
    move = engine._select_rollout_move(bb, 1, legal)
    assert move in legal


def test_eval_guided_rollout_is_deterministic_and_legal():
    from quantik_core import State
    from quantik_core.mcts import MCTSEngine, MCTSConfig
    from quantik_core.evaluation import EvalConfig
    from quantik_core.move import generate_legal_moves_list
    bb = State.from_qfen("Ab../..Cd/..../....").bb
    legal = generate_legal_moves_list(bb)
    cfg = MCTSConfig(max_iterations=1, random_seed=7,
                     rollout_eval_config=EvalConfig(), rollout_epsilon=0.0)
    # epsilon=0 => pure greedy argmax over evaluate; deterministic.
    m1 = MCTSEngine(cfg)._select_rollout_move(bb, 0, legal)
    m2 = MCTSEngine(cfg)._select_rollout_move(bb, 0, legal)
    assert m1 == m2 and m1 in legal


def test_eval_guided_search_finds_mate_in_one():
    from quantik_core import State
    from quantik_core.mcts import MCTSEngine, MCTSConfig
    from quantik_core.evaluation import EvalConfig
    cfg = MCTSConfig(max_iterations=400, random_seed=1,
                     rollout_eval_config=EvalConfig.load(), rollout_epsilon=0.2)
    best_move, _ = MCTSEngine(cfg).search(State.from_qfen("AbC./..../..../...."))
    assert best_move.shape == 3 and best_move.position == 3  # D at pos 3


def test_default_mcts_unchanged():
    # Regression: default config still returns a legal move; no eval used.
    from quantik_core import State
    from quantik_core.mcts import MCTSEngine, MCTSConfig
    best_move, prob = MCTSEngine(
        MCTSConfig(max_iterations=200, random_seed=0)
    ).search(State.from_qfen("ABc./d.../..../...."))
    assert best_move is not None and 0.0 <= prob <= 1.0
```

- [ ] **Step 2: Run, verify fail** — `.venv/bin/pytest tests/test_mcts.py -k "rollout or eval_guided or default_mcts" -x --no-cov`.

- [ ] **Step 3: Add imports + config fields.** In `src/quantik_core/mcts.py`:
  - Add to the imports near the top: `from quantik_core.evaluation import EvalConfig, evaluate`.
  - In `MCTSConfig`, add (keep existing fields):
    ```python
    # Optional eval-guided rollouts: when set, playout moves are chosen by
    # the fitted handcrafted evaluation instead of uniformly at random.
    # epsilon keeps some exploration (variance) so MCTS statistics stay
    # meaningful. None => original pure-random rollouts (default).
    rollout_eval_config: Optional[EvalConfig] = None
    rollout_epsilon: float = 0.2
    ```
    (`Optional` is already imported.)

- [ ] **Step 4: Add the helper method** to `MCTSEngine` (place it just above `_simulate`):

```python
    def _select_rollout_move(self, bb, current_player, all_moves):
        """Choose a playout move.

        With no `rollout_eval_config`, this is a uniform random choice
        (original behavior). Otherwise it is epsilon-greedy: with
        probability `rollout_epsilon` a uniform random move, else the move
        whose resulting position the fitted evaluation scores highest for
        `current_player`. Ties break on the first max encountered.
        """
        cfg = self.config.rollout_eval_config
        if cfg is None:
            return random.choice(all_moves)
        if random.random() < self.config.rollout_epsilon:
            return random.choice(all_moves)
        best_move = all_moves[0]
        best_score = float("-inf")
        for move in all_moves:
            child_bb = apply_move(bb, move)
            score = evaluate(child_bb, current_player, cfg)
            if score > best_score:
                best_score = score
                best_move = move
        return best_move
```

- [ ] **Step 5: Wire into `_simulate`.** Replace exactly this block:
```python
            # Pick random move
            move = random.choice(all_moves)
            current_bb = apply_move(current_bb, move)  # type: ignore[assignment]
```
with:
```python
            # Pick a rollout move (random, or eval-guided if configured)
            move = self._select_rollout_move(current_bb, current_player, all_moves)
            current_bb = apply_move(current_bb, move)  # type: ignore[assignment]
```

- [ ] **Step 6: Run tests, verify pass** — `.venv/bin/pytest tests/test_mcts.py -v --no-cov` (both new and existing).

- [ ] **Step 7: Full gate** — `./auto-lint.sh` then `./dev-check.sh`. Coverage of `mcts.py` must stay ≥ 90% overall; the new branch is exercised by the tests above.

- [ ] **Step 8: Commit** — `git add src/quantik_core/mcts.py tests/test_mcts.py`; commit `feat(mcts): optional eval-guided rollout policy`.

---

## Task 2: Document the option

**Files:** Modify `docs/MCTS.md`.
- [ ] **Step 1:** Add a short "Eval-guided rollouts" subsection: how to enable it (`MCTSConfig(rollout_eval_config=EvalConfig.load(), rollout_epsilon=0.2)`), the epsilon/variance trade-off, and the honest cost note: evaluating every candidate move per playout step is far more expensive than a random pick, so use fewer iterations or expect slower searches.
- [ ] **Step 2:** Commit — `docs(mcts): document eval-guided rollout option`.

---

## Self-review checklist
- Default path (`rollout_eval_config=None`) is literally `random.choice(all_moves)` — behavior identical; existing tests untouched and passing.
- Determinism holds because both the epsilon draw and the fallback use the global `random` seeded in `__init__`.
- Cost caveat documented (per-move evaluate in the inner playout loop).
