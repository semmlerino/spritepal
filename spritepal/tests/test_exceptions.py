"""Tests for custom exceptions"""
from __future__ import annotations

import pytest

from core.exceptions import (
    CGRAMError,
    ExtractionError,
    FileFormatError,
    InjectionError,
    OAMError,
    SpritePalError,
    TileError,
    ValidationError,
    VRAMError,
)

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.no_manager_setup,
]

class TestExceptions:
    """Test custom exception classes"""

    def test_sprite_pal_error_base(self):
        """Test base SpritePalError"""
        with pytest.raises(SpritePalError) as exc_info:
            raise SpritePalError("Test error message")

        assert str(exc_info.value) == "Test error message"

    def test_vram_error(self):
        """Test VRAMError inherits from SpritePalError"""
        with pytest.raises(VRAMError) as exc_info:
            raise VRAMError("VRAM read error")

        assert str(exc_info.value) == "VRAM read error"
        assert isinstance(exc_info.value, SpritePalError)

    def test_cgram_error(self):
        """Test CGRAMError"""
        with pytest.raises(CGRAMError) as exc_info:
            raise CGRAMError("Invalid palette data")

        assert str(exc_info.value) == "Invalid palette data"
        assert isinstance(exc_info.value, SpritePalError)

    def test_oam_error(self):
        """Test OAMError"""
        with pytest.raises(OAMError) as exc_info:
            raise OAMError("OAM data corrupted")

        assert str(exc_info.value) == "OAM data corrupted"
        assert isinstance(exc_info.value, SpritePalError)

    def test_extraction_error(self):
        """Test ExtractionError"""
        with pytest.raises(ExtractionError) as exc_info:
            raise ExtractionError("Failed to extract tiles")

        assert str(exc_info.value) == "Failed to extract tiles"
        assert isinstance(exc_info.value, SpritePalError)

    def test_injection_error(self):
        """Test InjectionError"""
        with pytest.raises(InjectionError) as exc_info:
            raise InjectionError("Failed to inject sprite")

        assert str(exc_info.value) == "Failed to inject sprite"
        assert isinstance(exc_info.value, SpritePalError)

    def test_validation_error(self):
        """Test ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("File validation failed")

        assert str(exc_info.value) == "File validation failed"
        assert isinstance(exc_info.value, SpritePalError)

    def test_file_format_error(self):
        """Test FileFormatError"""
        with pytest.raises(FileFormatError) as exc_info:
            raise FileFormatError("Unsupported file format")

        assert str(exc_info.value) == "Unsupported file format"
        assert isinstance(exc_info.value, SpritePalError)

    def test_tile_error(self):
        """Test TileError"""
        with pytest.raises(TileError) as exc_info:
            raise TileError("Invalid tile data")

        assert str(exc_info.value) == "Invalid tile data"
        assert isinstance(exc_info.value, SpritePalError)

    def test_exception_with_no_message(self):
        """Test exceptions with no message"""
        with pytest.raises(SpritePalError) as exc_info:
            raise SpritePalError

        # Should have empty string or default message
        assert str(exc_info.value) == ""

    def test_exception_inheritance_chain(self):
        """Test that all custom exceptions inherit from SpritePalError"""
        exceptions = [
            VRAMError("test"),
            CGRAMError("test"),
            OAMError("test"),
            ExtractionError("test"),
            InjectionError("test"),
            ValidationError("test"),
            FileFormatError("test"),
            TileError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, SpritePalError)
            assert isinstance(exc, Exception)

    def test_exception_catch_hierarchy(self):
        """Test exception catch hierarchy"""
        # Should be able to catch specific exception
        with pytest.raises(ExtractionError):
            raise ExtractionError("specific")

        # Should be able to catch with base class
        with pytest.raises(SpritePalError):
            raise ExtractionError("base catch")

    def test_exception_attributes(self):
        """Test exception can carry additional attributes"""
        error = ValidationError("File too large")
        error.file_path = "/path/to/file"
        error.size = 1024

        assert error.file_path == "/path/to/file"
        assert error.size == 1024
        assert str(error) == "File too large"
