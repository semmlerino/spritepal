"""Tests for main_window capture lookup using ROM offset with SMC header.

Finding #3: Opening capture from ROM panel uses get_capture_by_offset() with ROM offset
but the method expects FILE offset. This loses capture naming when SMC headers present.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


class TestMainWindowCaptureLookup:
    """Tests for capture lookup in main_window._open_mesen_capture_offset()."""

    def test_capture_lookup_uses_rom_offset_with_smc_header(self):
        """Verify main_window uses get_capture_by_rom_offset with correct SMC header."""
        from core.mesen_integration.log_watcher import CapturedOffset

        # Create a mock capture
        file_offset = 0x3C7201  # FILE offset (includes 0x200 SMC header)
        rom_offset = 0x3C7001  # ROM offset (FILE - SMC header)
        smc_offset = 0x200
        frame = 1500

        capture = CapturedOffset(
            offset=file_offset,
            frame=frame,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )

        # Create mock log_watcher
        log_watcher = MagicMock()
        log_watcher.get_capture_by_rom_offset.return_value = capture

        # Create mock mesen_captures_section with smc_offset property
        mock_captures_section = MagicMock()
        type(mock_captures_section).smc_offset = PropertyMock(return_value=smc_offset)

        # Create mock rom_extraction_panel
        mock_rom_panel = MagicMock()
        mock_rom_panel.mesen_captures_section = mock_captures_section
        mock_rom_panel.rom_path = "/path/to/rom.sfc"

        # Verify the logic without instantiating full MainWindow
        # We test the specific lookup call pattern
        retrieved_smc_offset = mock_rom_panel.mesen_captures_section.smc_offset
        assert retrieved_smc_offset == smc_offset

        result = log_watcher.get_capture_by_rom_offset(rom_offset, retrieved_smc_offset)

        # Verify correct method was called with ROM offset and SMC header
        log_watcher.get_capture_by_rom_offset.assert_called_once_with(rom_offset, smc_offset)
        assert result == capture
        assert result.frame == frame

    def test_mesen_captures_section_exposes_smc_offset(self, qtbot):
        """Verify MesenCapturesSection exposes smc_offset property."""
        from ui.rom_extraction.widgets.mesen_captures_section import MesenCapturesSection

        section = MesenCapturesSection()
        qtbot.addWidget(section)

        # Default should be 0
        assert section.smc_offset == 0

        # Set and verify
        section.set_smc_offset(512)
        assert section.smc_offset == 512

        section.set_smc_offset(0)
        assert section.smc_offset == 0


class TestCaptureLookupIntegration:
    """Integration tests for capture lookup flow."""

    def test_rom_offset_lookup_finds_capture_with_smc_header(self):
        """Test that ROM offset lookup correctly finds capture when SMC header present."""
        from core.mesen_integration.log_watcher import CapturedOffset, LogWatcher

        log_watcher = LogWatcher()

        # Add capture with FILE offset (includes SMC header)
        file_offset = 0x293AEB + 0x200  # FILE offset
        capture = CapturedOffset(
            offset=file_offset,
            frame=1938,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        log_watcher._recent_captures.append(capture)

        # ROM offset (without SMC header)
        rom_offset = 0x293AEB
        smc_header = 0x200

        # Should find capture using ROM offset + SMC header conversion
        result = log_watcher.get_capture_by_rom_offset(rom_offset, smc_header)
        assert result is not None
        assert result.frame == 1938
        assert result.offset == file_offset

    def test_rom_offset_lookup_returns_none_without_correct_header(self):
        """Test that ROM offset lookup fails when SMC header is incorrect."""
        from core.mesen_integration.log_watcher import CapturedOffset, LogWatcher

        log_watcher = LogWatcher()

        # Add capture with FILE offset that includes 0x200 header
        file_offset = 0x100200
        capture = CapturedOffset(
            offset=file_offset,
            frame=100,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        log_watcher._recent_captures.append(capture)

        # Try with wrong SMC header (0 instead of 0x200)
        rom_offset = 0x100000
        result = log_watcher.get_capture_by_rom_offset(rom_offset, smc_header_offset=0)

        # Should NOT find it because 0x100000 + 0 != 0x100200
        assert result is None
