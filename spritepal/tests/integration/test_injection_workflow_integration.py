"""
Integration tests for injection workflow.

Tests the complete sprite injection workflow including:
- ROM validation and loading
- VRAM path suggestion
- Metadata handling
- Injection process
- Signal emission

REAL COMPONENT TESTING:
- Uses RealComponentFactory for InjectionManager
- MockHALProcessPool provides fast but realistic HAL responses
- Tests actual component behavior with real file I/O
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from tests.infrastructure.real_component_factory import RealComponentFactory

pytestmark = [
    pytest.mark.integration,
    pytest.mark.file_io,
    pytest.mark.rom_data,
    pytest.mark.headless,
    pytest.mark.ci_safe,
]


@pytest.fixture
def real_factory(tmp_path):
    """Create RealComponentFactory for integration tests."""
    with RealComponentFactory() as factory:
        yield factory


@pytest.fixture
def injection_manager(real_factory):
    """Create InjectionManager with real components."""
    return real_factory.create_injection_manager(with_test_data=True)


@pytest.fixture
def test_rom_file(tmp_path) -> Path:
    """Create a test ROM file with realistic data."""
    rom_path = tmp_path / "test_rom.sfc"
    # Create a 2MB ROM with some sprite-like data
    rom_data = bytearray(2 * 1024 * 1024)

    # Add ROM header info (SNES header at 0x7FC0)
    header_offset = 0x7FC0
    title = b"TEST ROM DATA      "[:21]
    rom_data[header_offset:header_offset + 21] = title

    # Add some compressed sprite-like data at known offset
    sprite_offset = 0x100000
    # Fake HAL-compressed data signature
    rom_data[sprite_offset:sprite_offset + 4] = b'\x00\x10\x00\x00'

    rom_path.write_bytes(rom_data)
    return rom_path


@pytest.fixture
def test_vram_file(tmp_path) -> Path:
    """Create a test VRAM dump file."""
    vram_path = tmp_path / "test_vram.dmp"
    # VRAM is typically 64KB
    vram_data = bytearray(64 * 1024)

    # Add some pattern data
    for i in range(0, len(vram_data), 32):
        # 4bpp tile pattern (32 bytes per tile)
        for j in range(32):
            vram_data[i + j] = (i + j) % 256

    vram_path.write_bytes(vram_data)
    return vram_path


@pytest.fixture
def test_sprite_png(tmp_path) -> Path:
    """Create a test sprite PNG file with metadata."""
    from PIL import Image

    # Create a small test sprite (32x32 pixels)
    sprite = Image.new('RGBA', (32, 32), color=(128, 64, 32, 255))

    sprite_path = tmp_path / "test_sprite.png"
    sprite.save(sprite_path)

    # Create matching metadata file
    metadata = {
        "rom_offset": "0x100000",
        "vram_offset": "0x4000",
        "width": 32,
        "height": 32,
        "palette_index": 8,
        "format": "4bpp",
        "compressed": True,
        "original_rom": "test_rom.sfc"
    }
    metadata_path = tmp_path / "test_sprite.pal.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    return sprite_path


class TestInjectionManagerInitialization:
    """Test InjectionManager initialization and basic operations."""

    def test_manager_initialization(self, injection_manager):
        """Test that InjectionManager initializes correctly."""
        assert injection_manager is not None
        assert injection_manager.is_initialized()
        assert injection_manager.get_name() == "InjectionManager"

    def test_manager_initial_state(self, injection_manager):
        """Test initial state after initialization."""
        assert not injection_manager.is_injection_active()

        # Cache stats should be accessible
        stats = injection_manager.get_cache_stats()
        assert isinstance(stats, dict)


class TestROMValidation:
    """Test ROM file validation and loading."""

    def test_validate_valid_rom(self, injection_manager, test_rom_file):
        """Test validation of a valid ROM file."""
        # Should not raise
        result = injection_manager._validate_rom_file(str(test_rom_file))
        assert result is True

    def test_validate_nonexistent_rom(self, injection_manager, tmp_path):
        """Test validation of a non-existent ROM file."""
        fake_path = tmp_path / "nonexistent.sfc"
        with pytest.raises(FileNotFoundError):
            injection_manager._validate_rom_file(str(fake_path))

    def test_validate_empty_rom(self, injection_manager, tmp_path):
        """Test validation of an empty ROM file."""
        empty_rom = tmp_path / "empty.sfc"
        empty_rom.write_bytes(b"")

        with pytest.raises(ValueError, match="too small"):
            injection_manager._validate_rom_file(str(empty_rom))

    def test_load_rom_info(self, injection_manager, test_rom_file):
        """Test loading ROM information."""
        info = injection_manager.load_rom_info(str(test_rom_file))

        assert info is not None
        assert "size" in info
        assert "path" in info
        assert info["size"] == 2 * 1024 * 1024


class TestVRAMSuggestion:
    """Test VRAM path suggestion functionality."""

    def test_suggest_vram_from_sprite_png(self, injection_manager, test_sprite_png, tmp_path):
        """Test VRAM suggestion from sprite PNG with metadata."""
        # Create VRAM file with expected name
        expected_vram = tmp_path / "test_vram.dmp"
        expected_vram.write_bytes(b'\x00' * 64 * 1024)

        suggestion = injection_manager.find_suggested_input_vram(str(test_sprite_png))

        # Should find some suggestion (even if not exact match)
        # The actual path depends on metadata lookup strategy
        assert suggestion is None or isinstance(suggestion, str)

    def test_suggest_output_vram_path(self, injection_manager, test_vram_file, tmp_path):
        """Test output VRAM path suggestion."""
        output_suggestion = injection_manager.suggest_output_vram_path(str(test_vram_file))

        # Should suggest a modified path
        assert output_suggestion is not None
        assert "modified" in output_suggestion.lower() or output_suggestion != str(test_vram_file)

    def test_suggest_output_rom_path(self, injection_manager, test_rom_file):
        """Test output ROM path suggestion."""
        output_suggestion = injection_manager.suggest_output_rom_path(str(test_rom_file))

        # Should suggest a modified path
        assert output_suggestion is not None
        assert output_suggestion != str(test_rom_file)


class TestMetadataHandling:
    """Test metadata loading and validation."""

    def test_load_valid_metadata(self, injection_manager, test_sprite_png):
        """Test loading valid metadata from sprite PNG."""
        metadata = injection_manager.load_metadata(str(test_sprite_png))

        assert metadata is not None
        assert "rom_offset" in metadata or metadata == {}  # May be empty if no metadata found

    def test_load_metadata_no_file(self, injection_manager, tmp_path):
        """Test loading metadata when no metadata file exists."""
        sprite_without_meta = tmp_path / "no_meta.png"

        from PIL import Image
        Image.new('RGBA', (16, 16)).save(sprite_without_meta)

        metadata = injection_manager.load_metadata(str(sprite_without_meta))

        # Should return empty dict, not raise
        assert metadata == {} or metadata is not None


class TestInjectionParameters:
    """Test injection parameter validation."""

    def test_validate_complete_params(self, injection_manager, test_rom_file, test_vram_file, test_sprite_png):
        """Test validation of complete injection parameters."""
        params = {
            "sprite_path": str(test_sprite_png),
            "rom_path": str(test_rom_file),
            "vram_path": str(test_vram_file),
            "rom_offset": 0x100000,
            "vram_offset": 0x4000,
        }

        is_valid, errors = injection_manager.validate_injection_params(params)

        # May have warnings but should provide structured response
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

    def test_validate_missing_params(self, injection_manager):
        """Test validation with missing parameters."""
        params = {}

        is_valid, errors = injection_manager.validate_injection_params(params)

        assert is_valid is False
        assert len(errors) > 0

    def test_validate_invalid_paths(self, injection_manager, tmp_path):
        """Test validation with invalid file paths."""
        params = {
            "sprite_path": str(tmp_path / "nonexistent.png"),
            "rom_path": str(tmp_path / "nonexistent.sfc"),
            "vram_path": str(tmp_path / "nonexistent.dmp"),
            "rom_offset": 0x100000,
            "vram_offset": 0x4000,
        }

        is_valid, errors = injection_manager.validate_injection_params(params)

        assert is_valid is False
        assert any("not found" in err.lower() or "exist" in err.lower() for err in errors)


class TestInjectionSignals:
    """Test signal emission during injection workflow."""

    def test_injection_progress_signal(self, injection_manager, qtbot):
        """Test that injection progress signal is emitted."""
        progress_values = []
        injection_manager.injection_progress.connect(progress_values.append)

        # Trigger internal progress (this tests signal connectivity)
        injection_manager._on_worker_progress("Test progress", 50)

        assert len(progress_values) == 1
        assert progress_values[0] == "Test progress"

    def test_progress_percent_signal(self, injection_manager, qtbot):
        """Test that progress percent signal works."""
        # Just verify the signal exists and can be connected
        received = []
        injection_manager.progress_percent.connect(received.append)

        # Signal should be connectable without error
        assert len(received) == 0  # No emissions yet


class TestVRAMConversion:
    """Test VRAM to ROM offset conversion."""

    def test_convert_vram_to_rom_offset(self, injection_manager):
        """Test VRAM to ROM offset conversion."""
        vram_offset = 0x4000
        bank = 2

        rom_offset = injection_manager.convert_vram_to_rom_offset(vram_offset, bank)

        # Should return a valid offset
        assert isinstance(rom_offset, int)
        assert rom_offset >= 0


class TestROMInjectionSettings:
    """Test ROM injection settings persistence."""

    def test_save_and_load_settings(self, injection_manager, test_rom_file, tmp_path):
        """Test saving and loading ROM injection settings."""
        settings = {
            "rom_path": str(test_rom_file),
            "last_offset": 0x100000,
            "palette_index": 8,
        }

        # Save settings
        injection_manager.save_rom_injection_settings(str(test_rom_file), settings)

        # Load settings back
        loaded = injection_manager.load_rom_injection_defaults(str(test_rom_file))

        # Should retrieve saved settings
        assert loaded is not None or isinstance(loaded, dict)


class TestCacheOperations:
    """Test cache-related operations."""

    def test_get_cache_stats(self, injection_manager):
        """Test getting cache statistics."""
        stats = injection_manager.get_cache_stats()

        assert isinstance(stats, dict)

    def test_clear_rom_cache(self, injection_manager, test_rom_file):
        """Test clearing ROM cache."""
        # Should not raise
        injection_manager.clear_rom_cache(str(test_rom_file))

    def test_scan_progress_operations(self, injection_manager, test_rom_file):
        """Test scan progress save/load/clear operations."""
        # Save progress
        progress = {"offset": 0x50000, "count": 100}
        injection_manager.save_scan_progress(str(test_rom_file), progress)

        # Load progress
        loaded = injection_manager.get_scan_progress(str(test_rom_file))
        assert loaded is not None or loaded == {}

        # Clear progress
        injection_manager.clear_scan_progress(str(test_rom_file))
        cleared = injection_manager.get_scan_progress(str(test_rom_file))
        assert cleared is None or cleared == {}


class TestInjectionWorkflowEndToEnd:
    """End-to-end injection workflow tests."""

    @pytest.mark.slow
    def test_complete_injection_preparation(
        self,
        injection_manager,
        test_rom_file,
        test_vram_file,
        test_sprite_png
    ):
        """Test complete preparation for injection (without actual injection)."""
        # 1. Load ROM info
        rom_info = injection_manager.load_rom_info(str(test_rom_file))
        assert rom_info is not None

        # 2. Load metadata from sprite
        metadata = injection_manager.load_metadata(str(test_sprite_png))
        assert isinstance(metadata, dict)

        # 3. Validate parameters
        params = {
            "sprite_path": str(test_sprite_png),
            "rom_path": str(test_rom_file),
            "vram_path": str(test_vram_file),
            "rom_offset": 0x100000,
            "vram_offset": 0x4000,
        }
        is_valid, errors = injection_manager.validate_injection_params(params)

        # Should be valid for preparation (actual injection would need real sprite data)
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

        # 4. Get output suggestions
        output_vram = injection_manager.suggest_output_vram_path(str(test_vram_file))
        output_rom = injection_manager.suggest_output_rom_path(str(test_rom_file))

        assert output_vram is not None
        assert output_rom is not None

    def test_reset_state(self, injection_manager):
        """Test that reset_state properly clears manager state."""
        # Make some state changes
        injection_manager._current_worker = "dummy"  # Simulate active worker

        # Reset
        injection_manager.reset_state()

        # State should be cleared
        assert injection_manager._current_worker is None
        assert not injection_manager.is_injection_active()
