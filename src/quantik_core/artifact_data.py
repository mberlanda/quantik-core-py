"""Readers for Quantik artifact contracts beyond self-play rows.

The contracts repository defines bulk observations and completed games as
Parquet-first artifacts. This module intentionally starts with JSON/JSONL
readers because the Rust generator can emit those without optional Parquet
dependencies; a Parquet reader can materialize the same dataclasses later.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .commons import Bitboard
from .contracts import SUPPORTED_CONTRACTS, SUPPORTED_CONTRACTS_RELEASE
from .move import generate_legal_moves_list
from .qfen import bb_from_qfen
from .state_validator import ValidationResult, validate_game_state

ACTION_COUNT = 64
OBSERVATION_SCHEMA = SUPPORTED_CONTRACTS["observation"]
GAME_RESULT_SCHEMA = SUPPORTED_CONTRACTS["game_result"]
MODEL_CHECKPOINT_SCHEMA = SUPPORTED_CONTRACTS["model_checkpoint"]
_SUPPORTED_WEIGHTS_FORMATS = frozenset(("safetensors", "onnx", "npz", "custom-binary"))
_SUPPORTED_INPUT_CONTRACTS = frozenset(
    contract
    for key, contract in SUPPORTED_CONTRACTS.items()
    if key not in ("contracts_release", "model_checkpoint")
)


@dataclass(frozen=True)
class ObservationRow:
    """One `observation.v1` row from a search/evaluation run."""

    run_id: str
    row_id: int
    position_key: str
    ply: int
    side_to_move: int
    bitboards: Bitboard
    legal_action_mask: int
    engine_kind: str
    engine_version: str
    policy_visits: tuple[int, ...]
    value: float
    value_source: str
    source_confidence: float
    qfen: str | None = None


@dataclass(frozen=True)
class GameResultRow:
    """One completed `game-result.v1` head-to-head game."""

    game_id: str
    p0_engine_kind: str
    p1_engine_kind: str
    initial_position_key: str
    winner: int
    plies: int
    terminal_reason: str
    move_action_indices: tuple[int, ...]
    run_id: str | None = None


@dataclass(frozen=True)
class ModelCheckpointManifest:
    """Metadata for one `model-checkpoint.v1` artifact."""

    schema: str
    contract_version: str
    model_id: str
    model_family: str
    created_at: str
    input_contracts: tuple[str, ...]
    output_contract: str
    weights_format: str
    weights_hash: str
    size_bytes: int
    training_data_manifest: str
    calibration_report: str
    feature_hash: str | None = None
    quantization: str | None = None
    parameter_count: int | None = None
    architecture: str | None = None
    legal_action_mask_required: bool | None = None
    recommended_engine_order: tuple[str, ...] | None = None
    notes: str | None = None


def _expect_int(record: Mapping[str, Any], key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _expect_str(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _expect_optional_str(record: Mapping[str, Any], key: str) -> str | None:
    if key not in record or record.get(key) is None:
        return None
    return _expect_str(record, key)


def _expect_optional_positive_int(record: Mapping[str, Any], key: str) -> int | None:
    if key not in record or record.get(key) is None:
        return None
    value = _expect_int(record, key)
    if value <= 0:
        raise ValueError(f"{key} must be positive")
    return value


def _expect_optional_bool(record: Mapping[str, Any], key: str) -> bool | None:
    if key not in record or record.get(key) is None:
        return None
    value = record.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _expect_optional_str_tuple(
    record: Mapping[str, Any], key: str
) -> tuple[str, ...] | None:
    if key not in record or record.get(key) is None:
        return None
    value = record.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key}[{index}] must be a non-empty string")
        items.append(item)
    if not items:
        raise ValueError(f"{key} must be non-empty when present")
    return tuple(items)


def _expect_number(record: Mapping[str, Any], key: str) -> float:
    value = record.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _validate_schema(record: Mapping[str, Any], expected_schema: str) -> None:
    schema = record.get("schema")
    if schema != expected_schema:
        raise ValueError(f"schema must be {expected_schema}")
    contract_version = record.get("contract_version")
    if contract_version != SUPPORTED_CONTRACTS_RELEASE:
        raise ValueError(
            "contract_version must match supported contracts release "
            f"{SUPPORTED_CONTRACTS_RELEASE}"
        )


def _parse_bitboards(value: Any) -> Bitboard:
    if not isinstance(value, list) or len(value) != 8:
        raise ValueError("bitboards must contain exactly 8 uint16 planes")
    planes: list[int] = []
    for index, plane in enumerate(value):
        if not isinstance(plane, int) or isinstance(plane, bool):
            raise ValueError(f"bitboards[{index}] must be an integer")
        if plane < 0 or plane > 0xFFFF:
            raise ValueError(f"bitboards[{index}] must be in 0..65535")
        planes.append(plane)
    return tuple(planes)  # type: ignore[return-value]


def _parse_u64_mask(record: Mapping[str, Any], key: str) -> int:
    value = _expect_int(record, key)
    if value < 0 or value > 0xFFFF_FFFF_FFFF_FFFF:
        raise ValueError(f"{key} must be a uint64")
    return value


def _parse_fixed_policy_visits(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != ACTION_COUNT:
        raise ValueError("policy_visits must contain exactly 64 integers")
    visits: list[int] = []
    for index, visit in enumerate(value):
        if not isinstance(visit, int) or isinstance(visit, bool):
            raise ValueError(f"policy_visits[{index}] must be an integer")
        if visit < 0:
            raise ValueError(f"policy_visits[{index}] must be non-negative")
        visits.append(visit)
    if sum(visits) <= 0:
        raise ValueError("policy_visits must contain at least one visit")
    return tuple(visits)


def _legal_action_mask(bitboards: Bitboard) -> int:
    mask = 0
    for move in generate_legal_moves_list(bitboards):
        mask |= 1 << (move.shape * 16 + move.position)
    return mask


def _validate_bitboards_and_side(
    bitboards: Bitboard, side_to_move: int, qfen: str | None
) -> None:
    current_player, result = validate_game_state(bitboards)
    if result != ValidationResult.OK or current_player != side_to_move:
        raise ValueError("side_to_move does not match bitboards")
    if qfen is not None and bb_from_qfen(qfen, validate=True) != bitboards:
        raise ValueError("qfen does not match bitboards")


def parse_observation_row(record: Mapping[str, Any]) -> ObservationRow:
    """Validate and parse one `observation.v1` JSON object."""
    _validate_schema(record, OBSERVATION_SCHEMA)
    row_id = _expect_int(record, "row_id")
    ply = _expect_int(record, "ply")
    side_to_move = _expect_int(record, "side_to_move")
    if row_id < 0:
        raise ValueError("row_id must be non-negative")
    if ply < 0:
        raise ValueError("ply must be non-negative")
    if side_to_move not in (0, 1):
        raise ValueError("side_to_move must be 0 or 1")

    bitboards = _parse_bitboards(record.get("bitboards"))
    qfen_value = record.get("qfen")
    qfen = qfen_value if isinstance(qfen_value, str) else None
    _validate_bitboards_and_side(bitboards, side_to_move, qfen)

    legal_action_mask = _parse_u64_mask(record, "legal_action_mask")
    expected_mask = _legal_action_mask(bitboards)
    if legal_action_mask != expected_mask:
        raise ValueError("legal_action_mask does not match bitboards")

    policy_visits = _parse_fixed_policy_visits(record.get("policy_visits"))
    for action_index, visits in enumerate(policy_visits):
        if visits and not ((legal_action_mask >> action_index) & 1):
            raise ValueError(f"policy_visits[{action_index}] is not legal")

    source_confidence = _expect_number(record, "source_confidence")
    if not 0.0 <= source_confidence <= 1.0:
        raise ValueError("source_confidence must be in 0.0..1.0")

    return ObservationRow(
        run_id=_expect_str(record, "run_id"),
        row_id=row_id,
        position_key=_expect_str(record, "position_key"),
        ply=ply,
        side_to_move=side_to_move,
        bitboards=bitboards,
        legal_action_mask=legal_action_mask,
        engine_kind=_expect_str(record, "engine_kind"),
        engine_version=_expect_str(record, "engine_version"),
        policy_visits=policy_visits,
        value=_expect_number(record, "value"),
        value_source=_expect_str(record, "value_source"),
        source_confidence=source_confidence,
        qfen=qfen,
    )


def parse_game_result_row(record: Mapping[str, Any]) -> GameResultRow:
    """Validate and parse one `game-result.v1` JSON object."""
    _validate_schema(record, GAME_RESULT_SCHEMA)
    winner = _expect_int(record, "winner")
    plies = _expect_int(record, "plies")
    if winner not in (0, 1):
        raise ValueError("winner must be 0 or 1")
    if plies < 0:
        raise ValueError("plies must be non-negative")

    moves_value = record.get("move_action_indices")
    if not isinstance(moves_value, list):
        raise ValueError("move_action_indices must be a list")
    moves: list[int] = []
    for index, action in enumerate(moves_value):
        if not isinstance(action, int) or isinstance(action, bool):
            raise ValueError(f"move_action_indices[{index}] must be an integer")
        if action < 0 or action >= ACTION_COUNT:
            raise ValueError(f"move_action_indices[{index}] must be in 0..63")
        moves.append(action)
    if plies != len(moves):
        raise ValueError("plies must match move_action_indices length")

    run_id_value = record.get("run_id")
    return GameResultRow(
        game_id=_expect_str(record, "game_id"),
        p0_engine_kind=_expect_str(record, "p0_engine_kind"),
        p1_engine_kind=_expect_str(record, "p1_engine_kind"),
        initial_position_key=_expect_str(record, "initial_position_key"),
        winner=winner,
        plies=plies,
        terminal_reason=_expect_str(record, "terminal_reason"),
        move_action_indices=tuple(moves),
        run_id=run_id_value if isinstance(run_id_value, str) else None,
    )


def parse_model_checkpoint_manifest(
    record: Mapping[str, Any],
) -> ModelCheckpointManifest:
    """Validate and parse one `model-checkpoint.v1` manifest object."""
    _validate_schema(record, MODEL_CHECKPOINT_SCHEMA)
    input_contracts_value = record.get("input_contracts")
    if not isinstance(input_contracts_value, list) or not input_contracts_value:
        raise ValueError("input_contracts must be a non-empty list")
    input_contracts: list[str] = []
    for index, contract in enumerate(input_contracts_value):
        if not isinstance(contract, str) or not contract.strip():
            raise ValueError(f"input_contracts[{index}] must be a non-empty string")
        if contract not in _SUPPORTED_INPUT_CONTRACTS:
            raise ValueError(f"unsupported input contract: {contract}")
        input_contracts.append(contract)
    size_bytes = _expect_int(record, "size_bytes")
    if size_bytes <= 0:
        raise ValueError("size_bytes must be positive")
    weights_format = _expect_str(record, "weights_format")
    if weights_format not in _SUPPORTED_WEIGHTS_FORMATS:
        raise ValueError(f"unsupported weights_format: {weights_format}")

    return ModelCheckpointManifest(
        schema=MODEL_CHECKPOINT_SCHEMA,
        contract_version=SUPPORTED_CONTRACTS_RELEASE,
        model_id=_expect_str(record, "model_id"),
        model_family=_expect_str(record, "model_family"),
        created_at=_expect_str(record, "created_at"),
        input_contracts=tuple(input_contracts),
        output_contract=_expect_str(record, "output_contract"),
        weights_format=weights_format,
        weights_hash=_expect_str(record, "weights_hash"),
        size_bytes=size_bytes,
        training_data_manifest=_expect_str(record, "training_data_manifest"),
        calibration_report=_expect_str(record, "calibration_report"),
        feature_hash=_expect_optional_str(record, "feature_hash"),
        quantization=_expect_optional_str(record, "quantization"),
        parameter_count=_expect_optional_positive_int(record, "parameter_count"),
        architecture=_expect_optional_str(record, "architecture"),
        legal_action_mask_required=_expect_optional_bool(
            record, "legal_action_mask_required"
        ),
        recommended_engine_order=_expect_optional_str_tuple(
            record, "recommended_engine_order"
        ),
        notes=_expect_optional_str(record, "notes"),
    )


def _load_jsonl(path: str | Path, parser: Any, label: str) -> list[Any]:
    rows: list[Any] = []
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
                rows.append(parser(record))
            except ValueError as exc:
                raise ValueError(
                    f"invalid {label} row on line {line_number}: {exc}"
                ) from exc
    return rows


def load_observations_jsonl(path: str | Path) -> list[ObservationRow]:
    """Load `observation.v1` JSONL rows."""
    return _load_jsonl(path, parse_observation_row, "observation")


def load_game_results_jsonl(path: str | Path) -> list[GameResultRow]:
    """Load `game-result.v1` JSONL rows."""
    return _load_jsonl(path, parse_game_result_row, "game-result")


def load_model_checkpoint_manifest(path: str | Path) -> ModelCheckpointManifest:
    """Load a `model-checkpoint.v1` manifest JSON file."""
    with Path(path).open(encoding="utf-8") as handle:
        record = json.load(handle)
    if not isinstance(record, dict):
        raise ValueError("model checkpoint manifest must be a JSON object")
    return parse_model_checkpoint_manifest(record)
