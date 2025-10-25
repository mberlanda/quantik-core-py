"""
Tests for storage module: CompactState and GameState classes.

This module tests the hybrid storage system that provides both fast computation
(tuples) and compact serialization (16-byte format) for distributed computing.
"""

import pytest
import struct
import sys

from quantik_core.storage.compact_state import (
    CompactState,
    serialize_bitboard,
    deserialize_bitboard,
    batch_serialize,
    batch_deserialize,
    calculate_memory_savings,
)
from quantik_core.storage.game_tree import GameState, GameTree
from .fixtures import (
    CanonicalBitboardFactory,
    BitboardPatterns,
    MoveSequenceFactory,
)


class TestCompactState:
    """Test CompactState class for 16-byte storage format."""

    def test_creation_from_tuple(self):
        """Test creating CompactState from tuple bitboard."""
        fixture = CanonicalBitboardFactory.empty_board()
        compact = CompactState.from_tuple(fixture.bitboard)

        assert compact.to_tuple() == fixture.bitboard
        assert len(compact) == 8
        assert isinstance(compact.to_bytes(), bytes)
        assert len(compact.to_bytes()) == 16

    def test_creation_from_bytes(self):
        """Test creating CompactState from byte data."""
        # Create 16 bytes of test data
        test_data = struct.pack("<8H", 0, 1, 2, 3, 4, 5, 6, 7)
        compact = CompactState.from_bytes(test_data)

        assert compact.to_tuple() == (0, 1, 2, 3, 4, 5, 6, 7)
        assert compact.to_bytes() == test_data

    def test_roundtrip_conversion(self):
        """Test roundtrip: tuple -> compact -> tuple."""
        fixtures = CanonicalBitboardFactory.all_fixtures()

        for fixture in fixtures:
            compact = CompactState.from_tuple(fixture.bitboard)
            roundtrip = compact.to_tuple()
            assert roundtrip == fixture.bitboard, f"Roundtrip failed for {fixture.name}"

    def test_all_fixture_compatibility(self):
        """Test CompactState with all canonical fixtures."""
        for fixture in CanonicalBitboardFactory.all_fixtures():
            # Test creation and conversion
            compact = CompactState.from_tuple(fixture.bitboard)
            assert compact.to_tuple() == fixture.bitboard

            # Test consistency with CompactBitboard
            assert compact.to_tuple() == fixture.compact_bitboard.to_tuple()

    def test_validation_range_limits(self):
        """Test validation of 16-bit range limits."""
        # Valid range (0-65535)
        valid_tuple = (0, 1, 32767, 65535, 1000, 2000, 3000, 4000)
        CompactState.from_tuple(valid_tuple)  # Should not raise

        # Invalid range (> 65535)
        with pytest.raises(ValueError, match="must be 0-65535"):
            CompactState.from_tuple((0, 0, 0, 0, 0, 0, 0, 65536))

        # Invalid range (negative)
        with pytest.raises(ValueError, match="must be 0-65535"):
            CompactState.from_tuple((0, 0, 0, 0, 0, 0, 0, -1))

    def test_invalid_input_types(self):
        """Test error handling for invalid input types."""
        with pytest.raises(TypeError, match="Expected bytes or 8-tuple"):
            CompactState("invalid")

        with pytest.raises(TypeError, match="Expected bytes or 8-tuple"):
            CompactState([1, 2, 3, 4, 5, 6, 7, 8])  # List instead of tuple

        with pytest.raises(ValueError, match="Byte data must be exactly 16 bytes"):
            CompactState(b"too_short")

        with pytest.raises(TypeError, match="Expected bytes or 8-tuple"):
            CompactState((1, 2, 3))  # Wrong tuple length

    def test_equality_comparison(self):
        """Test equality comparison between CompactState objects and tuples."""
        fixture = CanonicalBitboardFactory.single_piece_corner()
        compact1 = CompactState.from_tuple(fixture.bitboard)
        compact2 = CompactState.from_tuple(fixture.bitboard)

        # CompactState vs CompactState
        assert compact1 == compact2

        # CompactState vs tuple
        assert compact1 == fixture.bitboard

        # Different values
        different_fixture = CanonicalBitboardFactory.single_piece_center()
        compact_different = CompactState.from_tuple(different_fixture.bitboard)
        assert compact1 != compact_different
        assert compact1 != different_fixture.bitboard

    def test_hash_functionality(self):
        """Test hash functionality for use as dictionary keys."""
        fixture1 = CanonicalBitboardFactory.empty_board()
        fixture2 = CanonicalBitboardFactory.single_piece_corner()

        compact1 = CompactState.from_tuple(fixture1.bitboard)
        compact2 = CompactState.from_tuple(fixture2.bitboard)
        compact3 = CompactState.from_tuple(fixture1.bitboard)  # Same as compact1

        # Hash consistency
        assert hash(compact1) == hash(compact3)
        assert hash(compact1) != hash(compact2)

        # Use as dictionary keys
        state_dict = {compact1: "empty", compact2: "corner"}
        assert state_dict[compact3] == "empty"

    def test_string_representation(self):
        """Test string representation."""
        fixture = CanonicalBitboardFactory.alternating_moves()
        compact = CompactState.from_tuple(fixture.bitboard)

        repr_str = repr(compact)
        assert "CompactState" in repr_str
        assert str(fixture.bitboard[0]) in repr_str

    def test_memory_size_property(self):
        """Test memory size calculation."""
        compact = CompactState.from_tuple(BitboardPatterns.EMPTY)

        # Should be 16 bytes data + Python object overhead
        assert compact.memory_size == 40  # 16 + 24
        assert compact.memory_size > 16  # Has overhead


