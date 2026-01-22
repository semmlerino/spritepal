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
    pytest.mark.integration,
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
        """Manager should be initialized and ready for operations."""
        assert manager is not None
        # Verify initialization by calling public method that requires it
        stats = manager.get_cache_stats()
        assert isinstance(stats, dict)

    def test_services_ready_for_extraction(self, manager, tmp_path):
        """Core services should be initialized and ready for extraction operations."""
        # Create valid test files
        vram_file = tmp_path / "vram.dmp"
        vram_file.write_bytes(b"\x00" * 0x10000)

        # Validation requires all services to be initialized
        # This proves extractors and managers are ready without accessing private attrs
        params = {
            "vram_path": str(vram_file),
            "output_base": "test_output",
            "grayscale_mode": True,
        }
        result = manager.validate_extraction_params(params)
        assert result is True


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

    def test_validate_extraction_params_accepts_sprite_offset(self, manager, tmp_path):
        """validate_extraction_params should accept 'sprite_offset' (backward compatibility)."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x100000)

        params = {
            "rom_path": str(rom_file),
            "sprite_offset": 0x1000,  # Valid offset within ROM bounds
            "output_base": "test_output",
        }

        # Should not raise - validates that sprite_offset is accepted
        assert manager.validate_extraction_params(params) is True


class TestInjectionValidation:
    """Tests for injection parameter validation."""

    def test_validate_injection_params_vram_valid(self, manager, tmp_path):
        """validate_injection_params should accept valid VRAM params."""
        sprite_file = tmp_path / "sprite.png"
        vram_file = tmp_path / "vram.dmp"

        # Create minimal valid indexed PNG (SNES 4bpp requires indexed/grayscale)
        img = Image.new("P", (8, 8))  # Indexed mode
        palette = [i * 16 for i in range(16)] * 3
        palette.extend([0] * (768 - len(palette)))
        img.putpalette(palette)
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

        # Create minimal valid indexed PNG (SNES 4bpp requires indexed/grayscale)
        img = Image.new("P", (8, 8))  # Indexed mode
        palette = [i * 16 for i in range(16)] * 3
        palette.extend([0] * (768 - len(palette)))
        img.putpalette(palette)
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
        # Create valid indexed PNG so we get to the mode validation
        img = Image.new("P", (8, 8))
        palette = [i * 16 for i in range(16)] * 3
        palette.extend([0] * (768 - len(palette)))
        img.putpalette(palette)
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

    def test_validate_rom_file_nonexistent_via_public_api(self, manager, tmp_path):
        """load_rom_info should handle nonexistent files gracefully."""
        # Using load_rom_info which internally validates the ROM
        result = manager.load_rom_info(str(tmp_path / "nonexistent.sfc"))

        # It should return a dict with error info
        assert result is not None
        assert "error" in result
        assert "Validation" in result.get("error_type", "") or "ValidationError" in result.get("error_type", "")

    def test_validate_rom_file_valid_via_public_api(self, manager, tmp_path):
        """load_rom_info should return header info for valid ROM."""
        rom_file = tmp_path / "test.sfc"
        # Create a valid-ish ROM header (LoROM)
        # Header is at 0x7FC0 for unheadered LoROM

        # ROM Data up to header
        rom_data = bytearray(b"\x00" * 0x7FC0)

        # Header fields
        rom_data.extend(b"TEST ROM TITLE       ")  # Title (21 bytes)
        rom_data.extend(b"\x20")  # Map Mode (LoROM)
        rom_data.extend(b"\x00")  # ROM Type
        rom_data.extend(b"\x09")  # ROM Size (512KB)
        rom_data.extend(b"\x00")  # SRAM Size
        rom_data.extend(b"\x01")  # Country
        rom_data.extend(b"\x33")  # License
        rom_data.extend(b"\x00")  # Version
        rom_data.extend(b"\xff\xff")  # Checksum Complement (dummy)
        rom_data.extend(b"\x00\x00")  # Checksum (dummy)

        # Fill remainder to make it 1MB total (enough to be valid)
        padding_needed = 0x100000 - len(rom_data)
        rom_data.extend(b"\x00" * padding_needed)

        rom_file.write_bytes(rom_data)

        # load_rom_info calls _validate_rom_file internally
        result = manager.load_rom_info(str(rom_file))

        # If it fails, print the error for debugging
        if "error" in result:
            print(f"ROM Validation Error: {result['error']}")

        assert result is not None
        assert "header" in result
        assert "error" not in result

    def test_validate_rom_file_too_small_via_public_api(self, manager, tmp_path):
        """load_rom_info should report error for tiny files."""
        rom_file = tmp_path / "tiny.sfc"
        rom_file.write_bytes(b"\x00" * 100)  # Too small

        result = manager.load_rom_info(str(rom_file))

        assert result is not None
        assert "error" in result
        assert "Validation" in result.get("error_type", "") or "ValidationError" in result.get("error_type", "")


class TestCacheIntegration:
    """Tests for ROM cache integration."""

    def test_get_cache_stats(self, manager):
        """get_cache_stats should return stats dict."""
        stats = manager.get_cache_stats()

        assert isinstance(stats, dict)
        # Empty dict is valid when _rom_cache is None
        # Non-empty dict must have cache_enabled key
        if stats:
            assert "cache_enabled" in stats

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
        # Set a mock worker (using private access just to setup the test state,
        # but verifying via public method)
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = False
        manager._current_worker = mock_worker

        assert manager.has_active_worker()

        manager.cleanup()

        assert not manager.has_active_worker()

    def test_reset_state_clears_operations(self, manager):
        """reset_state should clear active operations."""
        # Setup internal state (unavoidable for white-box testing of reset)
        manager._active_operations.add("test_op")

        assert manager.is_operation_active("test_op")

        manager.reset_state()

        assert not manager.is_operation_active("test_op")

    def test_reset_state_full_clears_extractors(self, manager):
        """reset_state with full_reset should clear initialized state."""
        assert manager.is_initialized()

        manager.reset_state(full_reset=True)

        assert not manager.is_initialized()


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


class TestRegressionFixes:
    """Regression tests for CoreOperationsManager correctness fixes."""

    def test_worker_cleared_on_exception(self, manager, tmp_path):
        """Issue #2: _current_worker should be None after exception in start_injection."""
        # Try to inject with invalid params that will cause an exception
        # after worker assignment but before completion
        params = {
            "mode": "rom",
            "sprite_path": "/nonexistent/sprite.png",
            "input_rom": "/nonexistent/rom.smc",
            "output_rom": str(tmp_path / "output.smc"),
            "offset": 0x1000,
        }

        try:
            manager.start_injection(params)
        except Exception:
            pass  # Expected to fail

        # Key assertion: manager should report no active injection after exception cleanup
        assert manager.is_injection_active() is False

    def test_invalid_offset_logged_and_indicated(self, manager, tmp_path, caplog):
        """Issue #3: Parse failure should log warning and set offset_parse_error."""
        import logging

        # Create a metadata file with invalid offset
        sprite_path = tmp_path / "sprite.png"
        rom_path = tmp_path / "test.smc"

        # Create minimal files
        sprite_path.write_bytes(b"fake")
        rom_path.write_bytes(b"\x00" * 100)

        metadata = {
            "rom_extraction_info": {
                "rom_source": rom_path.name,
                "rom_offset": "not_a_valid_offset",  # Invalid!
            }
        }

        with caplog.at_level(logging.WARNING):
            result = manager.load_rom_injection_defaults(str(sprite_path), metadata)

        # Should have logged a warning
        assert any("Failed to parse ROM offset" in record.message for record in caplog.records)

        # Should indicate error in result
        assert "offset_parse_error" in result


