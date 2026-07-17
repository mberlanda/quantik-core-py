import json
import tempfile
import tomllib
from pathlib import Path

import numpy as np
import pytest

from quantik_core.artifact_data import (
    OBSERVATION_SCHEMA,
    ObservationRow,
    load_observations_jsonl,
    write_observations_parquet,
)
from quantik_core.training_dataset import (
    TrainingDatasetView,
    load_training_view_npz,
    load_training_view_from_observations_jsonl,
    load_training_view_from_observations_parquet,
    main,
    training_view_from_observations,
    write_training_view_npz,
)


def observation_record(row_id: int = 0):
    visits = [0] * 64
    visits[0] = 3
    visits[21] = 1
    return {
        "schema": OBSERVATION_SCHEMA,
        "contract_version": "1.1.0",
        "run_id": "run-1",
        "row_id": row_id,
        "position_key": f"pos-{row_id}",
        "ply": 0,
        "side_to_move": 0,
        "bitboards": [0] * 8,
        "qfen": "..../..../..../....",
        "legal_action_mask": (1 << 64) - 1,
        "engine_kind": "mcts",
        "engine_version": "0.1.0",
        "elapsed_ms": 12,
        "policy_visits": visits,
        "value": 0.25,
        "value_source": "strong-search",
        "source_confidence": 0.8,
    }


def test_training_view_from_observations_materializes_numpy_targets():
    rows = load_observations_jsonl_from_records([observation_record()])

    view = training_view_from_observations(rows)

    assert len(view) == 1
    assert view.tensors.shape == (1, 9, 4, 4)
    assert view.tensors.dtype == np.float32
    assert view.bitboards.shape == (1, 8)
    assert view.bitboards.dtype == np.uint16
    assert view.side_to_move.tolist() == [0]
    assert view.legal_action_mask.dtype == np.uint64
    assert view.policy_target.shape == (1, 64)
    assert view.policy_target[0, 0] == pytest.approx(0.75)
    assert view.policy_target[0, 21] == pytest.approx(0.25)
    assert view.policy_target[0].sum() == pytest.approx(1.0)
    assert view.value_target.tolist() == pytest.approx([0.25])
    assert view.sample_weight.tolist() == pytest.approx([0.68])
    assert "engine:mcts" in view.source_tags[0]
    assert "value:strong-search" in view.source_tags[0]


def test_training_view_tags_single_visit_policy_and_clips_value():
    record = observation_record()
    record["policy_visits"] = [0] * 64
    record["policy_visits"][0] = 1
    record["value"] = 2.0
    record["value_source"] = "synthetic"
    record["source_confidence"] = 1.0
    rows = load_observations_jsonl_from_records([record])

    view = training_view_from_observations(rows)

    assert view.value_target.tolist() == pytest.approx([1.0])
    assert view.sample_weight.tolist() == pytest.approx([0.2])
    assert "policy:single-visit" in view.source_tags[0]


def test_training_view_uses_materialized_bitboards_without_qfen_roundtrip():
    visits = [0] * 64
    visits[21] = 1
    row = ObservationRow(
        schema=OBSERVATION_SCHEMA,
        contract_version="1.1.0",
        run_id="run-1",
        row_id=0,
        position_key="pos-0",
        ply=1,
        side_to_move=1,
        bitboards=(1, 0, 0, 0, 0, 0, 0, 0),
        legal_action_mask=0,
        engine_kind="mcts",
        engine_version="0.1.0",
        elapsed_ms=12,
        policy_visits=tuple(visits),
        value=0.25,
        value_source="strong-search",
        source_confidence=0.8,
        qfen="not-a-qfen",
    )

    view = training_view_from_observations([row])

    assert view.tensors[0, 0, 0, 0] == 1.0
    assert view.tensors[0, 8].tolist() == [[1.0] * 4] * 4


def test_load_training_view_from_observations_jsonl(tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_text(json.dumps(observation_record()) + "\n", encoding="utf-8")

    view = load_training_view_from_observations_jsonl(path)

    assert len(view) == 1
    assert view.policy_target[0, 0] == pytest.approx(0.75)


def test_load_training_view_from_observations_parquet(tmp_path):
    pytest.importorskip("pyarrow")
    source_path = tmp_path / "observations.jsonl"
    parquet_path = tmp_path / "observations.parquet"
    source_path.write_text(json.dumps(observation_record()) + "\n", encoding="utf-8")
    write_observations_parquet(load_observations_jsonl(source_path), parquet_path)

    view = load_training_view_from_observations_parquet(parquet_path)

    assert len(view) == 1
    assert view.policy_target[0, 21] == pytest.approx(0.25)


def test_training_view_npz_roundtrip(tmp_path):
    rows = load_observations_jsonl_from_records([observation_record()])
    view = training_view_from_observations(rows)
    path = tmp_path / "training-view.npz"

    write_training_view_npz(view, path)
    loaded = load_training_view_npz(path)

    assert np.array_equal(loaded.bitboards, view.bitboards)
    assert np.allclose(loaded.policy_target, view.policy_target)
    assert loaded.source_tags == view.source_tags


def test_training_view_npz_roundtrips_empty_and_separator_tags(tmp_path):
    view = TrainingDatasetView(
        tensors=np.zeros((2, 9, 4, 4), dtype=np.float32),
        bitboards=np.zeros((2, 8), dtype=np.uint16),
        side_to_move=np.zeros(2, dtype=np.uint8),
        legal_action_mask=np.zeros(2, dtype=np.uint64),
        policy_target=np.zeros((2, 64), dtype=np.float32),
        value_target=np.zeros(2, dtype=np.float32),
        sample_weight=np.ones(2, dtype=np.float32),
        source_tags=((), ("tag\x1fwith-separator", "plain")),
    )
    path = tmp_path / "training-view.npz"

    write_training_view_npz(view, path)
    loaded = load_training_view_npz(path)

    assert loaded.source_tags == view.source_tags


def test_training_dataset_cli_writes_npz(tmp_path):
    source_path = tmp_path / "observations.jsonl"
    output_path = tmp_path / "training-view.npz"
    source_path.write_text(json.dumps(observation_record()) + "\n", encoding="utf-8")

    assert (
        main(
            [
                "--observations-jsonl",
                str(source_path),
                "--output-npz",
                str(output_path),
            ]
        )
        == 0
    )

    assert len(load_training_view_npz(output_path)) == 1


def test_training_dataset_cli_is_packaged_as_console_script(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["scripts"]["quantik-training-dataset"] == (
        "quantik_core.training_dataset:main"
    )


def test_training_view_requires_rows():
    with pytest.raises(ValueError, match="at least one observation row"):
        training_view_from_observations([])


def load_observations_jsonl_from_records(records):
    lines = [json.dumps(record) for record in records]
    # Keep test rows on disk so they pass through the public JSONL parser.
    with tempfile.TemporaryDirectory() as directory:
        file_path = Path(directory) / "observations.jsonl"
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return load_observations_jsonl(file_path)
