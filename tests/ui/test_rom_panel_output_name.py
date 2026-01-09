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
    assert panel.output_name_edit.text() == test_name


def test_inline_field_emits_signal(qtbot, app_context):
    """Test that typing in inline field emits signal."""
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
    panel.output_name_edit.setText(test_name)

    # Verify signal was emitted (textChanged emits for each character change)
    assert len(signal_spy) > 0
    assert signal_spy[-1] == test_name  # Last emission has full text


def test_no_duplicate_output_name_field(app_context):
    """Test that _output_name field no longer exists (removed)."""
    from ui.rom_extraction_panel import ROMExtractionPanel

    # Create panel
    panel = ROMExtractionPanel(
        extraction_manager=app_context.core_operations_manager,
        state_manager=app_context.application_state_manager,
        rom_cache=app_context.rom_cache,
    )

    # Verify _output_name field does NOT exist
    assert not hasattr(panel, "_output_name")

    # Verify provider field DOES exist
    assert hasattr(panel, "_output_name_provider")
