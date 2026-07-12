"""Tests for benchmarks.head_to_head: paired, side-balanced games.

Carries forward the old examples/cross_engine_benchmark.py::play_from
regression guarantees: the engine credited with a win must be bound to
whichever color is ACTUALLY to move at the sampled position, for both
parities.
"""

from quantik_core import State
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
)
from quantik_core.move import generate_legal_moves_list

from benchmarks import head_to_head
from benchmarks.adapters import MinimaxAdapter, RandomAdapter
from benchmarks.head_to_head import (
    aggregate_head_to_head,
    play_game,
    iter_head_to_head,
    run_head_to_head,
)
from benchmarks.checkpoint import h2h_key

ANCHOR = ".ba./..CC/DcbD/cA.A"  # P1 to move, immediate win available
P0_ANCHOR = "AbC./d.../..../...."  # P0 to move, immediate win (D at pos 3)


def _position(qfen, pos_id, phase="late_mid"):
    bb = State.from_qfen(qfen).bb
    p0, p1 = count_total_pieces(bb)
    return {
        "id": pos_id,
        "qfen": qfen,
        "phase": phase,
        "pieces": p0 + p1,
        "side_to_move": get_current_player_from_counts(p0, p1),
        "legal_moves": len(generate_legal_moves_list(bb)),
        "reference": None,
    }


class TestPlayGame:
    def test_credits_mover_when_p1_to_move(self):
        bb = State.from_qfen(ANCHOR).bb
        assert get_current_player_from_counts(*count_total_pieces(bb)) == 1
        winner, plies = play_game(
            MinimaxAdapter(max_depth=16), RandomAdapter(), bb, seed=0
        )
        assert winner == "minimax"
        assert plies == 1  # immediate mate

    def test_credits_mover_when_p0_to_move(self):
        bb = State.from_qfen(P0_ANCHOR).bb
        assert get_current_player_from_counts(*count_total_pieces(bb)) == 0
        winner, _ = play_game(MinimaxAdapter(max_depth=16), RandomAdapter(), bb, seed=0)
        assert winner == "minimax"


class TestRunHeadToHead:
    def test_paired_side_balanced_records(self):
        positions = [_position(ANCHOR, "p0000")]
        records = run_head_to_head(
            MinimaxAdapter(max_depth=16), RandomAdapter(), positions, seeds=[0, 1]
        )
        # 1 position x 2 seeds x 2 orientations = 4 games.
        assert len(records) == 4
        for seed in (0, 1):
            movers = sorted(r["mover"] for r in records if r["seed"] == seed)
            assert movers == ["minimax", "random"]  # both orientations played

    def test_aggregate_shape_and_draws_impossible(self):
        positions = [_position(ANCHOR, "p0000")]
        records = run_head_to_head(
            MinimaxAdapter(max_depth=16), RandomAdapter(), positions, seeds=[0]
        )
        agg = aggregate_head_to_head(records, "minimax", "random")
        assert agg["games"] == 2
        assert agg["paired_positions"] == 1
        assert agg["a_wins"] + agg["b_wins"] == agg["games"]
        assert agg["draws"] == 0
        assert agg["a_win_rate"] == agg["a_wins"] / agg["games"]
        lo, hi = agg["a_win_rate_ci95"]
        assert 0.0 <= lo <= agg["a_win_rate"] <= hi <= 1.0
        assert "late_mid" in agg["by_phase"]
        # The exact engine wins at least the game it moves first in.
        assert agg["a_wins_as_mover"] == 1

    def test_iter_head_to_head_skips_completed_keys(self):
        positions = [_position(ANCHOR, "p0000")]
        baseline = run_head_to_head(
            MinimaxAdapter(max_depth=16), RandomAdapter(), positions, seeds=[0]
        )
        skip = {h2h_key(baseline[0])}

        records = list(
            iter_head_to_head(
                MinimaxAdapter(max_depth=16),
                RandomAdapter(),
                positions,
                seeds=[0],
                skip_keys=skip,
            )
        )

        assert records == baseline[1:]
        assert baseline[0] not in records

    def test_parallel_head_to_head_preserves_logical_order(self, monkeypatch):
        seen_workers = []

        class InlineExecutor:
            def __init__(self, max_workers):
                seen_workers.append(max_workers)

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                return False

            def map(self, func, tasks):
                return map(func, tasks)

        monkeypatch.setattr(head_to_head, "ProcessPoolExecutor", InlineExecutor)
        positions = [_position(ANCHOR, "p0000")]
        sequential = run_head_to_head(
            MinimaxAdapter(max_depth=16),
            RandomAdapter(),
            positions,
            seeds=[0, 1],
            workers=1,
        )
        parallel = run_head_to_head(
            MinimaxAdapter(max_depth=16),
            RandomAdapter(),
            positions,
            seeds=[0, 1],
            workers=2,
        )

        assert seen_workers == [2]
        assert parallel == sequential
