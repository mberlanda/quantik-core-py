import itertools as it
import random
import struct
import pytest
from hypothesis import given, strategies as st

from quantik_core import State, D4, permute16, ALL_SHAPE_PERMS, VERSION, FLAG_CANON

# ---------- Helpers ----------

def apply_symmetry(bb8, d4_map, color_swap, shape_perm):
    # bb8: tuple/list of 8 uint16 in order [C0S0..C0S3, C1S0..C1S3]
    # returns transformed 8×uint16 in same order
    assert len(bb8) == 8
    # split [2][4]
    b = [[bb8[c*4 + s] for s in range(4)] for c in range(2)]
    # geometry
    g = [[permute16(b[c][s], d4_map) for s in range(4)] for c in range(2)]
    # color swap
    if color_swap:
        g[0], g[1] = g[1], g[0]
    # shape perm
    out = [0]*8
    for s in range(4):
        out[s]     = g[0][shape_perm[s]]
        out[4 + s] = g[1][shape_perm[s]]
    return tuple(out)

def payload(bb8):
    return struct.pack("<8H", *bb8)

# ---------- Golden/deterministic unit tests ----------

def test_pack_unpack_empty():
    s = State.empty()
    b = s.pack()
    assert len(b) == 18
    s2 = State.unpack(b)
    assert s == s2
    # canonical key for empty = 0x01 0x02 + 16 zero bytes
    canon = s.canonical_key()
    assert canon[:2] == bytes([VERSION, FLAG_CANON])
    assert canon[2:] == b"\x00" * 16

def test_qfen_roundtrip_examples():
    examples = [
        ".A../..b./.c../...D",
        ".... / .... / .... / ....",
        "AbCd/aBcD/..../....",
        "A.../B.../C.../D...",
        "..a./.b../c.../...d",
    ]
    for q in examples:
        s = State.from_qfen(q)
        assert State.from_qfen(s.to_qfen()) == s

def test_canonical_invariance_under_symmetry_examples():
    # Any symmetry of a position must yield the same canonical key
    q = ".A../..b./.c../...D"
    base = State.from_qfen(q)
    base_key = base.canonical_key()
    bb8 = base.bb
    for _, m in D4:
        for cs in (False, True):
            for sp in ALL_SHAPE_PERMS:
                tbb8 = apply_symmetry(bb8, m, cs, sp)
                ts = State(tbb8)
                assert ts.canonical_key() == base_key

def test_single_piece_canonical_forms():
    # Single pieces canonicalize to one of three possible forms depending on position symmetry class
    expected_forms = {
        struct.pack("<8H", 0, 0, 0, 0, 0, 0, 0, 256),   # corners
        struct.pack("<8H", 0, 0, 0, 0, 0, 0, 0, 512),   # edges  
        struct.pack("<8H", 0, 0, 0, 0, 0, 0, 0, 4096),  # center positions
    }

    # Collect all canonical forms for single pieces
    canonical_forms = set()
    for color in (0,1):
        for shape in range(4):
            for i in range(16):
                bb = [0]*8
                bb[color*4 + shape] = 1 << i
                s = State(tuple(bb))
                canonical_forms.add(s.canonical_payload())
    
    # All canonical forms should be in our expected set
    assert canonical_forms == expected_forms

def test_two_pieces_no_overlap():
    # Ensure different configurations canonicalize consistently and pack/unpack survive
    # Use a small set of arbitrary positions
    positions = [(0,0),(0,5),(5,10),(10,15)]
    for i,j in positions:
        if i==j: continue
        bb = [0]*8
        bb[0] = 1 << i      # C0S0
        bb[5] = 1 << j      # C1S1
        s = State(tuple(bb))
        key = s.canonical_key()
        # Unpack back to state (not guaranteed same orientation) but format is valid
        s2 = State.unpack(key[:2] + s.pack()[2:])  # reuse payload layout
        assert isinstance(s2, State)
        # Canonical key must be stable
        assert s2.canonical_key() == key

# ---------- Property-based tests ----------

@st.composite
def states(draw):
    # random board with the Quantik constraint: at most 1 piece per square
    # (we won't enforce legality per Quantik rules here; just occupancy)
    # pick up to N random pieces
    n = draw(st.integers(min_value=0, max_value=8))
    used = set()
    bb = [0]*8
    for _ in range(n):
        i = draw(st.integers(min_value=0, max_value=15))
        if i in used: continue
        used.add(i)
        color = draw(st.integers(min_value=0, max_value=1))
        shape = draw(st.integers(min_value=0, max_value=3))
        bb[color*4 + shape] |= 1 << i
    return State(tuple(bb))

@given(states())
def test_pack_unpack_roundtrip_random(s):
    data = s.pack()
    s2 = State.unpack(data)
    assert s == s2

@given(states())
def test_qfen_roundtrip_random(s):
    q = s.to_qfen()
    s2 = State.from_qfen(q)
    assert s == s2

@given(states())
def test_canonical_is_min_over_symmetry_orbit(s):
    # The canonical payload must equal the min over the full symmetry orbit
    base = s.bb
    payloads = []
    for _, m in D4:
        for cs in (False, True):
            for sp in ALL_SHAPE_PERMS:
                tbb8 = apply_symmetry(base, m, cs, sp)
                payloads.append(payload(tbb8))
    expected = min(payloads)
    assert s.canonical_payload() == expected

@given(states())
def test_canonical_stability(s):
    # canonicalizing twice is idempotent on the payload
    k1 = s.canonical_payload()
    s2 = State.unpack(bytes([VERSION, FLAG_CANON]) + k1)  # reconstruct State from payload
    k2 = s2.canonical_payload()
    assert k1 == k2


def test_cbor_roundtrip():
    pytest.importorskip("cbor2")  # Skip test if cbor2 not available
    s = State.from_qfen(".A../..b./.c../...D")
    blob = s.to_cbor(canon=False, mc=7, meta={"id":"X"})
    s2 = State.from_cbor(blob)
    assert s2 == s

def test_golden_empty():
    s = State.empty()
    # canonical key: 0x01 0x02 + 16 zero bytes
    key = s.canonical_key()
    assert key == bytes([VERSION, FLAG_CANON]) + b"\x00"*16

def test_canonical_single_piece_stability():
    # Verify that canonicalization is stable - same input always gives same output
    test_cases = [
        (0, 0, 0),  # C0S0 at position 0
        (1, 3, 15), # C1S3 at position 15
        (0, 2, 5),  # C0S2 at position 5
    ]
    
    for color, shape, pos in test_cases:
        bb = [0]*8
        bb[color*4 + shape] = 1 << pos
        s = State(tuple(bb))
        
        # Multiple calls should return same result
        canonical1 = s.canonical_payload()
        canonical2 = s.canonical_payload()
        assert canonical1 == canonical2

# Optional: quick CBOR payload shape
def test_cbor_payload_shape():
    pytest.importorskip("cbor2")  # Skip test if cbor2 not available
    s = State.empty()
    blob = s.to_cbor(canon=True)
    s2 = State.from_cbor(blob)
    assert s2 == s
