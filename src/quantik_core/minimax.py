"""
Classical alpha-beta minimax (negamax formulation) for Quantik.

Searches the exact game tree using `has_winning_line` for terminal
detection and falls back to `quantik_core.evaluation.evaluate` once
`max_depth` is exhausted. With `max_depth=16` (`MinimaxEngine.solve`) the
search always reaches true terminal states -- no Quantik game exceeds 16
plies -- so it acts as an exact solver, not just a heuristic engine.

Negamax sign convention: `_negamax` returns the value of a position from
the perspective of the side to move *at that node*. A caller negates a
child's value to fold it back into its own perspective
(`-self._negamax(child, depth - 1, -beta, -alpha, ply + 1)`).

Terminal values use `win - ply` (not a flat `win`) so that a forced mate
found sooner scores strictly higher than one found deeper -- this both
matches human intuition ("prefer the faster win") and is required for
alpha-beta pruning to behave sanely when comparing mates at different
plies.

`State.canonical_key()` collapses the D4 x S4 = 192 board symmetries
*without* swapping colors, so the negamax value (which is always relative
to the side to move, not a fixed color) is safe to cache/dedup by that
key. Only the value/bound is ever cached -- never the move -- since the
key alone doesn't preserve which concrete move produced a given child.

Sibling dedup (`dedup_children`) and the transposition table
(`use_transposition_table`) both key off `canonical_key()`, which itself
costs several hundred microseconds (it searches all 192 symmetries).
Dedup is folded into the base search rather than deferred, because
without it even modest depths blow up combinatorially in Quantik's wide
early game (dozens of legal moves per ply) and `use_alpha_beta=False`
(required by `test_alpha_beta_equals_plain_minimax`) has no pruning to
fall back on. Where dedup and the TT are both active on the same call,
the child key dedup already computed is threaded into the recursive call
so the TT probe does not recompute it.
"""

import dataclasses
import random
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

from .commons import Bitboard
from .core import State
from .evaluation import EvalConfig, evaluate
from .game_utils import count_total_pieces, get_current_player_from_counts
from .game_utils import has_winning_line
from .move import Move, apply_move, generate_legal_moves_list


class Bound(IntEnum):
    """Transposition-table bound kind for a stored negamax value."""

    EXACT = 0
    LOWER = 1
    UPPER = 2


@dataclass
class MinimaxConfig:
    """Configuration for `MinimaxEngine`."""

    max_depth: int = 16
    time_limit_s: Optional[float] = None
    use_alpha_beta: bool = True
    use_transposition_table: bool = True
    dedup_children: bool = True
    eval_config: EvalConfig = field(default_factory=EvalConfig)
    random_seed: Optional[int] = None


@dataclass
class MinimaxResult:
    """Result of a `MinimaxEngine.search` (or `.solve`) call."""

    best_move: Move
    score: float
    depth_reached: int
    nodes: int
    pv: List[Move]
    elapsed: float


# Transposition-table entry: (depth searched below this node, value from the
# side-to-move-at-this-node's perspective, bound kind).
_TTEntry = Tuple[int, float, Bound]

# A legal move paired with the bitboard it produces and -- when dedup
# computed one -- that child's canonical key, so a subsequent TT probe on
# the same state doesn't recompute the (expensive) key.
_ChildEntry = Tuple[Move, Bitboard, Optional[bytes]]


class _TimeUp(Exception):
    """Internal signal that the configured time limit was reached."""


def _side_to_move(bb: Bitboard) -> int:
    """Determine the side to move from piece counts on `bb`."""
    p0_total, p1_total = count_total_pieces(bb)
    return get_current_player_from_counts(p0_total, p1_total)


def _move_sort_key(move: Move) -> Tuple[int, int]:
    """Deterministic tie-break ordering: lowest `(shape, position)` first."""
    return (move.shape, move.position)


def _children(bb: Bitboard, moves: List[Move], dedup: bool) -> List[_ChildEntry]:
    """Apply each move in `moves` (assumed pre-sorted), pairing it with the
    resulting bitboard and (when `dedup`) that child's canonical key.

    When `dedup`, siblings whose resulting state shares a
    `State.canonical_key()` -- i.e. is reachable from another sibling's
    result by one of the 192 D4 x S4 board symmetries -- collapse onto a
    single representative (the first survivor in `moves`' order, so the
    lowest `(shape, position)` tie-break is preserved).
    """
    if not dedup:
        children_no_dedup: List[_ChildEntry] = []
        for move in moves:
            child_bb: Bitboard = apply_move(bb, move)  # type: ignore[assignment]
            children_no_dedup.append((move, child_bb, None))
        return children_no_dedup

    seen: Dict[bytes, None] = {}
    children: List[_ChildEntry] = []
    for move in moves:
        child_bb = apply_move(bb, move)  # type: ignore[assignment]
        key = State(child_bb).canonical_key()
        if key in seen:
            continue
        seen[key] = None
        children.append((move, child_bb, key))
    return children


