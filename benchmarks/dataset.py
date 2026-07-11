"""Shared, versioned position dataset for cross-engine benchmarks."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Dict, Optional, Tuple

from quantik_core import State, apply_move
from quantik_core.game_utils import (
    count_total_pieces,
    get_current_player_from_counts,
    has_winning_line,
)
from quantik_core.move import generate_legal_moves_list

SCHEMA_VERSION = 1
GENERATOR = "benchmarks.dataset.generate/v1"

PHASES: Dict[str, Tuple[int, int]] = {
    "opening": (0, 4),
    "early_mid": (5, 7),
    "late_mid": (8, 11),
    "endgame": (12, 16),
}


def phase_of(pieces: int) -> str:
    """Return the phase bucket for a piece count."""
    for phase, (lo, hi) in PHASES.items():
        if lo <= pieces <= hi:
            return phase
    raise ValueError(f"no benchmark phase for {pieces} pieces")


def _random_position(rng: random.Random, plies: int) -> Optional[Tuple[int, ...]]:
    bb = State.empty().bb

    for _ in range(plies):
        moves = generate_legal_moves_list(bb)
        if not moves:
            return None
        bb = apply_move(bb, rng.choice(moves))  # type: ignore[assignment]
        if has_winning_line(bb):
            return None

    if not generate_legal_moves_list(bb):
        return None
    return bb


def _position_payload(position_id: int, bb: Tuple[int, ...], phase: str) -> dict:
    p0_pieces, p1_pieces = count_total_pieces(bb)
    pieces = p0_pieces + p1_pieces

    return {
        "id": f"p{position_id:04d}",
        "qfen": State(bb).to_qfen(),
        "phase": phase,
        "pieces": pieces,
        "side_to_move": get_current_player_from_counts(p0_pieces, p1_pieces),
        "legal_moves": len(generate_legal_moves_list(bb)),
        "reference": None,
    }


def generate(requested: Dict[str, int], seed: int) -> dict:
    """Generate a deterministic benchmark dataset for requested phase counts."""
    unknown = set(requested) - set(PHASES)
    if unknown:
        raise ValueError(f"unknown phase(s): {sorted(unknown)}")

    rng = random.Random(seed)
    seen: set[bytes] = set()
    positions: list[dict] = []

    for phase, (lo, hi) in PHASES.items():
        want = requested.get(phase, 0)
        found = 0
        attempts = 0
        max_attempts = want * 500

        while found < want and attempts < max_attempts:
            attempts += 1
            target_plies = rng.randint(lo, min(hi, 15))
            bb = _random_position(rng, target_plies)
            if bb is None:
                continue

            key = State(bb).canonical_key()
            if key in seen:
                continue

            seen.add(key)
            positions.append(_position_payload(len(positions), bb, phase))
            found += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "seed": seed,
        "requested": dict(requested),
        "positions": positions,
    }


def checksum(payload: dict) -> str:
    """Return sha256 over canonical JSON excluding the checksum field."""
    stripped = {key: value for key, value in payload.items() if key != "checksum"}
    blob = json.dumps(stripped, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def save(payload: dict, path) -> str:
    """Write a checksum-bearing JSON dataset artifact and return its checksum."""
    output = dict(payload)
    output["checksum"] = checksum(output)
    Path(path).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return output["checksum"]


def load(path) -> dict:
    """Load a dataset artifact and verify its checksum."""
    payload = json.loads(Path(path).read_text())
    expected = payload.get("checksum")
    actual = checksum(payload)
    if expected != actual:
        raise ValueError(
            f"dataset checksum mismatch: expected {expected}, actual {actual}"
        )
    return payload
