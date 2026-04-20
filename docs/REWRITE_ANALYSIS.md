# Quantik Library Rewrite Analysis: Language Comparison

**Date:** 2026-04-16
**Baseline:** quantik-core-py (Python 3.10+, ~6,268 LOC, pure Python + numpy)

---

## Executive Summary

This document compares four target languages for a full rewrite of the quantik-core-py library:
**Erlang**, **Elixir**, **Go**, and **Rust**. Each was analyzed by a specialist architect.

### Winner by Category

| Criteria | Winner | Runner-up |
|----------|--------|-----------|
| Raw single-thread performance | **Rust** (100-250x) | Go (100-250x) |
| Parallel BFS throughput | **Rust** (1000-3000x) | Go (500-2000x) |
| MCTS per-search speed | **Rust** (600-1000x) | Go (60-200x) |
| Concurrency model elegance | **Erlang/Elixir** | Go |
| Distribution / multi-node | **Erlang/Elixir** (built-in) | Go (manual) |
| Developer productivity / time to deliver | **Go** (4-5 weeks) | Elixir (8 weeks) |
| Incremental migration (PyO3) | **Rust** (keep Python code) | N/A |
| Memory efficiency | **Rust/Go** (1 MB LUT) | Erlang/Elixir (1 MB) |
| Ecosystem maturity for this use case | **Rust** | Go |
| Fault tolerance / hot reload | **Erlang/Elixir** | N/A |

---

## Python Baseline Performance

| Metric | Value |
|--------|-------|
| `canonical_key()` per call | ~75 μs |
| MCTS 1000 iterations | ~3 s |
| BFS depth 3 | ~3.5 s (726 positions) |
| BFS depth 4 | ~47 s (10,958 positions) |
| BFS depth 5 | ~5 min est. (106,216 positions) |
| BFS depth 8 | Impractical (hours+) |
| Win detection | ~2-5 μs |
| Move generation | ~20-50 μs |
| LUT memory | ~19-50 MB |
| Total source LOC | ~6,268 |

---

## Projected Speedup Comparison Table

### Per-Call Performance (single thread)

| Component | Python | Erlang | Elixir | Go | Rust |
|-----------|--------|--------|--------|-----|------|
| `canonical_key()` | 75 μs | 25-30 μs | 8-12 μs | 0.3-0.8 μs | 0.3-0.75 μs |
| Speedup | 1x | **2.5-3x** | **6-10x** | **100-250x** | **100-250x** |
| canonical_key + NIF | — | 3-5 μs (NIF) | 0.5-2 μs (NIF) | — | — |
| NIF Speedup | — | 15-25x | 40-150x | — | — |

| Component | Python | Erlang | Elixir | Go | Rust |
|-----------|--------|--------|--------|-----|------|
| Win detection | 2-5 μs | 0.14 μs | 0.3-0.5 μs | 10-30 ns | 5-20 ns |
| Speedup | 1x | **~20x** | **4-6x** | **100-400x** | **100-500x** |

| Component | Python | Erlang | Elixir | Go | Rust |
|-----------|--------|--------|--------|-----|------|
| Move generation | 20-50 μs | ~5 μs | 2-5 μs | 100-300 ns | 100-300 ns |
| Speedup | 1x | **~15x** | **4-6x** | **70-200x** | **100-300x** |

### MCTS Engine (1000 iterations)

| Metric | Python | Erlang | Elixir | Go | Rust |
|--------|--------|--------|--------|-----|------|
| Single-core | 3 s | 120 ms | 0.5-1.0 s | 15-50 ms | 3-5 ms |
| Speedup | 1x | **25x** | **3-6x** | **60-200x** | **600-1000x** |
| 8-core parallel | 3 s | 20 ms | N/A (root par.) | ~5-10 ms | ~1-2 ms |
| Speedup | 1x | **150x** | — | **300-600x** | **1500-3000x** |

### BFS Opening Book Generation

| Depth | Python | Erlang (8-core) | Elixir (8-core) | Go (8-core) | Rust (8-core) |
|-------|--------|-----------------|-----------------|-------------|---------------|
| Depth 4 | 47 s | 2-3 s | 6-10 s | 0.5-1.5 s | 10-30 ms |
| Speedup | 1x | **15-23x** | **5-8x** | **30-90x** | **1,600-4,700x** |
| Depth 5 | ~5 min | 12-20 s | 8-12 s | 5-15 s | 100-300 ms |
| Speedup | 1x | **15-25x** | **25-38x** | **20-60x** | **1,000-3,000x** |
| Depth 8 | Hours+ | 2-5 min* | 2-5 min* | 2-10 min | 30-120 s |
| Feasibility | No | Possible | Possible | Yes | Yes |

*Erlang/Elixir depth 8 estimates assume NIF for canonical_key and multi-node.

### Memory

| Metric | Python | Erlang | Elixir | Go | Rust |
|--------|--------|--------|--------|-----|------|
| LUT tables | 19-50 MB | 1 MB | 1 MB | 1 MB | 1 MB |
| Per state | 224+ bytes | ~100 B (ETS) | 16 B (binary) | 16 B | 16 B |

