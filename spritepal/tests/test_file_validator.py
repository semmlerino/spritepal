
from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.headless,
    pytest.mark.no_manager_setup,
    pytest.mark.allows_registry_state,
]
"""
Test suite for the refactored FileValidator with separated concerns.

This test suite validates the behavior of each individual validator class
as well as the facade pattern implementation.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.file_validator import (
    BasicFileValidator,
    ContentValidator,
    FileInfo,
    FileValidator,
    FormatValidator,
)

# NOTE: pytestmark is defined at the top of the file

class TestBasicFileValidator:
    """Test cases for BasicFileValidator."""

    def test_validate_existence_with_empty_path(self):
        """Test validation fails for empty path."""
        result = BasicFileValidator.validate_existence("")
        assert not result.is_valid
        assert "path is empty or None" in result.error_message

    def test_validate_existence_with_none_path(self):
        """Test validation fails for None path."""
        result = BasicFileValidator.validate_existence(None)
        assert not result.is_valid
        assert "path is empty or None" in result.error_message

    def test_validate_existence_with_nonexistent_file(self):
        """Test validation fails for nonexistent file."""
        result = BasicFileValidator.validate_existence("/nonexistent/file.txt")
        assert not result.is_valid
        assert "does not exist" in result.error_message

    def test_validate_existence_with_directory(self):
        """Test validation fails when path is a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = BasicFileValidator.validate_existence(tmpdir)
            assert not result.is_valid
            assert "Path is not a file" in result.error_message

    def test_validate_existence_with_valid_file(self):
        """Test validation succeeds for valid file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content")
            tmp.flush()

            result = BasicFileValidator.validate_existence(tmp.name)
            assert result.is_valid
            assert result.file_info is not None
            assert result.file_info.exists
            assert result.file_info.is_readable

        os.unlink(tmp.name)

    def test_validate_existence_with_permission_error(self):
        """Test validation fails with permission error."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test")
            tmp.flush()

        # Mock Path.open to simulate permission error
        with patch("pathlib.Path.open", side_effect=PermissionError("Access denied")):
            result = BasicFileValidator.validate_existence(tmp.name)
            assert not result.is_valid
            assert "Permission denied" in result.error_message

        os.unlink(tmp.name)

    def test_validate_properties_with_extension_check(self):
        """Test validation with extension requirements."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"test")
            tmp.flush()

            # Should pass with correct extension
            result = BasicFileValidator.validate_properties(
                tmp.name, allowed_extensions={".txt"}
            )
            assert result.is_valid

            # Should fail with wrong extension
            result = BasicFileValidator.validate_properties(
                tmp.name, allowed_extensions={".pdf"}
            )
            assert not result.is_valid
            assert "Invalid file extension" in result.error_message

        os.unlink(tmp.name)

    def test_validate_properties_with_size_constraints(self):
        """Test validation with size constraints."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"x" * 100)
            tmp.flush()

            # Should pass within size limits
            result = BasicFileValidator.validate_properties(
                tmp.name, min_size=50, max_size=200
            )
            assert result.is_valid

            # Should fail below minimum
            result = BasicFileValidator.validate_properties(
                tmp.name, min_size=200
            )
            assert not result.is_valid
            assert "File too small" in result.error_message

            # Should fail above maximum
            result = BasicFileValidator.validate_properties(
                tmp.name, max_size=50
            )
            assert not result.is_valid
            assert "File too large" in result.error_message

        os.unlink(tmp.name)

    def test_get_file_info(self):
        """Test file info retrieval."""
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp.write(b"x" * 1024)
            tmp.flush()

            info = BasicFileValidator.get_file_info(tmp.name)
            assert info.exists
            assert info.is_readable
            assert info.size == 1024
            assert info.extension == ".bin"
            assert info.path == tmp.name
            assert Path(info.resolved_path).is_absolute()

        os.unlink(tmp.name)

    def test_get_file_info_with_invalid_path(self):
        """Test file info retrieval with invalid path."""
        info = BasicFileValidator.get_file_info("/nonexistent/file.txt")
        assert not info.exists
        assert not info.is_readable
        assert info.size == 0

    def test_format_file_size(self):
        """Test file size formatting."""
        assert BasicFileValidator.format_file_size(100) == "100 bytes"
        assert BasicFileValidator.format_file_size(1024) == "1KB"
        assert BasicFileValidator.format_file_size(2048) == "2KB"
        assert BasicFileValidator.format_file_size(1024 * 1024) == "1MB"
        assert BasicFileValidator.format_file_size(5 * 1024 * 1024) == "5MB"

