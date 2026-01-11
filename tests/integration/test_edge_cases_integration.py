"""
Edge case integration tests for critical system boundaries.

Tests handling of None, empty, and corrupted data across system components:
- RealComponentFactory edge cases
- Manager initialization edge cases
- Data validation edge cases

REAL COMPONENT TESTING:
- Uses RealComponentFactory where appropriate
- Tests actual component behavior with edge case inputs

Uses app_context fixture for proper test isolation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt

from core.exceptions import ValidationError
from tests.infrastructure.real_component_factory import RealComponentFactory
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

if TYPE_CHECKING:
    from core.app_context import AppContext
    from core.managers.core_operations_manager import CoreOperationsManager

# Use function-scoped app_context for proper test isolation
# (migrated from session_app_context to fix shared state and thread cleanup issues)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.headless,
    pytest.mark.usefixtures("app_context"),
]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def real_factory(tmp_path, app_context: AppContext):
    """Create RealComponentFactory for integration tests."""
    # context_guaranteed=True because app_context fixture guarantees context exists
    with RealComponentFactory(context_guaranteed=True) as factory:
        yield factory


@pytest.fixture
def core_manager(app_context: AppContext) -> CoreOperationsManager:
    """Get CoreOperationsManager from AppContext."""
    return app_context.core_operations_manager


@pytest.fixture
def test_rom_data() -> bytes:
    """Create minimal valid ROM data with proper SNES header."""
    # 512KB ROM (LoROM)
    data = bytearray(512 * 1024)

    # SNES internal header at 0x7FC0 (LoROM)
    header_offset = 0x7FC0
    # Game title (21 bytes)
    data[header_offset : header_offset + 21] = b"TEST ROM DATA        "[:21]
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


class TestRealComponentFactoryEdgeCases:
    """Test RealComponentFactory with edge case inputs.

    Uses shared session_managers fixture via module-level pytestmark.
    """

    def test_create_rom_cache_with_none_path(self, real_factory, tmp_path):
        """Test ROMCache creation handles None path gracefully."""
        # ROMCache should use default path when None provided
        cache = real_factory.create_rom_cache()
        assert cache is not None

    def test_core_operations_manager_initialized(self, core_manager):
        """Test CoreOperationsManager is properly initialized via AppContext."""
        assert core_manager is not None
        assert core_manager.is_initialized()
        assert core_manager.get_name() == "CoreOperationsManager"

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


class TestExtractionManagerEdgeCases:
    """Test ExtractionManager with edge case inputs.

    Uses shared session_managers fixture via module-level pytestmark.
    """

    def test_validate_missing_path_types(self, core_manager, tmp_path):
        """Test validation when neither vram_path nor rom_path provided."""
        manager = core_manager

        # No path type provided should raise ValidationError
        params = {"output_base": str(tmp_path / "test")}
        with pytest.raises(ValidationError, match="vram_path or rom_path"):
            manager.validate_extraction_params(params)

    def test_validate_with_empty_vram_path(self, core_manager, tmp_path):
        """Test validation with empty VRAM path."""
        manager = core_manager

        params = {"vram_path": "", "output_base": str(tmp_path / "test")}
        with pytest.raises(ValidationError):
            manager.validate_extraction_params(params)

    def test_validate_with_missing_output_base(self, core_manager, tmp_path):
        """Test validation with missing output_base."""
        manager = core_manager

        # Create a valid VRAM file
        vram_path = tmp_path / "test.vram"
        vram_path.write_bytes(b"\x00" * 64 * 1024)

        params = {"vram_path": str(vram_path)}
        with pytest.raises(ValidationError, match="output"):
            manager.validate_extraction_params(params)

    def test_validate_with_empty_output_base(self, core_manager, tmp_path):
        """Test validation with empty output_base."""
        manager = core_manager

        vram_path = tmp_path / "test.vram"
        vram_path.write_bytes(b"\x00" * 64 * 1024)

        params = {"vram_path": str(vram_path), "output_base": "", "grayscale_mode": True}
        with pytest.raises(ValidationError, match="(?i)output"):
            manager.validate_extraction_params(params)

    def test_validate_rom_with_negative_offset(self, core_manager, tmp_path, test_rom_data):
        """Test validation with negative ROM offset."""
        manager = core_manager

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        params = {
            "rom_path": str(rom_path),
            "offset": -1,
            "output_base": str(tmp_path / "test"),
        }
        with pytest.raises(ValidationError, match="offset"):
            manager.validate_extraction_params(params)


# =============================================================================
# Injection Manager Edge Cases
# =============================================================================


class TestInjectionManagerEdgeCases:
    """Test InjectionManager with edge case inputs.

    Uses shared session_managers fixture via module-level pytestmark.
    """

    def test_manager_initialization(self, core_manager):
        """Test InjectionManager initializes correctly."""
        manager = core_manager
        assert manager is not None
        assert manager.is_initialized()
        # Registry returns CoreOperationsManager (consolidated manager)
        assert manager.get_name() == "CoreOperationsManager"

    def test_load_metadata_nonexistent_file(self, core_manager, tmp_path):
        """Test loading metadata from nonexistent file."""
        manager = core_manager
        fake_path = tmp_path / "nonexistent.png"

        # Should return None for nonexistent file
        metadata = manager.load_metadata(str(fake_path))
        assert metadata is None

    def test_load_metadata_no_companion_json(self, core_manager, tmp_path):
        """Test loading metadata when no companion JSON exists."""
        manager = core_manager

        # Create a PNG file without companion JSON
        from PIL import Image

        png_path = tmp_path / "test.png"
        Image.new("RGBA", (16, 16)).save(png_path)

        metadata = manager.load_metadata(str(png_path))
        # Should return None when no metadata file exists
        assert metadata is None

    def test_find_vram_suggestion_nonexistent_path(self, core_manager, tmp_path):
        """Test VRAM suggestion with nonexistent path."""
        manager = core_manager
        fake_path = tmp_path / "nonexistent.png"

        suggestion = manager.find_suggested_input_vram(str(fake_path))
        assert suggestion is None or isinstance(suggestion, str)

    def test_suggest_output_path_with_valid_path(self, core_manager, tmp_path, test_rom_data):
        """Test output path suggestion with valid input."""
        manager = core_manager

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        suggestion = manager.suggest_output_rom_path(str(rom_path))
        assert suggestion is not None
        assert suggestion != str(rom_path)


# =============================================================================
# ROM Data Edge Cases
# =============================================================================


class TestROMDataEdgeCases:
    """Test ROM data handling edge cases.

    Uses shared session_managers fixture via module-level pytestmark.
    """

    def test_extraction_manager_read_header_valid_rom(self, core_manager, tmp_path, test_rom_data):
        """Test reading header from valid ROM."""
        manager = core_manager

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        header = manager.read_rom_header(str(rom_path))
        assert header is not None
        assert isinstance(header, dict)

    def test_extraction_manager_read_header_nonexistent_file(self, core_manager, tmp_path):
        """Test reading header from nonexistent file."""
        from core.exceptions import ExtractionError

        manager = core_manager
        fake_path = tmp_path / "nonexistent.sfc"

        # Should raise ExtractionError or FileNotFoundError
        with pytest.raises((ExtractionError, FileNotFoundError)):
            manager.read_rom_header(str(fake_path))


# =============================================================================
# Thread Safety Edge Cases
# =============================================================================


class TestThreadSafetyEdgeCases:
    """Test thread safety with edge case scenarios.

    Uses shared session_managers fixture via module-level pytestmark.
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


