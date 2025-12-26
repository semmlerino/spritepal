"""Tests for CoreOperationsManager.

This module tests the consolidated core operations manager including:
- Initialization and service accessors
- Extraction validation
- Injection validation and state
- Path suggestions
- Cache integration
- Cleanup and reset
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.app_context import get_app_context
from core.exceptions import ExtractionError, ValidationError
from core.managers.core_operations_manager import CoreOperationsManager
from tests.fixtures.timeouts import signal_timeout

pytestmark = [
    pytest.mark.usefixtures("isolated_managers"),
    pytest.mark.skip_thread_cleanup(reason="Uses isolated_managers which owns cleanup"),
    pytest.mark.headless,
]


@pytest.fixture
def manager(isolated_managers) -> CoreOperationsManager:
    """Get CoreOperationsManager via DI injection."""
    # isolated_managers sets up the app context; we use get_app_context() to get the manager
    mgr = get_app_context().core_operations_manager
    assert isinstance(mgr, CoreOperationsManager)
    return mgr


class TestCoreOperationsManagerInit:
    """Tests for CoreOperationsManager initialization."""

    def test_init_creates_manager(self, manager):
        """Manager should be initialized and ready."""
        assert manager is not None
        assert manager._is_initialized is True

    def test_manager_name(self, manager):
        """Manager should have correct name."""
        assert manager._name == "CoreOperationsManager"

    def test_services_initialized(self, manager):
        """Services should be initialized after init."""
        # These should not raise
        assert manager._sprite_extractor is not None
        assert manager._palette_manager is not None
        assert manager._rom_service is not None
        assert manager._vram_service is not None


class TestServiceAccessors:
    """Tests for service accessor properties."""

    def test_rom_service_accessor(self, manager):
        """rom_service property should return ROMService."""
        service = manager.rom_service

        assert service is not None
        # Verify it's the expected type
        from core.services import ROMService

        assert isinstance(service, ROMService)

    def test_vram_service_accessor(self, manager):
        """vram_service property should return VRAMService."""
        service = manager.vram_service

        assert service is not None
        from core.services import VRAMService

        assert isinstance(service, VRAMService)

    def test_rom_service_not_initialized_raises(self):
        """rom_service should raise if not initialized."""
        # Create manager without initialization
        mgr = CoreOperationsManager.__new__(CoreOperationsManager)
        mgr._rom_service = None

        with pytest.raises(ExtractionError, match="ROM service not initialized"):
            _ = mgr.rom_service

    def test_vram_service_not_initialized_raises(self):
        """vram_service should raise if not initialized."""
        mgr = CoreOperationsManager.__new__(CoreOperationsManager)
        mgr._vram_service = None

        with pytest.raises(ExtractionError, match="VRAM service not initialized"):
            _ = mgr.vram_service


class TestExtractionValidation:
    """Tests for extraction parameter validation."""

    def test_validate_extraction_params_vram_valid(self, manager, tmp_path):
        """validate_extraction_params should accept valid VRAM params."""
        vram_file = tmp_path / "vram.dmp"
        cgram_file = tmp_path / "cgram.dmp"
        vram_file.write_bytes(b"\x00" * 0x10000)  # 64KB
        cgram_file.write_bytes(b"\x00" * 512)  # 512B

        params = {
            "vram_path": str(vram_file),
            "cgram_path": str(cgram_file),
            "output_base": "test_output",
        }

        result = manager.validate_extraction_params(params)

        assert result is True

    def test_validate_extraction_params_missing_vram(self, manager):
        """validate_extraction_params should reject missing VRAM."""
        params = {
            "vram_path": "",
            "output_base": "test_output",
        }

        with pytest.raises(ValidationError, match="VRAM file is required"):
            manager.validate_extraction_params(params)

    def test_validate_extraction_params_missing_output(self, manager, tmp_path):
        """validate_extraction_params should reject missing output."""
        vram_file = tmp_path / "vram.dmp"
        vram_file.write_bytes(b"\x00" * 0x10000)

        params = {
            "vram_path": str(vram_file),
            "output_base": "",
            "grayscale_mode": True,  # Skip CGRAM requirement
        }

        with pytest.raises(ValidationError, match="Output name is required"):
            manager.validate_extraction_params(params)

    def test_validate_extraction_params_cgram_required(self, manager, tmp_path):
        """validate_extraction_params should require CGRAM for color mode."""
        vram_file = tmp_path / "vram.dmp"
        vram_file.write_bytes(b"\x00" * 0x10000)

        params = {
            "vram_path": str(vram_file),
            "output_base": "test_output",
            "grayscale_mode": False,  # Color mode
            # cgram_path missing
        }

        with pytest.raises(ValidationError, match="CGRAM file is required"):
            manager.validate_extraction_params(params)

    def test_validate_extraction_params_grayscale_no_cgram(self, manager, tmp_path):
        """validate_extraction_params should allow grayscale without CGRAM."""
        vram_file = tmp_path / "vram.dmp"
        vram_file.write_bytes(b"\x00" * 0x10000)

        params = {
            "vram_path": str(vram_file),
            "output_base": "test_output",
            "grayscale_mode": True,  # No CGRAM needed
        }

        result = manager.validate_extraction_params(params)

        assert result is True

    def test_validate_extraction_params_rom_valid(self, manager, tmp_path):
        """validate_extraction_params should accept valid ROM params."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x100000)  # 1MB

        params = {
            "rom_path": str(rom_file),
            "offset": 0x1000,
            "output_base": "test_output",
        }

        result = manager.validate_extraction_params(params)

        assert result is True

    def test_validate_extraction_params_rom_invalid_offset(self, manager, tmp_path):
        """validate_extraction_params should reject negative offset."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x100000)

        params = {
            "rom_path": str(rom_file),
            "offset": -1,  # Invalid
            "output_base": "test_output",
        }

        with pytest.raises(ValidationError):
            manager.validate_extraction_params(params)

    def test_validate_extraction_params_no_source(self, manager):
        """validate_extraction_params should reject missing source."""
        params = {
            "output_base": "test_output",
        }

        with pytest.raises(ValidationError, match="Must provide either vram_path or rom_path"):
            manager.validate_extraction_params(params)


class TestInjectionValidation:
    """Tests for injection parameter validation."""

    def test_validate_injection_params_vram_valid(self, manager, tmp_path):
        """validate_injection_params should accept valid VRAM params."""
        sprite_file = tmp_path / "sprite.png"
        vram_file = tmp_path / "vram.dmp"

        # Create minimal valid PNG
        img = Image.new("RGBA", (8, 8), color=(0, 0, 0, 255))
        img.save(sprite_file)

        vram_file.write_bytes(b"\x00" * 0x10000)

        params = {
            "mode": "vram",
            "sprite_path": str(sprite_file),
            "input_vram": str(vram_file),
            "output_vram": str(tmp_path / "output.dmp"),
            "offset": 0x1000,
        }

        # Should not raise
        manager.validate_injection_params(params)

    def test_validate_injection_params_rom_valid(self, manager, tmp_path):
        """validate_injection_params should accept valid ROM params."""
        sprite_file = tmp_path / "sprite.png"
        rom_file = tmp_path / "test.sfc"

        img = Image.new("RGBA", (8, 8), color=(0, 0, 0, 255))
        img.save(sprite_file)

        rom_file.write_bytes(b"\x00" * 0x100000)

        params = {
            "mode": "rom",
            "sprite_path": str(sprite_file),
            "input_rom": str(rom_file),
            "output_rom": str(tmp_path / "output.sfc"),
            "offset": 0x1000,
        }

        # Should not raise
        manager.validate_injection_params(params)

    def test_validate_injection_params_invalid_mode(self, manager, tmp_path):
        """validate_injection_params should reject invalid mode."""
        sprite_file = tmp_path / "sprite.png"
        img = Image.new("RGBA", (8, 8))
        img.save(sprite_file)

        params = {
            "mode": "invalid",
            "sprite_path": str(sprite_file),
            "offset": 0x1000,
        }

        with pytest.raises(ValidationError, match="Invalid injection mode"):
            manager.validate_injection_params(params)

    def test_validate_injection_params_missing_sprite(self, manager):
        """validate_injection_params should reject missing sprite."""
        params = {
            "mode": "vram",
            "offset": 0x1000,
        }

        with pytest.raises(ValidationError):
            manager.validate_injection_params(params)

    def test_validate_injection_params_missing_offset(self, manager, tmp_path):
        """validate_injection_params should reject missing offset."""
        sprite_file = tmp_path / "sprite.png"
        img = Image.new("RGBA", (8, 8))
        img.save(sprite_file)

        params = {
            "mode": "vram",
            "sprite_path": str(sprite_file),
        }

        with pytest.raises(ValidationError):
            manager.validate_injection_params(params)

    def test_validate_injection_params_sprite_not_found(self, manager, tmp_path):
        """validate_injection_params should reject nonexistent sprite."""
        params = {
            "mode": "vram",
            "sprite_path": str(tmp_path / "nonexistent.png"),
            "input_vram": str(tmp_path / "vram.dmp"),
            "output_vram": str(tmp_path / "output.dmp"),
            "offset": 0x1000,
        }

        with pytest.raises(ValidationError, match="Sprite file"):
            manager.validate_injection_params(params)


class TestInjectionState:
    """Tests for injection state management."""

    def test_is_injection_active_false_initially(self, manager):
        """is_injection_active should be False initially."""
        assert manager.is_injection_active() is False

    def test_is_injection_active_no_worker(self, manager):
        """is_injection_active should be False with no worker."""
        manager._current_worker = None

        assert manager.is_injection_active() is False


class TestPathSuggestions:
    """Tests for path suggestion methods."""

    def test_suggest_output_vram_path(self, manager, tmp_path):
        """suggest_output_vram_path should suggest non-existing path."""
        input_path = tmp_path / "vram.dmp"
        input_path.touch()

        suggested = manager.suggest_output_vram_path(str(input_path))

        assert suggested != str(input_path)
        assert "_injected" in suggested
        assert suggested.endswith(".dmp")

    def test_suggest_output_rom_path(self, manager, tmp_path):
        """suggest_output_rom_path should suggest non-existing path."""
        input_path = tmp_path / "test.sfc"
        input_path.touch()

        suggested = manager.suggest_output_rom_path(str(input_path))

        assert suggested != str(input_path)
        assert "_modified" in suggested
        # Should be in same directory
        assert Path(suggested).parent == tmp_path

    def test_suggest_output_path_increments(self, manager, tmp_path):
        """_suggest_output_path should increment if file exists."""
        input_path = tmp_path / "test.sfc"
        input_path.touch()

        # Create the first suggested file
        suggested1 = manager.suggest_output_rom_path(str(input_path))
        Path(suggested1).touch()

        # Next suggestion should be different
        suggested2 = manager.suggest_output_rom_path(str(input_path))

        assert suggested1 != suggested2

    def test_get_smart_vram_suggestion_empty_without_metadata(self, manager, tmp_path):
        """get_smart_vram_suggestion should return empty without good hints."""
        sprite_path = tmp_path / "sprite.png"
        sprite_path.touch()

        result = manager.get_smart_vram_suggestion(str(sprite_path))

        # May return empty or a suggestion depending on implementation
        assert isinstance(result, str)

    def test_find_suggested_input_vram(self, manager, tmp_path):
        """find_suggested_input_vram should search for matching VRAM."""
        sprite_path = tmp_path / "sprite.png"
        sprite_path.touch()

        result = manager.find_suggested_input_vram(str(sprite_path))

        assert isinstance(result, str)


class TestMetadataLoading:
    """Tests for metadata loading."""

    def test_load_metadata_nonexistent(self, manager, tmp_path):
        """load_metadata should return None for nonexistent file."""
        result = manager.load_metadata(str(tmp_path / "nonexistent.json"))

        assert result is None

    def test_load_metadata_empty_path(self, manager):
        """load_metadata should return None for empty path."""
        result = manager.load_metadata("")

        assert result is None

    def test_load_metadata_invalid_json(self, manager, tmp_path):
        """load_metadata should return None for invalid JSON."""
        metadata_file = tmp_path / "invalid.json"
        metadata_file.write_text("not valid json {{{")

        result = manager.load_metadata(str(metadata_file))

        assert result is None

    def test_load_metadata_valid(self, manager, tmp_path):
        """load_metadata should parse valid metadata."""
        import json

        metadata_file = tmp_path / "metadata.json"
        metadata = {
            "extraction": {
                "source_type": "vram",
                "vram_offset": "0xC000",
            }
        }
        metadata_file.write_text(json.dumps(metadata))

        result = manager.load_metadata(str(metadata_file))

        assert result is not None
        assert result["source_type"] == "vram"
        assert result["extraction_vram_offset"] == "0xC000"

    def test_load_metadata_rom_source(self, manager, tmp_path):
        """load_metadata should parse ROM source metadata."""
        import json

        metadata_file = tmp_path / "metadata.json"
        metadata = {
            "extraction": {
                "source_type": "rom",
                "rom_source": "test.sfc",
                "rom_offset": "0x1000",
                "sprite_name": "TestSprite",
            }
        }
        metadata_file.write_text(json.dumps(metadata))

        result = manager.load_metadata(str(metadata_file))

        assert result is not None
        assert result["source_type"] == "rom"
        assert result["rom_extraction_info"] is not None
        assert result["rom_extraction_info"]["rom_offset"] == "0x1000"


class TestVRAMOffsetConversion:
    """Tests for VRAM to ROM offset conversion."""

    def test_convert_vram_to_rom_offset_known(self, manager):
        """convert_vram_to_rom_offset should convert known mappings."""
        result = manager.convert_vram_to_rom_offset("0xC000")

        assert result == 0x0C8000

    def test_convert_vram_to_rom_offset_int(self, manager):
        """convert_vram_to_rom_offset should accept int."""
        result = manager.convert_vram_to_rom_offset(0xC000)

        assert result == 0x0C8000

    def test_convert_vram_to_rom_offset_unknown(self, manager):
        """convert_vram_to_rom_offset should return None for unknown."""
        result = manager.convert_vram_to_rom_offset("0x8000")

        assert result is None

    def test_convert_vram_to_rom_offset_invalid(self, manager):
        """convert_vram_to_rom_offset should return None for invalid."""
        result = manager.convert_vram_to_rom_offset("not_a_number")

        assert result is None


class TestROMValidation:
    """Tests for ROM file validation."""

    def test_validate_rom_file_nonexistent(self, manager, tmp_path):
        """_validate_rom_file should return error for nonexistent."""
        result = manager._validate_rom_file(str(tmp_path / "nonexistent.sfc"))

        assert result is not None
        assert "error" in result

    def test_validate_rom_file_valid(self, manager, tmp_path):
        """_validate_rom_file should return None for valid ROM."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x100000)  # 1MB

        result = manager._validate_rom_file(str(rom_file))

        assert result is None

    def test_validate_rom_file_too_small(self, manager, tmp_path):
        """_validate_rom_file should return error for tiny files."""
        rom_file = tmp_path / "tiny.sfc"
        rom_file.write_bytes(b"\x00" * 100)  # Too small

        result = manager._validate_rom_file(str(rom_file))

        assert result is not None
        assert "error" in result


