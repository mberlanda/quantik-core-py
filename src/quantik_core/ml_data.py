"""ML data helpers for cross-language self-play artifacts.

The companion Rust crate owns high-throughput self-play export. This module is
Python's reference reader for those JSONL rows and the first layer used by later
training code.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from .commons import Bitboard
from .contracts import SUPPORTED_CONTRACTS, SUPPORTED_CONTRACTS_RELEASE
from .move import generate_legal_moves_list
from .qfen import bb_from_qfen
from .state_validator import ValidationResult, validate_game_state

ACTION_COUNT = 64
BOARD_SIZE = 4
PLAYER_SHAPE_CHANNELS = 8
SIDE_TO_MOVE_CHANNEL = 8
TENSOR_CHANNELS = 9
SELFPLAY_SCHEMA = SUPPORTED_CONTRACTS["selfplay"]


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
    distribution = np.zeros(ACTION_COUNT, dtype=np.float32)
    total_visits = 0
    for visit in policy:
        if visit.visits <= 0:
            raise ValueError("policy visits must be positive")
        distribution[visit.action_index] += visit.visits
        total_visits += visit.visits
    if total_visits <= 0:
        raise ValueError("policy must contain at least one visit")
    distribution /= float(total_visits)
    return distribution
