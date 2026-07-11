"""Tests for benchmark dataset generation and artifact I/O."""

import json

import pytest

from quantik_core import State
from quantik_core.game_utils import has_winning_line
from quantik_core.move import generate_legal_moves_list

from benchmarks import dataset


class TestPhases:
    @pytest.mark.parametrize(
        ("pieces", "expected"),
        [
            (0, "opening"),
            (4, "opening"),
            (5, "early_mid"),
            (7, "early_mid"),
            (8, "late_mid"),
            (11, "late_mid"),
            (12, "endgame"),
            (16, "endgame"),
        ],
    )
    def test_phase_of(self, pieces, expected):
        assert dataset.phase_of(pieces) == expected

    def test_phase_of_rejects_out_of_range(self):
        with pytest.raises(ValueError):
            dataset.phase_of(-1)
        with pytest.raises(ValueError):
            dataset.phase_of(17)


class TestGenerate:
    def test_positions_are_valid_nonterminal_and_deduped(self):
        payload = dataset.generate({"late_mid": 3, "endgame": 2}, seed=42)
        keys = set()

        for pos in payload["positions"]:
            state = State.from_qfen(pos["qfen"])
            bb = state.bb

            assert not has_winning_line(bb)
            assert generate_legal_moves_list(bb)
            assert pos["phase"] == dataset.phase_of(pos["pieces"])
            assert pos["legal_moves"] == len(generate_legal_moves_list(bb))
            assert pos["side_to_move"] == pos["pieces"] % 2
            assert pos["reference"] is None
            keys.add(state.canonical_key())

        assert len(keys) == len(payload["positions"])

    def test_ids_are_sequential_and_unique(self):
        payload = dataset.generate({"late_mid": 3}, seed=7)

        assert [p["id"] for p in payload["positions"]] == [
            f"p{i:04d}" for i in range(len(payload["positions"]))
        ]

    def test_deterministic_for_same_seed(self):
        a = dataset.generate({"opening": 2, "late_mid": 2}, seed=5)
        b = dataset.generate({"opening": 2, "late_mid": 2}, seed=5)

        assert a == b

    def test_rejects_unknown_phase(self):
        with pytest.raises(ValueError):
            dataset.generate({"midgame": 3}, seed=1)


class TestArtifactIO:
    def test_save_load_roundtrip(self, tmp_path):
        payload = dataset.generate({"late_mid": 2}, seed=9)
        path = tmp_path / "positions.json"

        digest = dataset.save(payload, path)
        loaded = dataset.load(path)

        assert loaded["checksum"] == digest
        assert loaded["positions"] == payload["positions"]
        assert loaded["seed"] == 9

    def test_load_rejects_tampered_file(self, tmp_path):
        payload = dataset.generate({"late_mid": 2}, seed=9)
        path = tmp_path / "positions.json"
        dataset.save(payload, path)

        blob = json.loads(path.read_text())
        blob["positions"][0]["qfen"] = "AbC./..../..../...."
        path.write_text(json.dumps(blob))

        with pytest.raises(ValueError, match="checksum"):
            dataset.load(path)
