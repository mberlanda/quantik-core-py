"""Tests for benchmarks.adapters: uniform measurement and invariants."""

import pytest

from quantik_core import State, apply_move
from quantik_core.move import Move, generate_legal_moves_list

from benchmarks.adapters import (
    BeamAdapter,
    EngineAdapter,
    MCTSAdapter,
    MinimaxAdapter,
    RandomAdapter,
    fixed_time_adapters,
)
from benchmarks.reference import move_key

ANCHOR = ".ba./..CC/DcbD/cA.A"


def _anchor_bb():
    return State.from_qfen(ANCHOR).bb


def _fast_adapters():
    return [
        MinimaxAdapter(max_depth=2),
        MCTSAdapter(max_iterations=50),
        BeamAdapter(beam_width=4, max_depth=4),
        RandomAdapter(),
    ]


class _IllegalAdapter(EngineAdapter):
    name = "illegal"
    stochastic = False

    def __init__(self):
        super().__init__("illegal")

    def _select(self, bb, seed):
        return Move(0, 0, 0), {}


class _MutatingAdapter(EngineAdapter):
    name = "mutating"
    stochastic = False

    def __init__(self):
        super().__init__("mutating")

    def _select(self, bb, seed):
        move = generate_legal_moves_list(tuple(bb))[0]
        bb[0] ^= 1
        return move, {}


class TestSelectContract:
    @pytest.mark.parametrize("adapter", _fast_adapters(), ids=lambda a: a.name)
    def test_returns_legal_move_and_sane_observation(self, adapter):
        bb = _anchor_bb()
        move, obs = adapter.select(bb, "anchor", seed=0)
        legal = generate_legal_moves_list(bb)

        assert move in legal
        assert obs.engine == adapter.name
        assert obs.config_label == adapter.config_label
        assert obs.position_id == "anchor"
        assert obs.move == move_key(move)
        assert obs.wall_time_s >= 0.0
        assert obs.cpu_time_s >= 0.0
        assert obs.root_legal_moves == len(legal)
        assert obs.seed == 0
        assert obs.to_dict()["engine"] == adapter.name

    @pytest.mark.parametrize("adapter", _fast_adapters(), ids=lambda a: a.name)
    def test_rejects_terminal_input(self, adapter):
        bb = _anchor_bb()
        terminal = apply_move(bb, Move(player=1, shape=3, position=5))

        with pytest.raises(ValueError, match="terminal"):
            adapter.select(terminal, "won", seed=0)

    def test_rejects_illegal_returned_move(self):
        with pytest.raises(ValueError, match="illegal move"):
            _IllegalAdapter().select(_anchor_bb(), "anchor")

    def test_rejects_input_mutation(self):
        with pytest.raises(ValueError, match="mutated"):
            _MutatingAdapter().select(list(_anchor_bb()), "anchor")

    def test_track_memory_populates_peak(self):
        _, obs = MinimaxAdapter(max_depth=2).select(
            _anchor_bb(), "anchor", track_memory=True
        )

        assert obs.peak_memory_bytes is not None
        assert obs.peak_memory_bytes > 0


class TestMinimaxAdapter:
    def test_full_depth_solve_is_exact_and_optimal(self):
        move, obs = MinimaxAdapter(max_depth=16).select(_anchor_bb(), "anchor")

        assert obs.exact
        assert obs.nodes and obs.nodes > 0
        assert obs.depth_reached is not None

        child = apply_move(_anchor_bb(), move)
        from quantik_core.game_utils import has_winning_line

        assert has_winning_line(child) or not generate_legal_moves_list(child)

    def test_depth_limited_search_is_not_exact_on_open_board(self):
        _, obs = MinimaxAdapter(max_depth=2).select(
            State.from_qfen("Ab../..../..../....").bb, "open"
        )

        assert not obs.exact

    def test_is_deterministic(self):
        assert MinimaxAdapter.stochastic is False


class TestStochasticAdapters:
    @pytest.mark.parametrize(
        "adapter_factory",
        [
            lambda: MCTSAdapter(max_iterations=50),
            lambda: BeamAdapter(beam_width=4, max_depth=4),
            lambda: RandomAdapter(),
        ],
        ids=["mcts", "beam", "random"],
    )
    def test_same_seed_same_move(self, adapter_factory):
        adapter = adapter_factory()
        bb = _anchor_bb()
        _, first = adapter.select(bb, "anchor", seed=123)
        _, second = adapter.select(bb, "anchor", seed=123)

        assert adapter.stochastic is True
        assert first.move == second.move

    def test_mcts_records_iterations(self):
        _, obs = MCTSAdapter(max_iterations=50).select(_anchor_bb(), "anchor", seed=0)

        assert obs.iterations == 50
        assert obs.nodes and obs.nodes > 0

    def test_beam_records_depth_and_extra_stats(self):
        _, obs = BeamAdapter(beam_width=4, max_depth=4).select(
            _anchor_bb(), "anchor", seed=0
        )

        assert obs.depth_reached is not None
        assert obs.depth_reached >= 1
        assert "candidates_generated" in obs.extra


class TestFixedTimeFamily:
    def test_equal_budget_adapters(self):
        adapters = fixed_time_adapters(0.05, beam_width=4)

        assert [a.name for a in adapters] == ["minimax", "mcts", "beam"]
        for adapter in adapters:
            assert "t=0.05" in adapter.config_label
