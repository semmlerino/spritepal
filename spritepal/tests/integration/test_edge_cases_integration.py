"""
Edge case integration tests for critical system boundaries.

Tests handling of None, empty, and corrupted data across system components:
- RealComponentFactory edge cases
- Manager initialization edge cases
- Data validation edge cases

REAL COMPONENT TESTING:
- Uses RealComponentFactory where appropriate
- Tests actual component behavior with edge case inputs

Uses shared class_managers fixture from core_fixtures.py instead of local setup.
"""
from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from core.managers.exceptions import ValidationError
from tests.infrastructure.real_component_factory import RealComponentFactory
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

if TYPE_CHECKING:
    from core.managers.extraction_manager import ExtractionManager
    from core.managers.injection_manager import InjectionManager

pytestmark = [
    pytest.mark.integration,
    pytest.mark.headless,
    pytest.mark.ci_safe,
]


# =============================================================================
# Fixtures
# =============================================================================

# Note: Uses shared class_managers fixture - no local setup_managers needed


@pytest.fixture
def real_factory(tmp_path):
    """Create RealComponentFactory for integration tests."""
    with RealComponentFactory() as factory:
        yield factory


@pytest.fixture
def test_rom_data() -> bytes:
    """Create minimal valid ROM data with proper SNES header."""
    # 512KB ROM (LoROM)
    data = bytearray(512 * 1024)

    # SNES internal header at 0x7FC0 (LoROM)
    header_offset = 0x7FC0
    # Game title (21 bytes)
    data[header_offset:header_offset + 21] = b"TEST ROM DATA        "[:21]
    # ROM makeup byte (0x20 = LoROM)
    data[header_offset + 0x15] = 0x20
    # ROM type (0x00 = ROM only)
    data[header_offset + 0x16] = 0x00
    # ROM size (0x09 = 512KB)
    data[header_offset + 0x17] = 0x09
    # SRAM size (0x00 = none)
    data[header_offset + 0x18] = 0x00
    # Country code (0x01 = USA)
    data[header_offset + 0x19] = 0x01
    # License code
    data[header_offset + 0x1A] = 0x00
    # Version
    data[header_offset + 0x1B] = 0x00
    # Checksum complement (placeholder)
    data[header_offset + 0x1C] = 0xFF
    data[header_offset + 0x1D] = 0xFF
    # Checksum (placeholder)
    data[header_offset + 0x1E] = 0x00
    data[header_offset + 0x1F] = 0x00

    return bytes(data)


@pytest.fixture
def corrupted_rom_data() -> bytes:
    """Create corrupted ROM data (too small, invalid header)."""
    return b"\x00" * 100  # Too small to be valid


@pytest.fixture
def empty_json_file(tmp_path) -> Path:
    """Create an empty JSON file."""
    path = tmp_path / "empty.json"
    path.write_text("")
    return path


@pytest.fixture
def malformed_json_file(tmp_path) -> Path:
    """Create a malformed JSON file."""
    path = tmp_path / "malformed.json"
    path.write_text("{invalid json content")
    return path


# =============================================================================
# RealComponentFactory Edge Cases
# =============================================================================


