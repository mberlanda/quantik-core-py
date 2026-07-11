# Beam Search Implementation

This document describes the parametrizable beam search engine in Quantik Core: a memory-bounded search mode that guarantees reaching true terminal game states, complementing the statistical sampling of MCTS.

## Overview

`MCTSEngine` samples the game tree stochastically and its random playouts stop at `max_depth` without guaranteeing terminal resolution. Exhaustive expansion of the full game tree is infeasible (Quantik has ~2.2 × 10^12 legal move sequences). `BeamSearchEngine` fills the gap: a level-by-level frontier search that always descends to true terminal states (win, loss by blocked player) while bounding memory to a configurable width.

### Algorithm Phases

Per depth level (players strictly alternate, so every node at a given depth shares the same side to move):

1. **Expand**: generate legal moves for each frontier entry and apply them. A frontier state with no legal moves is itself terminal (the player to move loses).
2. **Classify**: any child that completes a winning line is recorded immediately as a terminal leaf and inserted into the tree — regardless of the beam width.
3. **Deduplicate**: remaining non-terminal candidates are deduplicated per depth by `State.canonical_key()` (symmetry-aware; first path encountered wins).
4. **Score**: each surviving candidate is evaluated and ranked **mover-relative** — from the perspective of the player who just moved (`score = value` for a P0 move, `-value` for a P1 move) — so the beam stays adversarially sensible at every level instead of optimizing one fixed player throughout.
5. **Prune**: only the top `beam_width` candidates survive (stable ordering, so seeded runs are deterministic); pruned candidates never allocate a tree node.
6. **Insert**: survivors are added to the shared `CompactGameTree` via `add_child_node` and become the next depth's frontier.

Search stops when the frontier empties (every line resolved to a terminal) or `max_depth` is reached.

## Quick Start

```python
from quantik_core import State
from quantik_core.beam_search import BeamSearchEngine, BeamSearchConfig

config = BeamSearchConfig(beam_width=8, max_depth=16, random_seed=42)
engine = BeamSearchEngine(config)

state = State.from_qfen("..../..../..../....")
result = engine.search(state)

print(f"Reached terminal: {result.reached_terminal}")
print(f"Best line: {result.best_leaf.moves}")
print(f"Value (P0 perspective): {result.best_leaf.value}")
```

## Configuration

### BeamSearchConfig Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `beam_width` | int | 64 | Frontier nodes kept per depth (>= 1) |
| `max_depth` | int | 16 | Plies from root; 16 = full Quantik game (1-16) |
| `rollouts_per_candidate` | int | 8 | Rollout budget for the built-in evaluator (>= 1) |
| `random_seed` | int\|None | None | Seeds a **private** `random.Random` — the global RNG is never touched |
| `evaluator` | `Callable[[State], float]`\|None | None | Custom evaluator; falls back to random-rollout scoring when omitted |
| `initial_tree_capacity` | int | 4096 | Initial `CompactGameTree` node capacity |
| `beam_schedule` | `Sequence[int]`\|None | None | Depth-dependent beam width (see Tuning below); `None` uses the flat `beam_width` everywhere |
| `rollout_schedule` | `Sequence[int]`\|None | None | Depth-dependent rollout budget for the **built-in** evaluator only (custom evaluators ignore it); same indexing semantics as `beam_schedule`; `None` uses the flat `rollouts_per_candidate` everywhere |
| `time_limit_s` | float\|None | None | Optional wall-clock budget in seconds for `search()`; checked between depth levels (depth 1 always completes), so a wide level can overshoot the cap. `None` keeps depth/width as the only stop conditions |

Invalid values (`beam_width < 1`, `max_depth` outside `1..16`, `rollouts_per_candidate < 1`, an empty or non-positive `beam_schedule` or `rollout_schedule`, or `time_limit_s <= 0`) raise `ValueError` from `BeamSearchEngine.__init__`.

### Evaluator Contract

`evaluator(state) -> float` returns a value in `[-1, 1]` from **player 0's perspective**, matching `MCTSEngine`'s convention. Values outside that range are clamped. When omitted, the engine uses the mean of `rollouts_per_candidate` uniform random playouts, each rolled out to a true terminal — a Quantik playout never exceeds 16 plies, so no depth-cutoff heuristic is needed.

### Tuning: Depth-Dependent Beam Width

Quantik's canonical state space is tiny early and explodes later — `UNIQUE_CANONICAL_STATES_PER_DEPTH` (from `GAME_TREE_ANALYSIS.md`) gives 3 / 51 / 726 / 10,946 unique canonical states at depths 1-4. A flat `beam_width` has to pick one number for every depth; `beam_schedule` lets it grow with the game tree instead:

