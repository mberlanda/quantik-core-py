"""Tests for exact benchmark references and complete optimal move sets."""

from quantik_core import State, apply_move
from quantik_core.game_utils import has_winning_line
from quantik_core.move import Move, generate_legal_moves_list

from benchmarks import dataset, reference

ANCHOR = ".ba./..CC/DcbD/cA.A"


class TestMoveKey:
    def test_roundtrip(self):
        move = Move(player=1, shape=3, position=5)

        assert reference.move_key(move) == "1:3:5"
        assert reference.parse_move_key("1:3:5") == (1, 3, 5)


class TestSolvePosition:
    def test_finds_the_mate_with_full_optimal_set(self):
        bb = State.from_qfen(ANCHOR).bb

        ref = reference.solve_position(bb, budget_s=30.0)

        assert ref is not None and ref["solved"] and ref["no_cutoff"]
        assert ref["value"] == 1
        assert "1:3:5" in ref["optimal_moves"]
        for key in ref["optimal_moves"]:
            player, shape, position = reference.parse_move_key(key)
            child = apply_move(bb, Move(player=player, shape=shape, position=position))
            assert has_winning_line(child) or not generate_legal_moves_list(child)

    def test_optimal_moves_are_legal_and_sorted(self):
        bb = State.from_qfen(ANCHOR).bb

        ref = reference.solve_position(bb, budget_s=30.0)

        legal = {reference.move_key(m) for m in generate_legal_moves_list(bb)}
        assert ref is not None
        assert set(ref["optimal_moves"]) <= legal
        assert ref["optimal_moves"] == sorted(ref["optimal_moves"])
        assert ref["pv"][0] in ref["optimal_moves"]

    def test_solver_metadata_reports_caller_budget(self):
        bb = State.from_qfen(ANCHOR).bb

        ref = reference.solve_position(bb, budget_s=30.0)

        assert ref is not None
        assert "budget_s=30.0" in ref["solver"]
        assert "remaining_budget" not in ref["solver"]

    def test_budget_exhaustion_returns_none_not_partial(self):
        bb = State.from_qfen("Ab../..../..../....").bb

        assert reference.solve_position(bb, budget_s=0.05) is None


class TestAugment:
    def test_opening_skipped_and_solvable_phases_filled(self):
        payload = dataset.generate({"opening": 1, "late_mid": 1}, seed=11)

        reference.augment_with_references(payload, budget_s=15.0)

        by_phase = {p["phase"]: p for p in payload["positions"]}
        assert by_phase["opening"]["reference"] is None
        ref = by_phase["late_mid"]["reference"]
        assert ref is not None and ref["solved"]
        assert ref["value"] in (1, -1)
        assert ref["optimal_moves"]