class TestCacheEdgeCases:
    """Test cache operations with edge case inputs.

    Uses shared session_managers fixture via module-level pytestmark.
    """

    def test_rom_cache_with_settings(self, real_factory):
        """Test ROMCache creation with settings."""
        cache = real_factory.create_rom_cache()
        assert cache is not None

    def test_injection_manager_cache_stats(self, core_manager):
        """Test getting cache stats from injection manager."""
        manager = core_manager

        stats = manager.get_cache_stats()
        assert isinstance(stats, dict)

    def test_extraction_manager_reset_state(self, core_manager):
        """Test reset_state on extraction manager."""
        manager = core_manager

        # Should not raise
        manager.reset_state()
        assert manager.is_initialized()

    def test_injection_manager_reset_state(self, core_manager):
        """Test reset_state on injection manager."""
        manager = core_manager

        # Should not raise
        manager.reset_state()
        assert manager.is_initialized()


# =============================================================================
# Integration Workflow Edge Cases
# =============================================================================


class TestWorkflowEdgeCases:
    """Test complete workflows with edge case scenarios.

    Uses shared session_managers fixture via module-level pytestmark.
    """

    def test_manager_double_reset(self, core_manager):
        """Test calling reset_state multiple times."""
        manager = core_manager

        manager.reset_state()
        manager.reset_state()  # Should not raise
        assert manager.is_initialized()

    def test_extraction_manager_validates_rom_path_type(self, core_manager, tmp_path, test_rom_data):
        """Test that ROM extraction validates offset type."""
        manager = core_manager

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        # String offset instead of int should fail
        params = {
            "rom_path": str(rom_path),
            "offset": "not_an_int",
            "output_base": str(tmp_path / "test"),
        }
        with pytest.raises((ValidationError, TypeError)):
            manager.validate_extraction_params(params)

    def test_factory_cleanup_on_exit(self, tmp_path, app_context: AppContext):
        """Test that factory properly cleans up resources."""
        # context_guaranteed=True because app_context fixture guarantees context exists
        with RealComponentFactory(context_guaranteed=True) as factory:
            cache = factory.create_rom_cache()
            renderer = factory.create_tile_renderer()
            assert cache is not None
            assert renderer is not None
        # Factory should clean up without errors

    @pytest.mark.slow
    def test_multiple_manager_access(self, core_manager):
        """Test accessing manager multiple times returns same instance."""
        managers = []
        for _ in range(3):
            manager = core_manager
            managers.append(manager)

        # All managers should be the same singleton
        for manager in managers:
            assert manager.is_initialized()
            assert manager is managers[0]


# =============================================================================
# File Validation Edge Cases
# =============================================================================


class TestFileValidationEdgeCases:
    """Test file validation edge cases.

    Uses shared session_managers fixture via module-level pytestmark.
    """

    def test_validate_vram_grayscale_mode_no_cgram(self, core_manager, tmp_path):
        """Test VRAM extraction in grayscale mode without CGRAM."""
        manager = core_manager

        vram_path = tmp_path / "test.vram"
        vram_path.write_bytes(b"\x00" * 64 * 1024)

        # Grayscale mode should NOT require CGRAM
        params = {
            "vram_path": str(vram_path),
            "output_base": str(tmp_path / "test"),
            "grayscale_mode": True,
        }
        # Should pass validation (no CGRAM required)
        result = manager.validate_extraction_params(params)
        assert result is True

    def test_validate_vram_full_color_requires_cgram(self, core_manager, tmp_path):
        """Test VRAM extraction in full color mode requires CGRAM."""
        manager = core_manager

        vram_path = tmp_path / "test.vram"
        vram_path.write_bytes(b"\x00" * 64 * 1024)

        # Full color mode without CGRAM should fail
        params = {
            "vram_path": str(vram_path),
            "output_base": str(tmp_path / "test"),
            "grayscale_mode": False,
        }
        with pytest.raises(ValidationError, match="CGRAM"):
            manager.validate_extraction_params(params)
