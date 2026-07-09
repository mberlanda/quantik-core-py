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
