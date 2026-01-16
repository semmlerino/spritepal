"""Tests for RecentCapturesWidget.has_capture() with FILE and ROM offset semantics.

After Fix 1.1 (FILE offset immutability), has_capture() needs to support both:
- FILE offset lookup (original Mesen capture identity)
- ROM offset lookup (after alignment adjustment)
"""

from datetime import UTC, datetime

import pytest


class TestHasCaptureFileOffset:
    """Tests for has_capture() with FILE offsets (original behavior)."""

    def test_has_capture_finds_file_offset(self, qtbot):
        """has_capture() should find captures by FILE offset."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        file_offset = 0x3C7001
        capture = CapturedOffset(
            offset=file_offset,
            frame=100,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture)

        # FILE offset should be found
        assert widget.has_capture(file_offset), "has_capture should find FILE offset"

    def test_has_capture_file_offset_persists_after_rom_update(self, qtbot):
        """FILE offset should still be findable after ROM offset alignment."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        file_offset = 0x293AEB
        rom_offset_aligned = 0x293AEF
        capture = CapturedOffset(
            offset=file_offset,
            frame=1938,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture)

        # Update ROM offset (alignment adjustment)
        widget.update_capture_offset(file_offset, rom_offset_aligned)

        # FILE offset should STILL be findable (it's the immutable identity)
        assert widget.has_capture(file_offset), "has_capture should still find FILE offset after ROM alignment"


class TestHasCaptureRomOffset:
    """Tests for has_capture() with ROM offsets (after alignment)."""

    def test_has_capture_finds_rom_offset_after_update(self, qtbot):
        """has_capture() should find captures by ROM offset after alignment."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        file_offset = 0x293AEB
        rom_offset_aligned = 0x293AEF
        capture = CapturedOffset(
            offset=file_offset,
            frame=1938,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture)

        # Update ROM offset (alignment adjustment)
        widget.update_capture_offset(file_offset, rom_offset_aligned)

        # ROM offset should be findable after update
        assert widget.has_capture(rom_offset_aligned), "has_capture should find aligned ROM offset"


class TestHasCaptureByExplicitType:
    """Tests for explicit FILE/ROM offset lookup methods."""

    def test_has_capture_by_file_offset_explicit(self, qtbot):
        """has_capture_by_file_offset() should only check FILE offsets."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        file_offset = 0x3C7001
        rom_offset_aligned = 0x3C7005
        capture = CapturedOffset(
            offset=file_offset,
            frame=100,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture)
        widget.update_capture_offset(file_offset, rom_offset_aligned)

        # Should have explicit FILE offset method
        assert hasattr(widget, "has_capture_by_file_offset")
        assert widget.has_capture_by_file_offset(file_offset)
        assert not widget.has_capture_by_file_offset(rom_offset_aligned)

    def test_has_capture_by_rom_offset_explicit(self, qtbot):
        """has_capture_by_rom_offset() should check item data ROM offsets."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        file_offset = 0x3C7001
        rom_offset_aligned = 0x3C7005
        capture = CapturedOffset(
            offset=file_offset,
            frame=100,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture)
        widget.update_capture_offset(file_offset, rom_offset_aligned)

        # Should have explicit ROM offset method
        assert hasattr(widget, "has_capture_by_rom_offset")
        assert widget.has_capture_by_rom_offset(rom_offset_aligned)
        # Original FILE offset should not be found as ROM offset (unless no header)
        # After alignment, the old rom_offset was file_offset, now it's rom_offset_aligned
        assert not widget.has_capture_by_rom_offset(file_offset)


class TestDisplayUpdateWithSMCHeader:
    """Tests for display text update when SMC header is present."""

    def test_display_updates_file_offset_when_smc_header_present(self, qtbot):
        """When SMC header is present, display text shows FILE offset and should be updated."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        # Set SMC header offset (0x200 bytes)
        smc_offset = 0x200
        widget.set_smc_offset(smc_offset)

        # FILE offset as reported by Mesen (includes SMC header)
        file_offset = 0x3C7201
        # ROM offset = FILE - SMC header
        rom_offset_initial = file_offset - smc_offset  # 0x3C7001

        capture = CapturedOffset(
            offset=file_offset,
            frame=100,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture)

        # Verify display shows FILE offset
        list_widget = widget._list_widget
        item = list_widget.item(0)
        initial_text = item.text()
        assert f"{file_offset:06X}" in initial_text.upper(), (
            f"Display should show FILE offset 0x{file_offset:06X}, got: {initial_text}"
        )

        # Alignment adjustment: ROM offset shifts by 4 bytes
        rom_offset_aligned = rom_offset_initial + 4  # 0x3C7005
        # New FILE offset = new ROM + SMC header
        file_offset_aligned = rom_offset_aligned + smc_offset  # 0x3C7205

        # Update offset (alignment discovered sprite at +4 bytes)
        widget.update_capture_offset(rom_offset_initial, rom_offset_aligned)

        # Verify display updated to new FILE offset
        updated_text = item.text()
        assert f"{file_offset_aligned:06X}" in updated_text.upper(), (
            f"Display should show updated FILE offset 0x{file_offset_aligned:06X}, got: {updated_text}"
        )

    def test_tooltip_shows_both_offsets_after_update(self, qtbot):
        """Tooltip should show both ROM and FILE offsets after alignment update."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        smc_offset = 0x200
        widget.set_smc_offset(smc_offset)

        file_offset = 0x100200
        rom_offset_initial = file_offset - smc_offset
        rom_offset_aligned = rom_offset_initial + 4

        capture = CapturedOffset(
            offset=file_offset,
            frame=500,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture)

        widget.update_capture_offset(rom_offset_initial, rom_offset_aligned)

        list_widget = widget._list_widget
        item = list_widget.item(0)
        tooltip = item.toolTip()

        # Tooltip should contain new ROM offset
        assert f"0x{rom_offset_aligned:06X}" in tooltip, f"Tooltip should contain ROM offset 0x{rom_offset_aligned:06X}"
