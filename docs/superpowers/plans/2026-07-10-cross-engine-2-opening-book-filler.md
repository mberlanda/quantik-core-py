# Cross-Engine Follow-up 2: Exact-Solver → Shared Opening Book Filler

> **For agentic workers:** Execute task-by-task with TDD. Standalone follow-up; depends only on merged code (`quantik_core.minimax`, `quantik_core.opening_book`, `tuning.build_dataset`). Read `docs/OPENING_BOOK.md` and `docs/MINIMAX.md` for context.

**Goal:** A tool that solves tractable Quantik positions exactly with the minimax solver and writes **ground-truth** entries into the shared `OpeningBookDatabase` — exact value, exact best move, exact terminal outcome — so MCTS and beam search (which key off the same `canonical_key`) read authoritative data instead of statistical estimates.

**Architecture:** A new script `tuning/fill_opening_book.py` with a pure mapping function (`exact_entry`) that converts a solved position into opening-book fields, and a `fill()` driver that samples tractable positions, solves each, and calls `OpeningBookDatabase.add_position`. Unit-tested against a temporary SQLite DB.

**Tech Stack:** Python 3.12+, numpy only (SQLite is stdlib). No new deps.

## Global Constraints
- Python `>=3.12`, numpy + stdlib only. No new runtime deps.
- `./auto-lint.sh` before every commit. Run `.venv/bin/pytest tests/test_opening_book_filler.py` to gate; do NOT run the full `./dev-check.sh`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Idempotent: `add_position` upserts, so re-running must not corrupt the DB.
- Reuse `from tuning.build_dataset import sample_states` (non-terminal bitboards, deduped, plies 8–12 — tractable to solve exactly).

## Verified existing APIs (use exactly)
- `from quantik_core.opening_book import OpeningBookDatabase, OpeningBookConfig, TerminalStatus`
  - `OpeningBookDatabase(OpeningBookConfig(database_path=<str>))`; supports `with ... as db:` (context manager) and `db.close()`.
  - `db.add_position(state, evaluation: float, visit_count: int, win_count_p0: int, win_count_p1: int, draw_count: int, best_moves: List[Move], depth: int, is_terminal: int = TerminalStatus.INTERIOR, symmetry_count: int = 0) -> None`. `evaluation` is in `[-1.0, 1.0]`.
  - `db.get_position(state) -> Optional[OpeningBookEntry]` (fields include `evaluation`, `best_moves: List[Tuple[int,int]]`, `win_count_p0/p1`).
  - `TerminalStatus.INTERIOR = 0`.
- `from quantik_core.minimax import MinimaxEngine, MinimaxConfig` — `.solve(State(bb))` → `MinimaxResult(best_move, score, ...)`; `score>0` = side-to-move wins (Quantik has no draws).
- `from quantik_core import State, Move`
- `from quantik_core.game_utils import count_total_pieces, get_current_player_from_counts`
- `State(bb).symmetry_count()` → orbit size (int).

---

## Task 1: Pure mapping `exact_entry(bb) -> dict`

**Files:**
- Create: `tuning/fill_opening_book.py`
- Test: `tests/test_opening_book_filler.py`

**Convention (document in the module docstring):** the book `evaluation` is stored from the **side-to-move's** perspective: `+1.0` if the side to move wins with perfect play, `-1.0` if it loses. `win_count_p0/p1` record the exact winner as a single ground-truth "game".

- [x] **Step 1: Write failing tests**:

```python
import numpy as np  # noqa: F401  (parity with repo style; remove if unused)
from quantik_core import State
from tuning.fill_opening_book import exact_entry, fill
from quantik_core.opening_book import OpeningBookConfig, OpeningBookDatabase


def test_exact_entry_win_for_side_to_move():
    # Row 0 = A b C . ; P0 to move forces a win (mate in 1).
    e = exact_entry(State.from_qfen("AbC./..../..../....").bb)
    assert e["evaluation"] == 1.0
    assert e["win_count_p0"] == 1 and e["win_count_p1"] == 0
    assert (3, 3) in [(m.shape, m.position) for m in e["best_moves"]]  # D at pos 3


def test_exact_entry_loss_for_side_to_move():
    # A position where the side to move (P0) is lost.
    e = exact_entry(State.from_qfen(".D.a/D..c/..d./.BBd").bb)
    assert e["evaluation"] == -1.0
    assert e["win_count_p1"] == 1 and e["win_count_p0"] == 0


def test_fill_writes_and_is_idempotent(tmp_path):
    db_path = str(tmp_path / "book.db")
    cfg = OpeningBookConfig(database_path=db_path)
    with OpeningBookDatabase(cfg) as db:
        n1 = fill(db, n=15, seed=1)
        assert n1 > 0
        sample = State.from_qfen("AbC./..../..../....")
        db.add_position(sample, **{k: v for k, v in exact_entry(sample.bb).items()})
        entry = db.get_position(sample)
        assert entry is not None and entry.evaluation == 1.0
    # Reopen and re-fill: must not error (upsert).
    with OpeningBookDatabase(cfg) as db:
        fill(db, n=15, seed=1)
```

- [x] **Step 2: Run, verify fail** — `.venv/bin/pytest tests/test_opening_book_filler.py -x --no-cov`. Ensure `tuning/` is importable (a `tuning/__init__.py` already exists from the minimax feature).

