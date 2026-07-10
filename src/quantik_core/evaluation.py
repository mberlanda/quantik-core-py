"""
Fitted-linear handcrafted evaluation for non-terminal Quantik positions.

Scores a position as the dot product of a small, hand-designed feature
vector and a fitted weight vector (`EvalConfig.weights`). `features` is a
pure function of `(bb, player)`: it never mutates `bb` and always returns
a fresh `np.ndarray`. This module only scores positions; the search engine
and the weight-fitting pipeline that produce/consume `EvalConfig` live in
later tasks.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union, cast

import numpy as np

from .commons import Bitboard, PlayerId, WIN_MASKS
from .game_utils import count_pieces_by_shape, get_current_player_from_counts
from .move import generate_legal_moves_list

# Feature vector layout produced by `features()`, in order:
#   threat_own    -- live 3-lines `player` can complete this turn
#   threat_opp    -- live 3-lines the opponent can complete this turn
#   threat_shared -- signed count of live 3-lines BOTH sides can complete
#                    (a race for the same cell); sign follows side-to-move
#   mobility_diff -- `player`'s legal-move count minus the opponent's
#   build_two     -- signed count of live 2-occupied lines (1 shape short
#                    of a threat)
#   build_one     -- signed count of live 1-occupied lines
FEATURE_NAMES: List[str] = [
    "threat_own",
    "threat_opp",
    "threat_shared",
    "mobility_diff",
    "build_two",
    "build_one",
]

_SEEDED_WEIGHTS = (100.0, -100.0, 20.0, 3.0, 2.0, 0.0)

_SHAPES_PER_PLAYER = 4


@dataclass
class EvalConfig:
    """Weights for the fitted-linear evaluation and the terminal win bonus.

    `weights` follows `FEATURE_NAMES` order. `win` is not consumed by
    `evaluate` (which only scores non-terminal positions) — it is reserved
    for the search engine built on top of this module to score forced wins.
    """

    weights: np.ndarray = field(
        default_factory=lambda: np.array(_SEEDED_WEIGHTS, dtype=np.float64)
    )
    win: float = 10_000.0

    @classmethod
    def load(cls, path: Optional[Union[str, Path]] = None) -> "EvalConfig":
        """Load fitted weights from a JSON file, or return seeded defaults.

        The JSON format is the one written by `tuning/fit_weights.py`:
        `{"weights": [w0..w5], "win": <float>, ...}`. When `path` is `None`,
        the repo-root `tuning/weights.json` is used if it exists. Seeded
        defaults (`weights = [100, -100, 20, 3, 2, 0]`, `win = 10_000.0`) are
        returned when the target file is absent.

        Args:
            path: Optional path to a weights JSON file. If `None`, defaults to
                `<repo-root>/tuning/weights.json`.

        Returns:
            An `EvalConfig` with the loaded (or seeded default) weights.
        """
        if path is None:
            # src/quantik_core/evaluation.py -> parents[2] == repo root
            path = Path(__file__).resolve().parents[2] / "tuning" / "weights.json"
        else:
            path = Path(path)

        if not path.exists():
            return cls()

        data = json.loads(path.read_text())
        weights = np.asarray(data["weights"], dtype=np.float64)
        win = float(data.get("win", 10_000.0))
        return cls(weights=weights, win=win)


def _placement_is_legal(bb: Bitboard, player: int, shape: int, position: int) -> bool:
    """Whether `player` may place `shape` at the empty `position`.

    Mirrors `move._is_move_legal_on_position`'s win-line rule (a shape
    cannot be placed on a line where the opponent already holds the same
    shape) without the occupancy check, since callers only ask this for
    cells already known to be empty.
    """
    opponent_shape_bits = bb[(1 - player) * _SHAPES_PER_PLAYER + shape]
    position_mask = 1 << position
    for mask in WIN_MASKS:
        if (position_mask & mask) and (opponent_shape_bits & mask):
            return False
    return True


def count_legal_moves(bb: Bitboard, player: int) -> int:
    """Count `player`'s legal moves, 0 if it is not `player`'s turn.

    Args:
        bb: Bitboard to evaluate.
        player: Player ID (0 or 1) whose mobility to count.

    Returns:
        Number of legal moves for `player`. Quantik is strictly
        turn-alternating, so this is 0 whenever `player` is not the side
        to move.
    """
    return len(generate_legal_moves_list(bb, cast(PlayerId, player)))


def features(bb: Bitboard, player: int) -> np.ndarray:
    """Compute the 6-dimensional handcrafted feature vector for `bb`.

    Features are from `player`'s perspective (see `FEATURE_NAMES`), but
    `player` need not be the side to move: it is simply the perspective
    the caller wants scored.

    Args:
        bb: Bitboard to evaluate. Should be non-terminal.
        player: Player ID (0 or 1) whose perspective to score from.

    Returns:
        A fresh `np.ndarray` of shape `(6,)`, dtype `float64`, in
        `FEATURE_NAMES` order.
    """
    p0_counts, p1_counts = count_pieces_by_shape(bb)
    counts = (p0_counts, p1_counts)
    side_to_move = get_current_player_from_counts(sum(p0_counts), sum(p1_counts))
    sign = 1.0 if side_to_move == player else -1.0

    union_all = 0
    for bits in bb:
        union_all |= bits
    shape_unions = [bb[s] | bb[s + _SHAPES_PER_PLAYER] for s in range(4)]

    threat_own = 0.0
    threat_opp = 0.0
    threat_shared = 0.0
    build_two = 0.0
    build_one = 0.0

    for mask in WIN_MASKS:
        present = [s for s in range(4) if shape_unions[s] & mask]
        occupied = (union_all & mask).bit_count()

        if len(present) < occupied:
            continue  # dead line: some shape repeats, can never be 4-distinct

        if occupied == 3:
            missing_shape = next(s for s in range(4) if s not in present)
            empty_position = (mask & ~union_all).bit_length() - 1
            completable = [
                counts[side][missing_shape] < 2
                and _placement_is_legal(bb, side, missing_shape, empty_position)
                for side in (0, 1)
            ]
            if completable[player]:
                threat_own += 1.0
            if completable[1 - player]:
                threat_opp += 1.0
            if completable[0] and completable[1]:
                threat_shared += sign
        elif occupied == 2:
            build_two += sign
        elif occupied == 1:
            build_one += sign

    mobility_diff = float(
        count_legal_moves(bb, player) - count_legal_moves(bb, 1 - player)
    )

    return np.array(
        [threat_own, threat_opp, threat_shared, mobility_diff, build_two, build_one],
        dtype=np.float64,
    )


def evaluate(bb: Bitboard, player: int, cfg: Optional[EvalConfig] = None) -> float:
    """Score a non-terminal position as `cfg.weights @ features(bb, player)`.

    Args:
        bb: Bitboard to evaluate. Should be non-terminal.
        player: Player ID (0 or 1) whose perspective to score from.
        cfg: Weight configuration; defaults to the seeded weights when
            omitted (a fresh `EvalConfig()` is constructed per call, so no
            mutable default is shared across callers).

    Returns:
        The dot product of `cfg.weights` and `features(bb, player)`.
    """
    if cfg is None:
        cfg = EvalConfig()
    return float(cfg.weights @ features(bb, player))