---

## Detailed Language Assessment

### 1. Erlang/OTP

**Architecture:** OTP application with supervisor trees. Bitboard as 16-byte binary + 8-tuple
working format. LUT in `persistent_term` (zero-copy, shared across processes). Tree stored in
ETS tables.

**Strengths:**
- Lightweight processes (~2KB each) enable massive parallelism
- ETS `insert_new` provides atomic lock-free dedup
- Built-in distribution across nodes (10 lines of code to add a machine)
- `persistent_term` provides ideal LUT storage (1 MB, zero-copy)
- Crash isolation via supervisors

**Weaknesses:**
- Pure Erlang canonicalization only 2.5-3x faster than Python (BEAM is interpreted)
- No SIMD/vectorization potential on BEAM
- Need C NIF for competitive single-call performance
- No numpy-equivalent for dense tree storage
- Smaller game development ecosystem

**Key Insight:** Erlang's strength is *concurrency*, not *computation*. The per-call speedup
is modest, but the ability to trivially parallelize across cores and nodes compensates. Best
when multi-node distribution is a requirement.

**Estimated LOC:** ~2,190 (~34% fewer than Python)
**Timeline:** ~9.5 weeks
**Risk:** If pure Erlang `canonical_key` > 40μs, NIF is mandatory.

---

### 2. Elixir

**Architecture:** Mix project with optional Rustler NIF for hot paths. OTP supervisor tree.
Bitboard as 16-byte binary. ETS for dedup and MCTS tree. `Task.async_stream` for parallel BFS.

**Strengths:**
- Same BEAM concurrency as Erlang with more ergonomic syntax
- Better tooling (Mix, ExUnit, StreamData for property tests)
- Rustler NIF integration is first-class (40-150x for canonical_key)
- `Task.async_stream` with `ordered: false` is elegant for BFS
- Hot code reloading during long book generation runs
- Phoenix/LiveView for optional game UI
- Pattern matching on binaries (`<<a::16-little, b::16-little, ...>>`)

**Weaknesses:**
- Same BEAM computational limitations as Erlang
- Pure Elixir only 6-10x faster than Python (better binary handling than raw Erlang)
- Requires Rust NIF for competitive hot-path performance
- No native dense array storage

**Key Insight:** Elixir is "Erlang done right" for this use case. Better ergonomics, Rustler
integration gives a clean path to native performance, and the ecosystem is more active.
If choosing BEAM, choose Elixir.

**Estimated LOC:** ~3,500-4,000 (~40% fewer than Python)
**Timeline:** ~8 weeks
**Risk:** Rust NIF compilation adds build complexity.

---

### 3. Go

**Architecture:** Flat package layout with `bitboard.go`, `symmetry.go`, etc. Sub-packages
for `mcts/` and `openingbook/`. Bitboard as `[8]uint16` value type. Goroutines + sharded
maps for BFS parallelism.

**Strengths:**
- **Value types are the killer feature**: `[8]uint16` on stack = zero heap allocation in hot paths
- 100-250x speedup on `canonical_key` from LUT cache efficiency + no struct.pack
- Goroutines provide easy parallelism (cheaper than OS threads, no GIL)
- `math/bits` intrinsics (POPCNT, TrailingZeros) compile to hardware instructions
- Built-in benchmarking and profiling (`go test -bench`, pprof)
- Single static binary distribution (no Python/venv needed)
- CGo-free SQLite via `modernc.org/sqlite`
- **Fastest time to deliver: 4-5 weeks**

**Weaknesses:**
- No SIMD intrinsics (compiler auto-vectorizes, but limited control)
- GC pauses possible during deep BFS (mitigate with `GOGC=off`)
- Error handling verbosity
- No pattern matching
- No REPL for interactive exploration

**Key Insight:** Go hits the sweet spot of "close to C performance with Python-level
development speed." The value-type system eliminates the heap allocation that dominates
Python's overhead, and goroutines provide clean parallelism. Best choice if time-to-market
matters and 100x improvement suffices.

**Estimated LOC:** ~3,200 (~51% fewer than Python)
**Timeline:** ~4-5 weeks
**Risk:** GC pauses during deep BFS; no SIMD control for extreme optimization.

---

### 4. Rust

**Architecture:** Cargo workspace with `quantik-core`, `quantik-mcts`, `quantik-book`,
`quantik-py` crates. Bitboard as `#[repr(C, align(16))] [u16; 8]`. Rayon for parallelism.
DashMap for concurrent dedup.

**Strengths:**
- **Highest raw performance**: 100-250x on canonical_key, 600-1000x on MCTS
- 128-bit bitboard fits exactly in one SSE/NEON SIMD register
- `const fn` LUT generation at compile time (zero runtime init)
- Zero heap allocation on critical path (everything is `Copy`)
- No GC: predictable latency for time-limited MCTS
- Rayon provides zero-copy work-stealing parallelism
- **PyO3 bridge**: expose Rust core to existing Python code (incremental migration!)
- `derive(Hash, Eq, Ord)` for canonical key
- `proptest` for property-based testing of group axioms
- BFS depth 8 becomes feasible in 30-120 seconds