```python
from quantik_core.beam_search import BeamSearchConfig, UNIQUE_CANONICAL_STATES_PER_DEPTH

# Exhaustive through depth 3 (every legal line kept), then guided sampling.
schedule = [UNIQUE_CANONICAL_STATES_PER_DEPTH[d] for d in (1, 2, 3)] + [64]
config = BeamSearchConfig(beam_schedule=schedule, max_depth=16)
```

Width at depth `d` resolves to `beam_schedule[min(d - 1, len(beam_schedule) - 1)]`, so the schedule's last entry extends to every deeper level. A single-entry schedule (e.g. `beam_schedule=[8]`) is exactly equivalent to `beam_width=8`.

**Cost model**: evaluations at level `d + 1` are proportional to `width(d) x branching_factor x rollouts(d + 1)` (or a single evaluator call each, if using a custom evaluator). An exhaustive prefix is cheap while the canonical count is small (3, then 51) but grows fast — by depth 4 (10,946 unique states) exhaustive search is usually no longer worth it; that's the point at which a schedule typically switches to a fixed guided width.

**Wide-and-cheap early, narrow-and-precise late**: on a level where the width meets or exceeds the canonical state count, *nothing is pruned*, so evaluation precision there is wasted budget. `rollout_schedule` pairs with `beam_schedule` to spend playouts only where pruning decisions actually happen:

```python
config = BeamSearchConfig(
    beam_schedule=[3, 51, 726, 64],   # exhaustive plies 1-3, width-64 tail
    rollout_schedule=[1, 1, 1, 8],    # 1 playout on exhaustive levels, 8 after
)
```

The exact playout spend is observable as `stats["rollouts"]` (0 when a custom evaluator is used).

See `examples/beam_search_demo.py` (DEMO 3) for a worked comparison of a scheduled vs. flat-width run.

## Result

```python
@dataclass
class BeamLeaf:
    moves: Tuple[Move, ...]   # principal variation from the root
    value: float              # P0 perspective; +/-1.0 for terminal leaves
    depth: int
    is_terminal: bool
    multiplicity: int = 1      # raw move sequences this leaf represents

@dataclass
class BeamSearchResult:
    best_leaf: Optional[BeamLeaf]      # best for the ROOT player to move
    terminal_leaves: List[BeamLeaf]    # all terminals discovered, best first
    reached_terminal: bool
    max_depth_reached: int
    stats: Dict[str, int]              # candidates_generated, candidates_deduped,
                                        # nodes_inserted, nodes_pruned,
                                        # evaluations, memory_usage
    root_player: int = 0               # player to move at the root
    frontier_leaves: List[BeamLeaf] = field(default_factory=list)
    # ^ non-terminal leaves still live at max_depth_reached; empty once
    #   reached_terminal is True
```

`best_leaf` ranks every collected leaf — terminals plus, if the search hit `max_depth` with a live frontier, the final frontier entries — from the **root player's** fixed perspective (unlike the mover-relative pruning score used level by level). `search()` raises `ValueError` if the root state is already terminal or has no legal moves.

### "Moves Till Win"

When `best_leaf.is_terminal` is `True`, `best_leaf.moves` *is* the full principal variation to a proven win (or loss) — no further search needed:

```python
if result.best_leaf.is_terminal:
    print(f"Forced result in {len(result.best_leaf.moves)} plies: {result.best_leaf.moves}")
```

## Ranked Root Moves

For midgame positions with several reasonable options, `BeamSearchResult.ranked_root_moves(top_k=None)` aggregates every collected leaf (`terminal_leaves` plus `frontier_leaves`) by its first move from the root and summarizes each option:

```python
result = engine.search(state)
for entry in result.ranked_root_moves(top_k=5):
    print(entry.move, entry.best_value, entry.win_probability, entry.leaf_count)
```

Each `RankedRootMove` has:

| Field | Description |
|-------|-------------|
| `move` | The first move from the root |
| `best_value` | Max leaf value reached via this move (root-player perspective, `[-1, 1]`) |
| `mean_value` | **Multiplicity-weighted** mean leaf value via this move (root-player perspective) |
| `win_probability` | Heuristic rescaling `(mean_value + 1) / 2`, in `[0, 1]` |
| `leaf_count` | Number of collected leaves supporting this move (unweighted) |
| `total_multiplicity` | Sum of `multiplicity` over supporting leaves — see Symmetry Multiplicity below |
| `has_terminal_win` | A proven root-player-winning terminal exists via this move |

Entries are sorted by `best_value`, then `mean_value`, then `leaf_count` (all descending), with a deterministic tiebreak on the move itself.