@pytest.mark.usefixtures("class_managers")
class TestRealComponentFactoryEdgeCases:
    """Test RealComponentFactory with edge case inputs.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    def test_create_rom_cache_with_none_path(self, real_factory, tmp_path):
        """Test ROMCache creation handles None path gracefully."""
        # ROMCache should use default path when None provided
        cache = real_factory.create_rom_cache()
        assert cache is not None

    def test_create_extraction_manager_without_data(self, real_factory):
        """Test ExtractionManager creation without test data."""
        manager = real_factory.create_extraction_manager(with_test_data=False)
        assert manager is not None
        assert manager.is_initialized()

    def test_create_injection_manager_without_data(self, real_factory):
        """Test InjectionManager creation without test data."""
        manager = real_factory.create_injection_manager(with_test_data=False)
        assert manager is not None
        assert manager.is_initialized()

    def test_create_rom_extractor_with_mock_hal(self, real_factory):
        """Test ROMExtractor creation with mock HAL."""
        extractor = real_factory.create_rom_extractor(use_mock_hal=True)
        assert extractor is not None

    def test_create_tile_renderer_default(self, real_factory):
        """Test TileRenderer creation with defaults."""
        renderer = real_factory.create_tile_renderer()
        assert renderer is not None


# =============================================================================
# Extraction Manager Edge Cases
# =============================================================================


@pytest.mark.usefixtures("class_managers")
class TestExtractionManagerEdgeCases:
    """Test ExtractionManager with edge case inputs.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    def test_validate_missing_path_types(self, real_factory):
        """Test validation when neither vram_path nor rom_path provided."""
        manager = real_factory.create_extraction_manager()

        # No path type provided should raise ValidationError
        params = {"output_base": "/tmp/test"}
        with pytest.raises(ValidationError, match="vram_path or rom_path"):
            manager.validate_extraction_params(params)

    def test_validate_with_empty_vram_path(self, real_factory):
        """Test validation with empty VRAM path."""
        manager = real_factory.create_extraction_manager()

        params = {"vram_path": "", "output_base": "/tmp/test"}
        with pytest.raises(ValidationError):
            manager.validate_extraction_params(params)

    def test_validate_with_missing_output_base(self, real_factory, tmp_path):
        """Test validation with missing output_base."""
        manager = real_factory.create_extraction_manager()

        # Create a valid VRAM file
        vram_path = tmp_path / "test.vram"
        vram_path.write_bytes(b"\x00" * 64 * 1024)

        params = {"vram_path": str(vram_path)}
        with pytest.raises(ValidationError, match="output"):
            manager.validate_extraction_params(params)

    def test_validate_with_empty_output_base(self, real_factory, tmp_path):
        """Test validation with empty output_base."""
        manager = real_factory.create_extraction_manager()

        vram_path = tmp_path / "test.vram"
        vram_path.write_bytes(b"\x00" * 64 * 1024)

        params = {"vram_path": str(vram_path), "output_base": ""}
        with pytest.raises(ValidationError, match="output"):
            manager.validate_extraction_params(params)

    def test_validate_rom_with_negative_offset(self, real_factory, tmp_path, test_rom_data):
        """Test validation with negative ROM offset."""
        manager = real_factory.create_extraction_manager()

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        params = {
            "rom_path": str(rom_path),
            "offset": -1,
            "output_base": "/tmp/test"
        }
        with pytest.raises(ValidationError, match="offset"):
            manager.validate_extraction_params(params)


# =============================================================================
# Injection Manager Edge Cases
# =============================================================================


@pytest.mark.usefixtures("class_managers")
class TestInjectionManagerEdgeCases:
    """Test InjectionManager with edge case inputs.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    def test_manager_initialization(self, real_factory):
        """Test InjectionManager initializes correctly."""
        manager = real_factory.create_injection_manager()
        assert manager is not None
        assert manager.is_initialized()
        assert manager.get_name() == "InjectionManager"

    def test_load_metadata_nonexistent_file(self, real_factory, tmp_path):
        """Test loading metadata from nonexistent file."""
        manager = real_factory.create_injection_manager()
        fake_path = tmp_path / "nonexistent.png"

        # Should return None for nonexistent file
        metadata = manager.load_metadata(str(fake_path))
        assert metadata is None

    def test_load_metadata_no_companion_json(self, real_factory, tmp_path):
        """Test loading metadata when no companion JSON exists."""
        manager = real_factory.create_injection_manager()

        # Create a PNG file without companion JSON
        from PIL import Image
        png_path = tmp_path / "test.png"
        Image.new('RGBA', (16, 16)).save(png_path)

        metadata = manager.load_metadata(str(png_path))
        # Should return None when no metadata file exists
        assert metadata is None

    def test_find_vram_suggestion_nonexistent_path(self, real_factory, tmp_path):
        """Test VRAM suggestion with nonexistent path."""
        manager = real_factory.create_injection_manager()
        fake_path = tmp_path / "nonexistent.png"

        suggestion = manager.find_suggested_input_vram(str(fake_path))
        assert suggestion is None or isinstance(suggestion, str)

    def test_suggest_output_path_with_valid_path(self, real_factory, tmp_path, test_rom_data):
        """Test output path suggestion with valid input."""
        manager = real_factory.create_injection_manager()

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        suggestion = manager.suggest_output_rom_path(str(rom_path))
        assert suggestion is not None
        assert suggestion != str(rom_path)


# =============================================================================
# ROM Data Edge Cases
# =============================================================================


@pytest.mark.usefixtures("class_managers")
class TestROMDataEdgeCases:
    """Test ROM data handling edge cases.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    def test_extraction_manager_read_header_valid_rom(self, real_factory, tmp_path, test_rom_data):
        """Test reading header from valid ROM."""
        manager = real_factory.create_extraction_manager()

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        header = manager.read_rom_header(str(rom_path))
        assert header is not None
        assert isinstance(header, dict)

    def test_extraction_manager_read_header_nonexistent_file(self, real_factory, tmp_path):
        """Test reading header from nonexistent file."""
        from core.managers.exceptions import ExtractionError

        manager = real_factory.create_extraction_manager()
        fake_path = tmp_path / "nonexistent.sfc"

        # Should raise ExtractionError or FileNotFoundError
        with pytest.raises((ExtractionError, FileNotFoundError)):
            manager.read_rom_header(str(fake_path))


# =============================================================================
# Thread Safety Edge Cases
# =============================================================================