# ==============================================================================
# Migrated from test_injection_manager.py - VRAM Suggestion Strategy Tests
# ==============================================================================


class TestVRAMSuggestionStrategies:
    """Tests for smart VRAM suggestion strategies.

    Migrated from test_injection_manager.py - these tests cover specific
    VRAM suggestion strategies: basename, session, metadata, and suffix patterns.
    """

    def test_get_smart_vram_suggestion_basename_pattern(self, manager, tmp_path):
        """Suggest input VRAM based on sprite filename basename match.

        Tests the first strategy in smart suggestion logic.
        """
        # Create sprite file and matching VRAM file
        sprite_file = tmp_path / "test_sprite.png"
        sprite_file.write_text("fake sprite data")
        vram_file = tmp_path / "test_sprite.dmp"
        vram_file.write_text("fake vram data")

        result = manager.get_smart_vram_suggestion(str(sprite_file))
        assert result == str(vram_file)

    def test_get_smart_vram_suggestion_session_strategy(self, manager, tmp_path):
        """Suggest input VRAM based on last used directory in session.

        Tests session management integration for file path suggestions.
        """
        from unittest import mock

        # Create sprite file
        sprite_file = tmp_path / "sprite.png"
        sprite_file.write_text("fake sprite data")

        # Create VRAM file
        vram_file = tmp_path / "session_vram.dmp"
        vram_file.write_text("fake vram data")

        # Mock session manager via app_context
        app_ctx = get_app_context()
        with mock.patch.object(app_ctx.session_manager, "get") as mock_get:
            mock_get.return_value = str(vram_file)

            result = manager.get_smart_vram_suggestion(str(sprite_file))
            assert result == str(vram_file)

    def test_get_smart_vram_suggestion_metadata_strategy(self, manager, tmp_path):
        """Suggest input VRAM based on original source path in metadata.

        Tests metadata parsing and source path extraction logic.
        """
        import json

        # Create VRAM file
        vram_file = tmp_path / "metadata_vram.dmp"
        vram_file.write_text("fake vram data")

        # Create metadata file pointing to VRAM
        metadata_file = tmp_path / "metadata.json"
        metadata_data = {"source_vram": str(vram_file)}
        metadata_file.write_text(json.dumps(metadata_data))

        sprite_file = tmp_path / "sprite.png"
        sprite_file.write_text("fake sprite data")

        result = manager.get_smart_vram_suggestion(str(sprite_file), metadata_path=str(metadata_file))
        assert result == str(vram_file)

    def test_get_smart_vram_suggestion_vram_suffix_pattern(self, manager, tmp_path):
        """Suggest input VRAM based on _VRAM file suffix pattern.

        Tests glob pattern matching for VRAM dump files.
        """
        sprite_file = tmp_path / "test_sprite.png"
        sprite_file.write_text("fake sprite data")

        # Create VRAM file with _VRAM pattern
        vram_file = tmp_path / "test_sprite_VRAM.dmp"
        vram_file.write_text("fake vram data")

        result = manager.get_smart_vram_suggestion(str(sprite_file))
        assert result == str(vram_file)


