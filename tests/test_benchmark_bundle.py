"""Tests for benchmarks.bundle and benchmarks.report."""

import json

from benchmarks import bundle, report


def _synthetic_bundle():
    dataset_payload = {
        "schema_version": 1,
        "generator": "benchmarks.dataset.generate/v1",
        "seed": 7,
        "requested": {"late_mid": 1},
        "checksum": "cafe" * 16,
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
    observations = [
        {
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
    ]
    aggregates = {
        "agreement": [
            {
                "engine": "minimax",
                "config_label": "minimax(d=16)",
                "phase": "late_mid",
                "n": 1,
                "hits": 1,
                "agreement": 1.0,
                "ci95_low": 0.207,
                "ci95_high": 1.0,
            }
        ],
        "cost": [
            {
                "engine": "minimax",
                "config_label": "minimax(d=16)",
                "n": 1,
                "median_time_s": 0.01,
                "p95_time_s": 0.01,
                "median_nodes": 42.0,
                "peak_memory_bytes": None,
            }
        ],
        "stability": [
            {
                "engine": "minimax",
                "config_label": "minimax(d=16)",
                "seeds": 1,
                "move_consistency": 1.0,
                "agreement_mean": 1.0,
                "agreement_std": 0.0,
            }
        ],
    }
    head_to_head = {
        "records": [
            {
                "position_id": "p0000",
                "phase": "late_mid",
                "mover": "minimax",
                "responder": "random",
                "winner": "minimax",
                "plies": 1,
                "seed": 0,
            }
        ],
        "aggregates": [
            {
                "engine_a": "minimax",
                "engine_b": "random",
                "games": 2,
                "paired_positions": 1,
                "a_wins": 2,
                "b_wins": 0,
                "draws": 0,
                "a_win_rate": 1.0,
                "a_win_rate_ci95": [0.342, 1.0],
                "a_wins_as_mover": 1,
                "b_wins_as_mover": 0,
                "by_phase": {"late_mid": {"games": 2, "a_wins": 2, "b_wins": 0}},
            }
        ],
    }
    config = {"family": "fixed", "time_limit": 1.0, "engine_seeds": [0]}
    return bundle.make_bundle(
        config=config,
        dataset_payload=dataset_payload,
        observations=observations,
        head_to_head=head_to_head,
        aggregates=aggregates,
    )


class TestEnvironment:
    def test_required_keys_present(self):
        env = bundle.collect_environment()
        for key in (
            "quantik_core_version",
            "git_sha",
            "python_version",
            "platform",
            "processor",
            "cpu_count",
            "total_memory_bytes",
        ):
            assert key in env
        assert env["python_version"].count(".") >= 1


class TestBundle:
    def test_bundle_is_self_describing_and_json_serializable(self):
        result = _synthetic_bundle()
        assert result["schema_version"] == bundle.SCHEMA_VERSION
        assert result["dataset"]["checksum"] == "cafe" * 16
        assert result["dataset"]["positions"] == 1
        assert result["dataset"]["phases"] == {"late_mid": 1}
        assert result["observations"]
        json.dumps(result)

    def test_save_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "results" / "nested" / "run.json"
        bundle.save_bundle(_synthetic_bundle(), target)
        assert json.loads(target.read_text())["schema_version"] == 1


class TestReport:
    def test_contains_all_four_tables_and_metadata(self):
        md = report.render_markdown(_synthetic_bundle())
        for heading in (
            "## Exact move agreement",
            "## Computational cost",
            "## Head-to-head (paired, side-balanced)",
            "## Stability across seeds",
            "## Interpretation guardrails",
        ):
            assert heading in md
        assert "cafe" in md
        assert "minimax" in md
        assert "| Draws |" in md or "Draws" in md

    def test_none_values_render_as_dash_not_none(self):
        md = report.render_markdown(_synthetic_bundle())
        assert "None" not in md
