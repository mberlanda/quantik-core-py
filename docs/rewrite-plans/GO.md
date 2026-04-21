# Quantik Go Rewrite Plan

## 1. Architecture

### 1.1 Module Layout

```
quantik/
├── go.mod
├── bitboard.go                   # Bitboard type ([8]uint16)
├── state.go                      # State, canonical key, QFEN
├── move.go                       # Move struct, apply, validate
├── movegen.go                    # Legal move generation
├── wincheck.go                   # Win masks, has_winning_line
├── symmetry.go                   # D4 + shape perm canonicalization
├── qfen.go                       # QFEN encode/decode
├── constants.go                  # WIN_MASKS, version
├── mcts/
│   ├── engine.go                 # UCB1, search loop
│   ├── node.go                   # Arena-allocated tree nodes
│   └── bench_test.go
├── openingbook/
│   ├── database.go               # SQLite-backed opening book
│   ├── bfs.go                    # BFS with goroutine workers
│   └── checkpoint.go
├── cmd/
│   ├── generate-book/main.go
│   └── solve/main.go
└── internal/lut/perm16.go
```

### 1.2 Core Types

```go
type Bitboard [8]uint16            // 16 bytes, stack-allocated, Copy

type State struct {
    BB Bitboard
}

type Move struct {
    Player   uint8                  // 0 or 1
    Shape    uint8                  // 0-3
    Position uint8                  // 0-15
}

type CanonicalKey [18]byte         // Directly usable as map key
```

All value types. Zero heap allocation. Directly comparable with `==`.

### 1.3 LUT (1 MB, fits in L2 cache)

```go
var perm16LUT [8][65536]uint16     // Initialized in init()

func init() {
    for d4 := 0; d4 < 8; d4++ {
        for x := 0; x < 65536; x++ {
            var y uint16
            for i := 0; i < 16; i++ {
                if x&(1<<i) != 0 {
                    y |= 1 << d4Mappings[d4][i]
                }
            }
            perm16LUT[d4][x] = y
        }
    }
}
```

Init time: ~2ms (vs ~500ms in Python).

---

## 2. Performance Analysis

### 2.1 Symmetry Canonicalization

- **Python**: ~75μs (192 iter × struct.pack + bytes compare)
- **Go**: ~0.3-0.8μs (LUT in L2, direct [8]uint16 compare, no allocation)
- **Speedup: 100-250x**

Key insight: No `struct.pack` needed. `[8]uint16` comparison is a simple loop. LUT is a contiguous `[8][65536]uint16` array (1 MB) that fits in L2 cache.

### 2.2 MCTS

- **Python**: ~3s for 1000 iterations
- **Go**: ~15-50ms (canonical_key 0.5μs + move gen 0.2μs + rollout 4μs per iter)
- **Speedup: 60-200x**

### 2.3 Move Generation

- **Python**: ~20-50μs
- **Go**: ~100-300ns (math/bits.TrailingZeros, bitwise scan)
- **Speedup: 70-200x**

### 2.4 BFS Generation

- **Depth 4**: Python ~47s → Go ~0.5-1.5s (8-core) → **30-90x**
- **Depth 5**: Python ~5min → Go ~5-15s (8-core) → **20-60x**
- **Depth 8**: Go ~2-10 min (feasible)

### 2.5 Win Detection

- **Python**: ~5μs
- **Go**: ~10-30ns
- **Speedup: 150-500x**

---

## 3. Parallelization

### Goroutines + Sharded Map

```go
const numShards = 64

type ShardedSet struct {
    shards [numShards]struct {
        mu sync.Mutex
        m  map[CanonicalKey]struct{}
    }
}
```

O(1) amortized insert/lookup with minimal lock contention.

### BFS Worker Pool

```go
func processDepth(frontier []Bitboard, depth int) {
    numWorkers := runtime.GOMAXPROCS(0)
    chunkSize := max(1, len(frontier)/(numWorkers*4))
    results := make(chan []Result, numWorkers*4)
    var wg sync.WaitGroup

    for i := 0; i < len(frontier); i += chunkSize {
        chunk := frontier[i:min(i+chunkSize, len(frontier))]
        wg.Add(1)
        go func(chunk []Bitboard) {
            defer wg.Done()
            results <- expandChunk(chunk, depth)
        }(chunk)
    }
    // ...
}
```

No serialization overhead (shared memory), no process startup cost.

### MCTS: Root Parallelism

N independent trees on N goroutines, merge visit counts.

---

## 4. Go-Specific Advantages

- **Value types**: `[8]uint16` on stack, zero heap allocation in hot paths
- **bytes.Compare elimination**: Direct `[8]uint16` comparison
- **math/bits intrinsics**: POPCNT, TrailingZeros compile to hardware instructions
- **CGo-free SQLite**: `modernc.org/sqlite`
- **Built-in profiling**: pprof, trace, benchmark
- **Cross-compilation**: Single static binary for any OS/arch
- **Testing + benchmarks**: Built into the language

---

## 5. Projected Speedups

| Component | Python | Go | Speedup |
|-----------|--------|----|---------|
| `canonical_key()` | ~75μs | 0.3-0.8μs | **100-250x** |
| Win detection | ~5μs | 10-30ns | **150-500x** |
| Move generation | ~20μs | 100-300ns | **70-200x** |
| MCTS 1000 iter | ~3s | 15-50ms | **60-200x** |
| BFS depth 4 (8-core) | ~47s | 0.5-1.5s | **30-90x** |
| BFS depth 5 (8-core) | ~5 min | 5-15s | **20-60x** |
| Memory (LUT) | ~19-50MB | 1MB | **19-50x** |
| State memory | 40+ bytes | 16 bytes | **2.5x+** |

---

## 6. Implementation Effort

**Estimated LOC:** ~3,200 (~51% of Python)
**Timeline:** ~4-5 weeks
- Phase 1: Core types + symmetry (1 week)
- Phase 2: Game logic (3-4 days)
- Phase 3: MCTS engine (1 week)
- Phase 4: Opening book + BFS (1 week)
- Phase 5: CLI tools (2-3 days)
- Phase 6: Validation + benchmarking (3-4 days)

### Key Risks

| Risk | Mitigation |
|------|------------|
| GC pauses during deep BFS | `GOGC=off`, pre-allocate map capacity |
| SQLite write bottleneck | Large batch sizes (10K+), WAL mode |
| Canonical key ordering divergence | Golden file testing at depth 3 |
| `modernc.org/sqlite` quirks | Fallback to `mattn/go-sqlite3` (CGo) |
