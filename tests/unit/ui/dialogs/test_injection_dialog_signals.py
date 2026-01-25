"""
Tests for signal loop protection in injection dialog.

Crash fix: Prevent infinite recursion from signal cascades between
sprite_location_combo and rom_offset_input.
Split from tests/integration/test_rom_extraction_regression.py
"""

from __future__ import annotations

import pytest

from ui.injection_dialog import InjectionDialog

pytestmark = [
    pytest.mark.usefixtures("mock_hal"),
    pytest.mark.skip_thread_cleanup(reason="Uses app_context which owns worker threads"),
    pytest.mark.headless,
]


@pytest.fixture
def injection_dialog(qtbot, app_context):
    """Create injection dialog for testing."""
    dialog = InjectionDialog(
        injection_manager=app_context.core_operations_manager,
        settings_manager=app_context.application_state_manager,
    )
    qtbot.addWidget(dialog)
    return dialog


class TestSignalLoopFixes:
    """Test signal loop protection in injection dialog.

    Crash fix: Prevent infinite recursion from signal cascades between
    sprite_location_combo and rom_offset_input.
    """

    def test_sprite_location_change_blocks_signals(self, injection_dialog):
        """Test that changing sprite location blocks signals to prevent recursion"""
        dialog = injection_dialog

        # Mock the combo box to have sprite data
        dialog.sprite_location_combo.clear()
        dialog.sprite_location_combo.addItem("Select sprite location...", None)
        dialog.sprite_location_combo.addItem("Test Sprite (0x8000)", 0x8000)

        # Track if signals were fired
        rom_offset_changed_called = False
        original_handler = dialog._on_rom_offset_changed

        def mock_rom_offset_changed(text):
            nonlocal rom_offset_changed_called
            rom_offset_changed_called = True
            return original_handler(text)

        dialog._on_rom_offset_changed = mock_rom_offset_changed

        # Simulate selecting a sprite location
        dialog.sprite_location_combo.setCurrentIndex(1)

        # Verify the offset field was updated
        assert dialog.rom_offset_input.hex_edit.text() == "0x8000"

        # Verify the signal handler was NOT called due to signal blocking
        assert not rom_offset_changed_called

    def test_rom_offset_change_blocks_signals(self, injection_dialog):
        """Test that changing ROM offset blocks signals to prevent recursion"""
        dialog = injection_dialog

        # Set up combo box with a selection
        dialog.sprite_location_combo.clear()
        dialog.sprite_location_combo.addItem("Select sprite location...", None)
        dialog.sprite_location_combo.addItem("Test Sprite (0x8000)", 0x8000)
        dialog.sprite_location_combo.setCurrentIndex(1)

        # Track if signals were fired
        sprite_location_changed_called = False
        original_handler = dialog._on_sprite_location_changed

        def mock_sprite_location_changed(index):
            nonlocal sprite_location_changed_called
            sprite_location_changed_called = True
            return original_handler(index)

        dialog._on_sprite_location_changed = mock_sprite_location_changed

        # Manually change the offset field
        dialog.rom_offset_input.hex_edit.setText("0x9000")

        # Verify the combo box was reset to index 0
        assert dialog.sprite_location_combo.currentIndex() == 0

        # Verify the signal handler was NOT called due to signal blocking
        assert not sprite_location_changed_called
