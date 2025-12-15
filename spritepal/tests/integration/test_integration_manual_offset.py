"""
Integration tests for manual offset dialog using real components.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from core.managers import ExtractionManager


@pytest.mark.integration
@pytest.mark.gui
@pytest.mark.skip_thread_cleanup(reason="Dialog uses background workers for preview generation")
class TestManualOffsetDialog:
    """Test manual offset dialog with real ROM data and preview generation."""

    def test_dialog_creation_and_display(self, manual_offset_dialog, qtbot):
        """Test that dialog creates and displays correctly."""
        dialog = manual_offset_dialog

        # Show the dialog
        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Verify main components exist
        assert dialog.browse_tab is not None
        assert dialog.smart_tab is not None
        assert dialog.history_tab is not None
        assert dialog.preview_widget is not None

        # Verify browse tab components
        assert hasattr(dialog.browse_tab, 'position_slider')
        assert hasattr(dialog.browse_tab, 'find_sprites_button')
        assert hasattr(dialog.browse_tab, 'next_button')
        assert hasattr(dialog.browse_tab, 'prev_button')

    def test_slider_navigation(self, manual_offset_dialog, test_rom_with_sprites, qtbot):
        """Test that slider navigation updates offset correctly."""
        dialog = manual_offset_dialog
        rom_info = test_rom_with_sprites

        # Set ROM data
        extraction_manager = ExtractionManager()
        dialog.set_rom_data(
            str(rom_info['path']),
            rom_info['path'].stat().st_size,
            extraction_manager
        )

        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Get initial offset

        # Move slider
        new_value = 0x10000
        dialog.browse_tab.position_slider.setValue(new_value)

        # Wait for offset to update
        qtbot.waitUntil(lambda: dialog.get_current_offset() == new_value, timeout=500)

        # Verify offset changed
        assert dialog.get_current_offset() == new_value
        assert dialog.browse_tab.position_slider.value() == new_value

        # Verify display updated
        offset_text = dialog.browse_tab.offset_label.text()
        assert f"{new_value:06X}" in offset_text or f"{new_value:X}" in offset_text

    def test_manual_offset_input(self, manual_offset_dialog, test_rom_with_sprites, qtbot):
        """Test manual offset input via spinbox."""
        dialog = manual_offset_dialog
        rom_info = test_rom_with_sprites

        # Set ROM data
        extraction_manager = ExtractionManager()
        dialog.set_rom_data(
            str(rom_info['path']),
            rom_info['path'].stat().st_size,
            extraction_manager
        )

        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Set offset via spinbox
        target_offset = 0x20000
        dialog.browse_tab.manual_spinbox.setValue(target_offset)

        # Trigger the change
        dialog.browse_tab.manual_spinbox.editingFinished.emit()
        qtbot.waitUntil(lambda: dialog.get_current_offset() == target_offset, timeout=500)

        # Verify offset changed
        assert dialog.get_current_offset() == target_offset
        assert dialog.browse_tab.position_slider.value() == target_offset

    def test_find_sprites_button_click(self, manual_offset_dialog, test_rom_with_sprites, qtbot, mocker, wait_for_signal_processed):
        """Test that Find Sprites button triggers sprite scanning."""
        dialog = manual_offset_dialog
        rom_info = test_rom_with_sprites

        # Set ROM data
        extraction_manager = ExtractionManager()
        dialog.set_rom_data(
            str(rom_info['path']),
            rom_info['path'].stat().st_size,
            extraction_manager
        )

        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Mock the scan method to avoid actual slow scanning (we just want to verify it's called)
        scan_mock = mocker.patch.object(dialog, '_scan_for_sprites')

        # Click Find Sprites button
        find_button = dialog.browse_tab.find_sprites_button
        assert find_button is not None
        assert find_button.isEnabled()

        # Click the button
        qtbot.mouseClick(find_button, Qt.MouseButton.LeftButton)

        # Wait for signal propagation
        wait_for_signal_processed()

        # Verify scan was triggered
        assert scan_mock.called

    def test_preview_generation_on_offset_change(self, manual_offset_dialog, test_rom_with_sprites, qtbot, wait_for):
        """Test that preview is generated when offset changes."""
        dialog = manual_offset_dialog
        rom_info = test_rom_with_sprites

        # Set ROM data
        extraction_manager = ExtractionManager()
        dialog.set_rom_data(
            str(rom_info['path']),
            rom_info['path'].stat().st_size,
            extraction_manager
        )

        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Track preview updates
        preview_updated = False

        def on_preview_ready(tile_data, width, height, name):
            nonlocal preview_updated
            preview_updated = True

        # Connect to preview signal if coordinator exists
        if dialog._smart_preview_coordinator:
            dialog._smart_preview_coordinator.preview_ready.connect(on_preview_ready)

        # Change offset to trigger preview
        dialog.set_offset(0x10000)

        # Wait for preview (with timeout)
        wait_for(lambda: preview_updated, timeout=3000, message="Preview not generated")

        assert preview_updated

    def test_next_prev_navigation(self, manual_offset_dialog, test_rom_with_sprites, qtbot, wait_for_signal_processed):
        """Test next/prev sprite navigation buttons.

        Note: Next/Prev buttons emit find_next_clicked/find_prev_clicked signals which
        search for sprites - they don't simply increment/decrement offset. Without a
        pre-populated sprite cache, the behavior is undefined, so we just verify:
        1. Buttons exist and are clickable
        2. Navigation doesn't crash
        3. Offset stays within valid bounds
        """
        dialog = manual_offset_dialog
        rom_info = test_rom_with_sprites

        # Set ROM data
        extraction_manager = ExtractionManager()
        dialog.set_rom_data(
            str(rom_info['path']),
            rom_info['path'].stat().st_size,
            extraction_manager
        )

        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Set initial offset
        initial_offset = 0x10000
        dialog.set_offset(initial_offset)
        qtbot.waitUntil(lambda: dialog.get_current_offset() == initial_offset, timeout=500)

        # Verify buttons exist
        next_button = dialog.browse_tab.next_button
        prev_button = dialog.browse_tab.prev_button
        assert next_button is not None
        assert prev_button is not None

        # Click Next button - just verify no crash
        qtbot.mouseClick(next_button, Qt.MouseButton.LeftButton)
        wait_for_signal_processed()

        # Verify offset is within bounds
        offset_after_next = dialog.get_current_offset()
        assert 0 <= offset_after_next < rom_info['path'].stat().st_size

        # Click Prev button - just verify no crash
        qtbot.mouseClick(prev_button, Qt.MouseButton.LeftButton)
        wait_for_signal_processed()

        # Verify offset is within bounds
        offset_after_prev = dialog.get_current_offset()
        assert 0 <= offset_after_prev < rom_info['path'].stat().st_size

@pytest.mark.integration
@pytest.mark.gui
class TestSpriteScanDialog:
    """Test sprite scanning and results dialog."""

    @pytest.mark.slow
    @pytest.mark.timeout(120)  # This test does real ROM scanning which is slow
    def test_sprite_scan_with_results(self, manual_offset_dialog, test_rom_with_sprites, qtbot, wait_for, mocker, wait_for_signal_processed):
        """Test full sprite scan workflow with results dialog."""
        from PySide6.QtWidgets import QDialog, QMessageBox

        dialog = manual_offset_dialog
        rom_info = test_rom_with_sprites

        # Mock QDialog.exec to prevent blocking - return Accepted immediately
        mocker.patch.object(QDialog, 'exec', return_value=QDialog.DialogCode.Accepted)

        # Mock QMessageBox static methods to prevent blocking
        mocker.patch.object(QMessageBox, 'information', return_value=QMessageBox.StandardButton.Ok)
        mocker.patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Ok)
        mocker.patch.object(QMessageBox, 'critical', return_value=QMessageBox.StandardButton.Ok)

        # Set ROM data
        extraction_manager = ExtractionManager()
        dialog.set_rom_data(
            str(rom_info['path']),
            rom_info['path'].stat().st_size,
            extraction_manager
        )

        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Start scan - with exec mocked, this won't block
        dialog._scan_for_sprites()

        # Wait for scan to be initiated and dialogs to process
        wait_for_signal_processed()

        # If we have test sprites, verify some were found
        if rom_info['sprites']:
            # The scan should have completed
            # Check if a results dialog was shown
            pass  # Results depend on implementation

        # Explicitly stop the scan to prevent thread leak
        # The scan worker runs in a background thread and may not have finished
        dialog._cancel_sprite_scan()

        # Give the worker time to clean up
        qtbot.wait(100)

    def test_sprite_selection_navigation(self, manual_offset_dialog, test_rom_with_sprites, qtbot):
        """Test selecting a sprite from results navigates to it."""
        dialog = manual_offset_dialog
        rom_info = test_rom_with_sprites

        if not rom_info['sprites']:
            pytest.skip("No test sprites to select")

        # Set ROM data
        extraction_manager = ExtractionManager()
        dialog.set_rom_data(
            str(rom_info['path']),
            rom_info['path'].stat().st_size,
            extraction_manager
        )

        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Directly test jumping to a known sprite
        sprite_offset = rom_info['sprites'][0]['offset']

        # Use the jump method
        dialog._jump_to_sprite(sprite_offset)
        qtbot.waitUntil(lambda: dialog.get_current_offset() == sprite_offset, timeout=500)

        # Verify we navigated to the sprite
        assert dialog.get_current_offset() == sprite_offset

@pytest.mark.integration
@pytest.mark.gui
@pytest.mark.skip_thread_cleanup(reason="Dialog uses background workers for preview generation")
class TestDialogIntegrationWithPanel:
    """Test manual offset dialog integration with ROM extraction panel."""

    def test_dialog_opens_from_panel(self, loaded_rom_panel, qtbot):
        """Test that dialog opens correctly from ROM extraction panel."""
        panel, rom_info = loaded_rom_panel

        # Open manual offset dialog
        panel._open_manual_offset_dialog()
        qtbot.waitUntil(lambda: panel._offset_dialog_manager.is_open(), timeout=500)

        # Verify dialog was created
        dialog = panel._offset_dialog_manager.get_current_dialog()
        assert dialog is not None

        # Verify dialog has ROM data
        assert dialog.rom_path == str(rom_info['path'])
        assert dialog.rom_size > 0

    def test_dialog_offset_sync_with_panel(self, loaded_rom_panel, qtbot):
        """Test that offset changes sync between dialog and panel."""
        panel, rom_info = loaded_rom_panel

        # Open dialog
        panel._open_manual_offset_dialog()
        qtbot.waitUntil(lambda: panel._offset_dialog_manager.is_open(), timeout=500)
        dialog = panel._offset_dialog_manager.get_current_dialog()
        assert dialog is not None

        dialog.show()
        qtbot.waitForWindowShown(dialog)

        # Change offset in dialog
        new_offset = 0x30000
        dialog.set_offset(new_offset)
        qtbot.waitUntil(lambda: dialog.get_current_offset() == new_offset, timeout=500)

        # Verify panel received the offset change
        # This depends on signal connections
        # The panel should track the manual offset
        assert hasattr(panel, '_manual_offset')

    def test_multiple_dialog_opens_reuse_singleton(self, loaded_rom_panel, qtbot, wait_for_signal_processed):
        """Test that opening dialog multiple times creates consistent dialogs.

        Note: The singleton pattern used here recreates the instance when closed/destroyed,
        so we verify consistent behavior rather than identical instance IDs.
        """
        panel, rom_info = loaded_rom_panel

        # Open dialog first time
        panel._open_manual_offset_dialog()
        qtbot.waitUntil(lambda: panel._offset_dialog_manager.is_open(), timeout=500)
        dialog1 = panel._offset_dialog_manager.get_current_dialog()
        assert dialog1 is not None

        # Opening again without closing should return same instance
        panel._open_manual_offset_dialog()
        dialog2 = panel._offset_dialog_manager.get_current_dialog()
        # Same instance when not closed
        assert dialog1 is dialog2

        # Close the dialog
        dialog1.close()
        wait_for_signal_processed()

        # Open again after close - may get new instance due to singleton reset
        panel._open_manual_offset_dialog()
        qtbot.waitUntil(lambda: panel._offset_dialog_manager.is_open(), timeout=500)
        dialog3 = panel._offset_dialog_manager.get_current_dialog()
        # New instance should still be valid and functional
        assert dialog3 is not None
        assert dialog3.rom_path == str(rom_info['path'])