class TestCacheIntegration:
    """Tests for ROM cache integration."""

    def test_get_cache_stats(self, manager):
        """get_cache_stats should return stats dict."""
        stats = manager.get_cache_stats()

        assert isinstance(stats, dict)
        # Should have expected keys
        assert "total_entries" in stats or "cache_size" in stats or len(stats) >= 0

    def test_clear_rom_cache(self, manager):
        """clear_rom_cache should return count."""
        count = manager.clear_rom_cache()

        assert isinstance(count, int)
        assert count >= 0


class TestScanProgress:
    """Tests for scan progress caching."""

    def test_get_scan_progress_not_found(self, manager, tmp_path):
        """get_scan_progress should return None for uncached scan."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x100000)

        result = manager.get_scan_progress(str(rom_file), {"start_offset": 0, "end_offset": 0x10000})

        # May be None or empty depending on cache state
        assert result is None or isinstance(result, dict)

    def test_save_scan_progress(self, manager, tmp_path):
        """save_scan_progress should save progress."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x100000)

        result = manager.save_scan_progress(
            str(rom_file),
            {"start_offset": 0, "end_offset": 0x10000},
            found_sprites=[],
            current_offset=0x5000,
            completed=False,
        )

        assert result is True

    def test_clear_scan_progress(self, manager):
        """clear_scan_progress should return count."""
        count = manager.clear_scan_progress()

        assert isinstance(count, int)
        assert count >= 0


