"""Tests for the runnable example scripts under examples/.

These import the demo modules (both are guarded by `if __name__ ==
"__main__":`, so import has no side effects) and pin the pure
formatting helpers they expose, so display bugs like ignoring
`move.player` don't silently regress.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from quantik_core import Move

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _load_demo_module(filename: str):
    module_name = f"_examples_{filename.removesuffix('.py')}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, EXAMPLES_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mcts_demo():
    return _load_demo_module("mcts_demo.py")


@pytest.fixture(scope="module")
def beam_search_demo():
    return _load_demo_module("beam_search_demo.py")


class TestMCTSDemoFormatMove:
    """Pins the player-0/player-1 QFEN case convention for mcts_demo.py."""

    def test_player_0_move_is_uppercase(self, mcts_demo):
        move = Move(player=0, shape=0, position=1)

        formatted = mcts_demo.format_move(move)

        assert formatted.startswith("A ")
        assert "a " not in formatted

    def test_player_1_move_is_lowercase(self, mcts_demo):
        move = Move(player=1, shape=1, position=11)

        formatted = mcts_demo.format_move(move)

        # Mutation guard: prior to the fix this always rendered "B",
        # ignoring move.player entirely.
        assert formatted.startswith("b ")
        assert "B " not in formatted

    def test_includes_row_col_and_position(self, mcts_demo):
        move = Move(player=0, shape=2, position=11)

        formatted = mcts_demo.format_move(move)

        assert "(2, 3)" in formatted
        assert "[pos 11]" in formatted


class TestBeamSearchDemoFormatMove:
    """Same convention, pinned for the sibling demo (regression guard)."""

    def test_player_0_move_is_uppercase(self, beam_search_demo):
        move = Move(player=0, shape=0, position=1)

        formatted = beam_search_demo.format_move(move)

        assert "P0 A " in formatted

    def test_player_1_move_is_lowercase(self, beam_search_demo):
        move = Move(player=1, shape=1, position=11)

        formatted = beam_search_demo.format_move(move)

        assert "P1 b " in formatted


@pytest.fixture(scope="module")
def minimax_demo():
    return _load_demo_module("minimax_demo.py")


@pytest.fixture(scope="module")
def minimax_benchmark():
    return _load_demo_module("minimax_benchmark.py")


class TestMinimaxDemo:
    """Pins the player-aware QFEN case convention for minimax_demo.py and
    smoke-checks that the demo helpers actually run a search."""

    def test_player_0_move_is_uppercase(self, minimax_demo):
        assert minimax_demo.format_move(Move(player=0, shape=0, position=1)).startswith(
            "A "
        )

    def test_player_1_move_is_lowercase(self, minimax_demo):
        # Mutation guard: rendering that ignored move.player would print "B".
        formatted = minimax_demo.format_move(Move(player=1, shape=1, position=11))
        assert formatted.startswith("b ") and "B " not in formatted

    def test_minimax_player_returns_legal_move(self, minimax_demo):
        from quantik_core import State
        from quantik_core.move import generate_legal_moves_list

        state = State.from_qfen("AbC./..../..../....")
        select = minimax_demo.minimax_player(max_depth=2)
        move = select(state)
        assert move in generate_legal_moves_list(state.bb)

    def test_play_game_returns_a_winner(self, minimax_demo):
        from quantik_core.game_utils import WinStatus

        result = minimax_demo.play_game(
            minimax_demo.random_player(seed=1), minimax_demo.random_player(seed=2)
        )
        assert result in (WinStatus.PLAYER_0_WINS, WinStatus.PLAYER_1_WINS)


def test_minimax_benchmark_imports(minimax_benchmark):
    # Importing exercises the module-level `from minimax_demo import ...`; the
    # heavy work is guarded under __main__.
    assert hasattr(minimax_benchmark, "main")


@pytest.fixture(scope="module")
def cross_engine_benchmark():
    return _load_demo_module("cross_engine_benchmark.py")


class TestCrossEngineBenchmark:
    # A mid-game anchor (8 plies in, near-terminal) rather than the plan's
    # original near-empty "AbC./..../..../...." position: optimal_moves
    # exact-solves every non-immediately-terminal legal move, and from a
    # near-empty board that took >170s for a SINGLE child (measured), vs.
    # sub-millisecond here. P1 (side to move) has three moves that each
    # immediately end the game (shape=3,pos=5 completes a line; the other
    # two leave P0 with zero legal replies) -- all three legitimately tie
    # as optimal.
    _ANCHOR = ".ba./..CC/DcbD/cA.A"

    def test_optimal_moves_finds_the_mate(self, cross_engine_benchmark):
        from quantik_core import State

        bb = State.from_qfen(self._ANCHOR).bb
        opt = cross_engine_benchmark.optimal_moves(bb)
        assert any(m.shape == 3 and m.position == 5 for m in opt)

    def test_optimal_moves_handles_no_legal_reply_without_solving(
        self, cross_engine_benchmark
    ):
        # A move that leaves the opponent with zero legal moves is terminal
        # (MinimaxEngine.solve/search reject states with no legal moves for
        # the side to move) -- optimal_moves must score it directly rather
        # than calling solve() on it.
        from quantik_core import State, apply_move
        from quantik_core.game_utils import has_winning_line
        from quantik_core.move import generate_legal_moves_list

        bb = State.from_qfen(self._ANCHOR).bb
        opt = cross_engine_benchmark.optimal_moves(bb)
        for m in opt:
            child = apply_move(bb, m)
            assert has_winning_line(child) or not generate_legal_moves_list(child)

    def test_engine_move_returns_legal(self, cross_engine_benchmark):
        from quantik_core import State
        from quantik_core.move import generate_legal_moves_list

        bb = State.from_qfen(self._ANCHOR).bb
        legal = generate_legal_moves_list(bb)
        for name in ("minimax", "mcts", "beam"):
            assert cross_engine_benchmark.engine_move(name, bb) in legal

    def test_move_agreement_handles_empty_sample(self, cross_engine_benchmark):
        # sample_states can return fewer than n (or zero) positions; the
        # division by len(positions) must not raise ZeroDivisionError.
        result = cross_engine_benchmark.move_agreement(n=0, seed=1)
        assert result == {"minimax": 0.0, "mcts": 0.0, "beam": 0.0}

    def test_play_from_credits_the_actual_side_to_move(self, cross_engine_benchmark):
        # Regression: play_from must bind mover_name to whichever color is
        # ACTUALLY to move at bb, not a hard-coded P0. This anchor (P1 to
        # move, per the class-level note above) has an immediate win for
        # the side to move; mover_name="minimax" must be credited with
        # that win even though P1 -- not P0 -- moves first here.
        from quantik_core import State
        from quantik_core.game_utils import (
            count_total_pieces,
            get_current_player_from_counts,
        )

        bb = State.from_qfen(self._ANCHOR).bb
        p0, p1 = count_total_pieces(bb)
        assert get_current_player_from_counts(p0, p1) == 1  # P1 to move
        assert cross_engine_benchmark.play_from(bb, "minimax", "mcts") is True

    def test_play_from_p0_to_move_case(self, cross_engine_benchmark):
        # Same guarantee for the other parity: P0 to move (row 0 = A b C .
        # plus a P1 piece elsewhere to balance the piece count) with an
        # immediate win, D at pos 3 completing row 0.
        from quantik_core import State
        from quantik_core.game_utils import (
            count_total_pieces,
            get_current_player_from_counts,
        )

        bb = State.from_qfen("AbC./d.../..../....").bb
        p0, p1 = count_total_pieces(bb)
        assert get_current_player_from_counts(p0, p1) == 0  # P0 to move
        assert cross_engine_benchmark.play_from(bb, "minimax", "mcts") is True
