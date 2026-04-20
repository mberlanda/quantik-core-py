# Quantik Rust Rewrite Plan

## 1. Architecture

### 1.1 Workspace Layout

```
quantik/
├── Cargo.toml                    # workspace root
├── crates/
│   ├── quantik-core/             # no_std compatible core engine
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── bitboard.rs       # [u16; 8], repr(C, align(16))
│   │       ├── state.rs          # State, canonical key, QFEN
│   │       ├── moves.rs          # Move, legal move generation
│   │       ├── game.rs           # Win detection, validation
│   │       ├── symmetry.rs       # D4 + shape perm, const fn LUT
│   │       ├── qfen.rs
│   │       └── constants.rs
│   ├── quantik-mcts/             # MCTS engine (feature-gated)
│   │   └── src/
│   │       ├── engine.rs         # UCB1, search loop
│   │       └── arena.rs          # Typed arena for tree nodes
│   ├── quantik-book/             # Opening book + BFS
│   │   └── src/
│   │       ├── bfs.rs            # Rayon parallel BFS
│   │       ├── database.rs       # rusqlite storage
│   │       └── checkpoint.rs
│   └── quantik-py/               # PyO3 Python bindings
│       └── src/lib.rs
├── benches/criterion_benchmarks.rs
└── tests/proptest_symmetry.rs
```

### 1.2 Bitboard (128-bit, fits in one SSE/NEON register)

```rust
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
#[repr(C, align(16))]
pub struct Bitboard {
    planes: [u16; 8],
}
```

- 16 bytes, `Copy`, stack-allocated
- `#[repr(C, align(16))]` enables aligned SIMD loads
- `as_bytes()` provides zero-copy serialization
- `derive(Hash, Eq, Ord)` for canonical key operations

### 1.3 Core Types

```rust
pub struct CanonicalKey {
    version: u8,
    flags: u8,
    payload: Bitboard,
}  // 18 bytes, Copy

pub struct Move {
    pub player: u8,
    pub shape: u8,
    pub position: u8,
}  // 3 bytes, Copy
```

### 1.4 Compile-Time LUT

```rust
const fn build_perm16_lut() -> [[u16; 65536]; 8] {
    // Computed at compile time — zero runtime init
    // 1 MB in .rodata section
}

static PERM16_LUT: [[u16; 65536]; 8] = build_perm16_lut();
```

---

## 2. Performance Analysis

### 2.1 Symmetry Canonicalization

- **Python**: ~75μs (192 × struct.pack + bytes comparison)
- **Rust**: ~300-750ns (LUT in L2, direct [u16; 8] comparison, zero allocation)
- **Speedup: 100-250x**

Optimization: Pre-compute all 64 D4-transformed planes once (8 D4 × 8 planes), then 192 candidate builds are pure array gathers + comparison. LLVM auto-vectorizes the comparison.

### 2.2 MCTS

- **Python**: ~3s for 1000 iterations
- **Rust**: ~3-5ms (canonical_key 500ns + move gen 200ns + rollout 2.5μs per iter)
- **Speedup: 600-1000x**

Arena allocator (single `Vec<MCTSNode>`) gives cache-friendly sequential access. No GC pauses during time-limited search.

### 2.3 Move Generation

```rust
pub fn legal_moves(bb: &Bitboard) -> ArrayVec<Move, 64> {
    // Stack-allocated result, no heap
    // Iterate set bits with trailing_zeros()
    // 12 mask checks per position via bitwise ops
}
```

- **Python**: ~20-50μs → **Rust**: ~100-300ns → **100-300x**

### 2.4 BFS Generation

- **Depth 4**: Python ~47s → Rust ~10-30ms (8-core Rayon) → **1,600-4,700x**
- **Depth 5**: Python ~5min → Rust ~100-300ms (8-core) → **1,000-3,000x**
- **Depth 8**: Rust ~30-120s (8-core) — previously impractical

### 2.5 Win Detection

- **Python**: ~2μs → **Rust**: ~5-20ns → **100-500x**

---

## 3. SIMD Opportunities

The 128-bit bitboard ([u16; 8]) fits exactly in one SSE2/NEON register.

### Candidate Comparison

```rust
fn simd_lt(a: __m128i, b: __m128i) -> bool {
    // Unsigned comparison via signed bias trick
    let bias = _mm_set1_epi16(i16::MIN);
    let gt = _mm_cmpgt_epi16(_mm_add_epi16(b, bias), _mm_add_epi16(a, bias));
    let lt = _mm_cmpgt_epi16(_mm_add_epi16(a, bias), _mm_add_epi16(b, bias));
    (_mm_movemask_epi8(gt) as u32).trailing_zeros()
        < (_mm_movemask_epi8(lt) as u32).trailing_zeros()
}
```

