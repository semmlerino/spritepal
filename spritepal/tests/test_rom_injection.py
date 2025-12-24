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

from core.di_container import inject
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
        self.test_rom[header_offset + 28 : header_offset + 30] = complement.to_bytes(
            2, "little"
        )
        self.test_rom[header_offset + 30 : header_offset + 32] = checksum.to_bytes(
            2, "little"
        )

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

    def test_sprite_location_finding(self):
        """Test finding sprite locations using real Kirby Super Star ROM"""
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

        injection_manager = inject(CoreOperationsManager)
        settings_manager = inject(ApplicationStateManager)
        dialog = InjectionDialog(
            injection_manager=injection_manager,
            settings_manager=settings_manager,
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

if __name__ == "__main__":
    unittest.main()
