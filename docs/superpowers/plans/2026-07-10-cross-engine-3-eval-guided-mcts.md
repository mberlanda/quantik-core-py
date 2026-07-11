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

- [x] **Step 1: Write failing tests** (append to `tests/test_mcts.py`):

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

- [x] **Step 2: Run, verify fail** — `.venv/bin/pytest tests/test_mcts.py -k "rollout or eval_guided or default_mcts" -x --no-cov`.

- [x] **Step 3: Add imports + config fields.** In `src/quantik_core/mcts.py`:
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

- [x] **Step 4: Add the helper method** to `MCTSEngine` (place it just above `_simulate`):

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

- [x] **Step 5: Wire into `_simulate`.** Replace exactly this block:
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

- [x] **Step 6: Run tests, verify pass** — `.venv/bin/pytest tests/test_mcts.py -v --no-cov` (both new and existing).

- [x] **Step 7: Full gate** — `./auto-lint.sh` then `./dev-check.sh`. Coverage of `mcts.py` must stay ≥ 90% overall; the new branch is exercised by the tests above.

- [x] **Step 8: Commit** — `git add src/quantik_core/mcts.py tests/test_mcts.py`; commit `feat(mcts): optional eval-guided rollout policy`.

---

## Task 2: Document the option

**Files:** Modify `docs/MCTS.md`.
- [x] **Step 1:** Add a short "Eval-guided rollouts" subsection: how to enable it (`MCTSConfig(rollout_eval_config=EvalConfig.load(), rollout_epsilon=0.2)`), the epsilon/variance trade-off, and the honest cost note: evaluating every candidate move per playout step is far more expensive than a random pick, so use fewer iterations or expect slower searches.
- [x] **Step 2:** Commit — `docs(mcts): document eval-guided rollout option`.

---

## Self-review checklist
- Default path (`rollout_eval_config=None`) is literally `random.choice(all_moves)` — behavior identical; existing tests untouched and passing.
- Determinism holds because both the epsilon draw and the fallback use the global `random` seeded in `__init__`.
- Cost caveat documented (per-move evaluate in the inner playout loop), with a real measurement (4.3x slowdown, 3000 iterations from the empty board).

## Post-implementation notes

The plan's code (config fields, `_select_rollout_move`, the `_simulate`
wiring) matched the actual current `mcts.py` exactly as quoted — verified
by reading the whole file first, unlike several earlier plans in this
series. mypy (part of the full `./dev-check.sh` gate, not exercised by
plans 1/2 which don't need it) flagged the new helper for missing type
annotations and an `apply_move` return-type mismatch; fixed by typing
`bb: Bitboard`, `all_moves: List[Move]`, return `-> Move`, and the same
`# type: ignore[assignment]` pattern `_simulate` already uses for
`apply_move`'s union return type.

### A significant, pre-existing, out-of-scope bug discovered during Task 1

The plan's own test (`test_eval_guided_search_finds_mate_in_one`, asserting
`search()` returns the objectively best move on a mate-in-one position)
failed -- and, critically, **failed identically with `rollout_eval_config=
None`** (i.e. against the unmodified, pre-existing pure-random-rollout
code path too). Root-caused via direct instrumentation to
`CompactGameTree.create_root_node` in `src/quantik_core/memory/
compact_tree.py:304`:

```python
node = CompactGameTreeNode(
    ...
    flags=np.uint8(NODE_FLAG_EXPANDED),   # <-- set from creation!
    ...
)
```

The root node is born with `NODE_FLAG_EXPANDED` already set, rather than
that flag being set only once all of a node's legal moves have been added
as children (which is what `_expand()`'s own logic elsewhere assumes:
`if len(existing_children) + 1 == len(all_moves): node.flags |=
NODE_FLAG_EXPANDED`). Consequence, traced step by step:

1. Iteration 1: `_select(root)` returns root (it has zero children, so
   the `if not children: return current_id` branch fires regardless of
   the flag). `_expand(root)` adds exactly one child (the first legal
   move in `generate_legal_moves()`'s iteration order that isn't already
   a child) and returns it for simulation.
