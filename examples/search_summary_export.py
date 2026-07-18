"""Draft search-telemetry exporter example.

Runs the MCTS, minimax, and beam engines against a handful of fixed positions
and writes one `search-summary.v1` JSONL row per completed root search
whose root identity was preserved. Rows skipped for an unpreserved root
identity are logged to stderr, not written. Uses the SAME positions and seed as
the Rust example (`examples/search_summary_export.rs`) so rows are
cross-checkable.

Usage:
    python examples/search_summary_export.py --out search-summaries.jsonl
"""

import argparse
import json
import sys
from pathlib import Path
from typing import IO, Optional, Tuple

from quantik_core import State
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.search_summary import (
    SearchSummaryRunConfig,
    search_summary_row,
)
from quantik_core.search_telemetry import SearchTelemetry

SEED = 20260716
RUN_ID = "search-summary-export"

# Empty board plus two known-valid mid-game positions (same as the Rust
# example: qfen.rs mixed_position + the contract-shape fixture).
POSITIONS = [
    ("empty", "..../..../..../...."),
    ("mid-6ply", "A.bC/..../d..B/...a"),
    ("mid-4ply", "Ab../..c./...D/...."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="search-summaries.jsonl")
    args = parser.parse_args()

    out_path = Path(args.out)
    if out_path.parent and str(out_path.parent) not in ("", "."):
        out_path.parent.mkdir(parents=True, exist_ok=True)

    row_id = 0
    rows_written = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for label, qfen in POSITIONS:
            state = State.from_qfen(qfen)

            # MCTS: use_transposition_table MUST be False for export.
            mcts = MCTSEngine(
                MCTSConfig(
                    max_iterations=200, random_seed=SEED, use_transposition_table=False
                )
            )
            mcts.search(state)
            row_id, rows_written = _emit(
                handle,
                row_id,
                rows_written,
                label,
                "mcts",
                qfen,
                mcts.telemetry(),
                SearchSummaryRunConfig(config_label="mcts-default", rollouts=200),
            )

            # Minimax: dedup_children MUST be False for export.
            minimax = MinimaxEngine(
                MinimaxConfig(max_depth=4, dedup_children=False, random_seed=SEED)
            )
            minimax.search(state)
            row_id, rows_written = _emit(
                handle,
                row_id,
                rows_written,
                label,
                "minimax",
                qfen,
                minimax.telemetry(),
                SearchSummaryRunConfig(config_label="minimax-depth4", search_depth=4),
            )

            # Beam: default config plus a fixed seed; depth-1 dedup makes a
            # legitimate, expected skip.
            beam_config = BeamSearchConfig(random_seed=SEED)
            beam = BeamSearchEngine(beam_config)
            result = beam.search(state)
            row_id, rows_written = _emit(
                handle,
                row_id,
                rows_written,
                label,
                "beam",
                qfen,
                beam.telemetry(result),
                SearchSummaryRunConfig(
                    config_label="beam-default",
                    search_depth=beam_config.max_depth,
                    rollouts=beam_config.rollouts_per_candidate,
                    beam_width=beam_config.beam_width,
                ),
            )

    print(f"{rows_written} rows exported -> {out_path}")


def _emit(
    handle: IO[str],
    row_id: int,
    rows_written: int,
    label: str,
    engine: str,
    qfen: str,
    telemetry: Optional[SearchTelemetry],
    run_config: SearchSummaryRunConfig,
) -> Tuple[int, int]:
    if telemetry is None:
        print(f"[{label}] {engine}: no telemetry, skipping", file=sys.stderr)
        return row_id, rows_written
    row = search_summary_row(row_id, RUN_ID, qfen, telemetry, run_config)
    if row is None:
        print(
            f"[{label}] {engine}: root identity not preserved, skipping",
            file=sys.stderr,
        )
        return row_id, rows_written
    handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row_id + 1, rows_written + 1


if __name__ == "__main__":
    main()