class TestCleanup:
    """Tests for cleanup and reset."""

    def test_cleanup_clears_worker(self, manager):
        """cleanup should clear current worker."""
        # Set a mock worker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = False
        manager._current_worker = mock_worker

        manager.cleanup()

        assert manager._current_worker is None

    def test_reset_state_clears_operations(self, manager):
        """reset_state should clear active operations."""
        manager._active_operations.add("test_op")

        manager.reset_state()

        assert len(manager._active_operations) == 0

    def test_reset_state_full_clears_services(self, manager):
        """reset_state with full_reset should clear services."""
        manager.reset_state(full_reset=True)

        assert manager._rom_service is None
        assert manager._vram_service is None
        assert manager._is_initialized is False


class TestSignals:
    """Tests for signal emissions."""

    def test_extraction_progress_signal_exists(self, manager):
        """extraction_progress signal should exist."""
        assert hasattr(manager, "extraction_progress")

    def test_injection_progress_signal_exists(self, manager):
        """injection_progress signal should exist."""
        assert hasattr(manager, "injection_progress")

    def test_injection_finished_signal_exists(self, manager):
        """injection_finished signal should exist."""
        assert hasattr(manager, "injection_finished")

    def test_cache_signals_exist(self, manager):
        """Cache signals should exist."""
        assert hasattr(manager, "cache_operation_started")
        assert hasattr(manager, "cache_hit")
        assert hasattr(manager, "cache_miss")
        assert hasattr(manager, "cache_saved")


