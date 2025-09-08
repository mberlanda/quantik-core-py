import struct
import pytest
from unittest.mock import patch, MagicMock
import sys

from quantik_core import State, VERSION


class TestCBORFunctionality:
    """Test CBOR serialization functionality and error handling."""
    
    def test_cbor_roundtrip(self):
        """Test basic CBOR roundtrip functionality."""
        pytest.importorskip("cbor2")  # Skip test if cbor2 not available
        s = State.from_qfen(".A../..b./.c../...D")
        blob = s.to_cbor(canon=False, mc=7, meta={"id": "X"})
        s2 = State.from_cbor(blob)
        assert s2 == s


class TestCBORErrorScenarios:
    """Test CBOR functionality when cbor2 module is not available or raise deserialization errors."""
    
    def test_to_cbor_import_error(self):
        """Test that to_cbor raises RuntimeError when cbor2 is not available."""
        s = State.empty()
        
        # Mock the import to raise ImportError
        with patch.dict(sys.modules, {'cbor2': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'cbor2'")):
                with pytest.raises(RuntimeError, match="Please install cbor2"):
                    s.to_cbor()
    
    def test_from_cbor_import_error(self):
        """Test that from_cbor raises RuntimeError when cbor2 is not available."""
        # Mock the import to raise ImportError
        with patch.dict(sys.modules, {'cbor2': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'cbor2'")):
                with pytest.raises(RuntimeError, match="Please install cbor2"):
                    State.from_cbor(b"dummy_data")
    
    def test_from_cbor_version_mismatch(self):
        """Test that from_cbor raises ValueError when CBOR version is unsupported."""
        pytest.importorskip("cbor2")  # Skip test if cbor2 not available
        
        import cbor2
        # Create CBOR data with wrong version
        wrong_version_data = {"v": VERSION + 1, "bb": b"0123456789abcdef"}
        cbor_data = cbor2.dumps(wrong_version_data)
        
        with pytest.raises(ValueError, match="Unsupported CBOR version"):
            State.from_cbor(cbor_data)
    
    def test_from_cbor_invalid_bb_field_type(self):
        """Test that from_cbor raises ValueError when bb field is not bytes/bytearray."""
        pytest.importorskip("cbor2")  # Skip test if cbor2 not available
        
        import cbor2
        # Create CBOR data with bb field as string instead of bytes
        invalid_bb_data = {"v": VERSION, "bb": "not_bytes_or_bytearray"}
        cbor_data = cbor2.dumps(invalid_bb_data)
        
        with pytest.raises(ValueError, match="CBOR field 'bb' must be 16 bytes"):
            State.from_cbor(cbor_data)
    
    def test_from_cbor_invalid_bb_field_length(self):
        """Test that from_cbor raises ValueError when bb field is not 16 bytes."""
        pytest.importorskip("cbor2")  # Skip test if cbor2 not available
        
        import cbor2
        # Create CBOR data with bb field that's too short
        short_bb_data = {"v": VERSION, "bb": b"short"}
        cbor_data = cbor2.dumps(short_bb_data)
        
        with pytest.raises(ValueError, match="CBOR field 'bb' must be 16 bytes"):
            State.from_cbor(cbor_data)
        
        # Test bb field that's too long
        long_bb_data = {"v": VERSION, "bb": b"this_is_too_long_for_bb_field"}
        cbor_data = cbor2.dumps(long_bb_data)
        
        with pytest.raises(ValueError, match="CBOR field 'bb' must be 16 bytes"):
            State.from_cbor(cbor_data)
    