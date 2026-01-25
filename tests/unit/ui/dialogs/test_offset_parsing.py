"""
Tests for hex offset parsing in injection dialog.

Bug fix: Accept various hex formats (0x, 0X, bare hex) and reject invalid input.
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


class TestOffsetParsingFixes:
    """Test improved offset parsing with error handling.

    Bug fix: Accept various hex formats (0x, 0X, bare hex) and reject invalid input.
    """

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("0x8000", 0x8000),
            ("0X8000", 0x8000),
            ("8000", 0x8000),
            ("0xABCD", 0xABCD),
            ("abcd", 0xABCD),
            ("0x0", 0x0),
            ("FFFF", 0xFFFF),
            (" 0x8000 ", 0x8000),  # With whitespace
        ],
    )
    def test_parse_hex_offset_valid(self, injection_dialog, input_text, expected):
        """Test parsing of valid hex offset format: {input_text}"""
        result = injection_dialog.rom_offset_input._parse_hex_offset(input_text)
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_input",
        [
            "",
            "   ",
            "not_hex",
            "0xGGGG",
            "12345G",
            "0x",
            "x8000",
            None,
        ],
    )
    def test_parse_hex_offset_invalid(self, injection_dialog, invalid_input):
        """Test parsing rejects invalid hex input"""
        result = injection_dialog.rom_offset_input._parse_hex_offset(invalid_input)
        assert result is None

    def test_offset_validation_in_get_parameters(self, injection_dialog):
        """Test that get_parameters properly validates offsets"""
        dialog = injection_dialog

        # Set up dialog for ROM injection
        dialog.set_current_tab(1)  # ROM tab

        # Mock file selectors to avoid UI blocking
        with (
            patch.object(dialog.sprite_file_selector, "get_path", return_value="/fake/sprite.png"),
            patch.object(dialog.input_rom_selector, "get_path", return_value="/fake/input.sfc"),
            patch.object(dialog.output_rom_selector, "get_path", return_value="/fake/output.sfc"),
        ):
            # Test invalid offset
            dialog.rom_offset_input.hex_edit.setText("invalid_hex")

            # Mock QDialog.accept and dialog result
            dialog.setResult(dialog.DialogCode.Accepted)

            # Should return None due to invalid offset
            with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
                result = dialog.get_parameters()
                assert result is None
                mock_warning.assert_called_once()
                args = mock_warning.call_args[0]
                assert "Invalid ROM offset value" in args[2]
