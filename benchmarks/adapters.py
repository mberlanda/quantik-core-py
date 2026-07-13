"""Uniform engine adapters with effective-work observations."""

from __future__ import annotations

import random
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from quantik_core import State
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine
from quantik_core.game_utils import count_total_pieces, has_winning_line
from quantik_core.mcts import MCTSConfig, MCTSEngine
from quantik_core.minimax import MinimaxConfig, MinimaxEngine
from quantik_core.move import Move, generate_legal_moves_list

from benchmarks.reference import move_key


def _label(name: str, **params) -> str:
    parts = ",".join(
        f"{key}={value}" for key, value in params.items() if value is not None
    )
    return f"{name}({parts})" if parts else name


def _snapshot(bb):
    if hasattr(bb, "to_tuple"):
        return bb.to_tuple()
    return tuple(bb)


@dataclass
class MoveObservation:
    """Effective work measured for one move selection."""

    engine: str
    config_label: str
    position_id: str
    move: str
    wall_time_s: float
    cpu_time_s: float
    root_legal_moves: int
    exact: bool
    seed: Optional[int] = None
    nodes: Optional[int] = None
    iterations: Optional[int] = None
    depth_reached: Optional[int] = None
    score: Optional[float] = None
    peak_memory_bytes: Optional[int] = None
    extra: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class EngineAdapter:
    """Base adapter that times, validates, and records an engine call."""

    name = "base"
    stochastic = False

    def __init__(self, config_label: str) -> None:
        self.config_label = config_label

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        raise NotImplementedError

    def select(
        self,
        bb,
        position_id: str,
        seed: Optional[int] = None,
        track_memory: bool = False,
    ) -> Tuple[Move, MoveObservation]:
        before = _snapshot(bb)
        legal = generate_legal_moves_list(before)
        if has_winning_line(before) or not legal:
            raise ValueError(f"{self.name}: cannot select from a terminal state")

        peak = None
        if track_memory:
            tracemalloc.start()

        wall0 = time.perf_counter()
        cpu0 = time.process_time()
        try:
            move, metrics = self._select(bb, seed)
        finally:
            if track_memory:
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

        wall_time_s = time.perf_counter() - wall0
        cpu_time_s = time.process_time() - cpu0

        if _snapshot(bb) != before:
            raise ValueError(f"{self.name}: engine mutated its input state")
        if move not in legal:
            raise ValueError(f"{self.name}: returned illegal move {move}")

        metrics = dict(metrics)
        observation_keys = {"exact", "nodes", "iterations", "depth_reached", "score"}
        extra = {
            key: float(value)
            for key, value in metrics.items()
            if key not in observation_keys
        }
        observation = MoveObservation(
            engine=self.name,
            config_label=self.config_label,
            position_id=position_id,
            move=move_key(move),
            wall_time_s=wall_time_s,
            cpu_time_s=cpu_time_s,
            root_legal_moves=len(legal),
            exact=bool(metrics.get("exact", False)),
            seed=seed,
            nodes=metrics.get("nodes"),
            iterations=metrics.get("iterations"),
            depth_reached=metrics.get("depth_reached"),
            score=metrics.get("score"),
            peak_memory_bytes=peak,
            extra=extra,
        )
        return move, observation


class MinimaxAdapter(EngineAdapter):
    """Alpha-beta iterative deepening adapter."""

    name = "minimax"
    stochastic = False

    def __init__(
        self, max_depth: int = 16, time_limit_s: Optional[float] = None
    ) -> None:
        super().__init__(_label("minimax", d=max_depth, t=time_limit_s))
        self.max_depth = max_depth
        self.time_limit_s = time_limit_s

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        engine = MinimaxEngine(
            MinimaxConfig(max_depth=self.max_depth, time_limit_s=self.time_limit_s)
        )
        result = engine.search(State(bb))
        if result.pv and result.pv[0] != result.best_move:
            raise ValueError("minimax: best_move inconsistent with reported PV")

        pieces = sum(count_total_pieces(bb))
        return result.best_move, {
            "exact": result.depth_reached >= 16 - pieces,
            "nodes": result.nodes,
            "depth_reached": result.depth_reached,
            "score": result.score,
        }


class MCTSAdapter(EngineAdapter):
    """Monte Carlo tree search adapter."""

    name = "mcts"
    stochastic = True

    def __init__(
        self,
        max_iterations: int = 1500,
        max_depth: int = 16,
        exploration_weight: float = 1.414,
        time_limit_s: Optional[float] = None,
    ) -> None:
        super().__init__(
            _label(
                "mcts",
                it=max_iterations,
                d=max_depth,
                c=exploration_weight,
                t=time_limit_s,
            )
        )
        self.max_iterations = max_iterations
        self.max_depth = max_depth
        self.exploration_weight = exploration_weight
        self.time_limit_s = time_limit_s

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        engine = MCTSEngine(
            MCTSConfig(
                max_iterations=self.max_iterations,
                max_depth=self.max_depth,
                exploration_weight=self.exploration_weight,
                random_seed=seed,
                time_limit_s=self.time_limit_s,
            )
        )
        move, win_probability = engine.search(State(bb))
        stats = engine.get_statistics()
        return move, {
            "exact": False,
            "iterations": stats["iterations"],
            "nodes": stats["nodes_created"],
            "score": win_probability,
        }


class BeamAdapter(EngineAdapter):
    """Beam search adapter."""

    name = "beam"
    stochastic = True

    def __init__(
        self,
        beam_width: int = 64,
        max_depth: int = 16,
        time_limit_s: Optional[float] = None,
    ) -> None:
        super().__init__(_label("beam", w=beam_width, d=max_depth, t=time_limit_s))
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.time_limit_s = time_limit_s

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        engine = BeamSearchEngine(
            BeamSearchConfig(
                beam_width=self.beam_width,
                max_depth=self.max_depth,
                random_seed=seed,
                time_limit_s=self.time_limit_s,
            )
        )
        result = engine.search(State(bb))
        if result.best_leaf is not None and result.best_leaf.moves:
            move = result.best_leaf.moves[0]
        else:
            ranked = result.ranked_root_moves()
            if not ranked:
                raise ValueError(
                    f"{self.name}: beam search produced no candidate moves"
                )
            move = ranked[0].move

        score = None
        if result.best_leaf is not None:
            score = result.best_leaf.value
            if result.root_player == 1:
                score = -score

        stats = result.stats
        return move, {
            "exact": False,
            "nodes": stats.get("nodes_inserted"),
            "depth_reached": result.max_depth_reached,
            "score": score,
            "candidates_generated": stats.get("candidates_generated", 0),
            "nodes_pruned": stats.get("nodes_pruned", 0),
            "rollouts": stats.get("rollouts", 0),
        }


class RandomAdapter(EngineAdapter):
    """Uniform-random baseline adapter."""

    name = "random"
    stochastic = True

    def __init__(self) -> None:
        super().__init__("random")

    def _select(self, bb, seed: Optional[int]) -> Tuple[Move, dict]:
        rng = random.Random(seed)
        return rng.choice(generate_legal_moves_list(bb)), {"exact": False}


def fixed_time_adapters(
    time_limit_s: float, beam_width: int = 256
) -> List[EngineAdapter]:
    """Return the fixed-time minimax, MCTS, and beam adapter family."""
    return [
        MinimaxAdapter(max_depth=16, time_limit_s=time_limit_s),
        MCTSAdapter(
            max_iterations=10_000_000,
            max_depth=16,
            time_limit_s=time_limit_s,
        ),
        BeamAdapter(beam_width=beam_width, max_depth=16, time_limit_s=time_limit_s),
    ]
