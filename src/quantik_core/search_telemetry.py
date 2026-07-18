"""Shared data types for search telemetry emitted by the MCTS, beam, and
minimax engines.

These definitions mirror `quantik-core-rust`'s
`crates/quantik-core/src/search_telemetry.rs` and are normative for both
stacks (see `docs/search-telemetry.md`).

Six event counters (`SearchEventCounters`):

- ``expanded_nodes``  -- a state's successor set was computed by the search.
- ``generated_nodes`` -- a successor state was constructed.
- ``transposition_hits`` -- a cached search result or subtree was reused via
  state-keyed lookup instead of being searched again.
- ``canonical_dedup_hits`` -- a generated state was merged with, or skipped in
  favor of, an already-present duplicate, without reusing any search result.
- ``terminal_hits`` -- a state was determined terminal during tree search.
  Rollout outcomes are excluded in every engine.
- ``tablebase_hits`` -- always 0 until an external probe artifact exists.

Value invariant: every ``root_value`` and ``RootMoveStat.q_value`` lies in
``[-1.0, 1.0]``, positive is good for the root player, and exact ``+/-1.0`` is
reserved for proven results. Unproven (sampled/heuristic) estimates are clamped
to ``[-UNPROVEN_VALUE_BOUND, UNPROVEN_VALUE_BOUND]`` via ``clamp_unproven``.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .move import Move

# Largest magnitude an UNPROVEN (sampled/heuristic) value may take. Exact
# +/-1.0 is reserved for proven results (terminal nodes, mates).
UNPROVEN_VALUE_BOUND: float = 1.0 - 1e-6


def clamp_unproven(v: float) -> float:
    """Clamp a sampled/heuristic estimate into the proven-exclusive range."""
    return max(-UNPROVEN_VALUE_BOUND, min(UNPROVEN_VALUE_BOUND, v))


class EngineKind(Enum):
    """Which engine produced a `SearchTelemetry`."""

    MCTS = "mcts"
    BEAM = "beam"
    MINIMAX = "minimax"

    def as_str(self) -> str:
        return self.value


class PolicyMassKind(Enum):
    """What `policy_mass` means for this engine's `RootMoveStat`s."""

    VISITS = "visits"
    MULTIPLICITY = "multiplicity"
    NONE = "none"

    def as_str(self) -> str:
        return self.value


@dataclass
class SearchEventCounters:
    """The six event counters; each field carries its normative definition
    from the module docstring."""

    expanded_nodes: int = 0
    generated_nodes: int = 0
    transposition_hits: int = 0
    canonical_dedup_hits: int = 0
    terminal_hits: int = 0
    tablebase_hits: int = 0


@dataclass
class RootMoveStat:
    """Per-root-move statistics."""

    mv: Move
    action_index: int  # shape * 16 + position (action-index.v1)
    policy_mass: int  # semantics per PolicyMassKind; 0 when NONE
    q_value: Optional[float]  # [-1, 1] root-player perspective; None if unknown

    @classmethod
    def from_move(
        cls, mv: Move, policy_mass: int, q_value: Optional[float]
    ) -> "RootMoveStat":
        return cls(
            mv=mv,
            action_index=mv.shape * 16 + mv.position,
            policy_mass=policy_mass,
            q_value=q_value,
        )


@dataclass
class SearchTelemetry:
    """One telemetry record for one completed root search."""

    engine_kind: EngineKind
    root_value: float
    policy_mass_kind: PolicyMassKind
    root_moves: List[RootMoveStat]
    root_identity_preserved: bool
    principal_variation: List[Move]
    counters: SearchEventCounters = field(default_factory=SearchEventCounters)
    elapsed_ms: int = 0
    depth_reached: int = 0
    seed: Optional[int] = None
