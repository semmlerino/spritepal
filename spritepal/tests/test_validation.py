"""Tests for validation utilities (FileValidator)"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# Mark this entire module for fast, pure unit tests
pytestmark = [
    pytest.mark.headless,
    pytest.mark.unit,
    pytest.mark.no_qt,
    pytest.mark.file_io,  # Involves file operations
    pytest.mark.validation,  # Validation tests
    pytest.mark.no_manager_setup,  # Pure unit tests for validation functions
]

from utils.file_validator import (
    FileValidator,
    FormatValidator,
    sanitize_filename,
)


class TestFileValidation:
    """Test file validation functions"""

    def test_validate_vram_file_valid(self):
        """Test valid VRAM file validation"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            # Write 64KB of data
            f.write(b"\x00" * 65536)
            f.flush()

        try:
            result = FileValidator.validate_vram_file(f.name)
            assert result.is_valid is True
            assert result.error_message is None
        finally:
            Path(f.name).unlink()

    def test_validate_vram_file_invalid_extension(self):
        """Test VRAM file with invalid extension"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"\x00" * 65536)
            f.flush()

        try:
            result = FileValidator.validate_vram_file(f.name)
            assert result.is_valid is False
            assert result.error_message is not None
            assert "Invalid file extension" in result.error_message
        finally:
            Path(f.name).unlink()

    def test_validate_vram_file_too_small(self):
        """Test VRAM file that's too small"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            # Write only 1KB (VRAM should be 64KB)
            f.write(b"\x00" * 1024)
            f.flush()

        try:
            result = FileValidator.validate_vram_file(f.name)
            # FileValidator correctly rejects files that are too small
            assert result.is_valid is False
            assert result.error_message is not None
            assert "too small" in result.error_message
        finally:
            Path(f.name).unlink()

    def test_validate_vram_file_too_large(self):
        """Test VRAM file that's too large"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            # Write more than 64KB (slightly over)
            f.write(b"\x00" * (65536 + 1024))
            f.flush()

        try:
            result = FileValidator.validate_vram_file(f.name)
            # FileValidator allows slightly oversized VRAM files with a warning
            # This is flexible behavior to handle edge cases
            assert result.is_valid is True
            assert len(result.warnings) > 0  # Should have a warning about size
        finally:
            Path(f.name).unlink()

    def test_validate_vram_file_much_too_large(self):
        """Test VRAM file that's much too large"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            # Write way more than 64KB (2x expected size)
            f.write(b"\x00" * (65536 * 2))
            f.flush()

        try:
            result = FileValidator.validate_vram_file(f.name)
            # FileValidator is permissive with oversized files - just adds warnings
            # This allows for edge cases like extended VRAM dumps
            assert result.is_valid is True
            assert len(result.warnings) > 0  # Should have size warning
            assert any("size" in w.lower() for w in result.warnings)
        finally:
            Path(f.name).unlink()

    def test_validate_vram_file_nonexistent(self):
        """Test validation of non-existent file - returns False by default"""
        result = FileValidator.validate_vram_file("/nonexistent/file.dmp")
        assert result.is_valid is False  # Non-existent files fail by default
        assert result.error_message is not None

    def test_validate_vram_file_nonexistent_allowed(self):
        """Test validation with allow_nonexistent=True for legacy compatibility"""
        result = FileValidator.validate_vram_file(
            "/nonexistent/file.dmp", allow_nonexistent=True
        )
        assert result.is_valid is True  # Legacy behavior: non-existent files OK
        assert result.error_message is None

    def test_validate_cgram_file_valid(self):
        """Test valid CGRAM file validation"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            # Write 512 bytes
            f.write(b"\x00" * 512)
            f.flush()

        try:
            result = FileValidator.validate_cgram_file(f.name)
            assert result.is_valid is True
            assert result.error_message is None
        finally:
            Path(f.name).unlink()

    def test_validate_cgram_file_too_small(self):
        """Test CGRAM file that's too small"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            # Write 256 bytes (CGRAM should be 512 bytes)
            f.write(b"\x00" * 256)
            f.flush()

        try:
            result = FileValidator.validate_cgram_file(f.name)
            # FileValidator correctly rejects files that are too small
            assert result.is_valid is False
            assert result.error_message is not None
            assert "too small" in result.error_message
        finally:
            Path(f.name).unlink()

    def test_validate_cgram_file_too_large(self):
        """Test CGRAM file that's too large"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            # Write more than 512 bytes
            f.write(b"\x00" * 1024)
            f.flush()

        try:
            result = FileValidator.validate_cgram_file(f.name)
            assert result.is_valid is False
            assert result.error_message is not None
            assert "File too large" in result.error_message
        finally:
            Path(f.name).unlink()

    def test_validate_oam_file_valid(self):
        """Test valid OAM file validation"""
        with tempfile.NamedTemporaryFile(suffix=".dmp", delete=False) as f:
            # Write 544 bytes
            f.write(b"\x00" * 544)
            f.flush()

        try:
            result = FileValidator.validate_oam_file(f.name)
            assert result.is_valid is True
            assert result.error_message is None
        finally:
            Path(f.name).unlink()

    def test_validate_image_file_valid_png(self):
        """Test valid PNG file validation"""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            # Create a minimal PNG header
            png_header = b"\x89PNG\r\n\x1a\n"
            f.write(png_header)
            f.flush()

        try:
            result = FileValidator.validate_image_file(f.name)
            assert result.is_valid is True
            assert result.error_message is None
        finally:
            Path(f.name).unlink()

    def test_validate_image_file_unsupported_format(self):
        """Test unsupported image format"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake jpg data")
            f.flush()

        try:
            result = FileValidator.validate_image_file(f.name)
            assert result.is_valid is False
            assert result.error_message is not None
            assert "Invalid file extension" in result.error_message
            assert ".jpg" in result.error_message
        finally:
            Path(f.name).unlink()

    def test_validate_json_file_valid(self):
        """Test valid JSON file"""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write('{"colors": [[0,0,0], [255,255,255]]}')
            f.flush()

        try:
            result = FileValidator.validate_json_file(f.name)
            assert result.is_valid is True
            assert result.error_message is None
        finally:
            Path(f.name).unlink()

    def test_validate_json_file_invalid_extension(self):
        """Test JSON file with wrong extension"""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write('{"valid": "json"}')
            f.flush()

        try:
            result = FileValidator.validate_json_file(f.name)
            assert result.is_valid is False
            assert result.error_message is not None
            assert "Invalid file extension" in result.error_message
        finally:
            Path(f.name).unlink()

    def test_validate_json_file_too_large(self):
        """Test JSON file that's too large"""
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            # Write more than 1MB
            f.write('{"data": "' + ("x" * (1024 * 1024 + 100)) + '"}')
            f.flush()

        try:
            result = FileValidator.validate_json_file(f.name)
            assert result.is_valid is False
            assert result.error_message is not None
            assert "File too large" in result.error_message
        finally:
            Path(f.name).unlink()