class MinimaxEngine:
    """Alpha-beta negamax search engine over the exact Quantik game tree."""

    def __init__(self, config: MinimaxConfig) -> None:
        self.config = config
        self._tt: Dict[bytes, _TTEntry] = {}
        self._nodes = 0
        self._deadline: Optional[float] = None
        self._rng: Optional[random.Random] = (
            random.Random(config.random_seed)
            if config.random_seed is not None
            else None
        )
        self._pv_hint: List[Move] = []

    def solve(self, state: State) -> MinimaxResult:
        """Exact solve: `search` with `max_depth=16` and no time limit.

        Every Quantik game resolves (win or no-legal-moves) within 16
        plies, so a depth-16 search from any reachable position always
        terminates on true terminal nodes rather than the heuristic eval
        cutoff -- i.e. this is an exact solver, not just a deep search.

        Temporarily swaps in a `max_depth=16, time_limit_s=None` config and
        delegates to `self.search` (restoring the original config
        afterward) rather than constructing a second `MinimaxEngine` --
        `search` already resets all other per-call state (`_tt`, `_nodes`,
        `_pv_hint`, `_deadline`), so reusing `self` is equivalent and avoids
        an always-discarded extra engine allocation on every call.
        """
        original_config = self.config
        self.config = dataclasses.replace(
            original_config, max_depth=16, time_limit_s=None
        )
        try:
            return self.search(state)
        finally:
            self.config = original_config

    def search(self, state: State) -> MinimaxResult:
        """Iterative-deepening alpha-beta negamax search from `state`.

        Deepens from depth 1 to `config.max_depth` (or until
        `config.time_limit_s` elapses), seeding each iteration's root move
        order with the previous iteration's principal variation. Returns
        the deepest iteration that completed before any time limit; if the
        very first (depth-1) iteration is cut off, that partial result is
        returned rather than raising.
        """
        start = time.monotonic()
        self._nodes = 0
        self._tt = {}
        self._pv_hint = []
        self._deadline = (
            start + self.config.time_limit_s
            if self.config.time_limit_s is not None
            else None
        )

        bb = state.bb
        root_moves = generate_legal_moves_list(bb)
        if not root_moves:
            raise ValueError("Cannot search from a state with no legal moves.")

        result: Optional[MinimaxResult] = None
        for depth in range(1, self.config.max_depth + 1):
            try:
                score, best_move, pv = self._search_root(bb, root_moves, depth)
            except _TimeUp:
                break
            self._pv_hint = pv
            result = MinimaxResult(
                best_move=best_move,
                score=score,
                depth_reached=depth,
                nodes=self._nodes,
                pv=pv,
                elapsed=time.monotonic() - start,
            )
            if self._deadline is not None and time.monotonic() >= self._deadline:
                break

        assert result is not None  # the depth-1 iteration always runs to completion
        result.elapsed = time.monotonic() - start
        return result

    # ----- internals -----------------------------------------------------

    def _order_root_moves(self, moves: List[Move]) -> List[Move]:
        """Sort root moves by the deterministic tie-break, then float the
        prior iteration's PV move (if any) to the front for better
        alpha-beta cutoffs on the next, deeper iteration.
        """
        ordered = sorted(moves, key=_move_sort_key)
        if self._pv_hint:
            pv_move = self._pv_hint[0]
            for i, move in enumerate(ordered):
                if move == pv_move:
                    ordered.insert(0, ordered.pop(i))
                    break
        return ordered

    def _search_root(
        self, bb: Bitboard, moves: List[Move], depth: int
    ) -> Tuple[float, Move, List[Move]]:
        """Search the root position to `depth`, returning `(score,
        best_move, pv)`.

        Every root child is searched with a FULL (-inf, +inf) window, so each
        returned value is EXACT rather than a fail-soft bound. This matters for
        the tie-break: if we narrowed `alpha` across siblings (as an internal
        node does), an inferior move searched after the current best could fail
        low and return an *upper bound* that happens to equal `best_value`,
        pollute the equal-value candidate set below, and -- with `random_seed`
        set -- be chosen, returning a suboptimal (even losing) move. The
        root-level pruning this forgoes is negligible (Quantik's root branching
        is small); each child's own subtree is still alpha-beta pruned inside
        `_negamax`.
        """
        ordered = self._order_root_moves(moves)
        children = _children(bb, ordered, self.config.dedup_children)

        best_value = float("-inf")
        scored: List[Tuple[Move, float, List[Move]]] = []

        for move, child_bb, child_key in children:
            child_pv: List[Move] = []
            value = -self._negamax(
                child_bb, depth - 1, float("-inf"), float("inf"), 1, child_pv, child_key
            )
            scored.append((move, value, child_pv))
            if value > best_value:
                best_value = value

        candidates = [(m, pv) for m, v, pv in scored if v == best_value]
        move, child_pv = (
            self._rng.choice(candidates) if self._rng is not None else candidates[0]
        )
        return best_value, move, [move, *child_pv]

    def _check_time(self) -> None:
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise _TimeUp()

    def _negamax(  # noqa: C901
        self,
        bb: Bitboard,
        depth: int,
        alpha: float,
        beta: float,
        ply: int,
        pv_out: List[Move],
        precomputed_key: Optional[bytes],
    ) -> float:
        """Negamax value of `bb` from the side-to-move's perspective.

        `pv_out` is filled in place with the principal variation from this
        node downward (empty if the node is terminal or a leaf).
        `precomputed_key` is this node's `canonical_key()` if the caller's
        sibling-dedup pass already computed it (else `None`, computed
        lazily here only if the TT is enabled).
        """
        self._nodes += 1
        if self._deadline is not None and (self._nodes & 0x3FF) == 0:
            self._check_time()

        win = self.config.eval_config.win

        if has_winning_line(bb):
            # The previous mover completed a line: the side to move here
            # has just lost. `ply` makes a sooner loss/win score more
            # extremely than a deeper one (shallower mates score higher).
            return -(win - ply)

        moves = generate_legal_moves_list(bb)
        if not moves:
            # No legal moves: the side to move also loses.
            return -(win - ply)

        if depth == 0:
            return evaluate(bb, _side_to_move(bb), self.config.eval_config)

        tt_key: Optional[bytes] = None
        orig_alpha = alpha
        orig_beta = beta
        if self.config.use_transposition_table:
            tt_key = (
                precomputed_key
                if precomputed_key is not None
                else State(bb).canonical_key()
            )
            entry = self._tt.get(tt_key)
            if entry is not None:
                stored_depth, stored_value, bound = entry
                if stored_depth >= depth:
                    if bound == Bound.EXACT:
                        return stored_value
                    if bound == Bound.LOWER:
                        alpha = max(alpha, stored_value)
                    elif bound == Bound.UPPER:
                        beta = min(beta, stored_value)
                    if alpha >= beta:
                        return stored_value

        ordered = sorted(moves, key=_move_sort_key)
        children = _children(bb, ordered, self.config.dedup_children)
        # Move ordering: try immediate winning replies first. A move that
        # completes a line makes this node a forced win (child is terminal,
        # value -(win-ply) negated to +(win-ply)), so exploring it first
        # yields the earliest possible beta cutoff. Stable so the
        # deterministic (shape, position) order is preserved among equals.
        children.sort(key=lambda c: 0 if has_winning_line(c[1]) else 1)

        best_value = float("-inf")
        best_move: Optional[Move] = None
        best_child_pv: List[Move] = []

        for move, child_bb, child_key in children:
            child_pv: List[Move] = []
            value = -self._negamax(
                child_bb, depth - 1, -beta, -alpha, ply + 1, child_pv, child_key
            )
            if value > best_value:
                best_value = value
                best_move = move
                best_child_pv = child_pv
            if self.config.use_alpha_beta:
                alpha = max(alpha, best_value)
                if alpha >= beta:
                    break

        if best_move is not None:
            pv_out.append(best_move)
            pv_out.extend(best_child_pv)

        if tt_key is not None:
            # Classify against the ORIGINAL (pre-TT-narrowing) window, not
            # the possibly-tightened `alpha`/`beta` used for this search --
            # otherwise a cutoff triggered only by an unrelated TT entry's
            # narrowed window could be misrecorded as a fail-high/fail-low
            # against a window this call never actually proved against.
            if best_value <= orig_alpha:
                bound = Bound.UPPER
            elif self.config.use_alpha_beta and best_value >= orig_beta:
                bound = Bound.LOWER
            else:
                bound = Bound.EXACT
            self._tt[tt_key] = (depth, best_value, bound)

        return best_value
