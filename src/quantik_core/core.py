from dataclasses import dataclass
from typing import List, Tuple
import itertools
import struct

# --- versioning/flags --------------------------------------------------------
VERSION = 1
FLAG_CANON = 1 << 1  # bit1

# --- board indexing ----------------------------------------------------------
def rc_to_i(r: int, c: int) -> int: return r * 4 + c
def i_to_rc(i: int) -> Tuple[int, int]: return divmod(i, 4)

def build_perm(fn):
    m = [0]*16
    for i in range(16):
        r, c = i_to_rc(i)
        r2, c2 = fn(r, c)
        m[i] = rc_to_i(r2, c2)
    return m

# 8 D4 symmetries
D4 = [
    ("id",      build_perm(lambda r,c:(r,    c   ))),
    ("rot90",   build_perm(lambda r,c:(c,    3-r))),
    ("rot180",  build_perm(lambda r,c:(3-r,  3-c))),
    ("rot270",  build_perm(lambda r,c:(3-c,  r  ))),
    ("reflV",   build_perm(lambda r,c:(r,    3-c))),
    ("reflH",   build_perm(lambda r,c:(3-r,  c  ))),
    ("reflD",   build_perm(lambda r,c:(c,    r  ))),
    ("reflAD",  build_perm(lambda r,c:(3-c,  3-r))),
]

# --- precomputed LUT: 8 × 65,536 --------------------------------------------
# perm16[S][mask] -> transformed 16-bit mask
def _build_perm16_lut() -> List[List[int]]:
    tables: List[List[int]] = []
    for _, mapping in D4:
        t = [0]*65536
        for x in range(65536):
            y = 0
            # scatter bits by mapping[i] in tight loop
            m = x
            i = 0
            while m:
                if m & 1:
                    y |= 1 << mapping[i]
                i += 1
                m >>= 1
            # finish remaining zeros if any
            while i < 16:
                # (no-op; just advance)
                i += 1
            t[x] = y
        tables.append(t)
    return tables

_perm16 = _build_perm16_lut()  # ~1.0 MB RAM, fast and worth it

# Convenience function for external use
def permute16(mask: int, mapping: List[int]) -> int:
    """Apply a 16-element permutation to a 16-bit mask."""
    result = 0
    for i in range(16):
        if (mask >> i) & 1:
            result |= 1 << mapping[i]
    return result

ALL_SHAPE_PERMS = list(itertools.permutations(range(4)))  # 24 tuples

@dataclass(frozen=True)
class State:
    # bitboards in order C0S0..C0S3, C1S0..C1S3 (each uint16)
    bb: Tuple[int, int, int, int, int, int, int, int]

    @staticmethod
    def empty(): return State((0,0,0,0,0,0,0,0))

    # ----- binary core (18 bytes: B B 8H) ------------------------------------
    def pack(self, flags: int = 0) -> bytes:
        return struct.pack("<BB8H", VERSION, flags, *self.bb)

    @staticmethod
    def unpack(data: bytes) -> "State":
        if len(data) < 18: raise ValueError("Buffer too small for v1 core (18 bytes).")
        ver, flags, *rest = struct.unpack("<BB8H", data[:18])
        if ver != VERSION: raise ValueError(f"Unsupported version {ver}")
        bb = tuple(int(x) & 0xFFFF for x in rest)
        return State(bb)  # flags ignored in state; carried in header

    # ----- human-friendly (QFEN) ---------------------------------------------
    SHAPE_LETTERS = "ABCD"

    def to_qfen(self) -> str:
        grid = []
        for r in range(4):
            row = []
            for c in range(4):
                i = rc_to_i(r,c)
                ch = "."
                for color in (0,1):
                    for s in range(4):
                        if (self.bb[color*4 + s] >> i) & 1:
                            letter = State.SHAPE_LETTERS[s]
                            ch = letter if color == 0 else letter.lower()
                row.append(ch)
            grid.append("".join(row))
        return "/".join(grid)

    @staticmethod
    def from_qfen(qfen: str) -> "State":
        parts = [p.strip() for p in qfen.replace(" ", "").split("/")]
        if len(parts) != 4 or any(len(p) != 4 for p in parts):
            raise ValueError("QFEN must be 4 ranks of 4 chars separated by '/'")
        bb = [0]*8
        letter_to_shape = {ch:i for i,ch in enumerate(State.SHAPE_LETTERS)}
        for r in range(4):
            for c in range(4):
                ch = parts[r][c]
                if ch == ".": continue
                color = 0 if ch.isupper() else 1
                s = letter_to_shape[ch.upper()]
                bb[color*4 + s] |= 1 << rc_to_i(r,c)
        return State(tuple(bb))

    # ----- canonicalization (uses LUT) ---------------------------------------
    def canonical_payload(self) -> bytes:
        best = None
        B = [[self.bb[c*4 + s] for s in range(4)] for c in range(2)]
        for s_idx, _ in enumerate(D4):
            lut = _perm16[s_idx]
            # geometry
            G0 = [lut[B[0][s]] for s in range(4)]
            G1 = [lut[B[1][s]] for s in range(4)]
            for color_swap in (0,1):
                C0, C1 = (G0, G1) if color_swap == 0 else (G1, G0)
                for perm in ALL_SHAPE_PERMS:
                    flat = [C0[perm[0]], C0[perm[1]], C0[perm[2]], C0[perm[3]],
                            C1[perm[0]], C1[perm[1]], C1[perm[2]], C1[perm[3]]]
                    candidate = struct.pack("<8H", *flat)
                    if best is None or candidate < best:
                        best = candidate
        return best  # 16 bytes

    def canonical_key(self) -> bytes:
        return bytes([VERSION, FLAG_CANON]) + self.canonical_payload()

    # ----- CBOR wrappers (portable, self-describing) -------------------------
    # { "v":1, "canon":bool, "bb": h'16bytes', ? "mc":uint, ? "meta":{...} }
    def to_cbor(self, canon: bool = False, mc: int | None = None, meta: dict | None = None) -> bytes:
        try:
            import cbor2  # pip install cbor2
        except ImportError:
            raise RuntimeError("Please install cbor2 (pip install cbor2)")
        payload = struct.pack("<8H", *self.bb)
        m = {"v": VERSION, "canon": bool(canon), "bb": payload}
        if mc is not None: m["mc"] = int(mc)
        if meta: m["meta"] = meta
        return cbor2.dumps(m)

    @staticmethod
    def from_cbor(data: bytes) -> "State":
        try:
            import cbor2
        except ImportError:
            raise RuntimeError("Please install cbor2 (pip install cbor2)")
        m = cbor2.loads(data)
        if m.get("v") != VERSION: raise ValueError("Unsupported CBOR version")
        bb = m.get("bb")
        if not isinstance(bb, (bytes, bytearray)) or len(bb) != 16:
            raise ValueError("CBOR field 'bb' must be 16 bytes")
        vals = struct.unpack("<8H", bb)
        return State(tuple(int(x) & 0xFFFF for x in vals))

