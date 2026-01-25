"""
Tests for ScanControlsPanel functionality.

Split from tests/integration/test_ui_components.py
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from core.app_context import get_app_context
from ui.components.panels.scan_controls_panel import ScanControlsPanel

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.headless,
]


@pytest.mark.usefixtures("isolated_managers")
class TestScanControlsPanel:
    """Test ScanControlsPanel functionality"""

    def test_scan_controls_creation(self, qtbot):
        """Test ScanControlsPanel creation"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = ScanControlsPanel(parent_widget, rom_cache=get_app_context().rom_cache)
        qtbot.addWidget(panel)

    def test_scan_parameters_validation(self, qtbot):
        """Test scan parameter validation"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = ScanControlsPanel(parent_widget, rom_cache=get_app_context().rom_cache)
        qtbot.addWidget(panel)

        # Test the validation method directly with mock parameters
        start_offset = 0x1000
        end_offset = 0x2000

        is_valid = panel._validate_scan_parameters(start_offset, end_offset)

        assert is_valid is True, "Valid scan parameters should pass validation"
        assert end_offset > start_offset, "End offset should be greater than start offset"
