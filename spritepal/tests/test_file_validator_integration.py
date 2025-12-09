
from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.rom_data,
]
"""
Integration test to verify refactored FileValidator maintains backward compatibility.
"""

import json
import os
import tempfile

import pytest

from utils.file_validator import FileValidator

# Mark all tests in this module to skip manager setup
pytestmark = pytest.mark.no_manager_setup

def test_file_validator_backward_compatibility():
    """Test that FileValidator maintains backward compatibility with existing usage."""

    # Test VRAM file validation
    with tempfile.NamedTemporaryFile(suffix=".vram", delete=False) as tmp:
        # Write 64KB of data
        tmp.write(b"\x00" * 0x10000)
        tmp.flush()

        result = FileValidator.validate_vram_file(tmp.name)
        assert result.is_valid
        assert result.file_info is not None
        assert result.file_info.size == 0x10000

    os.unlink(tmp.name)

    # Test CGRAM file validation
    with tempfile.NamedTemporaryFile(suffix=".cgram", delete=False) as tmp:
        # Write exactly 512 bytes
        tmp.write(b"\x00" * 512)
        tmp.flush()

        result = FileValidator.validate_cgram_file(tmp.name)
        assert result.is_valid

    os.unlink(tmp.name)

    # Test OAM file validation
    with tempfile.NamedTemporaryFile(suffix=".oam", delete=False) as tmp:
        # Write exactly 544 bytes
        tmp.write(b"\x00" * 544)
        tmp.flush()

        result = FileValidator.validate_oam_file(tmp.name)
        assert result.is_valid

    os.unlink(tmp.name)

    # Test ROM file validation
    with tempfile.NamedTemporaryFile(suffix=".smc", delete=False) as tmp:
        # Write 1MB ROM with SMC header
        tmp.write(b"\x00" * (0x100000 + 512))
        tmp.flush()

        result = FileValidator.validate_rom_file(tmp.name)
        assert result.is_valid
        assert any("SMC header" in w for w in result.warnings)

    os.unlink(tmp.name)

    # Test JSON file validation
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump({"sprites": [], "palettes": []}, tmp)
        tmp.flush()

        result = FileValidator.validate_json_file(tmp.name)
        assert result.is_valid

    os.unlink(tmp.name)

    # Test image file validation
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        # Write some data (not a real PNG, but size validation should pass)
        tmp.write(b"\x89PNG" + b"\x00" * 1000)
        tmp.flush()

        result = FileValidator.validate_image_file(tmp.name)
        assert result.is_valid

    os.unlink(tmp.name)

    # Test file existence validation
    result = FileValidator.validate_file_existence("/nonexistent/file.txt")
    assert not result.is_valid
    assert "does not exist" in result.error_message

    # Test offset validation
    result = FileValidator.validate_offset(0x1000)
    assert result.is_valid

    result = FileValidator.validate_offset(-1)
    assert not result.is_valid
    assert "negative" in result.error_message

def test_file_validator_error_messages_preserved():
    """Ensure error messages remain consistent after refactoring."""

    # Test nonexistent file error message
    result = FileValidator.validate_vram_file("/nonexistent/vram.dmp")
    assert "does not exist" in result.error_message

    # Test wrong extension error message
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp.write(b"test")
        tmp.flush()

        result = FileValidator.validate_vram_file(tmp.name)
        assert "Invalid file extension" in result.error_message
        assert ".txt" in result.error_message

    os.unlink(tmp.name)

    # Test file too small error message
    with tempfile.NamedTemporaryFile(suffix=".vram", delete=False) as tmp:
        tmp.write(b"\x00" * 100)  # Too small
        tmp.flush()

        result = FileValidator.validate_vram_file(tmp.name)
        assert "File too small" in result.error_message

    os.unlink(tmp.name)

    # Test CGRAM wrong size error message
    with tempfile.NamedTemporaryFile(suffix=".cgram", delete=False) as tmp:
        tmp.write(b"\x00" * 1024)  # Wrong size
        tmp.flush()

        result = FileValidator.validate_cgram_file(tmp.name)
        # Now caught by basic validator as size constraint
        assert ("File too large" in result.error_message or
                "Expected exactly 512 bytes" in result.error_message)

    os.unlink(tmp.name)

def test_file_validator_warnings_preserved():
    """Ensure warnings are preserved after refactoring."""

    # Test VRAM non-standard size warning
    with tempfile.NamedTemporaryFile(suffix=".vram", delete=False) as tmp:
        tmp.write(b"\x00" * 0x20000)  # 128KB
        tmp.flush()

        result = FileValidator.validate_vram_file(tmp.name)
        assert result.is_valid
        assert any("Non-standard VRAM size" in w for w in result.warnings)

    os.unlink(tmp.name)

    # Test ROM non-standard size warning
    with tempfile.NamedTemporaryFile(suffix=".sfc", delete=False) as tmp:
        tmp.write(b"\x00" * 0x150000)  # Non-standard size
        tmp.flush()

        result = FileValidator.validate_rom_file(tmp.name)
        assert result.is_valid
        assert any("Non-standard ROM size" in w for w in result.warnings)

    os.unlink(tmp.name)
