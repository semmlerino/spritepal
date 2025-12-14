"""
Fixed tests for UI components
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Test characteristics: Real GUI components requiring display
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.file_io,
    pytest.mark.gui,
    pytest.mark.qt_app,
    pytest.mark.qt_real,
    pytest.mark.rom_data,
    pytest.mark.slow,
    pytest.mark.widget,
    pytest.mark.requires_display,
]


class TestROMMapWidgetFixed:
    """Test ROMMapWidget functionality with proper setup"""

    def test_rom_map_widget_creation_fixed(self, qtbot):
        """Test ROMMapWidget can be created with qtbot"""
        from PySide6.QtWidgets import QWidget

        from ui.components.visualization.rom_map_widget import ROMMapWidget

        # Create widget with no parent first
        parent = QWidget()
        qtbot.addWidget(parent)

        # Create widget with proper parent
        widget = ROMMapWidget(parent)
        qtbot.addWidget(widget)

        # Verify basic initialization
        assert hasattr(widget, "found_sprites")
        assert hasattr(widget, "current_offset")
        assert hasattr(widget, "rom_size")
        assert widget.parent() == parent

    def test_add_sprite_data_fixed(self, qtbot):
        """Test adding sprite data to ROM map with qtbot"""
        from PySide6.QtWidgets import QWidget

        from ui.components.visualization.rom_map_widget import ROMMapWidget

        parent = QWidget()
        qtbot.addWidget(parent)
        widget = ROMMapWidget(parent)
        qtbot.addWidget(widget)

        # Test adding sprite with quality
        offset = 0x1000
        quality = 0.95

        widget.add_found_sprite(offset, quality)

        # Verify sprite was added
        assert len(widget.found_sprites) == 1
        assert widget.found_sprites[0] == (offset, quality)