class TestFormatValidator:
    """Test cases for FormatValidator."""

    def test_validate_vram_format_valid(self):
        """Test VRAM format validation with valid file."""
        file_info = FileInfo(
            path="/test/memory.dmp",  # Doesn't match VRAM patterns
            size=0x10000,  # 64KB
            exists=True,
            is_readable=True,
            extension=".dmp",
            resolved_path="/test/memory.dmp"
        )

        result = FormatValidator.validate_vram_format(file_info)
        assert result.is_valid
        assert len(result.warnings) == 1  # Pattern warning

    def test_validate_vram_format_too_small(self):
        """Test VRAM format validation with too small file."""
        file_info = FileInfo(
            path="/test/vram.dmp",
            size=1000,
            exists=True,
            is_readable=True,
            extension=".dmp",
            resolved_path="/test/vram.dmp"
        )

        result = FormatValidator.validate_vram_format(file_info)
        assert not result.is_valid
        assert "VRAM file too small" in result.error_message

    def test_validate_vram_format_too_large(self):
        """Test VRAM format validation with too large file."""
        file_info = FileInfo(
            path="/test/vram.dmp",
            size=0x200000,  # 2MB
            exists=True,
            is_readable=True,
            extension=".dmp",
            resolved_path="/test/vram.dmp"
        )

        result = FormatValidator.validate_vram_format(file_info)
        assert not result.is_valid
        assert "VRAM file too large" in result.error_message

    def test_validate_vram_format_non_standard_size(self):
        """Test VRAM format validation with non-standard size."""
        file_info = FileInfo(
            path="/test/vram_file.dmp",
            size=0x20000,  # 128KB
            exists=True,
            is_readable=True,
            extension=".dmp",
            resolved_path="/test/vram_file.dmp"
        )

        result = FormatValidator.validate_vram_format(file_info)
        assert result.is_valid
        assert any("Non-standard VRAM size" in w for w in result.warnings)

    def test_validate_cgram_format_valid(self):
        """Test CGRAM format validation with valid file."""
        file_info = FileInfo(
            path="/test/cgram.dmp",
            size=512,
            exists=True,
            is_readable=True,
            extension=".dmp",
            resolved_path="/test/cgram.dmp"
        )

        result = FormatValidator.validate_cgram_format(file_info)
        assert result.is_valid

    def test_validate_cgram_format_invalid_size(self):
        """Test CGRAM format validation with invalid size."""
        file_info = FileInfo(
            path="/test/cgram.dmp",
            size=1024,
            exists=True,
            is_readable=True,
            extension=".dmp",
            resolved_path="/test/cgram.dmp"
        )

        result = FormatValidator.validate_cgram_format(file_info)
        assert not result.is_valid
        assert "Expected exactly 512 bytes" in result.error_message

    def test_validate_oam_format_valid(self):
        """Test OAM format validation with valid file."""
        file_info = FileInfo(
            path="/test/oam.dmp",
            size=544,
            exists=True,
            is_readable=True,
            extension=".dmp",
            resolved_path="/test/oam.dmp"
        )

        result = FormatValidator.validate_oam_format(file_info)
        assert result.is_valid

    def test_validate_rom_format_with_smc_header(self):
        """Test ROM format validation with SMC header."""
        file_info = FileInfo(
            path="/test/rom.smc",
            size=0x100000 + 512,  # 1MB + SMC header
            exists=True,
            is_readable=True,
            extension=".smc",
            resolved_path="/test/rom.smc"
        )

        result = FormatValidator.validate_rom_format(file_info)
        assert result.is_valid
        assert any("SMC header" in w for w in result.warnings)

    def test_validate_rom_format_non_standard_size(self):
        """Test ROM format validation with non-standard size."""
        file_info = FileInfo(
            path="/test/rom.sfc",
            size=0x150000,  # Non-standard size
            exists=True,
            is_readable=True,
            extension=".sfc",
            resolved_path="/test/rom.sfc"
        )

        result = FormatValidator.validate_rom_format(file_info)
        assert result.is_valid
        assert any("Non-standard ROM size" in w for w in result.warnings)

    def test_validate_offset_valid(self):
        """Test offset validation with valid offset."""
        result = FormatValidator.validate_offset(0x1000)
        assert result.is_valid

        result = FormatValidator.validate_offset(0x1000, max_offset=0x2000)
        assert result.is_valid

    def test_validate_offset_negative(self):
        """Test offset validation with negative offset."""
        result = FormatValidator.validate_offset(-1)
        assert not result.is_valid
        assert "Offset cannot be negative" in result.error_message

    def test_validate_offset_too_large(self):
        """Test offset validation with too large offset."""
        result = FormatValidator.validate_offset(0x2000000)  # > 16MB
        assert not result.is_valid
        assert "exceeds maximum ROM size" in result.error_message

    def test_validate_offset_exceeds_max(self):
        """Test offset validation exceeding specified max."""
        result = FormatValidator.validate_offset(0x2000, max_offset=0x1000)
        assert not result.is_valid
        assert "exceeds maximum" in result.error_message

