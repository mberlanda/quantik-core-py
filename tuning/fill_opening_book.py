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

from typing import Dict, List, Optional, Union

from quantik_core import Move, State
from quantik_core.commons import Bitboard
from quantik_core.game_utils import count_total_pieces, has_winning_line
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import generate_legal_moves_list
from quantik_core.opening_book import (
    OpeningBookConfig,
    OpeningBookDatabase,
    TerminalStatus,
)
from quantik_core.state_validator import validate_game_state

try:
    from tuning.build_dataset import sample_states
except ImportError:
    # Script mode (`python tuning/fill_opening_book.py`): sys.path[0] is
    # tuning/ itself, so the package-qualified import above fails there
    # even though `python -m tuning.fill_opening_book` works.
    from build_dataset import sample_states  # type: ignore[import-not-found]


def exact_entry(
    bb: Bitboard, engine: Optional[MinimaxEngine] = None
) -> Dict[str, Union[float, int, List[Move]]]:
    """Solve `bb` exactly and return kwargs for `add_position` (minus `state`).

    `evaluation` is +1.0 if the side to move wins with perfect play, else
    -1.0 (Quantik has no draws). `best_moves` is the solver's best move.

    `engine` lets a caller solving many positions (e.g. `fill()`'s loop)
    reuse one `MinimaxEngine` instead of paying a fresh allocation per
    call -- `solve()` resets all its per-call state (TT, node count, PV),
    so reuse across independent positions is safe. When omitted (the
    default for standalone/test use), a fresh engine is constructed.

    `MinimaxEngine.solve`/`search` assume a non-terminal root: a
    no-legal-moves position raises, and a position with an already-completed
    winning line (but empty cells remaining, so `search` wouldn't raise) is
    silently mis-scored -- treated as an interior node instead of an already
    -decided one. `sample_states()` filters these out, but `exact_entry` is
    a public, reusable mapping function, so a terminal `bb` (either
    condition) is handled directly here instead of being solved: the side
    to move has already lost, matching the convention `_negamax` uses
    throughout `minimax.py`.

    A no-legal-moves position is scored as a WIN for the opponent here
    (`is_terminal=WIN_P0`/`WIN_P1`, `draw_count=0`), NOT `TerminalStatus
    .STALEMATE`/a draw. This intentionally diverges from
    `examples/opening_book_demo.py` and `examples/generate_opening_book.py`,
    which both encode no-legal-moves as a draw -- but `board.py`'s own
    `Board.get_game_result()` (the authoritative game-rules implementation)
    is explicit that "If a player has no legal moves, the other player
    wins", and Quantik has no draws at all (confirmed: `WinStatus` has no
    draw member, only `NO_WIN`/`PLAYER_0_WINS`/`PLAYER_1_WINS`). Those two
    examples appear to carry a pre-existing bug; fixing them is out of
    scope for this change, but a reader comparing conventions across the
    opening-book-writing code in this repo should not assume they agree.

    Raises `ValidationError` for an invalid `bb` (piece-count/overlap/
    turn-balance/placement violations) rather than treating it as a
    terminal loss: `generate_legal_moves_list` returns an empty list for
    BOTH a genuine no-legal-moves terminal AND an invalid bitboard, so
    that check alone can't tell them apart -- validating up front lets
    invalid input fail loudly instead of silently writing a bogus
    terminal-win entry into the database.
    """
    stm, _ = validate_game_state(bb, raise_on_error=True)
    # validate_game_state is typed Optional[PlayerId] because it can return
    # (None, error) -- but raise_on_error=True means we only reach here on
    # ValidationResult.OK, which always pairs with a concrete player. An
    # `assert` would be stripped under `python -O`, silently letting a
    # None stm through; raise explicitly instead so this invariant holds
    # even in optimized runs.
    if stm is None:
        raise RuntimeError("validate_game_state returned OK with stm=None")
    p0, p1 = count_total_pieces(bb)
    already_decided = has_winning_line(bb) or not generate_legal_moves_list(
        bb, player_id=stm
    )
    if already_decided:
        stm_wins = False
        best_moves: List[Move] = []
    else:
        solver = (
            engine if engine is not None else MinimaxEngine(MinimaxConfig(max_depth=16))
        )
        result = solver.solve(State(bb))
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
    """Sample up to `n` tractable positions, solve each, and upsert into `db`.

    `sample_states()` stops after a bounded number of attempts, so it can
    return fewer than `n` distinct positions; this returns however many
    were actually written, which may be less than `n`.
    """
    written = 0
    engine = MinimaxEngine(MinimaxConfig(max_depth=16))
    for bb in sample_states(n, seed):
        db.add_position(State(bb), **exact_entry(bb, engine=engine))
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
