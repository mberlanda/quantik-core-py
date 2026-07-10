from quantik_core import State
from tuning.fill_opening_book import exact_entry, fill
from quantik_core.opening_book import OpeningBookConfig, OpeningBookDatabase

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


def test_fill_writes_and_is_idempotent(tmp_path):
    db_path = str(tmp_path / "book.db")
    cfg = OpeningBookConfig(database_path=db_path)
    with OpeningBookDatabase(cfg) as db:
        n1 = fill(db, n=15, seed=1)
        assert n1 > 0
        sample = State.from_qfen(_WIN_ANCHOR)
        db.add_position(sample, **{k: v for k, v in exact_entry(sample.bb).items()})
        entry = db.get_position(sample)
        assert entry is not None and entry.evaluation == 1.0
    # Reopen and re-fill: must not error (upsert).
    with OpeningBookDatabase(cfg) as db:
        fill(db, n=15, seed=1)
