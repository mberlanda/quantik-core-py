"""Produce normalized Quantik API portability reports."""

from __future__ import annotations

import argparse
import json
import struct
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Sequence, cast

from .commons import FLAG_CANON, VERSION, Bitboard, PlayerId
from .game_utils import WinStatus, check_game_winner
from .move import Move, generate_legal_moves_list, validate_move
from .qfen import bb_from_qfen, bb_to_qfen
from .state_validator import validate_game_state
from .symmetry import SymmetryHandler

REPORT_SCHEMA = "api-portability-report.v1"
FIXTURE_SCHEMA = "api-portability-fixtures.v1"
FIXTURE_PATH = Path("fixtures/api-portability/game-state-v1.json")
CONTRACT_KEYS = ("qfen", "bitboard", "action_index")


def _package_version() -> str:
    try:
        return version("quantik-core")
    except PackageNotFoundError:
        return "0+editable"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def _contracts_release(contracts_root: Path, manifest: dict[str, Any]) -> str:
    release = manifest.get("release_version")
    if isinstance(release, str):
        release = release.strip()
    if not isinstance(release, str) or not release:
        raise ValueError("contracts release_version must be a non-empty string")

    version_path = contracts_root / "VERSION"
    if not version_path.exists():
        raise ValueError(f"{version_path}: VERSION file is required")
    version_text = version_path.read_text(encoding="utf-8").strip()
    if not version_text:
        raise ValueError(f"{version_path}: VERSION must be non-empty")
    if version_text != release:
        raise ValueError(
            f"{version_path}: VERSION {version_text!r} does not match "
            f"contracts.json release_version {release!r}"
        )
    return release


def _contract_ids(manifest: dict[str, Any]) -> dict[str, str]:
    contracts = manifest.get("contracts")
    if not isinstance(contracts, dict):
        raise ValueError("contracts.json must contain a contracts object")

    ids: dict[str, str] = {}
    for key in CONTRACT_KEYS:
        contract = contracts.get(key)
        if not isinstance(contract, dict) or not isinstance(contract.get("id"), str):
            raise ValueError(f"contracts.json missing contract id for {key}")
        ids[key] = contract["id"]
    return ids


def _action_index(move: Move) -> int:
    return move.shape * 16 + move.position


def _legal_actions(bb: Bitboard) -> tuple[str, list[int]]:
    action_indices = sorted(
        _action_index(move) for move in generate_legal_moves_list(bb)
    )
    mask = 0
    for action_index in action_indices:
        mask |= 1 << action_index
    return f"0x{mask:016x}", action_indices


def _validate_fixture_metadata(
    contracts_root: Path, fixture: dict[str, Any], contracts_release: str
) -> None:
    fixture_path = contracts_root / FIXTURE_PATH
    if fixture.get("schema") != FIXTURE_SCHEMA:
        raise ValueError(f"{fixture_path}: schema must be {FIXTURE_SCHEMA}")
    if fixture.get("contract_version") != contracts_release:
        raise ValueError(
            f"{fixture_path}: contract_version must match {contracts_release}"
        )


def _winner_name(bb: Bitboard) -> str:
    winner = check_game_winner(bb)
    if winner == WinStatus.PLAYER_0_WINS:
        return "player0"
    if winner == WinStatus.PLAYER_1_WINS:
        return "player1"
    return "none"


def _terminal_winner(
    winner: str, side_to_move: PlayerId, legal_action_indices: list[int]
) -> tuple[bool, str]:
    if winner != "none":
        return True, winner
    if legal_action_indices:
        return False, "none"
    return True, "player1" if side_to_move == 0 else "player0"


def _fixture_int(case_move: dict[str, Any], key: str, upper_bound: int) -> int:
    value = case_move.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"move.{key} must be an integer")
    if value < 0 or value > upper_bound:
        raise ValueError(f"move.{key} must be between 0 and {upper_bound}")
    return value


def _move_report(
    case_move: dict[str, Any], bb: Bitboard, side_to_move: PlayerId
) -> dict[str, Any]:
    shape = _fixture_int(case_move, "shape", 3)
    position = _fixture_int(case_move, "position", 15)
    move = Move(player=side_to_move, shape=shape, position=position)
    validation = validate_move(bb, move)

    report: dict[str, Any] = {
        "shape": shape,
        "position": position,
        "action_index": _action_index(move),
        "is_legal": validation.is_valid,
    }
    if validation.is_valid:
        if validation.new_bb is None:
            raise ValueError("valid move did not return a new bitboard")
        report["after_qfen"] = bb_to_qfen(cast(Bitboard, validation.new_bb))
    else:
        report["after_qfen"] = None
    return report


def _case_report(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case.get("case_id")
    qfen = case.get("qfen")
    case_move = case.get("move")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("game_state_case.case_id must be a non-empty string")
    if not isinstance(qfen, str):
        raise ValueError(f"{case_id}: qfen must be a string")
    if not isinstance(case_move, dict):
        raise ValueError(f"{case_id}: move must be an object")

    try:
        bb = bb_from_qfen(qfen, validate=False)
    except ValueError as exc:
        raise ValueError(f"{case_id}: qfen parse failed: {exc}") from exc
    normalized_qfen = bb_to_qfen(bb)
    side_to_move, validation_result = validate_game_state(bb)
    if side_to_move is None:
        raise ValueError(f"{case_id}: invalid game state {validation_result.name}")

    canonical_bb, _ = SymmetryHandler.find_canonical_form(bb)
    legal_action_mask, legal_action_indices = _legal_actions(bb)
    winner = _winner_name(bb)
    terminal, winner = _terminal_winner(winner, side_to_move, legal_action_indices)
    canonical_key = bytes([VERSION, FLAG_CANON]) + struct.pack("<8H", *canonical_bb)

    return {
        "case_id": case_id,
        "qfen": normalized_qfen,
        "bitboards": list(bb),
        "side_to_move": side_to_move,
        "canonical_qfen": bb_to_qfen(canonical_bb),
        "canonical_key": canonical_key.hex(),
        "orbit_size": SymmetryHandler.count_orbit_size(bb),
        "legal_action_mask": legal_action_mask,
        "legal_action_indices": legal_action_indices,
        "terminal": terminal,
        "winner": winner,
        "move": _move_report(case_move, bb, side_to_move),
    }


def build_report(contracts_root: Path) -> dict[str, Any]:
    manifest = _load_json(contracts_root / "contracts.json")
    fixture = _load_json(contracts_root / FIXTURE_PATH)
    contracts_release = _contracts_release(contracts_root, manifest)
    _validate_fixture_metadata(contracts_root, fixture, contracts_release)
    cases = fixture.get("game_state_cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(
            f"{contracts_root / FIXTURE_PATH}: game_state_cases must be a non-empty list"
        )
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(
                f"{contracts_root / FIXTURE_PATH}: game_state_cases[{index}] "
                "must be an object"
            )

    return {
        "schema": REPORT_SCHEMA,
        "contracts_release": contracts_release,
        "implementation": {
            "language": "python",
            "package": "quantik-core",
            "version": _package_version(),
        },
        "contract_ids": _contract_ids(manifest),
        "cases": sorted(
            (_case_report(case) for case in cases),
            key=lambda item: item["case_id"],
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    report = build_report(args.contracts_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
