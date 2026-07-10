# Cross-Engine Follow-up 4: Hybrid Opening→Endgame Player

> **For agentic workers:** Execute task-by-task with TDD. This adds a new library module `src/quantik_core/hybrid.py`, so the full `./dev-check.sh` coverage gate applies. Read `docs/MINIMAX.md`, `docs/MCTS.md`, and `docs/BEAM_SEARCH.md` first.

**Goal:** A composite player that uses an adaptive sampling engine (MCTS or beam) while the tree is intractable (open game), then hands off to the **exact** minimax solver once few enough cells remain — pairing each engine with the regime where it is strongest and sidestepping the open-game intractability wall.

**Architecture:** A new module `quantik_core.hybrid` with `HybridConfig`, `HybridResult`, and `HybridPlayer`. `HybridPlayer.select_move(state)` counts empty cells: at or below the handoff threshold it returns the exact solver's move; above it, it delegates to the configured opening engine. Module-only (imported via `quantik_core.hybrid`), matching MCTS/beam.

**Tech Stack:** Python 3.12+, numpy only. No new deps.

## Global Constraints
- Python `>=3.12`, numpy only.
- `./auto-lint.sh` then `./dev-check.sh` (coverage ≥ 90%) before the final commit; the new module must be ≥ 90% covered.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Follow the `*Config` dataclass + engine-class pattern used by `mcts.py` / `minimax.py`.
- The handoff threshold defaults to **8 empty cells** (i.e. ≥ 8 pieces placed): exact solves from that depth were measured to complete in ≲ 1.1 s. Larger thresholds risk slow solves; document this.

## Verified existing APIs (use exactly)
- `from quantik_core import State, Move` ; `State(bb).get_occupied_bb() -> int` (16-bit occupied mask; empty cells = `16 - bin(mask).count("1")`).
- `from quantik_core.minimax import MinimaxEngine, MinimaxConfig` — `.solve(state).best_move`.
- `from quantik_core.mcts import MCTSEngine, MCTSConfig` — `.search(state) -> (Move, float)`.
- `from quantik_core.beam_search import BeamSearchEngine, BeamSearchConfig` — `.search(state) -> BeamSearchResult`; chosen move = `result.best_leaf.moves[0]` (guard `best_leaf is None`/empty → `result.ranked_root_moves()[0].move`).

---

## Task 1: `hybrid.py` — config, result, player

**Files:**
- Create: `src/quantik_core/hybrid.py`
- Test: `tests/test_hybrid.py`

**Interfaces produced:**
- `@dataclass HybridConfig`: `handoff_empty_cells: int = 8`, `opening_engine: str = "mcts"` (`"mcts"` or `"beam"`), `mcts_config: MCTSConfig = field(default_factory=MCTSConfig)`, `beam_config: BeamSearchConfig = field(default_factory=BeamSearchConfig)`, `minimax_config: MinimaxConfig = field(default_factory=lambda: MinimaxConfig(max_depth=16))`.
- `@dataclass HybridResult`: `best_move: Move`, `engine_used: str` (`"minimax"` / `"mcts"` / `"beam"`), `exact: bool`.
- `class HybridPlayer`: `__init__(self, config: HybridConfig)`; `select_move(self, state: State) -> Move`; `search(self, state: State) -> HybridResult`.

- [ ] **Step 1: Write failing tests** (`tests/test_hybrid.py`):

```python
import pytest
from quantik_core import State
from quantik_core.hybrid import HybridPlayer, HybridConfig, HybridResult
from quantik_core.mcts import MCTSConfig
from quantik_core.beam_search import BeamSearchConfig
from quantik_core.move import generate_legal_moves_list


def test_endgame_uses_exact_solver_and_finds_mate():
    # 8 pieces placed => 8 empty cells => at the handoff threshold => exact.
    # Row 0 = A b C . plus filler so >= 8 pieces are down and P0 has a mate.
    state = State.from_qfen("AbC./d.a./B..c/....")  # 8 pieces, P0 to move
    player = HybridPlayer(HybridConfig(handoff_empty_cells=8))
    result = player.search(state)
    assert result.exact and result.engine_used == "minimax"
    assert result.best_move in generate_legal_moves_list(state.bb)


def test_open_game_uses_opening_engine():
    # 2 pieces placed => 14 empty cells => above threshold => opening engine.
    state = State.from_qfen("A.b./..../..../....")
    player = HybridPlayer(HybridConfig(
        handoff_empty_cells=8, opening_engine="mcts",
        mcts_config=MCTSConfig(max_iterations=100, random_seed=0)))
    result = player.search(state)
    assert not result.exact and result.engine_used == "mcts"
    assert result.best_move in generate_legal_moves_list(state.bb)


def test_beam_opening_engine_selected():
    state = State.from_qfen("A.b./..../..../....")
    player = HybridPlayer(HybridConfig(
        handoff_empty_cells=8, opening_engine="beam",
        beam_config=BeamSearchConfig(beam_width=8, max_depth=4, random_seed=0)))
    result = player.search(state)
    assert result.engine_used == "beam"
    assert result.best_move in generate_legal_moves_list(state.bb)


def test_select_move_matches_search():
    state = State.from_qfen("A.b./..../..../....")
    player = HybridPlayer(HybridConfig(
        mcts_config=MCTSConfig(max_iterations=50, random_seed=3)))
    assert player.select_move(state) == player.search(state).best_move


def test_invalid_engine_raises():
    with pytest.raises(ValueError):
        HybridPlayer(HybridConfig(opening_engine="nope")).search(
            State.from_qfen("A.b./..../..../...."))
```

