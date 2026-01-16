"""Test that output name provider pattern works correctly in ROM extraction panel."""

from unittest.mock import MagicMock

import pytest


def test_output_name_provider_pattern(app_context):
    """Test that ROM extraction panel uses provider for output name."""
    from ui.rom_extraction_panel import ROMExtractionPanel

    # Create panel
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

    from ui.rom_extraction_panel import ROMExtractionPanel

    # Create panel
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

    from ui.rom_extraction_panel import ROMExtractionPanel

    # Create panel
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
    from ui.rom_extraction_panel import ROMExtractionPanel

    # Create panel
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