class TestSerializationFunctions:
    """Test standalone serialization functions."""

    def test_serialize_deserialize_single(self):
        """Test single bitboard serialization/deserialization."""
        fixtures = CanonicalBitboardFactory.all_fixtures()

        for fixture in fixtures:
            # Serialize
            serialized = serialize_bitboard(fixture.bitboard)
            assert isinstance(serialized, bytes)
            assert len(serialized) == 16

            # Deserialize
            deserialized = deserialize_bitboard(serialized)
            assert deserialized == fixture.bitboard

    def test_batch_serialize_empty(self):
        """Test batch serialization with empty list."""
        result = batch_serialize([])
        assert result == b""

        deserialized = batch_deserialize(b"")
        assert deserialized == []

    def test_batch_serialize_single(self):
        """Test batch serialization with single bitboard."""
        fixture = CanonicalBitboardFactory.winning_row()
        serialized = batch_serialize([fixture.bitboard])

        assert len(serialized) == 16  # 1 * 16 bytes

        deserialized = batch_deserialize(serialized)
        assert len(deserialized) == 1
        assert deserialized[0] == fixture.bitboard

    def test_batch_serialize_multiple(self):
        """Test batch serialization with multiple bitboards."""
        fixtures = [
            CanonicalBitboardFactory.empty_board(),
            CanonicalBitboardFactory.single_piece_corner(),
            CanonicalBitboardFactory.winning_row(),
            CanonicalBitboardFactory.complex_mid_game(),
        ]
        bitboards = [f.bitboard for f in fixtures]

        # Serialize
        serialized = batch_serialize(bitboards)
        assert len(serialized) == 64  # 4 * 16 bytes

        # Deserialize
        deserialized = batch_deserialize(serialized)
        assert len(deserialized) == 4
        assert deserialized == bitboards

    def test_batch_deserialize_validation(self):
        """Test batch deserialization input validation."""
        # Invalid length (not multiple of 16)
        with pytest.raises(ValueError, match="is not multiple of 16"):
            batch_deserialize(b"invalid_length")

    def test_batch_large_dataset(self):
        """Test batch operations with larger dataset."""
        # Create 100 variations of test patterns
        bitboards = []
        for i in range(100):
            pattern = BitboardPatterns.single_piece_at(i % 16, i % 2, (i // 2) % 4)
            bitboards.append(pattern)

        # Batch serialize/deserialize
        serialized = batch_serialize(bitboards)
        assert len(serialized) == 1600  # 100 * 16 bytes

        deserialized = batch_deserialize(serialized)
        assert len(deserialized) == 100
        assert deserialized == bitboards


class TestGameState:
    """Test GameState class for hybrid computation/storage."""

    def test_creation_from_bitboard(self):
        """Test GameState creation from tuple bitboard."""
        fixture = CanonicalBitboardFactory.complex_mid_game()
        game_state = GameState(fixture.bitboard)

        assert game_state.bitboard == fixture.bitboard

    def test_creation_from_compact(self):
        """Test GameState creation from compact representation."""
        fixture = CanonicalBitboardFactory.winning_column()

        # From CompactState object
        compact = CompactState.from_tuple(fixture.bitboard)
        game_state1 = GameState.from_compact(compact)
        assert game_state1.bitboard == fixture.bitboard

        # From bytes
        serialized = serialize_bitboard(fixture.bitboard)
        game_state2 = GameState.from_compact(serialized)
        assert game_state2.bitboard == fixture.bitboard

    def test_serialization_methods(self):
        """Test GameState serialization methods."""
        fixture = CanonicalBitboardFactory.stress_test_bitboard()
        game_state = GameState(fixture.bitboard)

        # to_compact method
        compact = game_state.to_compact()
        assert isinstance(compact, CompactState)
        assert compact.to_tuple() == fixture.bitboard

        # serialize method (returns bytes)
        serialized = game_state.serialize()
        assert isinstance(serialized, bytes)
        assert len(serialized) == 16

        # Roundtrip
        restored = GameState.from_compact(serialized)
        assert restored.bitboard == fixture.bitboard


class TestGameTree:
    """Test GameTree class for managing multiple game states."""

    def test_creation_and_basic_operations(self):
        """Test GameTree creation and basic operations."""
        tree = GameTree()  # No arguments for constructor

        # Add a node
        initial_fixture = CanonicalBitboardFactory.empty_board()
        initial_state = GameState(initial_fixture.bitboard)
        tree.add_node(initial_state, 0.0)

        # Check if node was added
        node_data = tree.get_node(initial_state)
        assert node_data is not None
        assert node_data["value"] == 0.0

    def test_expand_from_state(self):
        """Test adding multiple states to game tree."""
        tree = GameTree()

        # Add multiple states
        fixtures = [
            CanonicalBitboardFactory.empty_board(),
            CanonicalBitboardFactory.single_piece_corner(),
            CanonicalBitboardFactory.alternating_moves(),
        ]

        for i, fixture in enumerate(fixtures):
            state = GameState(fixture.bitboard)
            tree.add_node(state, float(i))

            # Verify node was added
            node_data = tree.get_node(state)
            assert node_data is not None
            assert node_data["value"] == float(i)

    def test_batch_operations(self):
        """Test batch storage and retrieval operations."""
        fixtures = [
            CanonicalBitboardFactory.empty_board(),
            CanonicalBitboardFactory.single_piece_corner(),
            CanonicalBitboardFactory.alternating_moves(),
        ]

        tree = GameTree()

        # Add multiple states to tree
        for fixture in fixtures:
            state = GameState(fixture.bitboard)
            tree.add_node(state, 1.0)

        # Test that we can work with multiple states
        states = [GameState(f.bitboard) for f in fixtures]
        assert len(states) == 3

        # Test batch serialization of game states
        serialized_states = [state.serialize() for state in states]
        combined = b"".join(serialized_states)
        assert len(combined) == 48  # 3 * 16 bytes


class TestMemoryEfficiency:
    """Test memory efficiency calculations and comparisons."""

    def test_calculate_memory_savings_small(self):
        """Test memory savings calculation for small dataset."""
        savings = calculate_memory_savings(100)

        # Should have all required keys
        required_keys = [
            "sample_tuple_size",
            "sample_compact_size",
            "sample_compact_object_size",
            "tuples_mb",
            "compact_bytes_mb",
            "compact_objects_mb",
            "savings_vs_tuples",
            "compression_ratio",
        ]
        for key in required_keys:
            assert key in savings

        # Compact should be smaller than tuples
        assert savings["compact_bytes_mb"] < savings["tuples_mb"]
        assert savings["savings_vs_tuples"] > 0
        assert savings["compression_ratio"] > 1

    def test_calculate_memory_savings_large(self):
        """Test memory savings calculation for large dataset."""
        savings = calculate_memory_savings(1_000_000)  # 1 million states

        # Should show significant compression for large datasets
        assert savings["compression_ratio"] > 4  # At least 4x compression
        assert savings["savings_vs_tuples"] > 75  # At least 75% savings

    def test_actual_vs_theoretical_memory(self):
        """Test actual memory usage vs theoretical calculations."""
        # Create actual objects to measure
        sample_tuple = (1, 2, 3, 4, 5, 6, 7, 8)
        sample_compact = CompactState.from_tuple(sample_tuple)

        # Theoretical sizes
        tuple_size = sys.getsizeof(sample_tuple)
        compact_bytes_size = len(sample_compact.to_bytes())

        # Compact bytes should be significantly smaller
        assert compact_bytes_size < tuple_size
        assert compact_bytes_size == 16  # Exactly 16 bytes


class TestIntegrationWithFixtures:
    """Test integration between storage module and test fixtures."""

    def test_all_fixtures_compatible(self):
        """Test that all fixtures work with storage classes."""
        for fixture in CanonicalBitboardFactory.all_fixtures():
            # Test CompactState
            compact = CompactState.from_tuple(fixture.bitboard)
            assert compact.to_tuple() == fixture.bitboard

            # Test GameState
            game_state = GameState(fixture.bitboard)
            assert game_state.bitboard == fixture.bitboard

            # Test roundtrip through storage
            serialized = game_state.serialize()
            restored = GameState.from_compact(serialized)
            assert restored.bitboard == fixture.bitboard

    def test_move_sequence_storage(self):
        """Test storing and retrieving move sequences."""
        # Start with empty board
        current_fixture = CanonicalBitboardFactory.empty_board()
        current_bb = current_fixture.bitboard

        # Apply move sequence and store each state
        moves = MoveSequenceFactory.simple_opening()
        stored_states = []

        for move in moves:
            # Store current state
            game_state = GameState(current_bb)
            stored_states.append(game_state.serialize())

            # Apply move (this would require move integration)
            # For now, just verify we can store the states

        # Verify we stored the right number of states
        assert len(stored_states) == len(moves)

        # Verify each stored state can be restored
        for stored_bytes in stored_states:
            restored = GameState.from_compact(stored_bytes)
            assert isinstance(restored.bitboard, tuple)
            assert len(restored.bitboard) == 8

    def test_pattern_storage_efficiency(self):
        """Test storage efficiency with different bitboard patterns."""
        patterns = [
            BitboardPatterns.EMPTY,
            BitboardPatterns.ALTERNATING_BITS,
            BitboardPatterns.single_piece_at(0, 0, 0),
            BitboardPatterns.single_piece_at(15, 1, 3),
            BitboardPatterns.multiple_pieces([(0, 0, 0), (1, 1, 1), (15, 0, 3)]),
        ]

        # Test that all patterns can be stored efficiently
        for pattern in patterns:
            # Create and test storage
            compact = CompactState.from_tuple(pattern)
            assert compact.to_tuple() == pattern
            assert len(compact.to_bytes()) == 16

            # Test through GameState
            game_state = GameState(pattern)
            serialized = game_state.serialize()
            restored = GameState.from_compact(serialized)
            assert restored.bitboard == pattern


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_bitboard_values(self):
        """Test handling of invalid bitboard values."""
        # Values too large for 16-bit storage
        invalid_large = (0, 0, 0, 0, 0, 0, 0, 70000)  # > 65535
        with pytest.raises(ValueError, match="must be 0-65535"):
            CompactState.from_tuple(invalid_large)

    def test_corrupted_serialized_data(self):
        """Test handling of corrupted serialized data."""
        # Invalid length for deserialization
        with pytest.raises(ValueError, match="Byte data must be exactly 16 bytes"):
            CompactState.from_bytes(b"corrupted")

        # Invalid batch data
        with pytest.raises(ValueError, match="is not multiple of 16"):
            batch_deserialize(b"not_multiple_of_16")

    def test_edge_case_values(self):
        """Test edge case values at boundaries."""
        # Maximum valid values
        max_valid = (65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535)
        compact = CompactState.from_tuple(max_valid)
        assert compact.to_tuple() == max_valid

        # Minimum valid values
        min_valid = (0, 0, 0, 0, 0, 0, 0, 0)
        compact = CompactState.from_tuple(min_valid)
        assert compact.to_tuple() == min_valid


if __name__ == "__main__":
    # Run some basic tests when executed directly
    print("Running basic storage tests...")

    # Test fixtures compatibility
    for fixture in CanonicalBitboardFactory.all_fixtures():
        compact = CompactState.from_tuple(fixture.bitboard)
        assert compact.to_tuple() == fixture.bitboard
        print(f"✓ {fixture.name}: CompactState compatible")

    # Test memory efficiency
    savings = calculate_memory_savings(10000)
    print(f"✓ Memory savings for 10K states: {savings['savings_vs_tuples']:.1f}%")
    print(f"✓ Compression ratio: {savings['compression_ratio']:.1f}x")

    print("All basic tests passed!")