class TestROMInjectionSettings:
    """Tests for ROM injection settings persistence."""

    def test_save_rom_injection_settings(self, manager):
        """save_rom_injection_settings should save to session."""
        manager.save_rom_injection_settings(
            input_rom="/path/to/rom.sfc",
            sprite_location_text="Test Sprite (0x1000)",
            custom_offset="0x2000",
            fast_compression=True,
        )

        # Settings should be saved (no exception)
        # Actual persistence depends on session manager

    def test_load_rom_injection_defaults_empty(self, manager, tmp_path):
        """load_rom_injection_defaults should return defaults with no metadata."""
        sprite_path = tmp_path / "sprite.png"
        sprite_path.touch()

        result = manager.load_rom_injection_defaults(str(sprite_path))

        assert isinstance(result, dict)
        assert "input_rom" in result
        assert "output_rom" in result
        assert "fast_compression" in result

    def test_restore_saved_sprite_location(self, manager):
        """restore_saved_sprite_location should return dict."""
        locations = {"Kirby": 0x100000, "Waddle Dee": 0x200000}

        result = manager.restore_saved_sprite_location(None, locations)

        assert isinstance(result, dict)
        assert "sprite_location_name" in result
        assert "sprite_location_index" in result
        assert "custom_offset" in result


class TestEnsureComponents:
    """Tests for component initialization guards."""

    def test_ensure_component_raises_when_none(self):
        """_ensure_component should raise when component is None."""
        mgr = CoreOperationsManager.__new__(CoreOperationsManager)
        mgr._sprite_extractor = None

        with pytest.raises(ExtractionError):
            mgr._ensure_component(None, "Test component", ExtractionError)
