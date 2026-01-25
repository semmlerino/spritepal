"""
Tests for RangeScanDialog functionality.

Split from tests/integration/test_ui_components.py
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from ui.components.dialogs.range_scan_dialog import RangeScanDialog

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.headless,
]


@pytest.mark.usefixtures("isolated_managers")
class TestRangeScanDialog:
    """Test RangeScanDialog functionality"""

    def test_range_scan_dialog_creation(self, qtbot):
        """Test RangeScanDialog creation"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        dialog = RangeScanDialog(current_offset=0x10000, rom_size=0x400000, parent=parent_widget)
        qtbot.addWidget(dialog)

        # Check that attributes are set correctly
        assert dialog.current_offset == 0x10000
        assert dialog.rom_size == 0x400000

    def test_scan_parameters(self, qtbot):
        """Test scan parameter collection"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        dialog = RangeScanDialog(current_offset=0x10000, rom_size=0x400000, parent=parent_widget)
        qtbot.addWidget(dialog)

        # Test default range selection (index 2 = ±16KB)
        start_offset, end_offset = dialog.get_range()

        # The dialog should calculate the range based on current_offset and selected range size
        # Default is ±16KB (0x4000), so from 0x10000:
        # start = max(0, 0x10000 - 0x4000) = 0xC000
        # end = min(0x3FFFFF, 0x10000 + 0x4000) = 0x14000
        assert start_offset == 0xC000
        assert end_offset == 0x14000

    def test_validation_with_large_range(self, qtbot):
        """Test dialog can handle large range selection"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        # Create dialog with offset near the beginning of a large ROM
        dialog = RangeScanDialog(current_offset=0x10000, rom_size=0x400000, parent=parent_widget)
        qtbot.addWidget(dialog)

        # Select the largest range option (±256KB = index 4)
        dialog.range_combo.setCurrentIndex(4)

        # Get the calculated range
        start_offset, end_offset = dialog.get_range()

        # With ±256KB (0x40000) from 0x10000:
        # start = max(0, 0x10000 - 0x40000) = 0
        # end = min(0x3FFFFF, 0x10000 + 0x40000) = 0x50000
        assert start_offset == 0
        assert end_offset == 0x50000

        # Verify the range is large but valid
        range_size = end_offset - start_offset
        assert range_size == 0x50000  # 320KB range
        assert range_size <= 0x1000000  # Less than 16MB max
