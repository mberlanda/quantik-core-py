"""Fill the shared opening book with EXACT minimax-solved entries.

The opening book (`quantik_core.opening_book.OpeningBookDatabase`) is keyed
by `canonical_key()` and is engine-agnostic, so entries written here are
consumed by any engine. This tool samples positions that are tractable to
solve exactly (a few plies from the end) and records ground truth:
`evaluation` (+1 win / -1 loss, side-to-move perspective), the exact winner
as win counts, and the solver's best move.

Run: python -m tuning.fill_opening_book (preferred) or
python tuning/fill_opening_book.py -> writes quantik_opening_book.db
"""

from __future__ import annotations

from typing import Dict, List

from quantik_core import Move, State
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
    has_winning_line,
)
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import generate_legal_moves_list
from quantik_core.opening_book import (
    OpeningBookConfig,
    OpeningBookDatabase,
    TerminalStatus,
)

try:
    from tuning.build_dataset import sample_states
except ImportError:
    # Script mode (`python tuning/fill_opening_book.py`): sys.path[0] is
    # tuning/ itself, so the package-qualified import above fails there
    # even though `python -m tuning.fill_opening_book` works.
    from build_dataset import sample_states  # type: ignore[import-not-found]


def exact_entry(bb) -> Dict:
    """Solve `bb` exactly and return kwargs for `add_position` (minus `state`).

    `evaluation` is +1.0 if the side to move wins with perfect play, else
    -1.0 (Quantik has no draws). `best_moves` is the solver's best move.

    `MinimaxEngine.solve`/`search` assume a non-terminal root: a
    no-legal-moves position raises, and a position with an already-completed
    winning line (but empty cells remaining, so `search` wouldn't raise) is
    silently mis-scored -- treated as an interior node instead of an already
    -decided one. `sample_states()` filters these out, but `exact_entry` is
    a public, reusable mapping function, so a terminal `bb` (either
    condition) is handled directly here instead of being solved: the side
    to move has already lost, matching the convention `_negamax` uses
    throughout `minimax.py`.
    """
    p0, p1 = count_total_pieces(bb)
    stm = get_current_player_from_counts(p0, p1)
    already_decided = has_winning_line(bb) or not generate_legal_moves_list(bb)
    if already_decided:
        stm_wins = False
        best_moves: List[Move] = []
    else:
        result = MinimaxEngine(MinimaxConfig(max_depth=16)).solve(State(bb))
        stm_wins = result.score > 0
        best_moves = [result.best_move]
    winner = stm if stm_wins else 1 - stm
    is_terminal = (
        (TerminalStatus.WIN_P0 if winner == 0 else TerminalStatus.WIN_P1)
        if already_decided
        else TerminalStatus.INTERIOR
    )
    return {
        "evaluation": 1.0 if stm_wins else -1.0,
        "visit_count": 1,
        "win_count_p0": 1 if winner == 0 else 0,
        "win_count_p1": 1 if winner == 1 else 0,
        "draw_count": 0,
        "best_moves": best_moves,
        "depth": p0 + p1,
        "is_terminal": is_terminal,
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


def main(
    n: int = 300, seed: int = 20260710, db_path: str = "quantik_opening_book.db"
) -> None:
    import time

    start = time.time()
    with OpeningBookDatabase(OpeningBookConfig(database_path=db_path)) as db:
        written = fill(db, n=n, seed=seed)
    print(f"wrote {written} exact entries in {time.time() - start:.1f}s -> {db_path}")


if __name__ == "__main__":
    main()
