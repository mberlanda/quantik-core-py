"""Tests for resumable benchmark checkpoint storage."""

import pytest

from benchmarks import bundle, checkpoint, report


def test_jsonl_append_and_load_roundtrip(tmp_path):
    path = tmp_path / "rows.jsonl"

    checkpoint.append_jsonl(path, {"b": 2, "a": 1})
    checkpoint.append_jsonl(path, {"a": 3, "b": 4})

    assert checkpoint.load_jsonl(path) == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    assert path.read_text().splitlines() == ['{"a":1,"b":2}', '{"a":3,"b":4}']


def test_load_jsonl_missing_file_returns_empty_list(tmp_path):
    assert checkpoint.load_jsonl(tmp_path / "missing.jsonl") == []


def test_load_jsonl_bad_json_includes_file_and_line(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"ok":1}\n{"bad":\n')

    with pytest.raises(ValueError, match=r"rows\.jsonl:2"):
        checkpoint.load_jsonl(path)


def test_observation_and_h2h_keys_are_stable():
    observation = {
        "position_id": "p0008",
        "engine": "mcts",
        "config_label": "mcts(it=5000,d=16,c=1.414)",
        "seed": 7,
    }
    h2h = {
        "position_id": "p0008",
        "mover": "beam",
        "responder": "mcts",
        "seed": 11,
    }

    assert checkpoint.observation_key(observation) == (
        "p0008",
        "mcts",
        "mcts(it=5000,d=16,c=1.414)",
        7,
    )
    assert checkpoint.h2h_key(h2h) == ("p0008", "beam", "mcts", 11)
    assert checkpoint.key_set([observation], checkpoint.observation_key) == {
        ("p0008", "mcts", "mcts(it=5000,d=16,c=1.414)", 7)
    }


def test_manifest_lifecycle_and_bundle_rehydration(tmp_path):
    root = tmp_path / "checkpoint"
    manifest_path = root / checkpoint.MANIFEST
    config = {"family": "native", "engine_seeds": [0, 1]}
    dataset = {
        "checksum": "abc123",
        "generator": "benchmarks.dataset.generate/v1",
        "seed": 20260711,
        "schema_version": 1,
        "positions": 1,
        "phases": {"late_mid": 1},
    }
    manifest = {
        "status": "running",
        "started_at": "2026-07-12T00:00:00+0000",
        "environment": bundle.collect_environment(),
        "config": config,
        "dataset": dataset,
        "counts": {"observations": 0, "h2h_records": 0},
    }
    observation = {
        "engine": "minimax",
        "config_label": "minimax(d=16)",
        "position_id": "p0000",
        "move": "1:3:5",
        "wall_time_s": 0.01,
        "cpu_time_s": 0.01,
        "root_legal_moves": 10,
        "exact": True,
        "seed": 0,
        "nodes": 42,
        "iterations": None,
        "depth_reached": 8,
        "score": 9990.0,
        "peak_memory_bytes": None,
        "extra": {},
        "phase": "late_mid",
        "hit": True,
    }
    h2h_record = {
        "position_id": "p0000",
        "phase": "late_mid",
        "mover": "minimax",
        "responder": "random",
        "winner": "minimax",
        "plies": 1,
        "seed": 0,
    }

    checkpoint.write_manifest(manifest_path, manifest)
    checkpoint.append_jsonl(root / checkpoint.OBSERVATIONS, observation)
    checkpoint.append_jsonl(root / checkpoint.H2H_RECORDS, h2h_record)

    loaded = checkpoint.load_manifest(manifest_path)
    assert loaded["status"] == "running"
    assert loaded["dataset"] == dataset

    checkpoint.update_manifest_counts(
        manifest_path,
        observations=1,
        h2h_records=1,
        status="complete",
    )
    updated = checkpoint.load_manifest(manifest_path)
    assert updated["status"] == "complete"
    assert updated["counts"] == {"observations": 1, "h2h_records": 1}

    bundle_dict = checkpoint.bundle_from_checkpoint(root)
    assert bundle_dict["schema_version"] == bundle.SCHEMA_VERSION
    assert bundle_dict["config"] == config
    assert bundle_dict["dataset"] == dataset
    assert bundle_dict["observations"] == [observation]
    assert bundle_dict["head_to_head"]["records"] == [h2h_record]
    assert bundle_dict["aggregates"]["agreement"][0]["n"] == 1
    assert bundle_dict["aggregates"]["cost"][0]["median_nodes"] == 42
    assert bundle_dict["head_to_head"]["aggregates"][0]["games"] == 1
    assert bundle_dict["checkpoint"]["status"] == "complete"
    assert bundle_dict["checkpoint"]["counts"] == {
        "observations": 1,
        "h2h_records": 1,
    }
    assert "checkpoint status: complete" in report.render_markdown(bundle_dict)


def test_running_checkpoint_report_shows_status(tmp_path):
    root = tmp_path / "checkpoint"
    payload = {
        "schema_version": 1,
        "generator": "benchmarks.dataset.generate/v1",
        "seed": 20260711,
        "requested": {"late_mid": 1},
        "checksum": "abc123",
        "positions": [
            {
                "id": "p0000",
                "qfen": ".ba./..CC/DcbD/cA.A",
                "phase": "late_mid",
                "pieces": 8,
                "side_to_move": 1,
                "legal_moves": 10,
                "reference": None,
            }
        ],
    }
    checkpoint.write_manifest(
        root,
        config={"family": "native", "engine_seeds": [0]},
        dataset_payload=payload,
        status="running",
        observations=0,
        h2h_records=0,
    )

    bundle_dict = checkpoint.bundle_from_checkpoint(root)

    assert bundle_dict["checkpoint"]["status"] == "running"
    assert bundle_dict["checkpoint"]["counts"] == {
        "observations": 0,
        "h2h_records": 0,
    }
    assert "checkpoint status: running" in report.render_markdown(bundle_dict)