class TestValidationEdgeCases:
    """Test edge cases in validation"""

    def test_empty_file_path(self):
        """Test validation with empty file path"""
        result = FileValidator.validate_vram_file("")
        # Empty path is rejected with specific error message
        assert result.is_valid is False
        assert result.error_message is not None
        assert "empty" in result.error_message.lower()

    def test_directory_instead_of_file(self):
        """Test validation with directory path"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = FileValidator.validate_vram_file(tmpdir)
            assert result.is_valid is False
            assert result.error_message is not None
            assert "not a file" in result.error_message

    def test_file_with_multiple_extensions(self):
        """Test file with multiple extensions"""
        with tempfile.NamedTemporaryFile(suffix=".backup.dmp", delete=False) as f:
            f.write(b"\x00" * 65536)
            f.flush()

        try:
            result = FileValidator.validate_vram_file(f.name)
            assert result.is_valid is True  # Should work with .dmp extension
        finally:
            Path(f.name).unlink()


class TestOffsetValidation:
    """Test offset validation function"""

    def test_validate_offset_valid(self):
        """Test valid offset"""
        result = FileValidator.validate_offset(0x4000, 0x10000)
        assert result.is_valid is True
        assert result.error_message is None

    def test_validate_offset_negative(self):
        """Test negative offset"""
        result = FileValidator.validate_offset(-1, 0x10000)
        assert result.is_valid is False
        assert result.error_message is not None
        assert "cannot be negative" in result.error_message

    def test_validate_offset_too_large(self):
        """Test offset exceeding maximum"""
        result = FileValidator.validate_offset(0x10000, 0x10000)
        assert result.is_valid is False
        assert result.error_message is not None
        assert "exceeds maximum" in result.error_message

    def test_validate_offset_at_boundary(self):
        """Test offset at boundary"""
        result = FileValidator.validate_offset(0xFFFF, 0x10000)
        assert result.is_valid is True
        assert result.error_message is None


class TestTileCountValidation:
    """Test tile count validation"""

    def test_validate_tile_count_valid(self):
        """Test valid tile count"""
        result = FormatValidator.validate_tile_count(100)
        assert result.is_valid is True
        assert result.error_message is None

    def test_validate_tile_count_negative(self):
        """Test negative tile count"""
        result = FormatValidator.validate_tile_count(-10)
        assert result.is_valid is False
        assert result.error_message is not None
        assert "cannot be negative" in result.error_message

    def test_validate_tile_count_too_large(self):
        """Test tile count exceeding maximum"""
        result = FormatValidator.validate_tile_count(10000)
        assert result.is_valid is False
        assert result.error_message is not None
        assert "exceeds maximum" in result.error_message

    def test_validate_tile_count_custom_max(self):
        """Test tile count with custom maximum"""
        result = FormatValidator.validate_tile_count(50, max_count=100)
        assert result.is_valid is True

        result = FormatValidator.validate_tile_count(150, max_count=100)
        assert result.is_valid is False


class TestFilenameeSanitization:
    """Test filename sanitization"""

    def test_sanitize_filename_normal(self):
        """Test sanitizing normal filename"""
        result = sanitize_filename("normal_file.png")
        assert result == "normal_file.png"

    def test_sanitize_filename_with_path(self):
        """Test sanitizing filename with path"""
        result = sanitize_filename("/path/to/file.png")
        assert result == "file.png"

        # Test Windows-style path - backslash is NOT in invalid_chars
        result = sanitize_filename("..\\..\\file.png")
        # On Linux, basename doesn't recognize backslashes as path separators
        # And backslash is not in the invalid_chars list, so it remains
        assert result == "\\..\\file.png"  # Leading dots are stripped

    def test_sanitize_filename_invalid_chars(self):
        """Test sanitizing filename with invalid characters"""
        result = sanitize_filename('file<>:"|?*.png')
        assert result == "file_______.png"

    def test_sanitize_filename_leading_trailing(self):
        """Test sanitizing filename with leading/trailing dots and spaces"""
        result = sanitize_filename("  ..file.png..  ")
        assert result == "file.png"

    def test_sanitize_filename_empty(self):
        """Test sanitizing empty filename"""
        result = sanitize_filename("")
        assert result == "unnamed"

        result = sanitize_filename("   ")
        assert result == "unnamed"

    def test_sanitize_filename_null_byte(self):
        """Test sanitizing filename with null byte"""
        result = sanitize_filename("file\x00.png")
        assert result == "file_.png"
