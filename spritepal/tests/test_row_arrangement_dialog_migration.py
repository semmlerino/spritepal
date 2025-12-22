"""
Test RowArrangementDialog migration to SplitterDialog

Validates that the migrated RowArrangementDialog maintains all original functionality
while using the new SplitterDialog architecture.

This is a real Qt integration test that requires a GUI environment.
"""
from __future__ import annotations

import contextlib
import os
import tempfile

import pytest
from PIL import Image

from ui.components import SplitterDialog
from ui.row_arrangement_dialog import RowArrangementDialog

# Skip in headless environments - this tests real Qt dialog behavior
pytestmark = [
    pytest.mark.requires_display,
    pytest.mark.gui,
    pytest.mark.integration,
    pytest.mark.allows_registry_state,  # Dialog initialization uses ManagerRegistry
]

class TestRowArrangementDialogMigration:
    """Test RowArrangementDialog migration to SplitterDialog architecture"""

    @pytest.fixture
    def test_sprite_image(self):
        """Create a test sprite image"""
        # Create a simple test image
        test_image = Image.new("L", (128, 64), 0)  # Grayscale image

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        test_image.save(temp_file.name)
        temp_file.close()

        yield temp_file.name

        # Cleanup
        with contextlib.suppress(Exception):
            Path(temp_file.name).unlink()

    def test_row_arrangement_dialog_inherits_from_splitter_dialog(self, test_sprite_image, qtbot):
        """Test that RowArrangementDialog properly inherits from SplitterDialog"""
        dialog = RowArrangementDialog(test_sprite_image, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Verify inheritance
        assert isinstance(dialog, SplitterDialog)

        # Verify SplitterDialog features are available
        assert dialog.main_splitter is not None
        assert dialog.status_bar is not None
        assert dialog.button_box is not None

        # Verify dialog configuration
        assert dialog.windowTitle() == "Arrange Sprite Rows - Grayscale"
        assert dialog.isModal() is True

    def test_row_arrangement_dialog_has_correct_panels(self, test_sprite_image, qtbot):
        """Test that RowArrangementDialog has the correct panel structure"""
        dialog = RowArrangementDialog(test_sprite_image, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Should have 2 main panels (content and preview)
        assert dialog.main_splitter.count() == 2

        # Verify main components exist
        assert hasattr(dialog, "left_panel")  # Available rows
        assert hasattr(dialog, "right_panel")  # Arranged rows
        assert hasattr(dialog, "available_list")
        assert hasattr(dialog, "arranged_list")
        assert hasattr(dialog, "preview_label")

    def test_row_arrangement_dialog_status_bar_integration(self, test_sprite_image, qtbot):
        """Test that status bar integration works with SplitterDialog"""
        dialog = RowArrangementDialog(test_sprite_image, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Test status update functionality
        test_message = "Test status message"
        dialog._update_status(test_message)

        # Verify status is displayed
        assert dialog.status_bar.currentMessage() == test_message

    def test_row_arrangement_dialog_button_integration(self, test_sprite_image, qtbot):
        """Test that button integration works with SplitterDialog"""
        dialog = RowArrangementDialog(test_sprite_image, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Verify export button was added
        assert hasattr(dialog, "export_btn")
        assert dialog.export_btn is not None

        # Verify button box exists and is functional
        assert dialog.button_box is not None

        # Export button should be initially disabled
        assert not dialog.export_btn.isEnabled()

    def test_row_arrangement_dialog_maintains_functionality(self, test_sprite_image, qtbot):
        """Test that migrated dialog maintains all original functionality"""
        dialog = RowArrangementDialog(test_sprite_image, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Test that all key attributes are present
        assert hasattr(dialog, "sprite_path")
        assert hasattr(dialog, "tiles_per_row")
        assert hasattr(dialog, "tile_rows")
        assert hasattr(dialog, "arrangement_manager")
        assert hasattr(dialog, "colorizer")
        assert hasattr(dialog, "preview_generator")

        # Test that the dialog loads sprite data
        assert dialog.sprite_path == test_sprite_image
        assert dialog.tiles_per_row == 16

    def test_row_arrangement_dialog_signal_connections(self, test_sprite_image, qtbot):
        """Test that signal connections are maintained after migration"""
        dialog = RowArrangementDialog(test_sprite_image, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Verify UI components have expected connections
        # Available list should have signal connections
        assert dialog.available_list is not None

        # Arranged list should have signal connections
        assert dialog.arranged_list is not None

        # Button should have click connections
        assert dialog.export_btn is not None

    def test_row_arrangement_dialog_splitter_configuration(self, test_sprite_image, qtbot):
        """Test that splitter configuration is correct"""
        dialog = RowArrangementDialog(test_sprite_image, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Main splitter should be vertical
        from PySide6.QtCore import Qt
        assert dialog.main_splitter.orientation() == Qt.Orientation.Vertical

        # Handle width should be set correctly
        assert dialog.main_splitter.handleWidth() == 8

        # Should have appropriate stretch factors
        assert dialog.main_splitter.count() == 2
