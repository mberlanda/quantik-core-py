# Cross-Language API Portability

This document summarizes the Python/Rust boundary for `quantik-core`. Python
remains the ergonomic orchestration, benchmarking, and ML-training layer. Rust
owns high-throughput search, self-play generation, and other compute-heavy
loops. Both packages must agree on the canonical contracts from
`mberlanda/quantik-core-contracts`.

Python currently declares support for contracts release `1.0.0` via
`quantik_core.SUPPORTED_CONTRACTS_RELEASE`.

## Stable Shared Model

| Concept | Portable contract |
| --- | --- |
| Board size | 4x4, positions `0..15`, row-major from top-left to bottom-right. |
| Shapes | `0=A`, `1=B`, `2=C`, `3=D`. |
| Players | `0` is uppercase QFEN, `1` is lowercase QFEN. |
| Bitboard order | Eight 16-bit integers: player 0 shapes 0..3, then player 1 shapes 0..3. |
| QFEN | Four ranks of four chars separated by `/`; `.` for empty; `ABCD` for player 0; `abcd` for player 1. |
| Action index | `shape * 16 + position`, producing 64 policy slots. |
| Value target | Exactly `+1.0` or `-1.0` from `side_to_move` perspective. Quantik has no draw target. |

Cross-language contract identifiers live in `quantik_core.contracts`.
Cross-language ML data helpers live in `quantik_core.ml_data`.

## Rust Self-Play JSONL Schema

Rust self-play export rows are one JSON object per line:

```json
{
  "schema": "selfplay.v1",
  "contract_version": "1.0.0",
  "game_id": 0,
  "ply": 0,
  "qfen": "..../..../..../....",
  "side_to_move": 0,
  "policy": [
    {"shape": 0, "position": 0, "visits": 3},
    {"shape": 1, "position": 5, "visits": 1}
  ],
  "value": 1.0
}
```

Python validates that:

- `schema` is `selfplay.v1`.
- `contract_version`, when present, is `1.0.0`.
- `qfen` parses and `side_to_move` matches the current player implied by the bitboards.
- each policy entry is a legal move for the row state.
- each policy entry has `shape` in `0..3`, `position` in `0..15`, and positive integer `visits`.
- `policy` is non-empty and normalizes to a probability distribution over 64 action slots.
- `value` is exactly `+1.0` or `-1.0`; `0.0` is rejected.

## Tensor Encoding

`quantik_core.ml_data.qfen_to_tensor(qfen, side_to_move)` returns a NumPy array
with shape `(9, 4, 4)`:

- channels `0..3`: player 0 shapes `A..D`
- channels `4..7`: player 1 shapes `a..d`
- channel `8`: side-to-move plane, filled with `0.0` for player 0 or `1.0` for player 1

Rows and columns match the QFEN position order: `row = position // 4`,
`col = position % 4`.

## Conformance Fixtures

`tests/fixtures/selfplay_v1.jsonl` is the Python-side golden sample for the Rust
exporter schema. Rust should be able to emit rows with the same field names and
semantics; Python must keep parsing and validating this file in CI. The
dedicated `Contracts` workflow also validates the fixture through
`mberlanda/quantik-core-contracts/actions/validate-contracts@v1.0.0`.

## Next Steps

1. Rust: expose `MCTSEngine::root_move_visits()` and emit self-play JSONL rows using the schema above.
2. Python: keep `quantik_core.ml_data` as the reference reader and tensor/policy encoder.
3. Contracts: validate fixtures through `mberlanda/quantik-core-contracts/actions/validate-contracts@v1.0.0`.
4. Cross-repo: add a Rust-generated smoke artifact to CI or release evidence, then point Python tests at the generated artifact in addition to the checked-in fixture.
5. ML: build the PyTorch dataset and policy/value model on top of `SelfPlayRow`, `qfen_to_tensor`, and `policy_visits_to_distribution`.
6. Evaluation: register the trained model in the existing cross-engine benchmark harness instead of creating a separate ladder.
