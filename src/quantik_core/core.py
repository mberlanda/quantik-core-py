from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, TYPE_CHECKING
import struct
from .commons import VERSION, Bitboard
from .symmetry import SymmetryHandler
from .qfen import bb_to_qfen, bb_from_qfen

if TYPE_CHECKING:
    from .memory.bitboard_compact import CompactBitboard


@dataclass(frozen=True)
class State:
    # Internal storage: CompactBitboard for memory efficiency
    _compact_bb: "CompactBitboard"

    def __init__(self, bb: Union[Bitboard, "CompactBitboard"]) -> None:
        """
        Initialize State with either traditional Bitboard tuple or CompactBitboard.

        Args:
            bb: Bitboard tuple (8 integers) or CompactBitboard instance
        """
        from .memory.bitboard_compact import CompactBitboard

        if isinstance(bb, CompactBitboard):
            object.__setattr__(self, "_compact_bb", bb)
        else:
            # Convert tuple to CompactBitboard
            if len(bb) != 8:
                raise ValueError("Invalid bitboard data")
            object.__setattr__(self, "_compact_bb", CompactBitboard.from_tuple(bb))

    @property
    def bb(self) -> Bitboard:
        """
        Backward compatibility property returning traditional Bitboard tuple.

        Returns:
            8-tuple of integers representing the bitboards
        """
        return self._compact_bb.to_tuple()

    @staticmethod
    def empty() -> "State":
        from .memory.bitboard_compact import CompactBitboard

        empty_bb = CompactBitboard.from_tuple((0, 0, 0, 0, 0, 0, 0, 0))
        return State(empty_bb)

    # ----- binary core (18 bytes: B B 8H) ------------------------------------
    def pack(self, flags: int = 0) -> bytes:
        bb_tuple = self._compact_bb.to_tuple()
        return struct.pack("<BB8H", VERSION, flags, *bb_tuple)

    @staticmethod
    def unpack(data: bytes) -> "State":
        from .memory.bitboard_compact import CompactBitboard

        if len(data) < 18:
            raise ValueError("Buffer too small for v1 core (18 bytes).")
        ver, flags, *rest = struct.unpack("<BB8H", data[:18])
        if ver != VERSION:
            raise ValueError(f"Unsupported version {ver}")
        bb_tuple: Bitboard = tuple(int(x) & 0xFFFF for x in rest)  # type: ignore

        compact_bb = CompactBitboard.from_tuple(bb_tuple)
        return State(compact_bb)

    # ----- human-friendly (QFEN) ---------------------------------------------
    SHAPE_LETTERS = "ABCD"

    def to_qfen(self) -> str:
        """
        Convert the state to QFEN string representation.

        Returns:
            QFEN string representation of the board state
        """
        return bb_to_qfen(self._compact_bb.to_tuple())

    @staticmethod
    def from_qfen(qfen: str, validate: bool = False) -> "State":
        """
        Parse a QFEN (Quantik FEN) string into a State object.

        QFEN Format: 4 slash-separated ranks representing rows from top to bottom.

        4x4 Grid Layout:
        ┌─────┬─────┬─────┬─────┐
        │  0  │  1  │  2  │  3  │  ← Rank 1: positions 0-3
        ├─────┼─────┼─────┼─────┤
        │  4  │  5  │  6  │  7  │  ← Rank 2: positions 4-7
        ├─────┼─────┼─────┼─────┤
        │  8  │  9  │ 10  │ 11  │  ← Rank 3: positions 8-11
        ├─────┼─────┼─────┼─────┤
        │ 12  │ 13  │ 14  │ 15  │  ← Rank 4: positions 12-15
        └─────┴─────┴─────┴─────┘

        Shape Notation:
        • A, B, C, D = Player 0 pieces (uppercase)
        • a, b, c, d = Player 1 pieces (lowercase)
        • . = Empty square

        Examples:

        1. Starting position:
           QFEN: "..../..../..../....."
           Visual:
           ┌─────┬─────┬─────┬─────┐
           │  .  │  .  │  .  │  .  │
           ├─────┼─────┼─────┼─────┤
           │  .  │  .  │  .  │  .  │
           ├─────┼─────┼─────┼─────┤
           │  .  │  .  │  .  │  .  │
           ├─────┼─────┼─────┼─────┤
           │  .  │  .  │  .  │  .  │
           └─────┴─────┴─────┴─────┘

        2. Mixed position:
           QFEN: "A.bC/..../d..B/...a"
           Visual:
           ┌─────┬─────┬─────┬─────┐
           │  A  │  .  │  b  │  C  │ ← Player 0: A,C  Player 1: b
           ├─────┼─────┼─────┼─────┤
           │  .  │  .  │  .  │  .  │
           ├─────┼─────┼─────┼─────┤
           │  d  │  .  │  .  │  B  │ ← Player 0: B    Player 1: d
           ├─────┼─────┼─────┼─────┤
           │  .  │  .  │  .  │  a  │ ← Player 1: a
           └─────┴─────┴─────┴─────┘

        3. Winning position (row):
           QFEN: "AbCd/..../..../....."
           Visual:
           ┌─────┬─────┬─────┬─────┐
           │  A  │  b  │  C  │  d  │ ← WIN! All 4 shapes in row
           ├─────┼─────┼─────┼─────┤
           │  .  │  .  │  .  │  .  │
           ├─────┼─────┼─────┼─────┤
           │  .  │  .  │  .  │  .  │
           ├─────┼─────┼─────┼─────┤
           │  .  │  .  │  .  │  .  │
           └─────┴─────┴─────┴─────┘

        Args:
            qfen: String in format "rank1/rank2/rank3/rank4" where each rank
                  contains 4 characters representing one row of the board
            validate: If True, validate the resulting state against Quantik rules (default: False)

        Returns:
            State object with bitboards populated according to the QFEN

        Raises:
            ValueError: If QFEN format is invalid (not 4 ranks of 4 chars each)
                       or if validate=True and the state violates Quantik rules
        """
        bb = bb_from_qfen(qfen, validate)
        return State(bb)

    # ----- canonicalization (delegated to SymmetryHandler) ------------------
    def canonical_payload(self) -> bytes:
        """
        Get the canonical payload for this state.

        The canonical form is the lexicographically smallest among all symmetric variants.

        Returns:
            16-byte canonical payload
        """
        return SymmetryHandler.get_canonical_payload(self._compact_bb.to_tuple())

    def canonical_key(self) -> bytes:
        """
        Get the canonical key for this state.

        Returns:
            18-byte canonical key (version + flag + payload)
        """
        return SymmetryHandler.get_canonical_key(self._compact_bb.to_tuple())

    # TODO: provide a plugin architecture for serialization registering
    # ----- CBOR wrappers (portable, self-describing) -------------------------
    # { "v":1, "canon":bool, "bb": h'16bytes', ? "mc":uint, ? "meta":{...} }
    def to_cbor(
        self, canon: bool = False, mc: Optional[int] = None, meta: Optional[Dict] = None
    ) -> bytes:
        try:
            import cbor2
        except ImportError:
            raise RuntimeError("Please install cbor2 (pip install cbor2)")
        bb_tuple = self._compact_bb.to_tuple()
        payload = struct.pack("<8H", *bb_tuple)
        m: Dict[str, Any] = {"v": VERSION, "canon": bool(canon), "bb": payload}
        if mc is not None:
            m["mc"] = int(mc)
        if meta:
            m["meta"] = meta
        return cbor2.dumps(m)

    @staticmethod
    def from_cbor(data: bytes) -> "State":
        try:
            import cbor2
        except ImportError:
            raise RuntimeError("Please install cbor2 (pip install cbor2)")
        m: Any = cbor2.loads(data)
        if m.get("v") != VERSION:
            raise ValueError("Unsupported CBOR version")
        bb = m.get("bb")
        if not isinstance(bb, (bytes, bytearray)) or len(bb) != 16:
            raise ValueError("CBOR field 'bb' must be 16 bytes")
        vals = struct.unpack("<8H", bb)
        bb_tuple: Bitboard = tuple(int(x) & 0xFFFF for x in vals)  # type: ignore
        return State(bb_tuple)

    def get_occupied_bb(self) -> int:
        """
        Get a bitboard representing all occupied positions on the board.

        Returns:
            A 16-bit integer where each set bit represents an occupied position
        """
        return self._compact_bb.get_occupied_mask()
