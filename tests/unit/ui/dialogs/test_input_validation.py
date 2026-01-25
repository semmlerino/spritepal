"""
Tests for input validation improvements in injection dialog.

Bug fix: Real-time offset validation and comprehensive parameter validation.
Split from tests/integration/test_rom_extraction_regression.py
"""

from __future__ import annotations

from unittest.mock import patch

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


class TestInputValidation:
    """Test input validation improvements.

    Bug fix: Real-time offset validation and comprehensive parameter validation.
    """

    def test_real_time_offset_validation(self, injection_dialog):
        """Test offset input accepts various formats"""
        dialog = injection_dialog

        # Test valid hex input formats are accepted
        test_cases = [
            "0x8000",
            "0X8000",
            "8000",
            "ABCD",
            "  0x1234  ",  # with whitespace
        ]

        for test_input in test_cases:
            dialog.rom_offset_input.hex_edit.setText(test_input)
            # Just verify the text was set - the widget doesn't have decimal display
            assert dialog.rom_offset_input.hex_edit.text() == test_input

        # Test that parsing works correctly through the internal method
        assert dialog.rom_offset_input._parse_hex_offset("0x8000") == 0x8000
        assert dialog.rom_offset_input._parse_hex_offset("invalid") is None
        assert dialog.rom_offset_input._parse_hex_offset("") is None
        assert dialog.rom_offset_input._parse_hex_offset("   ") is None

    def test_comprehensive_parameter_validation(self, injection_dialog):
        """Test comprehensive parameter validation in get_parameters"""
        dialog = injection_dialog

        # Set dialog to accepted state
        dialog.setResult(dialog.DialogCode.Accepted)

        # Test ROM injection tab
        dialog.set_current_tab(1)

        # Test missing sprite path
        with (
            patch.object(dialog.sprite_file_selector, "get_path", return_value=""),
            patch.object(dialog.input_rom_selector, "get_path", return_value=""),
            patch.object(dialog.output_rom_selector, "get_path", return_value=""),
        ):
            with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
                result = dialog.get_parameters()
                assert result is None
                mock_warning.assert_called_once()
                args = mock_warning.call_args[0]
                assert "sprite file" in args[2].lower()