class TestContentValidator:
    """Test cases for ContentValidator."""

    def test_validate_json_content_valid(self):
        """Test JSON content validation with valid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump({"test": "data"}, tmp)
            tmp.flush()

            result = ContentValidator.validate_json_content(tmp.name)
            assert result.is_valid

        os.unlink(tmp.name)

    def test_validate_json_content_invalid(self):
        """Test JSON content validation with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp.write("{invalid json")
            tmp.flush()

            result = ContentValidator.validate_json_content(tmp.name)
            assert not result.is_valid
            assert "Invalid JSON format" in result.error_message

        os.unlink(tmp.name)

    def test_validate_json_content_read_error(self):
        """Test JSON content validation with read error."""
        result = ContentValidator.validate_json_content("/nonexistent/file.json")
        assert not result.is_valid
        assert "Cannot read JSON file" in result.error_message

    def test_validate_vram_header_valid(self):
        """Test VRAM header validation with valid header."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"x" * 20)  # More than 16 bytes
            tmp.flush()

            result = ContentValidator.validate_vram_header(tmp.name)
            assert result.is_valid

        os.unlink(tmp.name)

    def test_validate_vram_header_truncated(self):
        """Test VRAM header validation with truncated file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"x" * 10)  # Less than 16 bytes
            tmp.flush()

            result = ContentValidator.validate_vram_header(tmp.name)
            assert not result.is_valid
            assert "corrupted or truncated" in result.error_message

        os.unlink(tmp.name)

    def test_validate_vram_header_read_error(self):
        """Test VRAM header validation with read error."""
        result = ContentValidator.validate_vram_header("/nonexistent/file.bin")
        assert not result.is_valid
        assert "Cannot read VRAM file" in result.error_message

class TestFileValidatorFacade:
    """Test cases for FileValidator facade."""

    def test_facade_initialization(self):
        """Test facade initializes all validators."""
        validator = FileValidator()
        assert isinstance(validator.basic, BasicFileValidator)
        assert isinstance(validator.format, FormatValidator)
        assert isinstance(validator.content, ContentValidator)

    def test_validate_vram_file_complete(self):
        """Test complete VRAM file validation through facade."""
        with tempfile.NamedTemporaryFile(suffix=".vram", delete=False) as tmp:
            tmp.write(b"x" * 0x10000)  # 64KB
            tmp.flush()

            result = FileValidator.validate_vram_file(tmp.name)
            assert result.is_valid
            assert result.file_info is not None

        os.unlink(tmp.name)

    def test_validate_json_file_complete(self):
        """Test complete JSON file validation through facade."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump({"test": "data"}, tmp)
            tmp.flush()

            result = FileValidator.validate_json_file(tmp.name)
            assert result.is_valid

        os.unlink(tmp.name)

    def test_backward_compatibility_methods(self):
        """Test backward compatibility wrapper methods."""
        # Test _validate_basic_file_properties
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"test")
            tmp.flush()

            result = FileValidator._validate_basic_file_properties(
                tmp.name, {".txt"}
            )
            assert result.is_valid

            # Test _get_file_info
            info = FileValidator._get_file_info(tmp.name)
            assert info.exists

            # Test _format_file_size
            size_str = FileValidator._format_file_size(1024)
            assert size_str == "1KB"

        os.unlink(tmp.name)

    def test_validate_file_existence_facade(self):
        """Test file existence validation through facade."""
        result = FileValidator.validate_file_existence("/nonexistent/file.txt")
        assert not result.is_valid

    def test_validate_offset_facade(self):
        """Test offset validation through facade."""
        result = FileValidator.validate_offset(100)
        assert result.is_valid

        result = FileValidator.validate_offset(-1)
        assert not result.is_valid
