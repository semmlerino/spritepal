"""
Tests for ROMMapWidget functionality.

Split from tests/integration/test_ui_components.py
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from ui.components.visualization.rom_map_widget import (
    SPRITE_CLEANUP_TARGET,
    SPRITE_CLEANUP_THRESHOLD,
    ROMMapWidget,
)

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.headless,
]


@pytest.mark.usefixtures("isolated_managers")
class TestROMMapWidget:
    """Test ROMMapWidget functionality"""

    def test_rom_map_widget_creation(self, qtbot):
        """Test ROMMapWidget can be created with proper Qt parent"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        widget = ROMMapWidget(parent_widget)
        qtbot.addWidget(widget)

        assert widget.parent() == parent_widget

    def test_add_sprite_data(self, qtbot):
        """Test adding sprite data to ROM map"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        widget = ROMMapWidget(parent_widget)
        qtbot.addWidget(widget)

        # Test adding sprite with quality
        offset = 0x1000
        quality = 0.95

        widget.add_found_sprite(offset, quality)

        # Verify sprite was added
        assert len(widget.found_sprites) == 1
        assert widget.found_sprites[0] == (offset, quality)

    def test_sprite_count_limits(self, qtbot, monkeypatch):
        """Test sprite count limits prevent memory leaks"""
        # Patch constants to smaller values for fast testing (12,100 → ~200 iterations)
        test_threshold = 100
        test_target = 50
        monkeypatch.setattr("ui.components.visualization.rom_map_widget.SPRITE_CLEANUP_THRESHOLD", test_threshold)
        monkeypatch.setattr("ui.components.visualization.rom_map_widget.SPRITE_CLEANUP_TARGET", test_target)

        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        widget = ROMMapWidget(parent_widget)
        qtbot.addWidget(widget)

        # Add enough sprites to trigger cleanup (threshold + buffer)
        for i in range(test_threshold + 100):
            widget.add_found_sprite(0x1000 + i * 32, 1.0)

        # Should have cleaned up to around target count (allow small variation)
        assert len(widget.found_sprites) <= test_target + 100
        assert len(widget.found_sprites) < test_threshold

    def test_cleanup_method(self, qtbot):
        """Test cleanup method clears resources"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        widget = ROMMapWidget(parent_widget)
        qtbot.addWidget(widget)

        # Add some sprite data
        widget.add_found_sprite(0x1000, 1.0)
        widget.add_found_sprite(0x2000, 0.8)
        assert len(widget.found_sprites) > 0

        # Clear sprites
        widget.clear_sprites()

        # Verify resources cleared
        assert len(widget.found_sprites) == 0
