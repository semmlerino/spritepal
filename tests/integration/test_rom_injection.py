"""
Tests for ROM injection functionality
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.app_context import get_app_context
from core.hal_compression import HALCompressionError, HALCompressor
from core.managers.application_state_manager import ApplicationStateManager
from core.managers.core_operations_manager import CoreOperationsManager
from core.rom_injector import ROMHeader, ROMInjector

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.usefixtures("mock_hal"),
]


class TestHALCompression(unittest.TestCase):
    """Test HAL compression/decompression"""

    def setUp(self):
        """Set up test fixtures"""
        # Create test data
        self.test_data = b"Hello, World! This is test data for HAL compression." * 10

    # test_compress_to_file removed - heavily mocked test that doesn't test real behavior

    def test_data_size_limit(self):
        """Test that data size limit is enforced"""
        with patch.object(HALCompressor, "_find_tool", return_value="inhal"):
            compressor = HALCompressor()

            # Create data that's too large
            large_data = b"X" * (65536 + 1)

            with pytest.raises(HALCompressionError) as cm:
                compressor.compress_to_file(large_data, "output.bin")

            assert "too large" in str(cm.value)


class TestROMInjector(unittest.TestCase):
    """Test ROM injection functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.injector = ROMInjector()

        # Create a minimal SNES ROM header at 0x7FC0
        self.test_rom = bytearray(0x8000)
        header_offset = 0x7FC0

        # Title (21 bytes)
        title = b"TEST ROM".ljust(21, b" ")
        self.test_rom[header_offset : header_offset + 21] = title

        # ROM type, size, SRAM size
        self.test_rom[header_offset + 21] = 0x20  # LoROM
        self.test_rom[header_offset + 23] = 0x08  # 256KB
        self.test_rom[header_offset + 24] = 0x00  # No SRAM

        # Checksum and complement (must XOR to 0xFFFF)
        checksum = 0x1234
        complement = checksum ^ 0xFFFF
        self.test_rom[header_offset + 28 : header_offset + 30] = complement.to_bytes(2, "little")
        self.test_rom[header_offset + 30 : header_offset + 32] = checksum.to_bytes(2, "little")

    def test_read_rom_header(self):
        """Test reading ROM header"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(self.test_rom)
            tmp_path = tmp.name

        try:
            header = self.injector.read_rom_header(tmp_path)

            assert header.title.strip() == "TEST ROM"
            assert header.rom_type == 32
            assert header.rom_size == 8
            assert header.checksum == 4660
            assert header.header_offset == 0
            assert header.rom_type_offset == 0x7FC0  # Should detect LoROM offset

        finally:
            Path(tmp_path).unlink()

    def test_checksum_calculation(self):
        """Test ROM checksum calculation"""
        # Set header first
        self.injector.header = ROMHeader(
            title="TEST",
            rom_type=0x20,
            rom_size=0x08,
            sram_size=0,
            checksum=0,
            checksum_complement=0,
            header_offset=0,
            rom_type_offset=0x7FC0,  # LoROM offset
        )

        checksum, complement = self.injector.calculate_checksum(self.test_rom)

        # Verify checksum and complement XOR to 0xFFFF
        assert checksum ^ complement == 65535

    def test_sprite_location_finding_synthetic_rom(self):
        """Test finding sprite locations with synthetic ROM (deterministic, always runs)"""
        from core.sprite_config_loader import SpriteConfig

        # Use the synthetic ROM from setUp (already has valid header)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sfc") as tmp:
            tmp.write(self.test_rom)
            tmp_path = tmp.name

        try:
            # Mock sprite_config_loader to return known configurations for our test ROM
            mock_configs = {
                "Test_Sprite_1": SpriteConfig(
                    name="Test_Sprite_1",
                    offset=0x10000,
                    description="Test sprite 1",
                    compressed=True,
                    estimated_size=1024,
                ),
                "Test_Sprite_2": SpriteConfig(
                    name="Test_Sprite_2",
                    offset=0x20000,
                    description="Test sprite 2",
                    compressed=True,
                    estimated_size=2048,
                ),
            }

            with patch.object(
                self.injector.sprite_config_loader,
                "get_game_sprites",
                return_value=mock_configs,
            ):
                locations = self.injector.find_sprite_locations(tmp_path)

            # Should return the mocked locations
            assert "Test_Sprite_1" in locations
            assert "Test_Sprite_2" in locations

            # Verify SpritePointer structure is correctly derived from config
            sprite1 = locations["Test_Sprite_1"]
            assert sprite1.offset == 0x10000
            assert sprite1.bank == 0x01  # (0x10000 >> 16) & 0xFF
            assert sprite1.address == 0x0000  # 0x10000 & 0xFFFF
            assert sprite1.compressed_size == 1024

            sprite2 = locations["Test_Sprite_2"]
            assert sprite2.offset == 0x20000
            assert sprite2.bank == 0x02
            assert sprite2.address == 0x0000
            assert sprite2.compressed_size == 2048

        finally:
            Path(tmp_path).unlink()

    @pytest.mark.real_hal
    def test_sprite_location_finding_real_rom(self):
        """Test finding sprite locations using real Kirby Super Star ROM (optional)"""
        # Use real ROM file for testing
        rom_path = Path(__file__).parent.parent / "Kirby Super Star (USA).sfc"

        # Skip test if ROM file doesn't exist
        if not rom_path.exists():
            self.skipTest(f"ROM file not found: {rom_path}")

        locations = self.injector.find_sprite_locations(str(rom_path))

        # Should return known locations with new naming scheme
        assert "High_Quality_Sprite_1" in locations
        assert "High_Quality_Sprite_2" in locations

        # Check structure
        for pointer in locations.values():
            assert pointer.offset is not None
            assert pointer.bank is not None
            assert pointer.address is not None


@pytest.mark.gui
@pytest.mark.usefixtures("isolated_managers")
@pytest.mark.skip_thread_cleanup(reason="InjectionDialog may spawn background threads")
class TestROMInjectionDialog(unittest.TestCase):
    """Test ROM injection dialog (requires Qt)"""

    @pytest.fixture(autouse=True)
    def init_qt(self, qtbot):
        """Initialize Qt for testing"""
        self.qtbot = qtbot

    def test_dialog_creation(self):
        """Test that dialog can be created"""
        from ui.injection_dialog import InjectionDialog

        context = get_app_context()
        dialog = InjectionDialog(
            injection_manager=context.core_operations_manager,
            settings_manager=context.application_state_manager,
        )
        self.qtbot.addWidget(dialog)

        # Check tabs exist - tab_widget is created when add_tab is called
        assert hasattr(dialog, "tab_widget")
        assert dialog.tab_widget is not None
        assert dialog.tab_widget.count() == 2
        assert dialog.tab_widget.tabText(0) == "VRAM Injection"
        assert dialog.tab_widget.tabText(1) == "ROM Injection"

        # Check ROM-specific widgets exist
        assert hasattr(dialog, "input_rom_selector")
        assert hasattr(dialog, "output_rom_selector")
        assert hasattr(dialog, "sprite_location_combo")
        assert hasattr(dialog, "fast_compression_check")


class TestInjectionDimensionValidation:
    """Test early PNG dimension validation in injection params."""

    @pytest.mark.parametrize("width,height", [(7, 8), (8, 7), (15, 16), (9, 9)])
    def test_injection_rejects_invalid_dimensions(self, app_context, tmp_path: Path, width: int, height: int):
        """Verify injection params reject non-multiple-of-8 dimensions."""
        from PIL import Image

        from core.managers.core_operations_manager import ValidationError

        # Create invalid PNG with non-multiple-of-8 dimensions
        invalid_png = tmp_path / f"invalid_{width}x{height}.png"
        img = Image.new("P", (width, height))
        img.save(invalid_png)

        # Create minimal ROM file for validation
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x8000)

        params = {
            "mode": "rom",
            "sprite_path": str(invalid_png),
            "offset": 0,
            "input_rom": str(rom_file),
            "output_rom": str(tmp_path / "output.sfc"),
        }

        with pytest.raises(ValidationError, match="multiples of 8"):
            app_context.core_operations_manager.validate_injection_params(params)

    def test_injection_accepts_valid_dimensions(self, app_context, tmp_path: Path):
        """Verify injection params accept valid multiple-of-8 dimensions."""
        from PIL import Image

        # Create valid PNG with multiple-of-8 dimensions
        valid_png = tmp_path / "valid_16x24.png"
        img = Image.new("P", (16, 24))
        img.putpalette(list(range(256)) * 3)  # Add palette
        img.save(valid_png)

        # Create ROM file that meets minimum size requirement (512KB)
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x80000)  # 512KB

        params = {
            "mode": "rom",
            "sprite_path": str(valid_png),
            "offset": 0,
            "input_rom": str(rom_file),
            "output_rom": str(tmp_path / "output.sfc"),
        }

        # Should not raise - no assertion needed, just verify no exception
        app_context.core_operations_manager.validate_injection_params(params)


if __name__ == "__main__":
    unittest.main()
