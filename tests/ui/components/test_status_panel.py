"""
Tests for StatusPanel functionality.

Split from tests/integration/test_ui_components.py
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from core.app_context import get_app_context
from ui.components.panels.status_panel import StatusPanel

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.headless,
]


@pytest.mark.usefixtures("isolated_managers")
class TestStatusPanel:
    """Test StatusPanel functionality"""

    def test_status_panel_creation(self, qtbot):
        """Test StatusPanel creation"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        context = get_app_context()
        panel = StatusPanel(
            parent_widget, settings_manager=context.application_state_manager, rom_cache=context.rom_cache
        )
        qtbot.addWidget(panel)

    def test_status_updates(self, qtbot):
        """Test status message updates"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        context = get_app_context()
        panel = StatusPanel(
            parent_widget, settings_manager=context.application_state_manager, rom_cache=context.rom_cache
        )
        qtbot.addWidget(panel)

        # Ensure the parent widget is shown so the entire hierarchy is visible
        parent_widget.show()
        panel.show()

        # Test status update
        panel.update_status("Scanning ROM...")
        assert panel.detection_info.text() == "Scanning ROM..."

        # Test progress bar functionality
        panel.show_progress(0, 100)

        assert panel.scan_progress.minimum() == 0
        assert panel.scan_progress.maximum() == 100
        assert panel.scan_progress.value() == 0

        panel.update_progress(50)
        assert panel.scan_progress.value() == 50

        # Test hide functionality
        panel.hide_progress()
        assert panel.scan_progress.value() == 50

        # Test update_progress when progress bar is hidden (should not update)
        panel.update_progress(25)
        assert panel.scan_progress.value() == 50

        # Show again and test update works
        panel.show_progress(0, 100)
        panel.update_progress(75)
        assert panel.scan_progress.value() == 75
