"""Append-only checkpoint storage for long benchmark runs."""

from __future__ import annotations

import json
import time
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Callable, Iterable

from benchmarks import bundle
from benchmarks.agreement import aggregate_agreement, aggregate_cost
from benchmarks.head_to_head import aggregate_head_to_head
from benchmarks.stability import aggregate_stability

MANIFEST = "manifest.json"
OBSERVATIONS = "observations.jsonl"
H2H_RECORDS = "h2h.jsonl"
_RESUME_CONFIG_EXCLUDES = {"checkpoint_dir", "output", "resume", "workers"}


def append_jsonl(path, row: dict) -> None:
    """Append one JSON object as one compact, sorted-key JSONL row."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
        handle.write("\n")
        handle.flush()


def load_jsonl(path) -> list[dict]:
    """Load a JSONL file; missing files simply behave like an empty stream."""
    source = Path(path)
    if not source.exists():
        return []

    rows: list[dict] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{source}:{line_number}: invalid checkpoint JSON"
                ) from exc
    return rows


def observation_key(row: dict) -> tuple[str, str, str, int | None]:
    """Return the stable identity for one agreement observation."""
    return (
        row["position_id"],
        row["engine"],
        row["config_label"],
        row["seed"],
    )


def h2h_key(row: dict) -> tuple[str, str, str, int]:
    """Return the stable identity for one head-to-head record."""
    return (
        row["position_id"],
        row["mover"],
        row["responder"],
        row["seed"],
    )


def key_set(rows: Iterable[dict], key_func: Callable[[dict], tuple]) -> set[tuple]:
    """Build the set of stable resume keys already present in checkpoint rows."""
    return {key_func(row) for row in rows}


def write_manifest(path, manifest: dict | None = None, **kwargs) -> None:
    """Atomically write the checkpoint manifest."""
    if manifest is not None and kwargs:
        raise TypeError("pass either a manifest dict or keyword fields, not both")
    if manifest is None:
        manifest = _build_manifest(**kwargs)

    target = _manifest_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp.replace(target)


def load_manifest(path) -> dict:
    """Load the checkpoint manifest or return an empty manifest state."""
    source = _manifest_path(path)
    if not source.exists():
        return {}
    return json.loads(source.read_text(encoding="utf-8"))


def update_manifest_counts(
    path,
    *,
    observations: int,
    h2h_records: int,
    status: str | None = None,
) -> dict:
    """Update checkpoint progress counters in place and return the manifest."""
    source = _manifest_path(path)
    manifest = load_manifest(source)
    manifest["counts"] = {"observations": observations, "h2h_records": h2h_records}
    if status is not None:
        manifest["status"] = status
    manifest["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_manifest(source, manifest)
    return manifest


def normalize_run_config(config: dict) -> dict:
    """Drop volatile fields that must not participate in resume validation."""
    return {
        key: value
        for key, value in config.items()
        if key not in _RESUME_CONFIG_EXCLUDES
    }


def _config_signature(config: dict, *, ignore_skip_h2h: bool = False) -> dict:
    signature = normalize_run_config(config)
    if ignore_skip_h2h:
        signature.pop("skip_h2h", None)
    return signature


def _dataset_summary(manifest: dict) -> dict:
    dataset = manifest.get("dataset")
    if dataset is None:
        raise ValueError("checkpoint manifest is missing dataset metadata")
    return dataset


def _manifest_path(path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        return candidate / MANIFEST
    if candidate.name != MANIFEST and candidate.suffix != ".json":
        return candidate / MANIFEST
    return candidate


def _build_manifest(
    *,
    config: dict,
    dataset_payload: dict,
    h2h_pairs: list[list[str]] | None = None,
    status: str = "running",
    observations: int = 0,
    h2h_records: int = 0,
) -> dict:
    phases = dict(
        Counter(position["phase"] for position in dataset_payload["positions"])
    )
    manifest = {
        "schema_version": bundle.SCHEMA_VERSION,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "environment": bundle.collect_environment(),
        "config": config,
        "dataset": {
            "checksum": dataset_payload.get("checksum"),
            "generator": dataset_payload["generator"],
            "seed": dataset_payload["seed"],
            "schema_version": dataset_payload["schema_version"],
            "positions": len(dataset_payload["positions"]),
            "phases": phases,
        },
        "status": status,
        "counts": {"observations": observations, "h2h_records": h2h_records},
    }
    if h2h_pairs is not None:
        manifest["h2h_pairs"] = h2h_pairs
    return manifest


def validate_resume_manifest(
    manifest: dict,
    *,
    dataset_checksum,
    config: dict,
    allow_skip_h2h_mismatch: bool = False,
) -> None:
    """Raise ValueError when a resume checkpoint does not match the run."""
    manifest_dataset = manifest.get("dataset", {})
    expected_dataset_checksum = dataset_checksum
    actual_dataset_checksum = manifest_dataset.get("checksum")
    if actual_dataset_checksum != expected_dataset_checksum:
        raise ValueError(
            "checkpoint dataset checksum mismatch: "
            f"expected {expected_dataset_checksum!r}, found {actual_dataset_checksum!r}"
        )

    expected_config = _config_signature(config, ignore_skip_h2h=allow_skip_h2h_mismatch)
    actual_config = _config_signature(
        manifest.get("config", {}), ignore_skip_h2h=allow_skip_h2h_mismatch
    )
    if actual_config != expected_config:
        diffs = []
        for key in sorted(set(actual_config) | set(expected_config)):
            if actual_config.get(key) != expected_config.get(key):
                diffs.append(
                    f"{key}: expected {expected_config.get(key)!r}, "
                    f"found {actual_config.get(key)!r}"
                )
        detail = "; ".join(diffs) if diffs else "unknown difference"
        raise ValueError(f"checkpoint config mismatch: {detail}")


def _head_to_head_aggregates(records: list[dict]) -> list[dict]:
    grouped: OrderedDict[tuple[str, str], list[dict]] = OrderedDict()
    pair_order: dict[tuple[str, str], tuple[str, str]] = {}

    for record in records:
        pair_key = tuple(sorted((record["mover"], record["responder"])))
        grouped.setdefault(pair_key, []).append(record)
        pair_order.setdefault(pair_key, (record["mover"], record["responder"]))

    aggregates = []
    for pair_key in grouped:
        name_a, name_b = pair_order[pair_key]
        aggregates.append(aggregate_head_to_head(grouped[pair_key], name_a, name_b))
    return aggregates


def bundle_from_checkpoint(root) -> dict:
    """Rehydrate a checkpoint directory into the standard benchmark bundle."""
    root_path = Path(root)
    manifest = load_manifest(root_path / MANIFEST)
    observations = load_jsonl(root_path / OBSERVATIONS)
    records = load_jsonl(root_path / H2H_RECORDS)
    dataset = _dataset_summary(manifest)

    checkpoint_info = {
        "status": manifest.get("status", "unknown"),
        "counts": manifest.get("counts", {"observations": 0, "h2h_records": 0}),
    }
    if "h2h_pairs" in manifest:
        checkpoint_info["h2h_pairs"] = manifest["h2h_pairs"]

    return {
        "schema_version": bundle.SCHEMA_VERSION,
        "started_at": manifest.get("started_at", time.strftime("%Y-%m-%dT%H:%M:%S%z")),
        "environment": manifest.get("environment", bundle.collect_environment()),
        "config": manifest.get("config", {}),
        "dataset": dataset,
        "checkpoint": checkpoint_info,
        "observations": observations,
        "head_to_head": {
            "records": records,
            "aggregates": _head_to_head_aggregates(records),
        },
        "aggregates": {
            "agreement": aggregate_agreement(observations),
            "cost": aggregate_cost(observations),
            "stability": aggregate_stability(observations),
        },
    }
