"""Reproducible benchmark result bundles."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import quantik_core

SCHEMA_VERSION = 1


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _total_memory_bytes() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None


def collect_environment() -> dict:
    """Return the host and software fingerprint stored in result bundles."""
    return {
        "quantik_core_version": quantik_core.__version__,
        "git_sha": _git_sha(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "total_memory_bytes": _total_memory_bytes(),
    }


def make_bundle(
    *,
    config: dict,
    dataset_payload: dict,
    observations: list,
    head_to_head: dict,
    aggregates: dict,
) -> dict:
    """Assemble a JSON-serializable, self-describing benchmark result bundle."""
    positions = dataset_payload["positions"]
    phases = Counter(position["phase"] for position in positions)

    return {
        "schema_version": SCHEMA_VERSION,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "environment": collect_environment(),
        "config": config,
        "dataset": {
            "checksum": dataset_payload.get("checksum"),
            "generator": dataset_payload["generator"],
            "seed": dataset_payload["seed"],
            "schema_version": dataset_payload["schema_version"],
            "positions": len(positions),
            "phases": dict(phases),
        },
        "observations": observations,
        "head_to_head": head_to_head,
        "aggregates": aggregates,
    }


def save_bundle(bundle_dict: dict, path) -> None:
    """Write a result bundle as JSON, creating parent directories as needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle_dict, indent=2, sort_keys=True) + "\n")
