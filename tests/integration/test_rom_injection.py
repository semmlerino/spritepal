"""
Tests for ROM injection functionality and regression fixes.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.app_context import get_app_context
from core.hal_compression import HALCompressionError, HALCompressor
from core.rom_injector import ROMHeader, ROMInjector

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.usefixtures("mock_hal"),
]


class TestHALCompression:
    """Test HAL compression/decompression basics."""

    def test_data_size_limit(self):
        """Test that data size limit is enforced."""
        with patch.object(HALCompressor, "_find_tool", return_value="inhal"):
            compressor = HALCompressor()

            # Create data that's too large (64KB max)
            large_data = b"X" * (65536 + 1)

            with pytest.raises(HALCompressionError, match="too large"):
                compressor.compress_to_file(large_data, "output.bin")


class TestROMInjector:
    """Test ROM injection functionality."""

    @pytest.fixture
    def injector(self):
        return ROMInjector()

    @pytest.fixture
    def test_rom_data(self):
        """Create a minimal SNES ROM with a valid header."""
        data = bytearray(0x8000)
        header_offset = 0x7FC0
        title = b"TEST ROM".ljust(21, b" ")
        data[header_offset : header_offset + 21] = title
        data[header_offset + 21] = 0x20  # LoROM
        data[header_offset + 23] = 0x08  # 256KB
        checksum = 0x1234
        complement = checksum ^ 0xFFFF
        data[header_offset + 28 : header_offset + 30] = complement.to_bytes(2, "little")
        data[header_offset + 30 : header_offset + 32] = checksum.to_bytes(2, "little")
        return bytes(data)

    def test_read_rom_header(self, injector, test_rom_data, tmp_path):
        """Test reading ROM header."""
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        header = injector.read_rom_header(str(rom_path))

        assert header.title.strip() == "TEST ROM"
        assert header.rom_type == 32
        assert header.rom_size == 8
        assert header.rom_type_offset == 0x7FC0

    def test_checksum_calculation(self, injector, test_rom_data):
        """Test ROM checksum calculation."""
        injector.header = ROMHeader(
            title="TEST",
            rom_type=0x20,
            rom_size=0x08,
            sram_size=0,
            checksum=0,
            checksum_complement=0,
            header_offset=0,
            rom_type_offset=0x7FC0,
        )

        checksum, complement = injector.calculate_checksum(bytearray(test_rom_data))
        assert checksum ^ complement == 0xFFFF
        assert checksum == sum(test_rom_data) & 0xFFFF

    def test_sprite_location_finding_synthetic_rom(self, injector, test_rom_data, tmp_path):
        """Test finding sprite locations with synthetic ROM."""
        from core.sprite_config_loader import SpriteConfig

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(test_rom_data)

        mock_configs = {
            "Test_Sprite_1": SpriteConfig(
                name="Test_Sprite_1", offset=0x10000, description="", compressed=True, estimated_size=1024
            )
        }

        with patch.object(injector.sprite_config_loader, "get_game_sprites", return_value=mock_configs):
            locations = injector.find_sprite_locations(str(rom_path))

        assert "Test_Sprite_1" in locations
        assert locations["Test_Sprite_1"].offset == 0x10000


class TestRegressionFixes:
    """Regression tests for previously identified correctness issues."""

    def test_temp_file_cleaned_on_compression_error(self, tmp_path):
        """Issue #1: Verify temp files are cleaned up even when compression fails."""
        # Setup similar to original regression test but cleaned up
        rom_path = tmp_path / "test.smc"
        rom_path.write_bytes(b"\x00" * (512 * 1024))  # Minimal size
        sprite_path = tmp_path / "sprite.png"
        Image.new("P", (16, 16)).save(sprite_path)

        with (
            patch("core.rom_injector.HALCompressor") as mock_comp_cls,
            patch("core.rom_injector.ROMValidator") as mock_val,
        ):
            mock_comp = mock_comp_cls.return_value
            mock_comp.compress_to_file.side_effect = HALCompressionError("Test failure")
            mock_val.validate_rom_for_injection.return_value = ({"title": "TEST"}, 0x7FC0)

            injector = ROMInjector()
            injector.read_rom_header = MagicMock(return_value=MagicMock(header_offset=0x7FC0))

            temp_dir_path = Path(tempfile.gettempdir())
            files_before = set(temp_dir_path.glob("*.bin"))

            injector.inject_sprite_to_rom(str(sprite_path), str(rom_path), str(tmp_path / "out.sfc"), 0x1000)

            files_after = set(temp_dir_path.glob("*.bin"))
            assert files_after - files_before == set()

    def test_rom_data_unchanged_on_write_failure(self, tmp_path):
        """Issue #4: Verify ROM state is not corrupted when write fails."""
        rom_path = tmp_path / "test.smc"
        original_data = b"\xaa" * 1024
        rom_path.write_bytes(original_data)

        sprite_path = tmp_path / "sprite.png"
        Image.new("P", (8, 8)).save(sprite_path)

        with patch("core.rom_injector.atomic_write", side_effect=OSError("Disk full")):
            injector = ROMInjector()
            injector.rom_data = bytearray(original_data)

            injector.inject_sprite_to_rom(str(sprite_path), str(rom_path), str(tmp_path / "out.sfc"), 0)

            # Internal rom_data should not have been updated with "new" data if write failed
            # (In reality it might be complex to verify without deep mocking,
            # but we verify it doesn't crash and preserves original data if reload fails)
            assert injector.rom_data == bytearray(original_data)

    def test_vram_cleared_on_injection_error(self, tmp_path):
        """Issue #5: Verify VRAM buffer is cleared on injection error."""
        from core.injector import SpriteInjector

        vram_path = tmp_path / "input.vram"
        vram_path.write_bytes(b"\x00" * 65536)
        sprite_path = tmp_path / "sprite.png"
        Image.new("P", (8, 8)).save(sprite_path)

        injector = SpriteInjector()
        injector.vram_data = bytearray(b"\xaa" * 65536)

        with patch("core.injector.atomic_write", side_effect=OSError("Disk full")):
            injector.inject_sprite(str(sprite_path), str(vram_path), str(tmp_path / "out.vram"), 0)

        assert len(injector.vram_data) == 0


class TestInjectionDimensionValidation:
    """Test early PNG dimension validation in injection params."""

    @pytest.mark.parametrize("width,height", [(7, 8), (8, 7), (15, 16), (9, 9)])
    def test_injection_rejects_invalid_dimensions(self, tmp_path, width, height, app_context):
        from core.managers.core_operations_manager import ValidationError

        invalid_png = tmp_path / "invalid.png"
        Image.new("P", (width, height)).save(invalid_png)

        # The real manager validation logic:
        real_manager = app_context.core_operations_manager

        params = {"mode": "rom", "sprite_path": str(invalid_png), "offset": 0}
        with pytest.raises(ValidationError, match="multiples of 8"):
            real_manager.validate_injection_params(params)