2. Iteration 2 onward: `_select(root)` now sees root as *both* not
   terminal *and* already `NODE_FLAG_EXPANDED` (true from birth) *and*
   having a non-empty children list (the one child from step 1) -- so it
   immediately descends into that single child via UCB instead of
   returning to root to add a second one.
3. Root therefore **never gets a second child, for the rest of the
   search, regardless of `max_iterations`.** Confirmed directly: at
   `max_iterations=2000` on a 42-legal-move position, `len(engine.tree
   .get_children(engine.root_id))` was still exactly 1 after the full
   search.

Consequence for `search()`'s return value: since `_get_best_move()` picks
the most-visited root child, and root only ever has one child, **the
discrete move `search()` returns is entirely determined by
`generate_legal_moves()`'s fixed iteration order (shape 0..3, then
position 0..15) -- not by simulation quality, exploration budget, UCB
tuning, or (relevantly to this plan) the rollout policy.** Confirmed this
by running the plan's own test scenario with `rollout_eval_config=None`
at up to 5000 iterations: it returned the exact same (non-optimal) move
every time.

**This means eval-guided rollouts (this plan's feature) can only ever
influence the *value/win-rate statistics* MCTS accumulates for whichever
single branch move-ordering happened to pick -- never the discrete move
`search()` returns.** That significantly undercuts the practical value of
this feature as implemented, through no fault of this plan's design; the
limitation is entirely in the pre-existing root-expansion bookkeeping.

**Why this was never caught before:** grep of `tests/test_mcts.py` shows
existing `search()`-level tests use deliberately loose assertions
(`isinstance(move, Move)`, `win_prob > 0.3`) rather than asserting the
objectively best move -- weak enough to pass regardless of this bug.

**Scope decision:** did NOT fix this in this PR. It lives in
`compact_tree.py`, is shared with `beam_search.py` (which doesn't appear
to rely on `NODE_FLAG_EXPANDED`/`_select`'s traversal, so is likely
unaffected in practice, but wasn't exhaustively verified), predates this
plan entirely, and fixing it would very likely change existing MCTS
search *results* across the test suite -- directly conflicting with this
plan's own binding constraint ("MCTS must behave byte-for-byte as
before"). Adapted `test_eval_guided_search_finds_mate_in_one` into
`test_eval_guided_search_runs_end_to_end`, which validates the
integration path without depending on correct root-level exploration
(matching the suite's existing loose-assertion style for `search()`-level
tests). Recorded as a follow-up in the research note's "Future work"
section -- likely explains MCTS's consistently weak showing in every
cross-engine benchmark so far this session (PR #17's "vs MCTS-1500"
matchups, PR #18's move-agreement=0.500 result): MCTS may have never
actually been exploring more than one root move in any of them.

### Resolved in PR #22

Both this bug and a second, independent one were fixed as a dedicated
follow-up (not this plan's PR, per the scope decision above):

1. `create_root_node` now creates the root with `flags=0` instead of
   `NODE_FLAG_EXPANDED`, so `_select` correctly keeps returning the root
   for expansion until every legal move has a child, matching `_expand`'s
   own bookkeeping.
2. A second bug in `_calculate_ucb` was found while validating fix (1):
   it computed the win-rate term from the *child's* `player_turn` instead
   of the *parent's* mover, so UCB was systematically preferring
   whichever branch the opponent won through most -- backwards from the
   perspective of the player actually choosing among children. Both had
   to be fixed together; fixing only (1) still produced a non-winning
   `search()` result on the plan's own mate-in-one test (`win_prob=0.276`
   on a losing move) because the win-rate comparisons it now had access
   to were themselves inverted.

Post-fix, `test_eval_guided_search_runs_end_to_end` was restored to
assert the actual mate-in-one move (`shape=3, position=3`) rather than
the loose `isinstance`/probability-threshold check described above.
`root only ever has one child` is no longer true: root now explores
`>1` children on any position with a real search budget (see
`test_root_explores_multiple_children_not_stuck_at_one` in
`tests/test_mcts.py`). See `docs/research/2026-07-10-alpha-beta-eval-vs-mcts.md`'s
"Future work" section for the corresponding resolution note.