**Weaknesses:**
- Steeper learning curve (ownership, lifetimes)
- Longer compile times
- Canonical key ordering may differ from Python (migration needed for existing DBs)
- More complex error handling patterns

**Key Insight:** Rust provides the maximum performance ceiling. The SIMD potential
(128-bit bitboard = 1 SSE register) and zero-allocation hot paths make it 3-10x faster
even than Go. The PyO3 bridge enables a unique incremental migration strategy where
existing Python code keeps working while hot paths are replaced one at a time.

**Estimated LOC:** ~2,500-3,500 (~45-55% fewer than Python)
**Timeline:** ~3-4 weeks (Rust expertise assumed)
**Risk:** Compile-time LUT may hit limits; DashMap contention at >1M positions.

---

## Comparison Matrix

| Factor | Erlang | Elixir | Go | Rust |
|--------|--------|--------|-----|------|
| Single-thread speedup | 2.5-25x | 6-150x (w/NIF) | 100-250x | 100-250x |
| Parallel speedup (8-core BFS) | 15-25x | 25-100x (w/NIF) | 30-90x | 1000-3000x |
| MCTS speedup | 25-150x | 3-20x | 60-600x | 600-3000x |
| Memory reduction (LUT) | 50x | 50x | 19-50x | 19-50x |
| LOC (estimated) | 2,190 | 3,500-4,000 | 3,200 | 2,500-3,500 |
| Timeline | 9.5 weeks | 8 weeks | 4-5 weeks | 3-4 weeks* |
| Learning curve | Medium | Medium | Low | High |
| Multi-node distribution | Built-in | Built-in | Manual | Manual |
| Python interop | C NIF (complex) | Rustler NIF | CGo FFI | PyO3 (excellent) |
| Hot code reload | Yes | Yes | No | No |
| Fault tolerance | Excellent | Excellent | Good | Good |
| Static binary | No (needs BEAM) | No (needs BEAM) | Yes | Yes |
| SIMD potential | None | None (Rust NIF) | Limited | Full |
| Community for games | Small | Small | Medium | Large |

*Rust timeline assumes developer has Rust experience.

---

## Recommendations

### If you want maximum raw performance:
**Choose Rust.** The 600-1000x MCTS speedup and 1000-3000x parallel BFS speedup are
unmatched. BFS depth 8 becomes a 30-120 second computation. The PyO3 bridge means
you can start using Rust's speed from Python today.

### If you want fastest delivery with great performance:
**Choose Go.** 4-5 weeks to deliver with 100-250x single-thread improvement. Value types
eliminate Python's allocation overhead. Goroutines provide clean parallelism. Single
binary deployment simplifies distribution.

### If you want distributed computing across multiple nodes:
**Choose Elixir.** Built-in distribution, hot code reload for long-running generation,
and Rustler NIFs give you native speed for the hot path. Best if you envision
running book generation across a cluster.

### If you want the hybrid approach (recommended):
**Choose Rust with PyO3.** Build the core engine in Rust, expose via PyO3 to your existing
Python codebase. This gives you:
1. Immediate 100-250x speedup on the bottleneck (`canonical_key`)
2. Full Rust MCTS and BFS when ready
3. Existing Python examples, tests, and tools continue working
4. Path to a standalone Rust CLI for maximum performance

---

## Projected BFS Depth 8 Wall-Clock Times

The ultimate test: can we compute the full opening book to depth 8?

| Language | Single machine (8 cores) | Cluster (32 cores) |
|----------|--------------------------|---------------------|
| Python | Impractical (12+ hours est.) | Not supported |
| Erlang (pure) | 30-60 min | 10-20 min |
| Erlang (NIF) | 5-15 min | 2-5 min |
| Elixir (pure) | 20-40 min | 8-15 min |
| Elixir (NIF) | 3-10 min | 1-3 min |
| Go | 2-10 min | N/A (manual) |
| Rust | **30-120 s** | N/A (manual) |

---

## Appendix: Why Python Is Slow Here

The bottleneck is `canonical_key()`, called millions of times during BFS. Per call:

1. **192 iterations** of a Python `for` loop (~15ns interpreter overhead per iteration)
2. **1,536 list index operations** (8 LUT lookups × 192) — each is a bounds check + pointer dereference + Python object unboxing (~50ns each)
3. **192 `struct.pack` calls** — each allocates a 16-byte `bytes` object on the heap (~100ns)
4. **192 `bytes.__lt__` comparisons** — function dispatch + memcmp (~50ns)
5. **Python `int` objects** — each LUT entry is a 28-byte heap object (vs 2 bytes in compiled languages)

Total per call: ~75μs. In compiled languages with contiguous arrays and stack allocation,
the same algorithm runs in 300ns-800ns (Go/Rust) — a 100-250x improvement from
eliminating interpreter overhead, heap allocation, and object boxing.