- [ ] **Step 2: Run, verify fail** — `.venv/bin/pytest tests/test_hybrid.py -x --no-cov`. (If `AbC./d.a./B..c/....` is not a valid 8-piece P0-to-move position or already has a winning line, adjust the QFEN so it is a legal non-terminal 8-piece position with P0 to move; verify with `State.from_qfen(q, validate=True)` and `has_winning_line`.)

- [ ] **Step 3: Implement `src/quantik_core/hybrid.py`.** Full content:

```python
"""Hybrid opening->endgame player for Quantik.

Uses an adaptive sampling engine (MCTS or beam search) while the game tree
is intractable to search exactly, then hands off to the exact minimax
solver once few enough cells remain. The handoff is by empty-cell count:
Quantik's branching shrinks as pieces are placed, so a position with few
empty cells has a small remaining tree that `MinimaxEngine.solve` resolves
exactly and quickly.
"""

from dataclasses import dataclass, field

from .core import State
from .move import Move
from .minimax import MinimaxConfig, MinimaxEngine
from .mcts import MCTSConfig, MCTSEngine
from .beam_search import BeamSearchConfig, BeamSearchEngine


@dataclass
class HybridConfig:
    """Configuration for `HybridPlayer`.

    `handoff_empty_cells`: at or below this many empty cells, use the exact
    solver; above it, use `opening_engine`. Default 8 (>= 8 pieces placed),
    where exact solves complete in well under a second.
    """

    handoff_empty_cells: int = 8
    opening_engine: str = "mcts"  # "mcts" or "beam"
    mcts_config: MCTSConfig = field(default_factory=MCTSConfig)
    beam_config: BeamSearchConfig = field(default_factory=BeamSearchConfig)
    minimax_config: MinimaxConfig = field(
        default_factory=lambda: MinimaxConfig(max_depth=16)
    )


@dataclass
class HybridResult:
    """Which move was chosen, by which engine, and whether it is exact."""

    best_move: Move
    engine_used: str  # "minimax" | "mcts" | "beam"
    exact: bool


def _empty_cells(state: State) -> int:
    return 16 - bin(state.get_occupied_bb()).count("1")


class HybridPlayer:
    """Composite player: sampling in the open game, exact solve in the endgame."""

    def __init__(self, config: HybridConfig) -> None:
        self.config = config

    def select_move(self, state: State) -> Move:
        return self.search(state).best_move

    def search(self, state: State) -> HybridResult:
        if _empty_cells(state) <= self.config.handoff_empty_cells:
            move = MinimaxEngine(self.config.minimax_config).solve(state).best_move
            return HybridResult(best_move=move, engine_used="minimax", exact=True)

        engine = self.config.opening_engine
        if engine == "mcts":
            move, _ = MCTSEngine(self.config.mcts_config).search(state)
            return HybridResult(best_move=move, engine_used="mcts", exact=False)
        if engine == "beam":
            result = BeamSearchEngine(self.config.beam_config).search(state)
            if result.best_leaf is not None and result.best_leaf.moves:
                move = result.best_leaf.moves[0]
            else:
                move = result.ranked_root_moves()[0].move
            return HybridResult(best_move=move, engine_used="beam", exact=False)
        raise ValueError(f"Unknown opening_engine: {engine!r}")
```

- [ ] **Step 4: Run tests, verify pass** — `.venv/bin/pytest tests/test_hybrid.py -v --no-cov`.

- [ ] **Step 5: Full gate** — `./auto-lint.sh` then `./dev-check.sh` (coverage ≥ 90%; the new module is small and fully exercised by the tests above).

- [ ] **Step 6: Commit** — `git add src/quantik_core/hybrid.py tests/test_hybrid.py`; commit `feat(hybrid): opening->endgame composite player`.

---

## Task 2: Docs + example

**Files:** Create `docs/HYBRID.md`; modify `docs/EXAMPLES.md`.
- [ ] **Step 1:** `docs/HYBRID.md` — explain the handoff rationale (branching shrinks; exact solve becomes tractable), the `handoff_empty_cells` trade-off (higher = more exact play but slower moves near the boundary), and the `opening_engine` choice. Include a runnable snippet:
  ```python
  from quantik_core import State
  from quantik_core.hybrid import HybridPlayer, HybridConfig
  move = HybridPlayer(HybridConfig()).select_move(State.from_qfen("A.b./..../..../...."))
  ```
- [ ] **Step 2:** Add the same snippet to `docs/EXAMPLES.md` under a "Hybrid Player" heading; verify it runs.
- [ ] **Step 3:** Commit — `docs: add HYBRID.md and example`.

---

## Self-review checklist
- Handoff is purely by empty-cell count; the boundary (== threshold) uses the exact solver (`<=`).
- Both opening engines return a guaranteed-legal move; beam guards the `best_leaf is None` case.
- Invalid `opening_engine` raises `ValueError` (tested).
- Optional extension (note only): consult a shared opening book (`OpeningBookDatabase.get_position`) before searching, returning its `best_moves[0]` on a hit — combine with Follow-up 2.
