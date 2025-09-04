# Quantik Core — Canonical, Portable Game-State Representation

This document explains the **context**, **goals**, and the **technical design** for a compact, language-agnostic representation of Quantik game states, optimized for fast engine operations (legal moves, win checks) *and* for robust, symmetry-normalized serialization suitable for caches, Monte Carlo simulations, and cross-language tooling.

---

## 1) Context & Goals

**Quantik** is a 4×4 abstract game. Pieces come in **4 shapes** and **2 colors** (players). A move places one of your remaining shapes on an empty square; a player **wins** by completing a row, column, or 2×2 zone with **all four shapes present** (colors don’t matter for the win condition).

We want a representation that:

* ✅ **Is tiny** (fits in a few bytes).
* ✅ **Supports fast bitwise ops** (move generation, win checks).
* ✅ **Has a canonical serialization** under the game’s symmetries (so transposition tables deduplicate equivalent positions).
* ✅ **Is language-agnostic** (Python prototype, Go engine, etc.).
* ✅ **Provides human-friendly text** for debugging/fixtures.
* ✅ **Evolves cleanly** (versioned, self-describing option).

---

## 2) Board Model & Indexing

* Board is **4×4**; index squares **0..15** in **row-major** order:

```
r\c  0  1  2  3
 0   0  1  2  3
 1   4  5  6  7
 2   8  9 10 11
 3  12 13 14 15
```

* Precompute masks:

  * **Rows**: 4 masks
  * **Cols**: 4 masks
  * **Zones** (2×2): 4 masks
  * For each square `i`, `SCOPE[i] = Row(i) | Col(i) | Zone(i)`.

---

## 3) Bitboard Layout (Runtime Core)

Use **8 disjoint 16-bit bitboards**—one for each (color, shape):

```
B[color][shape] : uint16   # bit i is 1 ⇔ that (color,shape) occupies square i
Order in memory: C0S0, C0S1, C0S2, C0S3, C1S0, C1S1, C1S2, C1S3
```

* **Occupancy**: `O = OR over all 8 bitboards` (uint16)
* **Shape union** (color-agnostic): `U[shape] = B[0][shape] | B[1][shape]`

**Memory footprint (runtime):** 8 × 16 bits = **16 bytes** (+ optional 1 bit for side-to-move if not recoloring).

**Why bitboards?** Single-cycle popcounts, masks, and set membership yield **O(1)** checks for move legality and wins.

---

## 4) Fast Engine Operations

### 4.1 Legal Move (player to move = color 0)

To place shape `s` at empty square `i`:

```
empty     := ((O >> i) & 1) == 0
allowed   := (B[1][s] & SCOPE[i]) == 0
legal(i,s):= empty && allowed
```

To get *all* legal squares for shape `s`:

```
F_s := 0
for each bit j in B[1][s]:     # opponent’s s
    F_s |= SCOPE[j]
legalSquares_s := ~O & ~F_s    # mask of legal target squares for s
```

### 4.2 Victory Check (after a placement)

For each line mask `L ∈ rows ∪ cols ∪ zones`:

```
present := 0
for s in 0..3:
    present |= ( (U[s] & L) != 0 ) << s
win if present == 0b1111 for any L
```

(Only the 3 lines touching the last move need recomputation.)

---

## 5) Symmetry & Canonicalization

To avoid duplicate storage for symmetrical positions, canonicalize under:

* **Board symmetries**: the dihedral group **D4** (8 transforms)
* **Color swap**: swap players (2 transforms)
* **Shape relabel**: permute the four shape labels consistently (4! = **24**)

Total transforms per state: **8 × 2 × 24 = 384**.

**Canonical payload** = the **lexicographically smallest** (by bytes) 16-byte payload among all transformed variants.

### 5.1 D4 Transform Implementation

Represent each D4 symmetry as a permutation of bit indices for 16 squares. Apply to a 16-bit mask by bit permutation.

**Optimization:** Precompute **LUTs** for each D4 symmetry:

```
perm16[S][mask] -> transformed_mask   # S ∈ {0..7}, mask ∈ {0..65535}
Memory: 8 × 65,536 × 2 bytes ≈ 1.0 MB
```

This reduces geometry transforms to **O(1)** table lookups, making canonicalization \~3–5× faster.

---

## 6) Binary Core (Authoritative, Portable)

A small, endian-fixed, versioned binary for IPC, storage, and hashing:

```
byte 0  : version (= 1)
byte 1  : flags
          bit1 = 1 if already symmetry-canonicalized (others reserved)
bytes 2..17 : payload = 8 × uint16 (little-endian), order:
              [C0S0][C0S1][C0S2][C0S3][C1S0][C1S1][C1S2][C1S3]
```

* **Minimum size**: **18 bytes**.
* **Canonical key**: set `flags.bit1=1` and store the **canonical payload**.
* **Endianness**: always **little-endian** for the 16-bit words.
* **Versioning**: bump `byte 0` on format changes.

> You may also store a `move_count` or CRC in higher-level containers; keep the core minimal.

---

## 7) Human-Friendly Text (QFEN)

Define a compact, unambiguous “FEN-like” string for UI, logs, fixtures:

```
<rank0>/<rank1>/<rank2>/<rank3>

Each rank has 4 chars:
  '.'    = empty
  'A'..'D' = shape 0..3 for color 0
  'a'..'d' = shape 0..3 for color 1

Example: ".A../..b./.c../...D"
```

Round-trip:

* QFEN ⇆ bitboards
* QFEN ⇆ binary core (via bitboards)