**Important caveat**: these are beam-sampled statistics over whichever leaves this particular run happened to discover and keep — not a minimax-proven guarantee. A move can have `best_value == 1.0` (a winning line exists via it) alongside a low `win_probability` if most of the *other* leaves discovered via that move were mediocre; `win_probability` is a heuristic rescaling of `mean_value`, not a calibrated probability.

## Symmetry Multiplicity

Canonical deduplication (algorithm step 3) collapses whole symmetry orbits — rotations, reflections, and shape/color permutations — down to one representative per depth. That's essential for the memory bound, but it also means a naive leaf count under-represents how much of the raw game tree a move actually covers: a corner-adjacent move might stand in for 16 raw move sequences while an edge move stands in for 32, yet both count as "1 leaf" without multiplicity tracking.

`BeamLeaf.multiplicity` restores that mass via **path-count accumulation**, not orbit-size math: the root starts at multiplicity 1, and every raw legal move carries its parent's multiplicity forward — accumulating (summing) whenever multiple raw moves collapse onto the same canonical child at a given depth. Terminal leaves and tree nodes (`CompactGameTreeNode.multiplicity`, via `add_child_node`'s existing additive transposition-merge) both get their share of this weight.

```python
from quantik_core.beam_search import UNIQUE_CANONICAL_STATES_PER_DEPTH

config = BeamSearchConfig(beam_schedule=[3], max_depth=1, evaluator=lambda s: 0.0)
result = BeamSearchEngine(config).search(State.from_qfen("..../..../..../...."))

multiplicities = sorted(leaf.multiplicity for leaf in result.frontier_leaves)
assert multiplicities == [16, 16, 32]  # corner/center orbits (4 pos x 4 shapes)
assert sum(multiplicities) == 64        #  and the edge orbit (8 pos x 4 shapes)
```

This accounting is **exact when the beam was exhaustive at that depth** (e.g. a `beam_schedule` prefix matching `UNIQUE_CANONICAL_STATES_PER_DEPTH`) — the multiplicities then sum to the depth's true total legal-move count. Otherwise it's a **lower bound**: mass belonging to any canonical candidate that got pruned before its multiplicity could be counted is simply lost, not redistributed.

Multiplicity is statistics only — it never influences scoring or pruning, which remain strictly value-based.

## Memory Model

Only surviving candidates allocate a tree node, so growth is bounded by `beam_width x depth` non-terminal nodes plus however many terminal leaves were discovered along the way — versus the unbounded growth of exhaustive expansion. Each node is the same 64-byte `CompactGameTreeNode` used by MCTS. `get_statistics()` mirrors `MCTSEngine.get_statistics()`, delegating to `tree.memory_usage()` and `tree.get_stats()`.

## Sharing a Tree with MCTS

`BeamSearchEngine` accepts an existing `CompactGameTree` (e.g. `mcts_engine.tree`) so both engines can enrich the same transposition structure:

```python
from quantik_core.mcts import MCTSEngine, MCTSConfig
from quantik_core.beam_search import BeamSearchEngine, BeamSearchConfig

mcts_engine = MCTSEngine(MCTSConfig())
beam_engine = BeamSearchEngine(BeamSearchConfig(beam_width=8), tree=mcts_engine.tree)
```

**Caveat**: `CompactGameTree.create_root_node` hardcodes the root's `player_turn` to 0 and alternates from there. When sharing a tree, root the beam search at a position where **player 0 is to move** — otherwise every node's `player_turn` is inverted, which would corrupt MCTS's UCB calculation if it later resumes on the same tree.

Also note that `CompactGameTree`'s own transposition key is the literal `State.pack()` bytes (its `canonical_state_data` field is *not* symmetry-reduced), while beam search's own deduplication (step 3 above) uses the coarser `State.canonical_key()`. The shared tree therefore isn't itself symmetry-reduced — beam search just feeds it canonically-distinct representatives per depth.

## Comparison with MCTS

| Aspect | Beam Search | MCTS |
|--------|-------------|------|
| **Terminal guarantee** | Always reaches true terminals (within `max_depth`) | Not guaranteed; playouts stop at `max_depth` |
| **Exploration** | Deterministic frontier expansion, mover-relative pruning | Stochastic UCB1 sampling |
| **Memory** | O(beam_width x depth) | Grows with iteration count |
| **Best for** | Exhaustive-ish tactical verification under a memory budget | General-purpose anytime search |

## Examples

See `examples/beam_search_demo.py` for complete working examples:

- Full-depth search from the empty board reaching a true terminal
- Tactical (immediate win) position analysis, replaying the full winning line
- Beam width sweep demonstrating the memory bound, plus a scheduled vs. flat-width comparison
- Pluggable custom evaluator
- Ranked root move statistics from a midgame position
