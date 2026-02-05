"""Tests for HexOffsetInput widget."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.components.inputs.hex_offset_input import HexOffsetInput

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


pytestmark = pytest.mark.gui


@pytest.fixture
def widget(qtbot: QtBot) -> HexOffsetInput:
    """Create default HexOffsetInput widget."""
    w = HexOffsetInput()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def widget_no_decimal(qtbot: QtBot) -> HexOffsetInput:
    """Create HexOffsetInput without decimal display."""
    w = HexOffsetInput(with_decimal_display=False)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def widget_with_callback(qtbot: QtBot) -> tuple[HexOffsetInput, Mock]:
    """Create HexOffsetInput with external callback."""
    callback = Mock()
    w = HexOffsetInput(external_change_callback=callback)
    qtbot.addWidget(w)
    return w, callback


class TestHexOffsetInputParsing:
    """Tests for hex offset parsing."""

    def test_parse_prefixed_hex_lowercase(self, widget: HexOffsetInput) -> None:
        """Parse 0x prefixed hex (lowercase)."""
        widget.set_text("0xff")
        assert widget.get_value() == 255

    def test_parse_prefixed_hex_uppercase(self, widget: HexOffsetInput) -> None:
        """Parse 0X prefixed hex (uppercase)."""
        widget.set_text("0XFF")
        assert widget.get_value() == 255

    def test_parse_unprefixed_hex(self, widget: HexOffsetInput) -> None:
        """Parse hex without prefix."""
        widget.set_text("ff")
        assert widget.get_value() == 255

    def test_parse_mixed_case(self, widget: HexOffsetInput) -> None:
        """Parse mixed case hex."""
        widget.set_text("0xFfAa")
        assert widget.get_value() == 0xFFAA

    def test_parse_large_offset(self, widget: HexOffsetInput) -> None:
        """Parse large hex offset."""
        widget.set_text("0x1FFFFF")
        assert widget.get_value() == 0x1FFFFF

    def test_parse_zero(self, widget: HexOffsetInput) -> None:
        """Parse zero offset."""
        widget.set_text("0x0")
        assert widget.get_value() == 0

    def test_parse_empty_string(self, widget: HexOffsetInput) -> None:
        """Parse empty string returns None."""
        widget.set_text("")
        assert widget.get_value() is None

    def test_parse_whitespace_only(self, widget: HexOffsetInput) -> None:
        """Parse whitespace only returns None."""
        widget.set_text("   ")
        assert widget.get_value() is None

    def test_parse_with_surrounding_whitespace(self, widget: HexOffsetInput) -> None:
        """Parse hex with surrounding whitespace."""
        widget.set_text("  0xff  ")
        assert widget.get_value() == 255

    def test_parse_invalid_characters(self, widget: HexOffsetInput) -> None:
        """Parse invalid characters returns None."""
        widget.set_text("0xGG")
        assert widget.get_value() is None

    def test_parse_only_prefix(self, widget: HexOffsetInput) -> None:
        """Parse only '0x' returns None (or 0)."""
        widget.set_text("0x")
        # "0x" alone should fail to parse
        assert widget.get_value() is None


class TestHexOffsetInputSignals:
    """Tests for signal emission."""

    def test_value_changed_emits_on_valid(self, qtbot: QtBot, widget: HexOffsetInput) -> None:
        """value_changed emits parsed value on valid input."""
        received_values: list[int | None] = []

        def capture(val: int | None) -> None:
            received_values.append(val)

        _ = widget.value_changed.connect(capture)

        widget.set_text("0xff")

        assert len(received_values) == 1
        assert received_values[0] == 255

    def test_value_changed_emits_none_on_invalid(self, qtbot: QtBot, widget: HexOffsetInput) -> None:
        """value_changed emits None on invalid input."""
        received_values: list[int | None] = []

        def capture(val: int | None) -> None:
            received_values.append(val)

        _ = widget.value_changed.connect(capture)

        widget.set_text("invalid")

        assert len(received_values) == 1
        assert received_values[0] is None

    def test_text_changed_emits_raw_text(self, qtbot: QtBot, widget: HexOffsetInput) -> None:
        """text_changed emits raw text."""
        received_texts: list[str] = []

        def capture(text: str) -> None:
            received_texts.append(text)

        _ = widget.text_changed.connect(capture)

        widget.set_text("0xABC")

        assert len(received_texts) == 1
        assert received_texts[0] == "0xABC"

    def test_external_callback_invoked(self, qtbot: QtBot, widget_with_callback: tuple[HexOffsetInput, Mock]) -> None:
        """External callback is invoked on text change."""
        widget, callback = widget_with_callback

        widget.set_text("0x100")

        callback.assert_called_once_with("0x100")

    def test_external_callback_exception_handled(self, qtbot: QtBot) -> None:
        """External callback exceptions are handled gracefully."""
        callback = Mock(side_effect=RuntimeError("callback error"))
        widget = HexOffsetInput(external_change_callback=callback)
        qtbot.addWidget(widget)

        # Should not raise
        widget.set_text("0x100")

        callback.assert_called_once()


class TestHexOffsetInputValidation:
    """Tests for validation methods."""

    def test_is_valid_for_valid_hex(self, widget: HexOffsetInput) -> None:
        """is_valid returns True for valid hex."""
        widget.set_text("0xff")
        assert widget.is_valid() is True

    def test_is_valid_for_invalid_hex(self, widget: HexOffsetInput) -> None:
        """is_valid returns False for invalid hex."""
        widget.set_text("invalid")
        assert widget.is_valid() is False

    def test_is_valid_for_empty_string(self, widget: HexOffsetInput) -> None:
        """is_valid returns True for empty string (no input is valid)."""
        widget.set_text("")
        assert widget.is_valid() is True

    def test_is_valid_for_whitespace(self, widget: HexOffsetInput) -> None:
        """is_valid returns True for whitespace only."""
        widget.set_text("   ")
        assert widget.is_valid() is True


class TestHexOffsetInputDecimalDisplay:
    """Tests for decimal display functionality."""

    def test_decimal_updates_on_valid_input(self, widget: HexOffsetInput) -> None:
        """Decimal display updates on valid hex input."""
        widget.set_text("0x100")
        assert widget.decimal_label is not None
        assert widget.decimal_label.text() == "256"

    def test_decimal_shows_invalid_on_bad_input(self, widget: HexOffsetInput) -> None:
        """Decimal display shows 'Invalid' on bad input."""
        widget.set_text("xyz")
        assert widget.decimal_label is not None
        assert widget.decimal_label.text() == "Invalid"

    def test_decimal_clears_on_empty_input(self, widget: HexOffsetInput) -> None:
        """Decimal display clears on empty input."""
        widget.set_text("0x100")
        widget.set_text("")
        assert widget.decimal_label is not None
        assert widget.decimal_label.text() == ""

    def test_no_decimal_widget_handles_changes(self, widget_no_decimal: HexOffsetInput) -> None:
        """Widget without decimal display still handles changes."""
        widget_no_decimal.set_text("0xff")
        assert widget_no_decimal.get_value() == 255
