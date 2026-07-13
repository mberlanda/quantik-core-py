"""Tests for benchmark correctness preflight invariants."""

from quantik_core import State, apply_move
from quantik_core.game_utils import count_total_pieces
from quantik_core.move import Move, generate_legal_moves_list

from benchmarks.adapters import EngineAdapter, MinimaxAdapter, RandomAdapter
from benchmarks.correctness import run_preflight

ANCHOR = ".ba./..CC/DcbD/cA.A"


def _position(qfen, pos_id="p0000"):
    bb = State.from_qfen(qfen).bb
    p0, p1 = count_total_pieces(bb)
    return {
        "id": pos_id,
        "qfen": qfen,
        "phase": "late_mid",
        "pieces": p0 + p1,
        "side_to_move": (p0 + p1) % 2,
        "legal_moves": len(generate_legal_moves_list(bb)),
        "reference": None,
    }


class _FlipFlopAdapter(EngineAdapter):
    """Deliberately non-deterministic: alternates between two legal moves."""

    name = "flipflop"
    stochastic = True

    def __init__(self):
        super().__init__("flipflop")
        self._calls = 0

    def _select(self, bb, seed):
        moves = sorted(
            generate_legal_moves_list(bb), key=lambda m: (m.shape, m.position)
        )
        self._calls += 1
        return moves[self._calls % 2], {}


class TestPreflight:
    def test_passes_for_well_behaved_adapters(self):
        failures = run_preflight(
            [MinimaxAdapter(max_depth=2), RandomAdapter()],
            [_position(ANCHOR)],
        )

        assert failures == []

    def test_flags_terminal_dataset_position(self):
        bb = State.from_qfen(ANCHOR).bb
        won = apply_move(bb, Move(player=1, shape=3, position=5))
        bad = _position(State(won).to_qfen(), pos_id="pbad")

        failures = run_preflight([RandomAdapter()], [bad])

        assert any("terminal" in failure for failure in failures)

    def test_flags_nondeterminism_under_identical_seed(self):
        failures = run_preflight([_FlipFlopAdapter()], [_position(ANCHOR)])

        assert any("non-deterministic" in failure for failure in failures)