- [x] **Step 3: Implement `tuning/fill_opening_book.py`.** Full content:

```python
"""Fill the shared opening book with EXACT minimax-solved entries.

The opening book (`quantik_core.opening_book.OpeningBookDatabase`) is keyed
by `canonical_key()` and is engine-agnostic, so entries written here are
consumed by any engine. This tool samples positions that are tractable to
solve exactly (a few plies from the end) and records ground truth:
`evaluation` (+1 win / -1 loss, side-to-move perspective), the exact winner
as win counts, and the solver's best move.

Run: python tuning/fill_opening_book.py  ->  writes quantik_opening_book.db
"""

from __future__ import annotations

from typing import Dict, List

from quantik_core import Move, State
from quantik_core.game_utils import count_total_pieces, get_current_player_from_counts
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.opening_book import (
    OpeningBookConfig,
    OpeningBookDatabase,
    TerminalStatus,
)
from tuning.build_dataset import sample_states


def exact_entry(bb) -> Dict:
    """Solve `bb` exactly and return kwargs for `add_position` (minus `state`).

    `evaluation` is +1.0 if the side to move wins with perfect play, else
    -1.0 (Quantik has no draws). `best_moves` is the solver's best move.
    """
    result = MinimaxEngine(MinimaxConfig(max_depth=16)).solve(State(bb))
    p0, p1 = count_total_pieces(bb)
    stm = get_current_player_from_counts(p0, p1)
    stm_wins = result.score > 0
    winner = stm if stm_wins else 1 - stm
    best_moves: List[Move] = [result.best_move]
    return {
        "evaluation": 1.0 if stm_wins else -1.0,
        "visit_count": 1,
        "win_count_p0": 1 if winner == 0 else 0,
        "win_count_p1": 1 if winner == 1 else 0,
        "draw_count": 0,
        "best_moves": best_moves,
        "depth": p0 + p1,
        "is_terminal": TerminalStatus.INTERIOR,
        "symmetry_count": State(bb).symmetry_count(),
    }


def fill(db: OpeningBookDatabase, n: int = 300, seed: int = 20260710) -> int:
    """Sample `n` tractable positions, solve each, and upsert into `db`.

    Returns the number of positions written."""
    written = 0
    for bb in sample_states(n, seed):
        db.add_position(State(bb), **exact_entry(bb))
        written += 1
    return written


def main(n: int = 300, seed: int = 20260710,
         db_path: str = "quantik_opening_book.db") -> None:
    import time

    start = time.time()
    with OpeningBookDatabase(OpeningBookConfig(database_path=db_path)) as db:
        written = fill(db, n=n, seed=seed)
    print(f"wrote {written} exact entries in {time.time() - start:.1f}s -> {db_path}")


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests, verify pass** — `.venv/bin/pytest tests/test_opening_book_filler.py -v --no-cov`.

- [x] **Step 5: Smoke-run** — `.venv/bin/python tuning/fill_opening_book.py` with a small `n` (edit call or run `python -c "from tuning.fill_opening_book import main; main(n=30)"`). Confirm it writes a DB and prints a count. Do NOT commit the `.db` file — add `*.db` to `.gitignore` if not already ignored (`grep -q '\.db' .gitignore || echo '*.db' >> .gitignore`).

- [x] **Step 6: Lint + commit** — `./auto-lint.sh`; `git add tuning/fill_opening_book.py tests/test_opening_book_filler.py .gitignore`; commit `feat(tuning): exact-solver opening-book filler`.

---

## Self-review checklist
- `add_position` upsert verified idempotent by the re-fill test.
- `evaluation` perspective documented (side-to-move) and consistent with `win_count_*`.
- No `.db` artifact committed.
- Optional extension (note in the module, do not implement unless asked): store the FULL optimal-move set instead of just `result.best_move`, by solving each child (more expensive).

## Post-implementation notes

Both plan test anchors reused the SAME `"AbC./..../..../...."` position
already found to be intractable in follow-up 1: `exact_entry()` calls
`MinimaxEngine.solve()` on the **root** itself (not a child), and
`_search_root` deliberately does not prune across root siblings, so a
near-empty root requires exhaustively evaluating ~40 non-winning branches
from the intractable early game (timed out after 30s, never completed).
Replaced with a deep (12-piece) P0-to-move anchor with a single forced
win-in-1 (`"ad.b/.cDb/CaBC/D.A."`, solves in 0.58s); the second anchor
(a pre-existing 8-piece forced-loss-in-4 position from
`tests/test_minimax.py`) was already fine.

Proactively applied the script-mode import fallback pattern from
`fit_weights.py` (a PR #17 review finding) to `fill_opening_book.py`
before it could recur as its own finding, and added `*.db`/`*.db-shm`/
`*.db-wal` to `.gitignore` (the opening book's default WAL mode leaves
sidecar files alongside the main `.db`).

Verified both invocation modes end-to-end: `python -m tuning.fill_opening_book`
and `python tuning/fill_opening_book.py` (script mode, exercising the
fallback import) both wrote 300 entries in ~119s.

Documented the tool in `docs/OPENING_BOOK.md` under a new "Filling with
Exact Solver Ground Truth" section, distinguishing its ground-truth
`evaluation` convention (side-to-move perspective) from the pre-existing
self-play example's fixed-P0 convention.
