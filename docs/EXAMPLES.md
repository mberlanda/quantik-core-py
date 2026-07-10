# Examples

## State and QFEN

```python
from quantik_core import State

state = State.from_qfen("A.bC/..../d..B/...a")
assert state.to_qfen() == "A.bC/..../d..B/...a"
assert len(state.pack()) == 18
```

## Legal Moves

```python
from quantik_core import QuantikBoard

board = QuantikBoard.from_qfen("A.../..../..../....")
moves = list(board.generate_legal_moves())
assert board.current_player == 1
assert all(move.player == 1 for move in moves)
```

## Canonical Keys

```python
from quantik_core import State

state = State.from_qfen("A.../..../..../....")
key = state.canonical_key()
assert len(key) == 18
```

## MCTS

```python
from quantik_core import State
from quantik_core.mcts import MCTSConfig, MCTSEngine

state = State.from_qfen("ABc./d.../..../....")
engine = MCTSEngine(MCTSConfig(max_iterations=50, random_seed=42))
best_move, win_probability = engine.search(state)
assert best_move is not None
assert 0.0 <= win_probability <= 1.0
```

## Beam Search

```python
from quantik_core import State
from quantik_core.beam_search import BeamSearchConfig, BeamSearchEngine

state = State.from_qfen("ABc./..../..../...a")
engine = BeamSearchEngine(BeamSearchConfig(beam_width=4, max_depth=2, random_seed=1))
result = engine.search(state)
assert result.best_leaf is not None
assert result.best_leaf.is_terminal
```

## Minimax (Alpha-Beta)

```python
from quantik_core import State, MinimaxEngine, MinimaxConfig, EvalConfig

# Depth/time-limited play with the fitted evaluation weights.
engine = MinimaxEngine(MinimaxConfig(max_depth=6, time_limit_s=1.0,
                                     eval_config=EvalConfig.load()))
result = engine.search(State.from_qfen("AbC./..../..../...."))
assert result.best_move.shape == 3 and result.best_move.position == 3  # D at pos 3
assert result.score >= 9000  # a mate is available
```

## Exact Solve

```python
from quantik_core import State, MinimaxEngine, MinimaxConfig

# max_depth=16 is the whole game, so the search solves exactly. A forced
# result scores +/-(10_000 - plies_to_end).
result = MinimaxEngine(MinimaxConfig(max_depth=16)).solve(
    State.from_qfen(".B.C/a.../.Ca./..d."))
assert result.score == 10_000 - 3  # side to move forces a win in 3 plies
```

## Handcrafted Evaluation

```python
from quantik_core import State, evaluate, EvalConfig

state = State.from_qfen("AbC./..../d..B/...a")
score = evaluate(state.bb, player=0, cfg=EvalConfig.load())
assert isinstance(score, float)
```
