"""Draft `search-summary.v1-draft` JSONL exporter.

Mirrors `quantik-core-rust`'s `bench::contracts::search_summary_row`
field-for-field. This is a DRAFT surface: the schema label is
`search-summary.v1-draft` and the stable `search-summary.v1` label MUST NOT be
emitted until the contract is registered in quantik-core-contracts.
"""

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import List, Optional

from .artifact_data import _legal_action_mask
from .core import State
from .game_utils import count_total_pieces, get_current_player_from_counts
from .search_telemetry import SearchTelemetry

# Draft, unstable schema for per-search-call telemetry rows. NOT added to
# contracts.SUPPORTED_CONTRACTS -- this is a draft surface, not a stabilized
# cross-repository contract.
SEARCH_SUMMARY_DRAFT_SCHEMA = "search-summary.v1-draft"
SEARCH_SUMMARY_CONTRACT_VERSION = "1.1.0"

try:
    _ENGINE_VERSION = version("quantik-core")
except PackageNotFoundError:  # pragma: no cover
    _ENGINE_VERSION = "0+editable"


@dataclass
class SearchSummaryRunConfig:
    """Engine run configuration echoed into a row; None fields map to null."""

    config_label: str
    search_depth: Optional[int] = None
    rollouts: Optional[int] = None
    beam_width: Optional[int] = None
    node_budget: Optional[int] = None
    time_budget_ms: Optional[int] = None


def search_summary_row(
    row_id: int,
    run_id: str,
    qfen: str,
    telemetry: SearchTelemetry,
    run_config: SearchSummaryRunConfig,
) -> Optional[dict]:
    """Build one draft row, or None when root identity was not preserved.

    Skips (returns None) rows whose telemetry has
    root_identity_preserved == False -- a legitimate skip, not an error.
    Raises ValueError for an action_index outside [0, 64), matching the Rust
    exporter's Err. Unlike Rust (whose action_index is an unsigned u8, so a
    ``>= 64`` check suffices), Python's action_index is a signed int: a
    negative value would silently index policy_visits/root_q_values from the
    end and corrupt the row, so the lower bound must be checked too.
    """
    if not telemetry.root_identity_preserved:
        return None

    state = State.from_qfen(qfen)
    bb = state.bb
    p0, p1 = count_total_pieces(bb)
    side_to_move = get_current_player_from_counts(p0, p1)

    policy_visits: List[int] = [0] * 64
    root_q_values: List[Optional[float]] = [None] * 64
    for stat in telemetry.root_moves:
        idx = stat.action_index
        if idx < 0 or idx >= 64:
            raise ValueError(
                f"root move action_index {idx} out of range (must be in [0, 64))"
            )
        policy_visits[idx] = stat.policy_mass
        if stat.q_value is not None:
            root_q_values[idx] = stat.q_value

    principal_variation = [
        mv.shape * 16 + mv.position for mv in telemetry.principal_variation
    ]

    return {
        "schema": SEARCH_SUMMARY_DRAFT_SCHEMA,
        "contract_version": SEARCH_SUMMARY_CONTRACT_VERSION,
        "run_id": run_id,
        "row_id": row_id,
        "position_key": state.canonical_key().hex(),
        "ply": p0 + p1,
        "side_to_move": side_to_move,
        "bitboards": list(bb),
        "qfen": qfen,
        "legal_action_mask": _legal_action_mask(bb),
        "engine_kind": telemetry.engine_kind.as_str(),
        "engine_version": _ENGINE_VERSION,
        "engine_checkpoint": None,
        "config_label": run_config.config_label,
        "search_depth": run_config.search_depth,
        "rollouts": run_config.rollouts,
        "beam_width": run_config.beam_width,
        "node_budget": run_config.node_budget,
        "time_budget_ms": run_config.time_budget_ms,
        "seed": telemetry.seed,
        "root_value": telemetry.root_value,
        "policy_mass_kind": telemetry.policy_mass_kind.as_str(),
        "policy_visits": policy_visits,
        "root_q_values": root_q_values,
        "principal_variation": principal_variation,
        "expanded_nodes": telemetry.counters.expanded_nodes,
        "generated_nodes": telemetry.counters.generated_nodes,
        "transposition_hits": telemetry.counters.transposition_hits,
        "canonical_dedup_hits": telemetry.counters.canonical_dedup_hits,
        "terminal_hits": telemetry.counters.terminal_hits,
        "tablebase_hits": telemetry.counters.tablebase_hits,
        "elapsed_ms": telemetry.elapsed_ms,
        "depth_reached": telemetry.depth_reached,
    }
