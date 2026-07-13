# Benchmark Results

Date recorded: 2026-07-13

Related work:

- GitHub issue: `#24`
- Pull request: `#28`
- Evidence archive: `benchmark-evidence.zip`

This file summarizes the exploratory benchmark evidence kept in the repository.
The raw result files remain packed in `benchmark-evidence.zip` because
`benchmarks/results/` is intentionally gitignored.

## Evidence Archive

`benchmark-evidence.zip` contains:

- native benchmark JSON bundles, markdown reports, checkpoint JSONL rows, and
  checkpoint manifests
- depth-4 canonical sample inputs: `sample-1000.json` and four 250-position
  shards
- a copy of `benchmarks/README.md`
- this summary as the archive manifest

The archive is intended as merge-safe evidence, not as a public data API.

## Native Benchmark Run

The most complete run in the archive is
`benchmark-results/native-seeds30-h2h16x5.json`, with the companion report
`benchmark-results/native-seeds30-h2h16x5.md`.

Run metadata:

- benchmark family: `native`
- benchmark id: `2d00e5c8a4f7`
- dataset checksum:
  `a9aa7c316092be3b9a22c54e4306315e54d38af5bbe931f600c9ccd48213b9aa`
- dataset: 36 positions, grouped as opening 8, early_mid 8, late_mid 12,
  endgame 8
- dataset generation seed: `20260711`
- engine seeds: `0..29`
- benchmark environment: quantik-core 1.0.0, Python 3.12.13,
  Linux-6.6.122+-x86_64-with-glibc2.35, 2 CPUs
- benchmark started: 2026-07-12T07:34:54+0000
- checkpoint status: complete
- observations: 3276
- H2H records: 960

Engine settings:

```text
minimax: minimax(d=16,t=1.0)
mcts:    mcts(it=1000,d=16,c=1.414)
beam:    beam(w=16,d=12)
random:  random
```

Work volume:

```text
positions: 36
engine seeds: 30
observations: 3276
h2h positions: 16
h2h seeds: 5
engine pairs: 6
h2h games: 960
games per engine pair: 160
```

The expanded H2H command shape was:

```bash
.venv/bin/python examples/cross_engine_benchmark.py run \
  --dataset benchmarks/positions-v1.json \
  --family native \
  --seeds 30 \
  --minimax-depth 16 \
  --minimax-time 1.0 \
  --mcts-iterations 1000 \
  --beam-width 16 \
  --beam-depth 12 \
  --h2h-positions 16 \
  --h2h-seeds 5 \
  --workers 8 \
  --checkpoint-dir benchmarks/results/native-seeds30-h2h16x5.ckpt \
  --resume \
  --skip-agreement \
  --output benchmarks/results/native-seeds30-h2h16x5.json
```

## Main Findings

This is still an exploratory native-configuration benchmark. It compares each
engine with its own native settings, so it is useful for behavior and scaling
signals, not for final fair-budget ranking.

Head-to-head summary:

| Pair | Games | Result | Win rate |
| --- | ---: | --- | --- |
| minimax vs mcts | 160 | minimax 105, mcts 55 | minimax 65.6%, CI [58.0%, 72.5%] |
| minimax vs beam | 160 | minimax 104, beam 56 | minimax 65.0%, CI [57.3%, 72.0%] |
| minimax vs random | 160 | minimax 134, random 26 | minimax 83.8%, CI [77.3%, 88.7%] |
| mcts vs beam | 160 | mcts 78, beam 82 | mcts 48.7%, CI [41.1%, 56.4%] |
| mcts vs random | 160 | mcts 128, random 32 | mcts 80.0%, CI [73.1%, 85.5%] |
| beam vs random | 160 | beam 132, random 28 | beam 82.5%, CI [75.9%, 87.6%] |

Interpretation:

- Minimax was clearly ahead of MCTS and beam in this native configuration.
- MCTS and beam were statistically indistinguishable in this sample.
- MCTS and beam both clearly beat random.
- Endgames were less discriminating; most separation came from opening,
  early-mid, and late-mid positions.

Agreement and stability:

| Engine | Move consistency | Agreement mean | Agreement std |
| --- | ---: | ---: | ---: |
| beam | 0.680 | 0.865 | 0.022 |
| mcts | 0.726 | 0.727 | 0.049 |
| minimax | 1.000 | 1.000 | 0.000 |
| random | 0.268 | 0.444 | 0.057 |

Cost summary:

| Engine | Moves | Median time (s) | p95 time (s) | Median nodes |
| --- | ---: | ---: | ---: | ---: |
| beam | 1080 | 0.4108 | 16.7220 | 144 |
| mcts | 1080 | 1.3555 | 7.0397 | 168 |
| minimax | 36 | 1.0316 | 1.7313 | 892 |
| random | 1080 | 0.0001 | 0.0004 | - |

## Depth-4 Canonical Inputs

The archive includes reusable depth-4 canonical input datasets under
`depth4-canonical/`.

- `sample-1000.json`: combined deterministic 1,000-position sample
- `sample-1000-part-01.json` through `sample-1000-part-04.json`: four
  250-position shards from the same sample

Depth-4 context:

- depth 4 has 10,946 canonical nonterminal states in this implementation
- sample generation seed: `20260712`
- shard IDs match the combined dataset IDs
- the depth-4 files have `reference: null`

These inputs are ready for cost, stability, and H2H-style exploratory runs.
Exact agreement tables require a reference augmentation pass first.

The planned short depth-4 canonical smoke run has this estimated volume:

```text
positions: 1000
engine seeds: 5
observations: 16000
h2h positions: 16
h2h seeds: 2
engine pairs: 6
h2h games: 384
games per engine pair: 64
```

No completed depth-4 canonical result bundle was present in this worktree when
the archive was produced.

## Guardrails

- Treat the native H2H numbers as exploratory because the engines use native,
  not equalized, resource settings.
- Treat close pairwise results, especially MCTS vs beam, as unresolved unless a
  larger fixed-budget run confirms them.
- Use measured cost tables, not configured limits alone, when reasoning about
  engine runtime.
- Preserve the archive when squashing the PR so the ignored benchmark results
  remain recoverable after merge.
