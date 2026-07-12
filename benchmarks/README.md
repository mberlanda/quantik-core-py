# Benchmark Utilities

This directory contains the repo-local benchmark harness used for exploratory
cross-engine comparisons. The implementation is intentionally outside
`src/quantik_core`: it is tooling for experiments, reports, checkpoints, and
datasets, not part of the public library API.

The primary entry point is:

```bash
python examples/cross_engine_benchmark.py --help
```

Generated benchmark results belong under `benchmarks/results/`, which is
gitignored. Reusable input datasets can live under `benchmarks/` when they are
small enough to commit and useful across machines.

## Counting Work

Let:

- `P` = number of positions in the loaded dataset
- `S` = `--seeds`
- `E` = number of engines in the selected family
- `D` = number of deterministic engines
- `R` = number of stochastic engines
- `H` = `--h2h-positions`
- `G` = `--h2h-seeds`

For the current native/fixed families, `E = 4`: minimax, MCTS, beam, and
random. Minimax is deterministic, so `D = 1`; MCTS, beam, and random are
stochastic, so `R = 3`.

Agreement observation rows:

```text
P * (D + R * S)
```

For the 36-position dataset with 30 seeds:

```text
36 * (1 + 3 * 30) = 3276 observations
```

Head-to-head game records:

```text
H * G * combinations(E, 2) * 2
```

The final `* 2` is for side balancing: each engine pair plays both
orientations from each sampled position and seed. With four engines,
`combinations(4, 2) = 6`, so every `(position, seed)` contributes `12` games.

Examples:

```text
8 positions * 1 seed * 6 pairs * 2 orientations = 96 games
16 positions * 5 seeds * 6 pairs * 2 orientations = 960 games
```

If resuming from a partial checkpoint, remaining H2H work is:

```text
target_h2h_records - existing_unique_h2h_records
```

The stable H2H key is:

```text
(position_id, mover, responder, seed)
```

The stable agreement key is:

```text
(position_id, engine, config_label, seed)
```

## Observation-Only Runs

Use `--skip-h2h` when you want move-selection observations, cost, agreement,
and stability without playing games:

```bash
python examples/cross_engine_benchmark.py run \
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
  --skip-h2h \
  --checkpoint-dir benchmarks/results/native-seeds30-observations.ckpt \
  --checkpoint-every 25 \
  --output benchmarks/results/native-seeds30-observations.json
```

Set the future H2H target (`--h2h-positions` and `--h2h-seeds`) during the
observation-only run if you plan to reuse the checkpoint later for H2H. Resume
validation compares those values.

Later, play H2H from the same complete observation checkpoint:

```bash
python examples/cross_engine_benchmark.py run \
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
  --resume \
  --skip-agreement \
  --checkpoint-dir benchmarks/results/native-seeds30-observations.ckpt \
  --output benchmarks/results/native-seeds30-h2h16x5.json
```

If you started with a smaller H2H target and want to expand it, copy the
checkpoint directory first, then update the copied `manifest.json` target
fields. Keep the original checkpoint immutable so previous reports remain
reproducible.

## Merging Checkpoint Rows

There is no dedicated merge CLI yet. Merging is still possible because
checkpoint data is append-only JSONL plus a small manifest.

Only merge checkpoints when all of these match:

- dataset checksum
- engine family and all engine settings
- seed base and seed count for agreement rows
- intended H2H target for game rows
- position IDs are globally unique and refer to the same board states

To merge observation rows from multiple compatible checkpoints:

1. Create a new checkpoint directory.
2. Copy one compatible `manifest.json` into it.
3. Concatenate `observations.jsonl` rows from all sources.
4. Deduplicate by `(position_id, engine, config_label, seed)`.
5. Copy or merge `h2h.jsonl` if needed.
6. Update `manifest.json` counts.
7. Run `report --input <checkpoint-dir>` or resume with the merged checkpoint.

To merge H2H games from multiple compatible checkpoints, use the same process
but deduplicate `h2h.jsonl` by `(position_id, mover, responder, seed)`.

Minimal local merge pattern:

```python
import json
from pathlib import Path

def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]

def write_jsonl(path, rows):
    Path(path).write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    )

def unique(rows, key):
    merged = {}
    for row in rows:
        merged[key(row)] = row
    return [merged[k] for k in sorted(merged)]

observations = unique(
    load_jsonl("run-a/observations.jsonl") + load_jsonl("run-b/observations.jsonl"),
    lambda row: (row["position_id"], row["engine"], row["config_label"], row["seed"]),
)
games = unique(
    load_jsonl("run-a/h2h.jsonl") + load_jsonl("run-b/h2h.jsonl"),
    lambda row: (row["position_id"], row["mover"], row["responder"], row["seed"]),
)

write_jsonl("merged/observations.jsonl", observations)
write_jsonl("merged/h2h.jsonl", games)
```

After writing rows, edit `merged/manifest.json` so:

```json
"counts": {
  "observations": <number of merged observation rows>,
  "h2h_records": <number of merged h2h rows>
}
```

Then verify:

```bash
python examples/cross_engine_benchmark.py report \
  --input merged \
  --output merged.md
```

## Dataset Shards

`benchmarks/depth4-canonical/` contains reusable depth-4 canonical input
datasets for exploratory cloud runs:

- `sample-1000.json`: combined deterministic 1,000-position sample
- `sample-1000-part-01.json` through `sample-1000-part-04.json`: four
  250-position shards from the same sample

Depth 4 has 10,946 canonical nonterminal states in this implementation. The
committed files are a deterministic shuffled sample using seed `20260712`.
Shard IDs match the combined dataset IDs, so part 01 contains `d4c00000` to
`d4c00249`, part 02 contains `d4c00250` to `d4c00499`, and so on.

Do not concatenate JSON files byte-for-byte. To combine shards, concatenate
their `positions` arrays into one dataset payload and recompute the dataset
checksum with `benchmarks.dataset.save()`. The committed `sample-1000.json`
is already that combined file.

These depth-4 datasets have `reference: null`. They are ready for cost,
stability, and H2H-style exploratory runs. Exact agreement tables require a
reference augmentation pass first.