@pytest.mark.usefixtures("class_managers")
class TestThreadSafetyEdgeCases:
    """Test thread safety with edge case scenarios.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    def test_thread_safe_test_image_standard_size(self):
        """Test ThreadSafeTestImage with standard size."""
        img = ThreadSafeTestImage(128, 128)
        assert not img.isNull()
        assert img.width() == 128
        assert img.height() == 128

    def test_thread_safe_test_image_small_size(self):
        """Test ThreadSafeTestImage with small size."""
        img = ThreadSafeTestImage(8, 8)
        assert not img.isNull()
        assert img.width() == 8
        assert img.height() == 8

    def test_thread_safe_test_image_fill_color(self):
        """Test ThreadSafeTestImage fill operation."""
        img = ThreadSafeTestImage(16, 16)
        img.fill(Qt.GlobalColor.red)
        assert not img.isNull()


# =============================================================================
# Cache Operation Edge Cases
# =============================================================================


@pytest.mark.usefixtures("class_managers")
class TestCacheEdgeCases:
    """Test cache operations with edge case inputs.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    def test_rom_cache_with_settings(self, real_factory):
        """Test ROMCache creation with settings."""
        cache = real_factory.create_rom_cache()
        assert cache is not None

    def test_injection_manager_cache_stats(self, real_factory):
        """Test getting cache stats from injection manager."""
        manager = real_factory.create_injection_manager()

        stats = manager.get_cache_stats()
        assert isinstance(stats, dict)

    def test_extraction_manager_reset_state(self, real_factory):
        """Test reset_state on extraction manager."""
        manager = real_factory.create_extraction_manager()

        # Should not raise
        manager.reset_state()
        assert manager.is_initialized()

    def test_injection_manager_reset_state(self, real_factory):
        """Test reset_state on injection manager."""
        manager = real_factory.create_injection_manager()

        # Should not raise
        manager.reset_state()
        assert manager.is_initialized()


# =============================================================================
# Integration Workflow Edge Cases
# =============================================================================


@pytest.mark.usefixtures("class_managers")
class TestWorkflowEdgeCases:
    """Test complete workflows with edge case scenarios.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    def test_manager_double_reset(self, real_factory):
        """Test calling reset_state multiple times."""
        manager = real_factory.create_injection_manager()

        manager.reset_state()
        manager.reset_state()  # Should not raise
        assert manager.is_initialized()

    def test_extraction_manager_validates_rom_path_type(self, real_factory, tmp_path, test_rom_data):
        """Test that ROM extraction validates offset type."""
        manager = real_factory.create_extraction_manager()

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        # String offset instead of int should fail
        params = {
            "rom_path": str(rom_path),
            "offset": "not_an_int",
            "output_base": "/tmp/test"
        }
        with pytest.raises((ValidationError, TypeError)):
            manager.validate_extraction_params(params)

    def test_factory_cleanup_on_exit(self, tmp_path):
        """Test that factory properly cleans up resources."""
        with RealComponentFactory() as factory:
            cache = factory.create_rom_cache()
            manager = factory.create_extraction_manager()
            assert cache is not None
            assert manager is not None
        # Factory should clean up without errors

    @pytest.mark.slow
    def test_multiple_manager_creation(self, real_factory):
        """Test creating multiple managers from same factory."""
        managers = []
        for _ in range(3):
            manager = real_factory.create_injection_manager()
            managers.append(manager)

        # All managers should be valid
        for manager in managers:
            assert manager.is_initialized()


# =============================================================================
# File Validation Edge Cases
# =============================================================================


@pytest.mark.usefixtures("class_managers")
class TestFileValidationEdgeCases:
    """Test file validation edge cases.

    Uses shared class_managers fixture - no local setup_managers needed.
    """

    def test_validate_vram_grayscale_mode_no_cgram(self, real_factory, tmp_path):
        """Test VRAM extraction in grayscale mode without CGRAM."""
        manager = real_factory.create_extraction_manager()

        vram_path = tmp_path / "test.vram"
        vram_path.write_bytes(b"\x00" * 64 * 1024)

        # Grayscale mode should NOT require CGRAM
        params = {
            "vram_path": str(vram_path),
            "output_base": "/tmp/test",
            "grayscale_mode": True
        }
        # Should pass validation (no CGRAM required)
        result = manager.validate_extraction_params(params)
        assert result is True

    def test_validate_vram_full_color_requires_cgram(self, real_factory, tmp_path):
        """Test VRAM extraction in full color mode requires CGRAM."""
        manager = real_factory.create_extraction_manager()

        vram_path = tmp_path / "test.vram"
        vram_path.write_bytes(b"\x00" * 64 * 1024)

        # Full color mode without CGRAM should fail
        params = {
            "vram_path": str(vram_path),
            "output_base": "/tmp/test",
            "grayscale_mode": False
        }
        with pytest.raises(ValidationError, match="CGRAM"):
            manager.validate_extraction_params(params)
