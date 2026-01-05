#!/usr/bin/env python3
"""
Regression tests for DropZone feedback loop fixes (Task 4.1.A).

Tests verify that signal blocking prevents infinite loops when
programmatically setting file paths in ExtractTab.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

if TYPE_CHECKING:
    from pathlib import Path

    from pytestqt.qtbot import QtBot


class TestDropZoneFeedbackLoop:
    """Tests for DropZone signal feedback loop prevention."""

    def test_drop_zone_set_no_recursion(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify set_vram_file() doesn't trigger infinite signal loop.

        Bug: ExtractTab.set_vram_file() → DropZone.set_file() → signal emitted
             → lambda in ExtractTab → set_vram_file() → infinite loop

        Fix: Use QSignalBlocker in ExtractTab.set_vram_file() to prevent re-emission.
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.views.tabs.extract_tab import ExtractTab

        # Create temporary VRAM file
        vram_file = tmp_path / "test_vram.dmp"
        vram_file.write_bytes(b"\x00" * 1024)

        # Create settings manager (required by DropZone)
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create ExtractTab (contains DropZone)
        tab = ExtractTab(settings_manager=settings_mgr)

        # Connect signal counter to file_dropped
        signal_counter = Mock()
        tab.vram_drop.file_dropped.connect(signal_counter)

        # Call set_vram_file() with valid path
        tab.set_vram_file(str(vram_file))

        # Process Qt events
        qtbot.wait(10)

        # Assert signal emitted exactly once (not infinite)
        # The signal should NOT emit because of QSignalBlocker
        assert signal_counter.call_count == 0, (
            f"Expected 0 emissions (blocked), got {signal_counter.call_count}. "
            "QSignalBlocker should prevent signal during programmatic set."
        )

        # Verify file was actually set
        assert tab.vram_drop.has_file()
        assert tab.vram_drop.get_file_path() == str(vram_file)

    def test_drop_zone_clear_handles_empty(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify clear() handles empty state gracefully (idempotence).

        Bug: Calling clear() on empty DropZone could emit signal unnecessarily.

        Fix: Idempotence check in DropZone.clear() - return early if already empty.
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.widgets.drop_zone import DropZone

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create DropZone
        drop_zone = DropZone("VRAM", settings_manager=settings_mgr, required=True)

        # Create temporary file
        test_file = tmp_path / "test.dmp"
        test_file.write_bytes(b"\x00" * 64)

        # Set file
        drop_zone.set_file(str(test_file))
        assert drop_zone.has_file()
        assert drop_zone.file_path == str(test_file)

        # Clear it
        drop_zone.clear()
        assert not drop_zone.has_file()
        assert drop_zone.file_path == ""

        # Connect signal counter AFTER first clear
        signal_counter = Mock()
        drop_zone.file_dropped.connect(signal_counter)

        # Call clear() again on empty state
        drop_zone.clear()

        # Verify no error and still empty
        assert not drop_zone.has_file()
        assert drop_zone.file_path == ""

        # Signal should NOT emit on second clear (idempotence)
        assert signal_counter.call_count == 0, "clear() on empty state should not emit signal"

    def test_drop_zone_idempotence(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify set_file() with same path is idempotent.

        Bug: Calling set_file() multiple times with same path could emit signal each time.

        Fix: Idempotence check in DropZone.set_file() - return early if path unchanged.
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.widgets.drop_zone import DropZone

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create DropZone
        drop_zone = DropZone("VRAM", settings_manager=settings_mgr, required=True)

        # Create temporary file
        test_file = tmp_path / "test.dmp"
        test_file.write_bytes(b"\x00" * 64)

        # Connect signal counter
        signal_counter = Mock()
        drop_zone.file_dropped.connect(signal_counter)

        # Set file first time
        drop_zone.set_file(str(test_file))
        qtbot.wait(10)

        # Should emit once
        assert signal_counter.call_count == 1, "First set_file() should emit signal"
        signal_counter.reset_mock()

        # Set file again with SAME path
        drop_zone.set_file(str(test_file))
        qtbot.wait(10)

        # Should NOT emit again (idempotence)
        assert signal_counter.call_count == 0, "set_file() with same path should not emit signal"

        # Verify file is still set
        assert drop_zone.has_file()
        assert drop_zone.get_file_path() == str(test_file)

    def test_extract_tab_cgram_signal_blocking(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify set_cgram_file() also uses QSignalBlocker."""
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.views.tabs.extract_tab import ExtractTab

        # Create temporary CGRAM file
        cgram_file = tmp_path / "test_cgram.dmp"
        cgram_file.write_bytes(b"\x00" * 512)

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create ExtractTab
        tab = ExtractTab(settings_manager=settings_mgr)

        # Connect signal counter to cgram file_dropped
        signal_counter = Mock()
        tab.cgram_drop.file_dropped.connect(signal_counter)

        # Call set_cgram_file() with valid path
        tab.set_cgram_file(str(cgram_file))
        qtbot.wait(10)

        # Assert signal NOT emitted (blocked)
        assert signal_counter.call_count == 0, "QSignalBlocker should prevent signal during programmatic set"

        # Verify file was actually set
        assert tab.cgram_drop.has_file()
        assert tab.cgram_drop.get_file_path() == str(cgram_file)

    def test_inject_tab_signal_blocking(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify InjectTab also uses QSignalBlocker for PNG and VRAM."""
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.views.tabs.inject_tab import InjectTab

        # Create temporary files
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        vram_file = tmp_path / "test_vram.dmp"
        vram_file.write_bytes(b"\x00" * 1024)

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create InjectTab
        tab = InjectTab(settings_manager=settings_mgr)

        # Test PNG signal blocking
        png_counter = Mock()
        tab.png_drop.file_dropped.connect(png_counter)

        tab.set_png_file(str(png_file))
        qtbot.wait(10)

        assert png_counter.call_count == 0, "PNG set should block signals"
        assert tab.png_drop.has_file()

        # Test VRAM signal blocking
        vram_counter = Mock()
        tab.vram_drop.file_dropped.connect(vram_counter)

        tab.set_vram_file(str(vram_file))
        qtbot.wait(10)

        assert vram_counter.call_count == 0, "VRAM set should block signals"
        assert tab.vram_drop.has_file()
