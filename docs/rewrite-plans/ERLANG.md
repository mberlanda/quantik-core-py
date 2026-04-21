# Quantik Erlang/OTP Rewrite Plan

## 1. Architecture

### 1.1 Application Structure

```
quantik/
├── src/
│   ├── quantik_app.erl              % OTP application callback
│   ├── quantik_sup.erl              % Top-level supervisor
│   ├── quantik_bitboard.erl         % Bitboard type, creation, accessors
│   ├── quantik_move.erl             % Move type, apply_move/2, legal_moves/1
│   ├── quantik_win.erl              % Win detection (12-mask check)
│   ├── quantik_symmetry.erl         % D4 × S4 canonicalization, LUT
│   ├── quantik_state.erl            % State record, pack/unpack, canonical_key
│   ├── quantik_qfen.erl             % QFEN ↔ bitboard conversion
│   ├── quantik_validator.erl        % Move & state validation
│   ├── quantik_mcts.erl             % MCTS engine (gen_statem)
│   ├── quantik_mcts_tree.erl        % ETS-backed MCTS tree
│   ├── quantik_mcts_worker.erl      % Rollout worker process
│   ├── quantik_bfs.erl              % BFS opening book generation
│   ├── quantik_bfs_worker.erl       % BFS chunk expansion worker
│   ├── quantik_bfs_sup.erl          % BFS worker pool supervisor
│   ├── quantik_book.erl             % Opening book API (Mnesia or DETS)
│   └── quantik_book_store.erl       % Persistence backend
├── include/
│   ├── quantik.hrl                  % Records, macros, constants
│   └── quantik_masks.hrl            % Win masks as compile-time constants
├── test/
├── priv/
└── rebar.config
```

### 1.2 Bitboard Representation

**Recommended: Dual format** — 16-byte binary for serialization/comparison, 8-tuple for computation.

```erlang
-type bitboard() :: <<_:128>>.
-type bitboard_tuple() :: {non_neg_integer(), non_neg_integer(), ..., non_neg_integer()}.
```

### 1.3 OTP Process Architecture

```
quantik_sup (one_for_one)
├── quantik_symmetry          % gen_server: owns LUT in persistent_term
├── quantik_book_store        % gen_server: Mnesia/DETS wrapper
├── quantik_bfs_sup           % simple_one_for_one for BFS workers
│   └── quantik_bfs_worker    % transient children, one per chunk
└── quantik_mcts              % gen_statem: search coordinator
    └── quantik_mcts_tree     % ETS table (owned by mcts process)
```

### 1.4 LUT Strategy

```erlang
init_lut() ->
    Tables = [build_perm16_lut(D4Idx) || D4Idx <- lists:seq(0, 7)],
    Bins = [list_to_binary([<<Y:16/little>> || Y <- T]) || T <- Tables],
    persistent_term:put(quantik_perm16_lut, list_to_tuple(Bins)).

permute16(Mask, D4Idx) ->
    Bins = persistent_term:get(quantik_perm16_lut),
    Bin = element(D4Idx + 1, Bins),
    Offset = Mask * 2,
    <<_:Offset/binary, Result:16/little-unsigned, _/binary>> = Bin,
    Result.
```

`persistent_term` provides zero-copy reads from any process. The 1MB LUT is shared across all processes.

---

## 2. Performance Analysis

### 2.1 Symmetry Canonicalization

- **Python**: ~75μs per call
- **Erlang (pure)**: ~25-30μs (persistent_term binary reads ~15ns each, no struct.pack needed)
- **Erlang (NIF)**: ~3-5μs (C inner loop)
- **Speedup**: 2.5-3x (pure), 15-25x (NIF)

### 2.2 MCTS

- **Python**: ~3s for 1000 iterations
- **Erlang**: ~120ms (single core), ~20ms (8-core root parallel)
- **Speedup**: 25x (single), 150x (parallel)

Dominant improvement: rollout speed. Python pays ~100μs per random move due to dict creation, list flattening, dataclass frozen validation. Erlang uses flat lists and tuple updates.

### 2.3 Move Generation

- **Python**: ~50-100μs
- **Erlang**: ~5μs
- **Speedup**: ~10-20x

### 2.4 BFS Generation

- **Depth 4**: Python ~47s → Erlang ~2-3s (8 cores) → **15-23x**
- **Depth 5**: Python ~5min → Erlang ~12-20s (8 cores) → **15-25x**

### 2.5 Win Detection

- **Python**: ~3μs
- **Erlang**: ~0.14μs
- **Speedup**: ~20x

---

## 3. Parallelization

### BFS: Lightweight Processes + ETS Dedup

```erlang
ets:new(bfs_seen, [set, public, {write_concurrency, true}, {read_concurrency, true}]).

case ets:insert_new(bfs_seen, {CanonicalKey, Depth}) of
    true  -> %% New position
    false -> skip
end.
```

`ets:insert_new/2` is atomic — perfect lock-free dedup.

### Multi-Node Distribution

```erlang
Nodes = ['quantik@host1', 'quantik@host2'],
Chunks = split_frontier(Frontier, length(Nodes)),
Results = pmap(fun(Node, Chunk) ->
    rpc:call(Node, quantik_bfs_worker, expand_chunk, [Chunk, Depth, Opts])
end, lists:zip(Nodes, Chunks)).
```

### MCTS: Root Parallelism

Run N independent trees, merge statistics. No shared state, linear scaling.

---

## 4. Projected Speedups

| Component | Python | Erlang (pure) | Erlang (NIF) | Speedup (pure) | Speedup (NIF) |
|-----------|--------|---------------|--------------|-----------------|----------------|
| `canonical_key()` | ~75μs | ~25-30μs | ~3-5μs | **2.5-3x** | **15-25x** |
| MCTS 1000 iter | ~3s | ~120ms | ~50ms | **25x** | **60x** |
| BFS depth 4 (8-core) | ~47s | ~2-3s | ~1s | **15-23x** | **47x** |
| BFS depth 5 (8-core) | ~5 min | ~12-20s | ~5-8s | **15-25x** | **37-60x** |
| Win detection | ~3μs | ~0.14μs | ~0.14μs | **~20x** | **~20x** |
| Memory (LUT) | ~50MB | ~1MB | ~1MB | **50x** | **50x** |

---

## 5. Implementation Effort

**Estimated LOC:** ~2,190 (~34% fewer than Python)
**Timeline:** ~9.5 weeks
- Phase 1: Core engine (2 weeks)
- Phase 2: Symmetry (1.5 weeks)
- Phase 3: MCTS (2 weeks)
- Phase 4: BFS + Storage (2 weeks)
- Phase 5: NIF optimization (1 week)
- Phase 6: Polish (1 week)

### Key Risks

| Risk | Mitigation |
|------|------------|
| Canonicalization slower than expected | Phase 5 NIF fallback |
| ETS contention in parallel MCTS | Use root parallelism |
| GC pauses during deep BFS | Tune min_heap_size for workers |
