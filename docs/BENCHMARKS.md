# Cross-Engine Benchmark Methodology

`examples/cross_engine_benchmark.py` compares `MinimaxEngine`,
`MCTSEngine`, `BeamSearchEngine`, and a uniform-random baseline under
reproducible, methodologically consistent conditions for GH issue #24.

The harness separates four questions that a single timing or win-rate
number would conflate:

1. Move quality: does the engine select an objectively optimal move?
2. Playing strength: how do engines perform against one another?
3. Computational cost: measured time, nodes, iterations, and memory.
4. Stability: do stochastic engines behave consistently across seeds?

## Shared Dataset

All engines are evaluated on exactly the same positions, generated once by
the `dataset` subcommand and saved as `benchmarks/positions-v1.json`. The
artifact records the generation seed, generator id, schema version, and a
sha256 checksum that `run` verifies on load.

Positions are valid, reachable, non-terminal, globally deduplicated by
`State.canonical_key()`, and record the side to move. Phase buckets are by
pieces placed, which is the same as plies from the empty board:

- opening: 0-4
- early_mid: 5-7
- late_mid: 8-11
- endgame: 12-16

## Exact References

Non-opening positions may carry an exact reference: game value for the side
to move plus the complete set of optimal moves. References are produced by
full-depth minimax and stored only when every child was solved with no
cutoff. Quantik never exceeds 16 plies, so a completed iterative-deepening
depth at least equal to the child's remaining plies proves exactness.

Positions that exceed the per-position solve budget, and the whole opening
bucket, have no exact reference and never contribute to exact move-agreement
figures. An engine scores a hit when its selected move is in the complete
optimal set, not merely equal to one arbitrary principal-variation move.

## Benchmark Families

- `fixed`: every engine gets the same wall-clock budget per move. This is
  the fair practical-latency comparison. Beam search checks its deadline
  between depth levels, so a wide level can overshoot; compare measured
  wall times, not configured caps.
- `native`: each engine runs with explicit native settings such as minimax
  depth/time, MCTS iterations/depth/exploration, and beam width/depth. This
  explains scaling behavior but is not a fair head-to-head ranking.

Every generated bundle and Markdown report records which family was run.

## Stochastic Engines

MCTS, beam, and random are seed-sensitive; minimax is deterministic. The
`run` subcommand evaluates stochastic engines across `--seeds N` seeds
using the same ordered seed list for every stochastic adapter. Stability is
computed from the same raw agreement rows, so engines are not rerun just to
produce another table.

The stability table reports:

- move consistency: the average fraction of seeds choosing the modal move
  per position
- agreement mean/std: per-seed exact-reference agreement, then summarized
  across seeds

Use at least 10 seeds during development and at least 30 for publishable
results.

## Head-To-Head

Every sampled position is played twice per seed: each engine once as the
side already to move. Wins are credited to the actual engine/color mapping,
because sampled positions can have either player to move. Quantik has no
draws, but the bundle still carries `draws: 0` so reports have a stable
shape.

## Correctness Preflight

`run` refuses to benchmark until preflight invariants pass:

- dataset positions are non-terminal
- every adapter returns a legal move for the correct side
- adapters do not mutate their input bitboard
- identical settings and seed reproduce the same move
- minimax's chosen move matches the head of its principal variation

## Reproducing A Run

Generate or update the committed dataset artifact:

```bash
python examples/cross_engine_benchmark.py dataset \
  --opening 8 --early-mid 8 --late-mid 12 --endgame 8 \
  --seed 20260711 --solve-budget 30.0 \
  --output benchmarks/positions-v1.json
```

Run the recommended fixed-resource benchmark:

```bash
python examples/cross_engine_benchmark.py run \
  --dataset benchmarks/positions-v1.json \
  --time-limit 1.0 --seeds 30 \
  --output benchmarks/results/$(git rev-parse --short HEAD).json
python examples/cross_engine_benchmark.py report \
  --input benchmarks/results/$(git rev-parse --short HEAD).json
```

`benchmarks/results/` is gitignored. Attach reports to PRs or issues
instead of committing them.

For longer runs, add a checkpoint directory so completed agreement rows
and head-to-head games are persisted as they finish:

```bash
python examples/cross_engine_benchmark.py run \
  --dataset benchmarks/positions-v1.json \
  --time-limit 1.0 --seeds 30 \
  --workers 4 \
  --checkpoint-dir benchmarks/results/$(git rev-parse --short HEAD) \
  --checkpoint-every 25 \
  --output benchmarks/results/$(git rev-parse --short HEAD).json
python examples/cross_engine_benchmark.py run \
  --dataset benchmarks/positions-v1.json \
  --time-limit 1.0 --seeds 30 \
  --workers 4 \
  --checkpoint-dir benchmarks/results/$(git rev-parse --short HEAD) \
  --resume \
  --output benchmarks/results/$(git rev-parse --short HEAD).json
python examples/cross_engine_benchmark.py report \
  --input benchmarks/results/$(git rev-parse --short HEAD)
```

`manifest.json`, `observations.jsonl`, and `h2h.jsonl` live under the
checkpoint directory. `--resume` skips already completed observation and
head-to-head keys, and the final monolithic bundle is still written to
`--output`.

`--workers N` parallelizes independent agreement observations and
head-to-head games with process workers. The default is `1`, preserving
sequential execution. Worker count is intentionally ignored for resume
compatibility, so a checkpoint started with one worker count can be resumed
with another. Memory use can scale roughly with active workers because each
process owns its own engine search state; prefer a small value such as `2`
or `4` on constrained machines.

## Interpretation Guardrails

Minimax buys adversarial certainty when the remaining tree is small enough.
MCTS buys empirical confidence through repeated sampling. Beam search buys
bounded, selectively deep exploration. Claims that one engine is universally
superior require evidence across multiple phases, equivalent budgets,
repeated seeds, and statistically meaningful samples.