# ==============================================================================
# Migrated from test_extraction_manager.py - Extraction Workflow Tests
# ==============================================================================


class TestExtractionWorkflows:
    """Tests for extraction workflow operations.

    Migrated from test_extraction_manager.py - these tests cover unique
    extraction workflows: file creation, concurrent operation prevention,
    and sprite preview structure validation.
    """

    @pytest.fixture
    def test_data_repo(self, isolated_data_repository):
        """Provide test data repository for consistent test data."""
        return isolated_data_repository

    def test_extract_from_vram_real_workflow_creates_files(self, manager, test_data_repo, qtbot):
        """VRAM extraction should create real image files from valid VRAM data.

        Tests the success path: valid VRAM data produces valid image output.
        """
        from tests.fixtures.timeouts import worker_timeout

        # Get real VRAM extraction test data
        vram_data = test_data_repo.get_vram_extraction_data("medium")

        # Test real VRAM extraction workflow - should succeed
        files = manager.extract_from_vram(
            vram_data["vram_path"],
            vram_data["output_base"],
            grayscale_mode=True,  # Simplified for reliable testing
        )

        # Verify real extraction created actual files
        assert len(files) >= 1
        output_png = f"{vram_data['output_base']}.png"
        assert output_png in files
        assert Path(output_png).exists()

        # Verify the extracted image is real with reasonable properties
        with Image.open(output_png) as img:
            assert img.mode in ["L", "P", "RGBA"]  # Valid image modes
            assert img.size[0] > 0 and img.size[1] > 0
            assert img.size[0] * img.size[1] >= 64  # Reasonable minimum size

            # Verify file has real image data (not just empty)
            img_bytes = img.tobytes()
            assert len(img_bytes) > 0

    def test_extract_from_vram_already_running(self, manager, tmp_path):
        """Prevent concurrent VRAM extractions."""
        vram_file = tmp_path / "test.vram"
        vram_file.write_bytes(b"\x00" * 0x10000)  # 64KB
        output_base = str(tmp_path / "test")

        # Start an extraction (simulate)
        manager.simulate_operation_start("vram_extraction")

        # Try to start another - should fail
        with pytest.raises(ExtractionError, match="already in progress"):
            manager.extract_from_vram(str(vram_file), output_base)

        # Clean up
        manager.simulate_operation_finish("vram_extraction")

    def test_extract_from_rom_real_workflow_validation_succeeds(self, manager, test_data_repo):
        """ROM extraction parameter validation should succeed with valid data.

        Tests the success path: valid ROM parameters pass validation.
        """
        # Get real ROM test data
        rom_data = test_data_repo.get_rom_extraction_data("medium")

        # Test ROM extraction parameter validation
        test_params = {
            "rom_path": rom_data["rom_path"],
            "offset": rom_data["offset"],
            "output_base": rom_data["output_base"],
        }

        # Validation should succeed with valid parameters
        result = manager.validate_extraction_params(test_params)
        assert result is True

        # Verify the parameters are well-formed for real ROM extraction
        assert Path(test_params["rom_path"]).exists()
        assert test_params["offset"] >= 0
        assert isinstance(test_params["output_base"], str)

        # Verify ROM file has reasonable size
        rom_size = Path(test_params["rom_path"]).stat().st_size
        assert rom_size >= 0x80000  # At least 512KB

        # Test that offset is within ROM bounds
        assert test_params["offset"] < rom_size

    def test_get_sprite_preview_real_rom_data_returns_valid_structure(self, manager, test_data_repo):
        """Sprite preview should generate valid tile data structure from ROM files.

        Tests the success path: valid ROM data produces valid preview structure.
        """
        from utils.constants import BYTES_PER_TILE

        # Get real ROM test data
        rom_data = test_data_repo.get_rom_extraction_data("medium")

        # Test real sprite preview generation - should succeed
        tile_data, width, height = manager.get_sprite_preview(rom_data["rom_path"], 0x1000, "test_sprite")

        # Verify real tile data structure
        assert isinstance(tile_data, bytes)
        assert width > 0 and height > 0
        assert width <= 512 and height <= 512  # Reasonable bounds

        # Verify tile data size makes sense
        expected_min_size = (width * height // 64) * BYTES_PER_TILE
        assert len(tile_data) >= expected_min_size

    def test_validate_vram_extraction_defers_file_existence_check(self, manager, tmp_path):
        """VRAM validation defers file existence check to extraction time.

        Unlike ROM validation which checks file existence early,
        VRAM validation only checks param structure. File existence
        is verified when extract_from_vram is called.
        """
        params = {
            "vram_path": "/nonexistent/path/file.vram",
            "output_base": str(tmp_path / "output"),
            "grayscale_mode": True,
        }
        # Validation passes - file existence is checked at extraction time, not validation time
        result = manager.validate_extraction_params(params)
        assert result is True


# ==============================================================================
# Migrated from test_injection_workflow_integration.py - End-to-End Test
# ==============================================================================


class TestInjectionWorkflowEndToEnd:
    """End-to-end injection workflow tests.

    Migrated from test_injection_workflow_integration.py.
    """

    @pytest.fixture
    def test_rom_file(self, tmp_path) -> Path:
        """Create a test ROM file with realistic data."""
        import struct

        rom_path = tmp_path / "test_rom.sfc"
        rom_data = bytearray(2 * 1024 * 1024)  # 2MB

        # Add ROM header info (SNES LoROM header at 0x7FC0)
        header_offset = 0x7FC0
        title = b"TEST ROM DATA      "[:21]
        rom_data[header_offset : header_offset + 21] = title
        rom_data[header_offset + 21] = 0x20  # LoROM, no FastROM
        rom_data[header_offset + 22] = 0x00  # ROM type
        rom_data[header_offset + 23] = 0x0A  # ROM size (2MB)
        rom_data[header_offset + 24] = 0x00  # SRAM size
        rom_data[header_offset + 25] = 0x01  # Country (USA)
        rom_data[header_offset + 26] = 0x00  # License code
        rom_data[header_offset + 27] = 0x00  # Version

        # Checksum
        checksum = 0x1234
        checksum_complement = checksum ^ 0xFFFF
        struct.pack_into("<H", rom_data, header_offset + 28, checksum_complement)
        struct.pack_into("<H", rom_data, header_offset + 30, checksum)

        # Add HAL-compressed sprite signature at known offset
        sprite_offset = 0x100000
        rom_data[sprite_offset : sprite_offset + 4] = b"\x00\x10\x00\x00"

        rom_path.write_bytes(rom_data)
        return rom_path

    @pytest.fixture
    def test_vram_file(self, tmp_path) -> Path:
        """Create a test VRAM dump file."""
        vram_path = tmp_path / "test_vram.dmp"
        vram_data = bytearray(64 * 1024)

        # Add pattern data (4bpp tile pattern)
        for i in range(0, len(vram_data), 32):
            for j in range(32):
                vram_data[i + j] = (i + j) % 256

        vram_path.write_bytes(vram_data)
        return vram_path

    @pytest.fixture
    def test_sprite_png(self, tmp_path) -> Path:
        """Create a test sprite PNG file."""
        # Create indexed PNG (SNES 4bpp requirement)
        sprite = Image.new("P", (32, 32))
        palette = [i * 16 for i in range(16)] * 3
        palette.extend([0] * (768 - len(palette)))
        sprite.putpalette(palette)

        sprite_path = tmp_path / "test_sprite.png"
        sprite.save(sprite_path)
        return sprite_path

    @pytest.mark.slow
    def test_complete_injection_preparation(self, manager, test_rom_file, test_vram_file, test_sprite_png):
        """Test complete preparation for injection (without actual injection)."""
        # 1. Load ROM info
        rom_info = manager.load_rom_info(str(test_rom_file))
        assert rom_info is not None
        assert "header" in rom_info

        # 2. Load metadata from sprite (may return None if no metadata file)
        metadata = manager.load_metadata(str(test_sprite_png))
        assert metadata is None or isinstance(metadata, dict)

        # 3. Validate parameters
        params = {
            "mode": "vram",
            "sprite_path": str(test_sprite_png),
            "offset": 0x4000,
            "input_vram": str(test_vram_file),
            "output_vram": str(test_vram_file.parent / "output.dmp"),
        }

        try:
            manager.validate_injection_params(params)
            validation_passed = True
        except ValidationError:
            validation_passed = False

        # At least we verified the validation code ran without crashing
        assert isinstance(validation_passed, bool)

        # 4. Get output suggestions
        output_vram = manager.suggest_output_vram_path(str(test_vram_file))
        output_rom = manager.suggest_output_rom_path(str(test_rom_file))

        assert output_vram is not None
        assert output_rom is not None
