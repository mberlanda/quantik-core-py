import pytest

from quantik_core import State
from quantik_core.commons import ValidationError
from tuning.fill_opening_book import exact_entry, fill
from quantik_core.opening_book import (
    OpeningBookConfig,
    OpeningBookDatabase,
    TerminalStatus,
)

# A deep (12-piece) P0-to-move anchor with a single forced win-in-1 (B at
# pos 13), NOT the plan's original "AbC./..../..../...." (3 pieces placed):
# exact_entry() solves the ROOT itself at max_depth=16, and MinimaxEngine's
# _search_root deliberately does not prune across root siblings (see
# minimax.py), so a near-empty root requires exhaustively solving ~40
# non-winning branches from an intractable early-game position -- measured
# to exceed 30s (never completed) on the plan's original anchor, vs. 0.58s
# here.
_WIN_ANCHOR = "ad.b/.cDb/CaBC/D.A."


def test_exact_entry_win_for_side_to_move():
    e = exact_entry(State.from_qfen(_WIN_ANCHOR).bb)
    assert e["evaluation"] == 1.0
    assert e["win_count_p0"] == 1 and e["win_count_p1"] == 0
    assert (1, 13) in [(m.shape, m.position) for m in e["best_moves"]]  # B at pos 13


def test_exact_entry_loss_for_side_to_move():
    # A position where the side to move (P0) is lost (8 pieces placed --
    # reused from tests/test_minimax.py's forced-loss-in-4 anchor).
    e = exact_entry(State.from_qfen(".D.a/D..c/..d./.BBd").bb)
    assert e["evaluation"] == -1.0
    assert e["win_count_p1"] == 1 and e["win_count_p0"] == 0


def test_exact_entry_handles_completed_winning_line_without_solving():
    # Regression: MinimaxEngine.solve/search assume a non-terminal root.
    # This board's row 0 already completed a winning line (by the
    # PREVIOUS mover); calling solve() on it either mis-scores it as an
    # interior node or raises. P0 (the side to move here) has already
    # lost -- exact_entry must recognize this directly.
    bb = State.from_qfen("AbCd/..../..../....").bb
    e = exact_entry(bb)
    assert e["evaluation"] == -1.0
    assert e["win_count_p1"] == 1 and e["win_count_p0"] == 0
    assert e["best_moves"] == []
    assert e["is_terminal"] == TerminalStatus.WIN_P1


def test_exact_entry_handles_no_legal_moves_without_solving():
    # Regression, the other terminal condition: no winning line, but the
    # side to move has zero legal moves (search() raises on this).
    bb = State.from_qfen(".DbC/c.ab/cD.a/AA.C").bb
    e = exact_entry(bb)
    assert e["evaluation"] == -1.0
    assert e["best_moves"] == []


def test_exact_entry_raises_on_invalid_bitboard():
    # Regression: generate_legal_moves_list() returns [] for BOTH a
    # genuine no-legal-moves terminal AND an invalid bitboard -- that
    # check alone can't tell them apart. Two P0 shapes overlapping on
    # cell 0, with one P1 piece elsewhere so the piece-count TURN BALANCE
    # alone looks superficially valid (2 vs 1) and wouldn't have raised
    # via the old get_current_player_from_counts() check either -- only
    # full validation (piece overlap) catches this. An invalid bb must
    # raise, not silently be written to the book as a bogus terminal win.
    overlapping_bb = (0b1, 0b1, 0, 0, 0b10, 0, 0, 0)
    with pytest.raises(ValidationError):
        exact_entry(overlapping_bb)


def test_fill_writes_and_is_idempotent(tmp_path):
    db_path = str(tmp_path / "book.db")
    cfg = OpeningBookConfig(database_path=db_path)
    with OpeningBookDatabase(cfg) as db:
        n1 = fill(db, n=15, seed=1)
        assert n1 > 0
        sample = State.from_qfen(_WIN_ANCHOR)
        db.add_position(sample, **exact_entry(sample.bb))
        entry = db.get_position(sample)
        assert entry is not None and entry.evaluation == 1.0
    # Reopen and re-fill: must not error (upsert).
    with OpeningBookDatabase(cfg) as db:
        fill(db, n=15, seed=1)
