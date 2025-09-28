import struct
import pytest
from hypothesis import given, strategies as st

from quantik_core import State, VERSION, FLAG_CANON, SymmetryHandler

# ---------- Helpers ----------


def apply_symmetry(bb8, d4_map, color_swap, shape_perm):
    # bb8: tuple/list of 8 uint16 in order [C0S0..C0S3, C1S0..C1S3]
    # returns transformed 8×uint16 in same order
    assert len(bb8) == 8
    # split [2][4]
    b = [[bb8[c * 4 + s] for s in range(4)] for c in range(2)]
    # geometry
    g = [
        [SymmetryHandler.permute16(b[c][s], d4_map) for s in range(4)] for c in range(2)
    ]
    # color swap
    if color_swap:
        g[0], g[1] = g[1], g[0]
    # shape perm
    out = [0] * 8
    for s in range(4):
        out[s] = g[0][shape_perm[s]]
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
        "..../..../..../....",  # Empty board (normalized, no spaces)
        "AbCd/aBcD/..../....",
        "A.../B.../C.../D...",
        "..a./.b../c.../...d",
    ]
    for q in examples:
        s = State.from_qfen(q)
        assert State.from_qfen(s.to_qfen()) == s
        assert s.to_qfen() == q


def test_canonical_invariance_under_symmetry_examples():
    # Any symmetry of a position must yield the same canonical key
    q = ".A../..b./.c../...D"
    base = State.from_qfen(q)
    base_key = base.canonical_key()
    bb8 = base.bb
    for idx in range(len(SymmetryHandler.D4)):
        for cs in [False]:  # color shape swap can lead to invalid turn balance , True):
            for sp in SymmetryHandler.ALL_SHAPE_PERMS:
                tbb8 = apply_symmetry(bb8, idx, cs, sp)
                ts = State(tbb8)
                assert ts.canonical_key() == base_key


def test_single_piece_canonical_forms():
    expected_forms = {
        struct.pack(
            "<8H", 0, 0, 0, 256, 0, 0, 0, 0
        ),  # b'\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00'
        struct.pack(
            "<8H", 0, 0, 0, 512, 0, 0, 0, 0
        ),  # b'\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00'
        struct.pack(
            "<8H", 0, 0, 0, 4096, 0, 0, 0, 0
        ),  # b'\x00\x00\x00\x00\x00\x00\x00\x10\x00\x00\x00\x00\x00\x00\x00\x00'
    }

    # Collect all canonical forms for single pieces
    canonical_forms = set()
    for color in [0]:  # color swap should be considered only for balanced turns
        for shape in range(4):
            for i in range(16):
                bb = [0] * 8
                bb[color * 4 + shape] = 1 << i
                canonical_payload = SymmetryHandler.get_canonical_payload(bb)
                canonical_forms.add(canonical_payload)

    assert canonical_forms <= expected_forms


def test_two_pieces_no_overlap():
    # Ensure different configurations canonicalize consistently and pack/unpack survive
    # Use a small set of arbitrary positions
    positions = [(0, 0), (0, 5), (5, 10), (10, 15)]
    for i, j in positions:
        if i == j:
            continue
        bb = [0] * 8
        bb[0] = 1 << i  # C0S0
        bb[5] = 1 << j  # C1S1
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
    bb = [0] * 8
    for _ in range(n):
        i = draw(st.integers(min_value=0, max_value=15))
        if i in used:
            continue
        used.add(i)
        color = draw(st.integers(min_value=0, max_value=1))
        shape = draw(st.integers(min_value=0, max_value=3))
        bb[color * 4 + shape] |= 1 << i
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
    for idx in range(len(SymmetryHandler.D4)):
        for cs in [False]:  # color swap should be considered only for balanced turns
            for sp in SymmetryHandler.ALL_SHAPE_PERMS:
                tbb8 = apply_symmetry(base, idx, cs, sp)
                payloads.append(payload(tbb8))
    expected = min(payloads)
    assert s.canonical_payload() == expected


@given(states())
def test_canonical_stability(s):
    # canonicalizing twice is idempotent on the payload
    k1 = s.canonical_payload()
    s2 = State.unpack(
        bytes([VERSION, FLAG_CANON]) + k1
    )  # reconstruct State from payload
    k2 = s2.canonical_payload()
    assert k1 == k2


def test_golden_empty():
    s = State.empty()
    # canonical key: 0x01 0x02 + 16 zero bytes
    key = s.canonical_key()
    assert key == bytes([VERSION, FLAG_CANON]) + b"\x00" * 16


def test_canonical_single_piece_stability():
    # Verify that canonicalization is stable - same input always gives same output
    test_cases = [
        (0, 0, 0),  # C0S0 at position 0
        (1, 3, 15),  # C1S3 at position 15
        (0, 2, 5),  # C0S2 at position 5
    ]

    for color, shape, pos in test_cases:
        bb = [0] * 8
        bb[color * 4 + shape] = 1 << pos
        s = State(tuple(bb))

        # Multiple calls should return same result
        canonical1 = s.canonical_payload()
        canonical2 = s.canonical_payload()
        assert canonical1 == canonical2


def test_unpack_error_cases():
    """Test error conditions in State.unpack() for better coverage."""
    # Test buffer too small
    with pytest.raises(ValueError, match="Buffer too small"):
        State.unpack(b"\x00" * 17)  # Only 17 bytes, need 18

    # Test unsupported version
    invalid_version_data = struct.pack("<BB8H", 99, 0, *([0] * 8))  # version 99
    with pytest.raises(ValueError, match="Unsupported version"):
        State.unpack(invalid_version_data)


def test_qfen_error_cases():
    """Test error conditions in State.from_qfen() for better coverage."""
    # Test invalid QFEN format - wrong number of parts
    with pytest.raises(ValueError, match="QFEN must be 4 ranks"):
        State.from_qfen("A.../B.../C...")  # Only 3 parts

    # Test invalid QFEN format - wrong length
    with pytest.raises(ValueError, match="QFEN must be 4 ranks"):
        State.from_qfen("A../B.../C.../D...")  # Wrong part lengths


def test_state_bitboard_validation():
    """Test that State validates bitboard data has exactly 8 elements."""
    # Test with too few bitboards
    with pytest.raises(ValueError, match="Invalid bitboard data"):
        State((1, 2, 3, 4, 5, 6))  # Only 6 elements instead of 8

    # Test with too many bitboards
    with pytest.raises(ValueError, match="Invalid bitboard data"):
        State((1, 2, 3, 4, 5, 6, 7, 8, 9, 10))  # 10 elements instead of 8

    # Test with empty tuple
    with pytest.raises(ValueError, match="Invalid bitboard data"):
        State(())  # 0 elements instead of 8

    # Test that valid 8-element tuple works
    valid_state = State((0, 1, 2, 3, 4, 5, 6, 7))
    assert len(valid_state.bb) == 8
    assert valid_state.bb == (0, 1, 2, 3, 4, 5, 6, 7)
