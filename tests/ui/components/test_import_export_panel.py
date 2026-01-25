"""
Tests for ImportExportPanel functionality.

Split from tests/integration/test_ui_components.py
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from ui.components.panels.import_export_panel import ImportExportPanel

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="UI tests may involve managers that spawn threads"),
    pytest.mark.headless,
]


@pytest.mark.usefixtures("isolated_managers")
class TestImportExportPanel:
    """Test ImportExportPanel functionality"""

    def test_import_export_creation(self, qtbot):
        """Test ImportExportPanel creation"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = ImportExportPanel(parent_widget)
        qtbot.addWidget(panel)

    def test_file_operations(self, qtbot):
        """Test file import/export operations"""
        parent_widget = QWidget()
        qtbot.addWidget(parent_widget)

        panel = ImportExportPanel(parent_widget)
        qtbot.addWidget(panel)

        # Test setting ROM data
        panel.set_rom_data("/test/path/test_rom.smc", 0x400000)
        assert panel.rom_path == "/test/path/test_rom.smc"
        assert panel.rom_size == 0x400000

        # Test setting sprite data
        test_sprites = [(0x1000, 0.8), (0x2000, 0.9)]
        panel.set_found_sprites(test_sprites)
        assert panel.found_sprites == test_sprites