### Shape Permutation via Shuffle

```rust
// Single instruction applies shape perm to both player halves
let shuffled = _mm_shufflehi_epi16(
    _mm_shufflelo_epi16(candidate, 0b11_01_00_10),
    0b11_01_00_10
);
```

### Strategy

1. Start with scalar code + `#[repr(align(16))]`
2. Let LLVM auto-vectorize (2-5x over naive)
3. Add explicit `std::arch` intrinsics behind `simd` feature flag

---

## 4. Parallelization

### BFS with Rayon + DashMap

```rust
frontier.par_iter()
    .filter_map(|bb| {
        let key = canonical_key(bb);
        if !seen.insert(key, ()).is_none() { return None; }
        let moves = legal_moves(bb);
        let edges = moves.iter().map(|m| {
            let child_key = canonical_key(&bb.apply_move(m));
            (key, child_key)
        }).collect();
        Some((key, edges))
    })
    .collect()
```

- Zero-copy: Rayon shares memory, no pickle/serialization
- Work-stealing automatically balances workloads
- `DashMap` provides lock-free concurrent dedup
- `Send + Sync` enforced at compile time

### MCTS: Root Parallelism

N independent trees via `rayon::par_iter`, merge visit counts.

### Pipeline: Crossbeam Channels

```rust
let (tx, rx) = crossbeam::channel::bounded(64);
// Writer thread: dedicated SQLite inserter
// Rayon workers: send batches via tx
```

---

## 5. PyO3 Bridge Strategy

### Phase 1: Hot Path Replacement (1 week)

```rust
#[pyfunction]
fn canonical_key(bb: [u16; 8]) -> Vec<u8> { ... }

#[pyfunction]
fn legal_moves(bb: [u16; 8]) -> Vec<(u8, u8, u8)> { ... }
```

Existing Python code continues working with Rust speed for bottleneck.

### Phase 2: Full MCTS + BFS (1 week)

```rust
#[pyfunction]
fn mcts_search(py: Python, bb: [u16; 8], iterations: u32) -> PyResult<...> {
    py.allow_threads(|| { ... })  // Releases GIL
}
```

### Phase 3: Standalone Rust CLI

Replace Python scripts with Rust binaries for maximum performance.

---

## 6. Projected Speedups

| Component | Python | Rust | Speedup | Confidence |
|-----------|--------|------|---------|------------|
| `canonical_key()` | ~75μs | 300-750ns | **100-250x** | High |
| MCTS 1000 iter | ~3s | 3-5ms | **600-1000x** | Medium-High |
| BFS depth 4 (serial) | ~47s | 80-200ms | **235-590x** | High |
| BFS depth 4 (8-core) | ~47s | 10-30ms | **1,600-4,700x** | Medium |
| BFS depth 5 (8-core) | ~5 min | 100-300ms | **1,000-3,000x** | Medium |
| BFS depth 8 (8-core) | Hours+ | 30-120s | **N/A** | Medium |
| Win detection | ~2μs | 5-20ns | **100-400x** | High |
| Move generation | ~30μs | 100-300ns | **100-300x** | High |
| Memory (LUT) | ~19-50MB | 1.0MB | **19-50x** | Certain |

---

## 7. Implementation Effort

**Estimated LOC:** ~2,500-3,500 (~45-55% fewer than Python)
**Timeline:** ~3-4 weeks (Rust expertise assumed)
- Phase 1: Core engine + symmetry (1 week)
- Phase 2: MCTS (3-4 days)
- Phase 3: PyO3 bridge (3-4 days)
- Phase 4: Opening book + BFS (3-4 days)
- Phase 5: SIMD optimization (2-3 days)
- Phase 6: Polish (2-3 days)

### Key Risks

| Risk | Mitigation |
|------|------------|
| Canonical key ordering mismatch | One-time migration script for existing DBs |
| DashMap contention at >1M positions | Sharded HashMap fallback |
| PyO3 conversion overhead | Batch APIs, numpy buffer protocol |
| const fn LUT compile limits | Fall back to lazy_static! (~1ms init) |

### Validation Strategy

1. **Golden tests**: Python depth-3 canonical keys verified in Rust
2. **proptest**: Symmetry group axioms (closure, associativity, identity, inverse)
3. **Differential testing**: 100K random positions, compare Rust vs Python
4. **Benchmark regression**: Criterion in CI, fail if >5% regression
