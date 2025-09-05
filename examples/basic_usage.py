#!/usr/bin/env python3
"""
Basic usage example for quantik-core package.

This example demonstrates the core functionality of the quantik-core library.
"""

from quantik_core import State


def main():
    """Demonstrate basic quantik-core functionality."""
    print("=== Quantik Core Basic Usage Example ===\n")

    # 1. Create an empty game state
    print("1. Creating an empty game state:")
    empty_state = State.empty()
    print(f"   Empty state: {empty_state.to_qfen()}")
    print()

    # 2. Parse a game state from QFEN notation
    print("2. Parsing game states from QFEN notation:")
    # this state should not be considered valid
    test_positions = [
        "A.../..../..../....",  # Single piece
        "AB../..../..../....",  # Two pieces same player
        "AB../ab../..../....",  # Mixed players
        "ABCD/abcd/..../....",  # Full rows
    ]

    for qfen in test_positions:
        state = State.from_qfen(qfen)
        print(f"   {qfen} -> parsed successfully")
    print()

    # 3. Demonstrate binary serialization
    print("3. Binary serialization (pack/unpack):")
    state = State.from_qfen("AB../cd../..../..CA")
    packed = state.pack()
    unpacked = State.unpack(packed)
    print(f"   Original:  {state.to_qfen()}")
    print(f"   Packed:    {len(packed)} bytes")
    print(f"   Unpacked:  {unpacked.to_qfen()}")
    print(f"   Match:     {state.to_qfen() == unpacked.to_qfen()}")
    print()

    # 4. Demonstrate canonicalization
    print("4. Position canonicalization:")
    test_state = State.from_qfen("A.../..../..../...B")
    canonical_key = test_state.canonical_key()
    canonical_payload = test_state.canonical_payload()

    print(f"   Position:           {test_state.to_qfen()}")
    print(f"   Canonical key:      {len(canonical_key)} bytes")
    print(f"   Canonical payload:  {len(canonical_payload)} bytes")

    # Test symmetry invariance
    rotated_state = State.from_qfen("..../..../..A./B...")  # Same position, rotated
    rotated_canonical = rotated_state.canonical_payload()

    print(f"   Rotated position:   {rotated_state.to_qfen()}")
    print(f"   Same canonical:     {canonical_payload == rotated_canonical}")
    print()

    # 5. Test with CBOR (if available)
    print("5. CBOR serialization (optional):")
    try:
        cbor_data = state.to_cbor(canon=True, mc=42, meta={"test": True})
        restored = State.from_cbor(cbor_data)
        print(f"   CBOR size:     {len(cbor_data)} bytes")
        print(f"   Round-trip:    {restored.to_qfen() == state.to_qfen()}")
    except RuntimeError as e:
        print(f"CBOR not available: {e}")
    print()

    print("All examples completed successfully!")


if __name__ == "__main__":
    main()
