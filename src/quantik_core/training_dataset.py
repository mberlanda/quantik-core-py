"""NumPy-first training views over Quantik artifact contracts.

The contracts repository owns durable artifact shapes. This module is the
Python training-facing projection: validated rows become dense arrays that are
stable across stacks and cheap to hand to a model trainer.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import numpy.typing as npt

from .artifact_data import (
    ObservationRow,
    load_observations_jsonl,
    load_observations_parquet,
)
from .ml_data import (
    ACTION_COUNT,
    BOARD_SIZE,
    PLAYER_SHAPE_CHANNELS,
    SIDE_TO_MOVE_CHANNEL,
    TENSOR_CHANNELS,
)

DEFAULT_VALUE_SOURCE_WEIGHTS: Mapping[str, float] = {
    "exact": 1.0,
    "tablebase": 1.0,
    "opening-book": 1.0,
    "opening_book": 1.0,
    "bounded": 0.9,
    "strong-search": 0.85,
    "strong_search": 0.85,
    "search": 0.7,
    "mcts": 0.7,
    "minimax": 0.7,
    "beam": 0.6,
    "h2h": 0.45,
    "game-result": 0.45,
    "game_result": 0.45,
    "heuristic": 0.25,
    "synthetic": 0.2,
}


@dataclass(frozen=True)
class TrainingDatasetView:
    """Dense training arrays derived from artifact rows."""

    tensors: npt.NDArray[np.float32]
    bitboards: npt.NDArray[np.uint16]
    side_to_move: npt.NDArray[np.uint8]
    legal_action_mask: npt.NDArray[np.uint64]
    policy_target: npt.NDArray[np.float32]
    value_target: npt.NDArray[np.float32]
    sample_weight: npt.NDArray[np.float32]
    source_tags: tuple[tuple[str, ...], ...]

    def __len__(self) -> int:
        return int(self.value_target.shape[0])


def _policy_target(policy_visits: tuple[int, ...]) -> npt.NDArray[np.float32]:
    if len(policy_visits) != ACTION_COUNT:
        raise ValueError(f"policy_visits must contain {ACTION_COUNT} entries")
    visits = np.asarray(policy_visits, dtype=np.float32)
    total = float(visits.sum())
    if total <= 0.0:
        raise ValueError("policy_visits must contain at least one visit")
    return visits / total


def _value_source_weight(
    value_source: str, value_source_weights: Mapping[str, float] | None
) -> float:
    weights = value_source_weights or DEFAULT_VALUE_SOURCE_WEIGHTS
    return float(weights.get(value_source.lower(), 0.5))


def _sample_weight(
    row: ObservationRow, value_source_weights: Mapping[str, float] | None
) -> float:
    weight = row.source_confidence * _value_source_weight(
        row.value_source, value_source_weights
    )
    return float(min(1.0, max(0.0, weight)))


def _source_tags(row: ObservationRow) -> tuple[str, ...]:
    total_visits = sum(row.policy_visits)
    tags = [
        f"schema:{row.schema}",
        f"run:{row.run_id}",
        f"engine:{row.engine_kind}",
        f"value:{row.value_source}",
    ]
    if total_visits == 1:
        tags.append("policy:single-visit")
    return tuple(tags)


def _bitboards_to_tensor(
    bitboards: tuple[int, ...], side_to_move: int
) -> npt.NDArray[np.float32]:
    if len(bitboards) != PLAYER_SHAPE_CHANNELS:
        raise ValueError(f"bitboards must contain {PLAYER_SHAPE_CHANNELS} planes")
    if side_to_move not in (0, 1):
        raise ValueError("side_to_move must be 0 or 1")

    tensor = np.zeros((TENSOR_CHANNELS, BOARD_SIZE, BOARD_SIZE), dtype=np.float32)
    for channel, bits in enumerate(bitboards):
        for position in range(BOARD_SIZE * BOARD_SIZE):
            if (bits >> position) & 1:
                row = position // BOARD_SIZE
                col = position % BOARD_SIZE
                tensor[channel, row, col] = 1.0
    tensor[SIDE_TO_MOVE_CHANNEL, :, :] = float(side_to_move)
    return tensor


def training_view_from_observations(
    rows: Iterable[ObservationRow],
    *,
    value_source_weights: Mapping[str, float] | None = None,
) -> TrainingDatasetView:
    """Project `observation.v1` rows into dense policy/value training arrays."""
    materialized = list(rows)
    if not materialized:
        raise ValueError("training view requires at least one observation row")

    tensors = np.stack(
        [_bitboards_to_tensor(row.bitboards, row.side_to_move) for row in materialized]
    ).astype(np.float32, copy=False)
    bitboards = np.asarray(
        [row.bitboards for row in materialized],
        dtype=np.uint16,
    )
    side_to_move = np.asarray(
        [row.side_to_move for row in materialized],
        dtype=np.uint8,
    )
    legal_action_mask = np.asarray(
        [row.legal_action_mask for row in materialized],
        dtype=np.uint64,
    )
    policy_target = np.stack(
        [_policy_target(row.policy_visits) for row in materialized]
    ).astype(np.float32, copy=False)
    value_target = np.asarray(
        [min(1.0, max(-1.0, row.value)) for row in materialized],
        dtype=np.float32,
    )
    sample_weight = np.asarray(
        [_sample_weight(row, value_source_weights) for row in materialized],
        dtype=np.float32,
    )
    source_tags = tuple(_source_tags(row) for row in materialized)

    if tensors.shape[1:] != (PLAYER_SHAPE_CHANNELS + 1, 4, 4):
        raise ValueError("training tensors must have shape (n, 9, 4, 4)")
    return TrainingDatasetView(
        tensors=tensors,
        bitboards=bitboards,
        side_to_move=side_to_move,
        legal_action_mask=legal_action_mask,
        policy_target=policy_target,
        value_target=value_target,
        sample_weight=sample_weight,
        source_tags=source_tags,
    )


def load_training_view_from_observations_jsonl(
    path: str | Path,
    *,
    value_source_weights: Mapping[str, float] | None = None,
) -> TrainingDatasetView:
    """Load `observation.v1` JSONL and return the NumPy training view."""
    return training_view_from_observations(
        load_observations_jsonl(path),
        value_source_weights=value_source_weights,
    )


def load_training_view_from_observations_parquet(
    path: str | Path,
    *,
    value_source_weights: Mapping[str, float] | None = None,
) -> TrainingDatasetView:
    """Load `observation.v1` Parquet and return the NumPy training view."""
    return training_view_from_observations(
        load_observations_parquet(path),
        value_source_weights=value_source_weights,
    )


def write_training_view_npz(view: TrainingDatasetView, path: str | Path) -> None:
    """Write a compressed NumPy training dataset artifact."""
    encoded_tags = np.asarray(
        [json.dumps(tags, separators=(",", ":")) for tags in view.source_tags],
        dtype=np.str_,
    )
    np.savez_compressed(
        Path(path),
        tensors=view.tensors,
        bitboards=view.bitboards,
        side_to_move=view.side_to_move,
        legal_action_mask=view.legal_action_mask,
        policy_target=view.policy_target,
        value_target=view.value_target,
        sample_weight=view.sample_weight,
        source_tags=encoded_tags,
    )


def load_training_view_npz(path: str | Path) -> TrainingDatasetView:
    """Load a compressed NumPy training dataset artifact."""
    with np.load(Path(path), allow_pickle=False) as data:
        source_tags = tuple(
            tuple(json.loads(str(item))) for item in data["source_tags"].tolist()
        )
        return TrainingDatasetView(
            tensors=data["tensors"].astype(np.float32, copy=False),
            bitboards=data["bitboards"].astype(np.uint16, copy=False),
            side_to_move=data["side_to_move"].astype(np.uint8, copy=False),
            legal_action_mask=data["legal_action_mask"].astype(np.uint64, copy=False),
            policy_target=data["policy_target"].astype(np.float32, copy=False),
            value_target=data["value_target"].astype(np.float32, copy=False),
            sample_weight=data["sample_weight"].astype(np.float32, copy=False),
            source_tags=source_tags,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Materialize observation.v1 rows as a NumPy training view."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--observations-jsonl")
    source.add_argument("--observations-parquet")
    parser.add_argument("--output-npz", required=True)
    args = parser.parse_args(argv)

    if args.observations_jsonl:
        view = load_training_view_from_observations_jsonl(args.observations_jsonl)
    else:
        view = load_training_view_from_observations_parquet(args.observations_parquet)
    write_training_view_npz(view, args.output_npz)
    print(f"wrote training dataset view: {args.output_npz} rows={len(view)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