---

## 8) Self-Describing Wrapper (CBOR)

For portable documents and long-term storage, wrap the 16-byte payload in **CBOR** (compact, binary-friendly, no codegen):

```
{
  "v": 1,                     # version of this schema
  "canon": true|false,        # whether payload is already canonicalized
  "bb": h'16-bytes',          # payload: 8×uint16 LE
  ? "mc": uint,               # optional move count
  ? "meta": { ... }           # optional metadata (ids, timestamps, tags)
}
```

* **Why CBOR (vs. JSON/Protobuf)**:

  * Efficient binary field for `bb`
  * No codegen or .proto maintenance for small payloads
  * Widely available in Python & Go

> If you later add strict RPCs or cross-team interfaces, you can layer Protobuf over the same `bb` payload.

---

## 9) Canonicalization Algorithm (Summary)

1. Split state bitboards: `B[2][4]` from the 8 words.
2. For each D4 symmetry `S`:

   * `G[c][s] = perm16[S][B[c][s]]`
3. For color swap `σ ∈ {identity, swap}`:

   * `(C0, C1) = (G0, G1)` or `(G1, G0)`
4. For each shape permutation `π` over 0..3:

   * Output sequence: `C0[π(0..3)], C1[π(0..3)]` → 8×uint16
   * Pack LE into a 16-byte candidate payload
5. Keep the **lexicographically smallest** candidate (bytes compare).
6. Canonical key = `[version=1][flags with bit1=1][payload]`.

---

## 10) Testing Strategy (What to Verify)

* **Byte layout**: pack/unpack stability; version byte handled.
* **QFEN**: string ↔ state round-trip on many cases.
* **Symmetry invariance**: every symmetry image yields **same canonical key**.
* **Minimality**: canonical payload equals **min of orbit** over 384 transforms.
* **Idempotence**: canonicalize → reconstruct → canonicalize = same payload.
* **Goldens**:

  * Empty board: payload `00×16`; canonical key `01 02 00…00`
  * Any single piece: payload `0100 0000 0000 0000 0000 0000 0000 0000` (LE words)

Use both **deterministic** and **property-based** tests (Hypothesis in Python; fuzz tests in Go).

---

## 11) Performance Characteristics

* **Runtime ops** (legal moves, win checks): bitwise AND/OR/shift on 16-bit words; effectively constant time.
* **Canonicalization**:

  * Without LUTs: bit-scatter per permutation, still fast given 16 bits.
  * With LUTs: \~1.0 MB memory; **O(1)** geometry; **3–5×** faster overall.
* **Storage**:

  * Core binary: 18 bytes.
  * CBOR envelope: \~30–60 bytes typical (depends on metadata).
  * QFEN: 19 chars (including slashes), human-readable.

---

## 12) Interop & Implementation Notes

* **Language choice**: The core is trivial to implement in Python and Go directly; both achieve excellent performance for Quantik’s tiny states.

* **Native core (optional)**:

  * If you need a single source of truth with SIMD/LUT micro-optimizations, consider a **Rust** core with a **C ABI** and thin wrappers (Python via cffi, Go via cgo).
  * Otherwise, the per-language implementations are simpler to build, test, and ship.

* **Endianness**: Always **little-endian 16-bit** in the payload. Document this prominently.

* **Versioning**: Put the version byte first; bump on breaking changes. Reserve flag bits.

---

## 13) Worked Example

State (QFEN):

```
.A../..b./.c../...D
```

* Convert QFEN → 8×uint16 bitboards (C0S0..C1S3).
* Compute canonical payload via the 384-transform minimization (D4 × color-swap × shape-perm), using the LUTs for geometry.
* **Canonical key** (bytes):

  ```
  [0]=0x01  # version
  [1]=0x02  # flags (bit1=canon)
  [2..17]   # 16-byte minimal payload
  ```

(Exact payload bytes depend on the symmetry orbit; tests assert equivalence across all images.)

---

## 14) API Surface (Minimal & Sufficient)

**Core:**

* `pack(flags) -> 18 bytes`
* `unpack(bytes[18]) -> (state, flags)`
* `canonical_payload() -> 16 bytes`
* `canonical_key() -> 18 bytes`  (version + flags(bit1=1) + payload)

**Human text:**

* `to_qfen() -> str`
* `from_qfen(str) -> state`

**Self-describing:**

* `to_cbor(canon:bool, mc:int?, meta:map?) -> bytes`
* `from_cbor(bytes) -> state`

**Precomputation:**

* `perm16[8][65536]` LUTs (built once at init)

---

## 15) Future Extensions

* **Side-to-move**: If you don’t recolor STM as “color 0,” allocate a flag bit or field in CBOR.
* **CRC32 / checksum**: Add to CBOR for corruption checks.
* **Move history**: Keep outside the core; store as metadata as needed.
* **Rule variants / handicaps**: Introduce a new version number if core semantics change.

---

## 16) TL;DR

* Represent Quantik with **8×uint16 bitboards** (16 bytes), preserving **fast bitwise ops**.
* Define a stable, versioned **binary core** (18 bytes, little-endian).
* Canonicalize by minimizing over **D4 × color-swap × shape-perm**, accelerated by **8×65,536 LUTs**.
* Provide **QFEN** for humans and **CBOR** for portable, self-describing documents.
* Back it with **golden tests** and **property tests** to guarantee invariants.

This gives you a tiny, blazing-fast core you can use across Python, Go, and beyond—perfect for Monte Carlo search, caching, and reproducible analysis.
