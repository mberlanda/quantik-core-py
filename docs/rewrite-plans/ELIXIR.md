# Quantik Elixir Rewrite Plan

## 1. Architecture

### 1.1 Mix Project Structure

```
quantik/
├── mix.exs
├── config/
│   ├── config.exs
│   └── runtime.exs
├── native/quantik_nif/              # Rust NIF via Rustler
│   ├── Cargo.toml
│   └── src/lib.rs
├── lib/
│   ├── quantik.ex                   # Public façade
│   ├── quantik/
│   │   ├── bitboard.ex              # 128-bit binary representation
│   │   ├── move.ex                  # Move struct + validation
│   │   ├── state.ex                 # State struct
│   │   ├── commons.ex               # Win masks as module attributes
│   │   ├── game_utils.ex            # Win detection, piece counting
│   │   ├── qfen.ex                  # QFEN codec
│   │   ├── symmetry.ex              # Elixir-side symmetry
│   │   ├── symmetry_nif.ex          # Rustler NIF bridge
│   │   ├── mcts/
│   │   │   ├── engine.ex            # GenServer for MCTS
│   │   │   ├── node.ex              # ETS-backed nodes
│   │   │   └── config.ex
│   │   ├── opening_book/
│   │   │   ├── database.ex          # exqlite storage
│   │   │   ├── generator.ex         # BFS with Task.async_stream
│   │   │   ├── entry.ex
│   │   │   └── checkpoint.ex
│   │   ├── application.ex
│   │   └── supervisor.ex
│   └── quantik_web/                 # Optional Phoenix LiveView
├── test/
│   ├── quantik/
│   └── property/                    # StreamData property tests
└── priv/data/
```

### 1.2 Bitboard as 16-byte Binary

```elixir
defmodule Quantik.Bitboard do
  @type t :: <<_::128>>

  def apply_move(bb, player, shape, position) do
    offset = (player * 4 + shape) * 16
    <<pre::size(offset), plane::16-little, post::bitstring>> = bb
    new_plane = Bitwise.bor(plane, Bitwise.bsl(1, position))
    <<pre::size(offset), new_plane::16-little, post::bitstring>>
  end
end
```

16-byte binary = single allocation, zero per-element overhead. Comparison is `memcmp`.

### 1.3 OTP Patterns

| Pattern | Use Case |
|---------|----------|
| Supervisor | Crash isolation for workers |
| GenServer | MCTS search state machine |
| Task.async_stream | BFS frontier expansion |
| ETS | Canonical key dedup, MCTS transposition table |
| :persistent_term | LUT storage (1 MB, zero-copy) |

---

## 2. Performance Analysis

### 2.1 Symmetry Canonicalization

- **Python**: ~75μs
- **Elixir (pure)**: ~8-12μs (binary memcmp instead of struct.pack)
- **Elixir + Rust NIF**: ~0.5-2μs
- **Speedup**: 6-10x (pure), 40-150x (NIF)

### 2.2 MCTS

- **Python**: ~3s for 1000 iterations
- **Elixir**: ~0.5-1.0s (pure), ~0.15-0.3s (NIF)
- **Speedup**: 3-6x (pure), 10-20x (NIF)

### 2.3 BFS Generation (8-core)

- **Depth 4**: Python ~47s → Elixir ~6-10s (pure), ~2-4s (NIF) → **5-25x**
- **Depth 5**: Python ~5min → Elixir ~8-12s (NIF + 8-core) → **25-38x**

### 2.4 Win Detection

- **Python**: ~2μs → Elixir: ~0.3-0.5μs → **4-6x**

---

## 3. Parallelization

### BFS: Task.async_stream

```elixir
frontier
|> Stream.chunk_every(chunk_size)
|> Task.async_stream(
    fn chunk -> expand_chunk(chunk, depth, opts) end,
    max_concurrency: System.schedulers_online(),
    timeout: :infinity,
    ordered: false
  )
|> Stream.each(fn {:ok, results} -> persist_results(results) end)
|> Stream.run()
```

### ETS for Concurrent Dedup

```elixir
:ets.new(:canonical_seen, [:set, :public, :named_table,
                           read_concurrency: true, write_concurrency: true])

case :ets.insert_new(:canonical_seen, {canonical_key, true}) do
  true  -> :new_position
  false -> :already_seen
end
```

### Multi-Node Distribution

```elixir
for {node, chunk} <- Enum.zip(nodes, chunks) do
  Task.Supervisor.async({Quantik.TaskSup, node}, fn ->
    expand_chunk(chunk, depth, opts)
  end)
end
```

---

## 4. Elixir-Specific Advantages

- **Pattern matching** replaces isinstance checks and validation chains
- **Binary handling** (`<<a::16-little, b::16-little, ...>>`) — bitboard IS the wire format
- **Hot code reloading** during multi-hour book generation
- **StreamData** property-based testing for symmetry group axioms
- **Phoenix/LiveView** for optional game UI (~500 LOC, 2-3 days)

---

## 5. Projected Speedups

| Component | Python | Elixir (pure) | Elixir (NIF) | Speedup (pure) | Speedup (NIF) |
|-----------|--------|---------------|--------------|-----------------|----------------|
| `canonical_key()` | ~75μs | ~8-12μs | ~0.5-2μs | **6-10x** | **40-150x** |
| MCTS 1000 iter | ~3s | ~0.5-1.0s | ~0.15-0.3s | **3-6x** | **10-20x** |
| BFS depth 4 | ~47s | ~6-10s | ~2-4s | **5-8x** | **12-25x** |
| BFS depth 5 (8-core) | ~5 min | ~40-60s | ~3-5s | **5-8x** | **60-100x** |
| Win detection | ~2μs | ~0.3-0.5μs | N/A | **4-6x** | — |
| Memory (LUT) | ~50MB | ~1MB | ~0MB (Rust static) | **50x** | **∞** |

---

## 6. Implementation Effort

**Estimated LOC:** ~3,500-4,000 (~40% fewer than Python)
**Timeline:** ~8 weeks
- Phase 1: Core engine (2 weeks)
- Phase 2: Symmetry - pure Elixir (1 week)
- Phase 3: Opening book (1.5 weeks)
- Phase 4: MCTS (1.5 weeks)
- Phase 5: Rust NIF (1 week)
- Phase 6: Polish & Phoenix (1 week)

### Key Risks

| Risk | Mitigation |
|------|------------|
| NIF crash takes down BEAM | Rustler safety, no unsafe, property tests |
| ETS memory at depth 7+ | Spill to SQLite when threshold exceeded |
| SQLite write bottleneck | Batch inserts, consider ETS+DETS |
