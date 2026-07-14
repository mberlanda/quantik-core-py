"""ML data helpers for cross-language self-play artifacts.

The companion Rust crate owns high-throughput self-play export. This module is
Python's reference reader for those JSONL rows and the first layer used by later
training code.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, cast

import numpy as np
import numpy.typing as npt

from .commons import Bitboard
from .contracts import SUPPORTED_CONTRACTS, SUPPORTED_CONTRACTS_RELEASE
from .move import generate_legal_moves_list
from .qfen import bb_from_qfen, bb_to_qfen
from .state_validator import ValidationResult, validate_game_state

ACTION_COUNT = 64
BOARD_SIZE = 4
PLAYER_SHAPE_CHANNELS = 8
SIDE_TO_MOVE_CHANNEL = 8
TENSOR_CHANNELS = 9
SELFPLAY_SCHEMA = SUPPORTED_CONTRACTS["selfplay"]
ARROW_PARQUET_SELFPLAY_SCHEMA = SUPPORTED_CONTRACTS["arrow_parquet_selfplay"]
SELFPLAY_PARQUET_METADATA = {
    b"physical_schema": ARROW_PARQUET_SELFPLAY_SCHEMA.encode("utf-8"),
    b"logical_schema": SELFPLAY_SCHEMA.encode("utf-8"),
    b"logical_contract": SELFPLAY_SCHEMA.encode("utf-8"),
    b"contracts_release": SUPPORTED_CONTRACTS_RELEASE.encode("utf-8"),
    b"contract_version": SUPPORTED_CONTRACTS_RELEASE.encode("utf-8"),
}


@dataclass(frozen=True)
class PolicyVisit:
    """Visit count for one root action in a Rust self-play row."""

    shape: int
    position: int
    visits: int

    @property
    def action_index(self) -> int:
        """Return the shared 64-slot action index, shape-major."""
        return self.shape * 16 + self.position


@dataclass(frozen=True)
class SelfPlayRow:
    """One self-play training row emitted by the Rust exporter."""

    game_id: int
    ply: int
    qfen: str
    side_to_move: int
    policy: tuple[PolicyVisit, ...]
    value: float


def _expect_int(record: Mapping[str, Any], key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _expect_qfen(record: Mapping[str, Any]) -> str:
    value = record.get("qfen")
    if not isinstance(value, str):
        raise ValueError("qfen must be a string")
    return value


def _validate_contract_fields(record: Mapping[str, Any]) -> None:
    """Validate required schema and optional release pin.

    `schema` is required so readers can reject unsupported row layouts early.
    `contract_version` is optional for early Rust emitters, but must match this
    package's supported contracts release when present.
    """
    schema = record.get("schema")
    if schema != SELFPLAY_SCHEMA:
        raise ValueError(f"schema must be {SELFPLAY_SCHEMA}")

    contract_version = record.get("contract_version")
    if contract_version is not None and contract_version != SUPPORTED_CONTRACTS_RELEASE:
        raise ValueError(
            "contract_version must match supported contracts release "
            f"{SUPPORTED_CONTRACTS_RELEASE}"
        )


def _parse_policy(policy: Any) -> tuple[PolicyVisit, ...]:
    if not isinstance(policy, list) or not policy:
        raise ValueError("policy must be a non-empty list")

    visits: list[PolicyVisit] = []
    seen_actions: set[tuple[int, int]] = set()
    for index, item in enumerate(policy):
        if not isinstance(item, dict):
            raise ValueError(f"policy[{index}] must be an object")
        shape = _expect_int(item, "shape")
        position = _expect_int(item, "position")
        visit_count = _expect_int(item, "visits")
        if shape < 0 or shape > 3:
            raise ValueError(f"policy[{index}].shape must be in 0..3")
        if position < 0 or position > 15:
            raise ValueError(f"policy[{index}].position must be in 0..15")
        if visit_count <= 0:
            raise ValueError(f"policy[{index}].visits must be positive")
        action = (shape, position)
        if action in seen_actions:
            raise ValueError(
                f"policy[{index}] duplicates shape={shape}, position={position}"
            )
        seen_actions.add(action)
        visits.append(PolicyVisit(shape=shape, position=position, visits=visit_count))
    return tuple(visits)


def _validate_policy_is_legal(
    bitboard: Bitboard, policy: Sequence[PolicyVisit]
) -> None:
    legal_actions = {
        (move.shape, move.position) for move in generate_legal_moves_list(bitboard)
    }
    for visit in policy:
        if (visit.shape, visit.position) not in legal_actions:
            raise ValueError(
                "policy action is not legal for row state: "
                f"shape={visit.shape}, position={visit.position}"
            )


def parse_selfplay_row(record: Mapping[str, Any]) -> SelfPlayRow:
    """Validate and parse one Rust self-play JSON object."""
    _validate_contract_fields(record)
    game_id = _expect_int(record, "game_id")
    ply = _expect_int(record, "ply")
    if game_id < 0:
        raise ValueError("game_id must be non-negative")
    if ply < 0:
        raise ValueError("ply must be non-negative")

    qfen = _expect_qfen(record)
    side_to_move = _expect_int(record, "side_to_move")
    if side_to_move not in (0, 1):
        raise ValueError("side_to_move must be 0 or 1")

    bitboard = bb_from_qfen(qfen, validate=True)
    current_player, result = validate_game_state(bitboard)
    if result != ValidationResult.OK or current_player != side_to_move:
        raise ValueError("side_to_move does not match qfen")

    policy = _parse_policy(record.get("policy"))
    _validate_policy_is_legal(bitboard, policy)

    raw_value = record.get("value")
    if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
        raise ValueError("value must be numeric")
    value = float(raw_value)
    if value not in (-1.0, 1.0):
        raise ValueError("value must be exactly -1.0 or 1.0")

    return SelfPlayRow(
        game_id=game_id,
        ply=ply,
        qfen=qfen,
        side_to_move=side_to_move,
        policy=policy,
        value=value,
    )


def load_selfplay_jsonl(path: str | Path) -> list[SelfPlayRow]:
    """Load and validate a Rust self-play JSONL file."""
    rows: list[SelfPlayRow] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            try:
                rows.append(parse_selfplay_row(record))
            except ValueError as exc:
                raise ValueError(
                    f"invalid self-play row on line {line_number}: {exc}"
                ) from exc
    return rows


def qfen_to_tensor(qfen: str, side_to_move: int) -> npt.NDArray[np.float32]:
    """Encode a QFEN position as a `(9, 4, 4)` NumPy tensor."""
    if side_to_move not in (0, 1):
        raise ValueError("side_to_move must be 0 or 1")
    bitboard = bb_from_qfen(qfen, validate=True)
    tensor = np.zeros((TENSOR_CHANNELS, BOARD_SIZE, BOARD_SIZE), dtype=np.float32)

    for channel in range(PLAYER_SHAPE_CHANNELS):
        bits = bitboard[channel]
        for position in range(16):
            if (bits >> position) & 1:
                row = position // BOARD_SIZE
                col = position % BOARD_SIZE
                tensor[channel, row, col] = 1.0

    tensor[SIDE_TO_MOVE_CHANNEL, :, :] = float(side_to_move)
    return tensor


def policy_visits_to_distribution(
    policy: Iterable[PolicyVisit],
) -> npt.NDArray[np.float32]:
    """Normalize policy visit counts into the shared 64-slot action vector."""
    dense = policy_visits_to_dense(policy)
    total_visits = sum(dense)
    distribution = np.asarray(dense, dtype=np.float32)
    distribution /= float(total_visits)
    return distribution


def policy_visits_to_dense(policy: Iterable[PolicyVisit]) -> tuple[int, ...]:
    """Materialize policy visits as the Arrow/Parquet 64-slot action vector."""
    dense = [0] * ACTION_COUNT
    saw_visit = False
    for visit in policy:
        if visit.visits <= 0:
            raise ValueError("policy visits must be positive")
        dense[visit.action_index] += visit.visits
        saw_visit = True
    if not saw_visit:
        raise ValueError("policy must contain at least one visit")
    return tuple(dense)


def _selfplay_row_to_logical_record(row: SelfPlayRow) -> dict[str, Any]:
    return {
        "schema": SELFPLAY_SCHEMA,
        "contract_version": SUPPORTED_CONTRACTS_RELEASE,
        "game_id": row.game_id,
        "ply": row.ply,
        "qfen": row.qfen,
        "side_to_move": row.side_to_move,
        "policy": [
            {
                "shape": visit.shape,
                "position": visit.position,
                "visits": visit.visits,
            }
            for visit in row.policy
        ],
        "value": row.value,
    }


def _coerce_selfplay_row(row: SelfPlayRow | Mapping[str, Any]) -> SelfPlayRow:
    if isinstance(row, SelfPlayRow):
        return parse_selfplay_row(_selfplay_row_to_logical_record(row))
    return parse_selfplay_row(row)


def selfplay_row_to_arrow_parquet_record(row: SelfPlayRow) -> dict[str, Any]:
    """Convert a logical `selfplay.v1` row to the physical bulk-storage shape."""
    row = _coerce_selfplay_row(row)
    if row.ply > 65535:
        raise ValueError("ply must fit in uint16 for arrow-parquet-selfplay.v1")
    if row.value not in (-1.0, 1.0):
        raise ValueError("value must be exactly -1.0 or 1.0")
    return {
        "logical_schema": SELFPLAY_SCHEMA,
        "contract_version": SUPPORTED_CONTRACTS_RELEASE,
        "game_id": row.game_id,
        "ply": row.ply,
        "side_to_move": row.side_to_move,
        "bitboards": bb_from_qfen(row.qfen, validate=True),
        "policy_visits": policy_visits_to_dense(row.policy),
        "value": int(row.value),
        "qfen": row.qfen,
    }


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        pa = importlib.import_module("pyarrow")
        pq = importlib.import_module("pyarrow.parquet")
    except ImportError as exc:
        raise ImportError(
            "pyarrow is required for self-play Parquet I/O; install "
            "quantik-core[arrow]"
        ) from exc
    return pa, pq


def _selfplay_parquet_schema(pa: Any) -> Any:
    return pa.schema(
        [
            pa.field("logical_schema", pa.string(), nullable=False),
            pa.field("contract_version", pa.string(), nullable=False),
            pa.field("game_id", pa.uint64(), nullable=False),
            pa.field("ply", pa.uint16(), nullable=False),
            pa.field("side_to_move", pa.uint8(), nullable=False),
            pa.field(
                "bitboards",
                pa.list_(pa.uint16(), list_size=PLAYER_SHAPE_CHANNELS),
                nullable=False,
            ),
            pa.field(
                "policy_visits",
                pa.list_(pa.uint32(), list_size=ACTION_COUNT),
                nullable=False,
            ),
            pa.field("value", pa.int8(), nullable=False),
            pa.field("qfen", pa.string(), nullable=True),
        ],
        metadata=SELFPLAY_PARQUET_METADATA,
    )


def write_selfplay_parquet(
    rows: Iterable[SelfPlayRow | Mapping[str, Any]], path: str | Path
) -> None:
    """Write logical `selfplay.v1` rows to physical Parquet storage.

    The file is tagged with `arrow-parquet-selfplay.v1` metadata while rows keep
    `selfplay.v1` semantics through the dense physical columns.
    """
    pa, pq = _require_pyarrow()
    schema = _selfplay_parquet_schema(pa)
    records = [
        selfplay_row_to_arrow_parquet_record(_coerce_selfplay_row(row)) for row in rows
    ]
    table = pa.Table.from_pylist(records, schema=schema)
    pq.write_table(table, Path(path))


def _validate_selfplay_parquet_metadata(metadata: Mapping[bytes, bytes] | None) -> None:
    metadata = metadata or {}
    labels = {
        b"physical_schema": "physical schema",
        b"logical_schema": "logical schema",
        b"logical_contract": "logical contract",
        b"contracts_release": "contracts release",
        b"contract_version": "contract version",
    }
    for key, expected in SELFPLAY_PARQUET_METADATA.items():
        if metadata.get(key) != expected:
            raise ValueError(
                f"{labels[key]} metadata must be {expected.decode('utf-8')}"
            )


def _expect_fixed_int_vector(
    record: Mapping[str, Any], key: str, length: int
) -> tuple[int, ...]:
    value = record.get(key)
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{key} must contain exactly {length} integers")
    items: list[int] = []
    for index, item in enumerate(value):
        if not isinstance(item, int) or isinstance(item, bool):
            raise ValueError(f"{key}[{index}] must be an integer")
        items.append(item)
    return tuple(items)


def _sparse_policy_from_dense(policy_visits: Sequence[int]) -> list[dict[str, int]]:
    policy: list[dict[str, int]] = []
    for action_index, visits in enumerate(policy_visits):
        if visits < 0:
            raise ValueError(f"policy_visits[{action_index}] must be non-negative")
        if visits == 0:
            continue
        shape, position = divmod(action_index, BOARD_SIZE * BOARD_SIZE)
        policy.append({"shape": shape, "position": position, "visits": visits})
    if not policy:
        raise ValueError("policy must contain at least one visit")
    return policy


def _logical_record_from_parquet_record(record: Mapping[str, Any]) -> dict[str, Any]:
    bitboards = cast(
        Bitboard,
        _expect_fixed_int_vector(record, "bitboards", PLAYER_SHAPE_CHANNELS),
    )
    policy_visits = _expect_fixed_int_vector(record, "policy_visits", ACTION_COUNT)

    qfen = record.get("qfen")
    if qfen is None:
        qfen = bb_to_qfen(bitboards)
    elif not isinstance(qfen, str):
        raise ValueError("qfen must be a string when present")
    if bb_from_qfen(qfen, validate=True) != bitboards:
        raise ValueError("bitboards do not match qfen")
    value = record.get("value")
    if value not in (-1, 1):
        raise ValueError("value must be exactly -1 or 1")

    return {
        "schema": record.get("logical_schema"),
        "contract_version": record.get("contract_version"),
        "game_id": record.get("game_id"),
        "ply": record.get("ply"),
        "qfen": qfen,
        "side_to_move": record.get("side_to_move"),
        "policy": _sparse_policy_from_dense(policy_visits),
        "value": float(value),
    }


def load_selfplay_parquet(path: str | Path) -> list[SelfPlayRow]:
    """Load physical Parquet storage and validate as logical `selfplay.v1` rows."""
    pa, pq = _require_pyarrow()
    table = pq.read_table(Path(path))
    schema = _selfplay_parquet_schema(pa)
    _validate_selfplay_parquet_metadata(table.schema.metadata)
    if table.schema.remove_metadata() != schema.remove_metadata():
        raise ValueError("arrow-parquet-selfplay.v1 schema must match the contract")

    rows: list[SelfPlayRow] = []
    for row_number, record in enumerate(table.to_pylist(), start=1):
        try:
            rows.append(parse_selfplay_row(_logical_record_from_parquet_record(record)))
        except ValueError as exc:
            raise ValueError(
                f"invalid self-play parquet row {row_number}: {exc}"
            ) from exc
    return rows
