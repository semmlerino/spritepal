"""
Consolidated tests for ROMExtractionPanel component.

Merged from:
- tests/ui/test_rom_panel_output_name.py
- tests/ui/test_manual_offset_entry.py
- tests/ui/test_rom_mode_button_states.py
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ui.rom_extraction_panel import ROMExtractionPanel

# =============================================================================
# Output name provider tests (from test_rom_panel_output_name.py)
# =============================================================================


def test_output_name_provider_pattern(app_context):
    """Test that ROM extraction panel uses provider for output name."""
    panel = ROMExtractionPanel(
        extraction_manager=app_context.core_operations_manager,
        state_manager=app_context.application_state_manager,
        rom_cache=app_context.rom_cache,
    )
    # Set dummy ROM path to ensure get_extraction_params returns dict
    panel.rom_path = "dummy.sfc"
    # Set manual mode to bypass sprite selection requirement (otherwise returns None)
    panel.set_manual_offset(0)

    # Initially, no provider set
    params = panel.get_extraction_params()
    assert params["output_base"] == ""

    # Set a mock provider
    test_name = "my_sprites"
    provider = MagicMock(return_value=test_name)
    panel.set_output_name_provider(provider)

    # Now get_extraction_params should call the provider
    params = panel.get_extraction_params()
    assert params["output_base"] == test_name
    provider.assert_called_once()

    # Test with different value
    provider.return_value = "different_name"
    params = panel.get_extraction_params()
    assert params["output_base"] == "different_name"
    assert provider.call_count == 2


def test_set_output_name_syncs_inline_field(app_context):
    """Test that set_output_name updates the inline field."""
    from PySide6.QtWidgets import QLineEdit

    panel = ROMExtractionPanel(
        extraction_manager=app_context.core_operations_manager,
        state_manager=app_context.application_state_manager,
        rom_cache=app_context.rom_cache,
    )

    # Set output name via signal slot
    test_name = "test_sprites"
    panel.set_output_name(test_name)

    # Verify inline field was updated
    edit = panel.findChild(QLineEdit)
    assert edit.text() == test_name


def test_inline_field_emits_signal(qtbot, app_context):
    """Test that typing in inline field emits signal."""
    from PySide6.QtWidgets import QLineEdit

    panel = ROMExtractionPanel(
        extraction_manager=app_context.core_operations_manager,
        state_manager=app_context.application_state_manager,
        rom_cache=app_context.rom_cache,
    )

    # Connect to signal
    signal_spy = []
    panel.output_name_changed.connect(lambda text: signal_spy.append(text))

    # Type in inline field
    test_name = "my_output"
    edit = panel.findChild(QLineEdit)
    edit.setText(test_name)

    # Verify signal was emitted (textChanged emits for each character change)
    assert len(signal_spy) > 0
    assert signal_spy[-1] == test_name  # Last emission has full text


def test_sprite_location_error_disables_extraction(qtbot, app_context):
    """
    Verify that sprite location errors disable extraction readiness.

    Regression: Before fix, _on_sprite_locations_error() did not call
    _check_extraction_ready(), leaving extract button enabled.
    """
    panel = ROMExtractionPanel(
        extraction_manager=app_context.core_operations_manager,
        state_manager=app_context.application_state_manager,
        rom_cache=app_context.rom_cache,
    )
    qtbot.addWidget(panel)

    # Track readiness signals
    ready_states: list[bool] = []
    panel.extraction_ready.connect(lambda ready, _reason="": ready_states.append(ready))

    # Set ROM path to enable basic readiness
    panel.rom_path = "test.sfc"

    # Simulate sprite location error via orchestrator signal
    # This is the public way the panel receives this error
    panel.worker_orchestrator.sprite_locations_error.emit("Test error: failed to load locations")

    # Verify: readiness check was triggered and resulted in not-ready state
    assert len(ready_states) > 0, "Expected extraction_ready signal after sprite error"
    assert ready_states[-1] is False, "Expected extraction NOT ready after sprite location error"


# =============================================================================
# Manual offset entry tests (from test_manual_offset_entry.py)
# =============================================================================


def test_set_manual_offset_updates_display_label(qtbot):
    """
    Test that calling set_manual_offset on the ROMExtractionPanel
    correctly updates the manual_offset_section display label.
    """
    # Setup mocks
    mock_extraction_manager = MagicMock()
    mock_state_manager = MagicMock()
    mock_rom_cache = MagicMock()

    # Instantiate with qtbot to prevent crash
    panel = ROMExtractionPanel(
        extraction_manager=mock_extraction_manager, state_manager=mock_state_manager, rom_cache=mock_rom_cache
    )
    qtbot.addWidget(panel)
    panel.show()  # Ensure widget is shown for isVisible() checks

    # Initial state - using public API
    assert panel.manual_offset_section.get_offset_display_text() == ""
    # Might still be False because layout/show events might not have fully processed
    # but setVisible(False) was called in init.

    # Action: Set manual offset
    panel.set_manual_offset(0x3C6EF1)

    # Verify: Label should be updated and visible
    display_text = panel.manual_offset_section.get_offset_display_text()
    assert "3C6EF1" in display_text
    assert display_text == "Manual offset: 0x3C6EF1"

    # Use qtbot.waitUntil to give Qt time to update visibility if needed
    # although setVisible(True) should be immediate for the property
    assert panel.manual_offset_section.is_offset_display_visible()


# =============================================================================
# ROM mode button states tests (from test_rom_mode_button_states.py)
# =============================================================================


def test_ready_for_inject_hidden_in_rom_mode(qtbot):
    """Verify that 'Ready for Inject' button is hidden in ROM workflow page."""
    from unittest.mock import MagicMock

    from PySide6.QtCore import QObject, Signal

    from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

    page = ROMWorkflowPage()
    qtbot.addWidget(page)
    with qtbot.waitExposed(page):
        page.show()

    # Check initial state
    assert not page.workspace.is_inject_button_visible, "Ready for Inject button should be hidden in ROM mode"

    # Check Save to ROM button visibility (via SaveExportPanel)
    assert page.workspace.save_export_panel.save_to_rom_btn.isVisible(), (
        "Save to ROM button should be visible in ROM mode"
    )

    # Check initial enabled state (should be disabled until image loaded)
    assert not page.workspace.save_export_panel.save_to_rom_btn.isEnabled(), (
        "Save to ROM button should be disabled initially"
    )

    # Mock controller to trigger enablement
    class MockController(QObject):
        imageChanged = Signal()
        paletteChanged = Signal()
        toolChanged = Signal(str)
        colorChanged = Signal(int)
        paletteSourceAdded = Signal(str, str, int, object, bool)
        paletteSourceSelected = Signal(str, int)
        paletteSourcesCleared = Signal(str)
        validationChanged = Signal(bool, list)

        def __init__(self):
            super().__init__()
            self.image_model = MagicMock()
            self.palette_model = MagicMock()
            self.palette_model.name = "Test"

        def has_image(self):
            return True

        def get_current_colors(self):
            return [(0, 0, 0)] * 16

        def get_current_tool_name(self):
            return "pencil"

        def get_selected_color(self):
            return 1

        def get_image_size(self):
            return (8, 8)

        def handle_pixel_press(self, x, y):
            pass

        def handle_pixel_move(self, x, y):
            pass

        def handle_pixel_release(self, x, y):
            pass

        def set_tool(self, tool):
            pass

        def set_selected_color(self, color):
            pass

        def handle_palette_source_changed(self, source, index):
            pass

        def handle_load_palette(self):
            pass

        def handle_save_palette(self):
            pass

        def handle_edit_color(self):
            pass

        def get_palette_sources(self):
            return {}

        def get_current_palette_source(self):
            return None

    controller = MockController()
    page.workspace.set_controller(controller)

    # It should be enabled now because has_image() returns True and set_controller calls set_image_loaded
    assert page.workspace.save_export_panel.save_to_rom_btn.isEnabled(), (
        "Save to ROM button should be enabled after controller set"
    )

    # Verify set_workflow_mode was called correctly
    # We can't check internal state easily, but we can call it again and verify
    page.workspace.set_workflow_mode("rom")
    assert not page.workspace.is_inject_button_visible

    page.workspace.set_workflow_mode("vram")
    assert page.workspace.is_inject_button_visible
