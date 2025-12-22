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


class TestHexOffsetInputInit:
    """Tests for HexOffsetInput initialization."""

    def test_init_default(self, widget: HexOffsetInput) -> None:
        """Verify default initialization."""
        assert widget.hex_edit is not None
        assert widget.decimal_label is not None
        assert widget.get_text() == ""

    def test_init_with_custom_placeholder(self, qtbot: QtBot) -> None:
        """Verify custom placeholder text."""
        w = HexOffsetInput(placeholder="0x8000")
        qtbot.addWidget(w)
        assert w.hex_edit.placeholderText() == "0x8000"

    def test_init_without_decimal_display(
        self, widget_no_decimal: HexOffsetInput
    ) -> None:
        """Verify decimal display can be disabled."""
        assert widget_no_decimal.decimal_label is None
        assert widget_no_decimal.hex_edit is not None

    def test_init_with_decimal_display_shows_initial_value(
        self, qtbot: QtBot
    ) -> None:
        """Verify decimal display shows initial placeholder value."""
        w = HexOffsetInput(placeholder="0x100")
        qtbot.addWidget(w)
        # decimal_label should show 256 (0x100 in decimal)
        assert w.decimal_label is not None
        assert w.decimal_label.text() == "256"

    def test_init_with_label_prefix(self, qtbot: QtBot) -> None:
        """Verify label prefix is displayed."""
        w = HexOffsetInput(label_prefix="Offset:")
        qtbot.addWidget(w)
        assert hasattr(w, "prefix_label")
        assert w.prefix_label.text() == "Offset:"

    def test_init_custom_widths(self, qtbot: QtBot) -> None:
        """Verify custom input and decimal widths."""
        w = HexOffsetInput(input_width=200, decimal_width=100)
        qtbot.addWidget(w)
        assert w.hex_edit.maximumWidth() == 200
        assert w.decimal_label is not None
        assert w.decimal_label.minimumWidth() == 100


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

    def test_parse_with_surrounding_whitespace(
        self, widget: HexOffsetInput
    ) -> None:
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


class TestHexOffsetInputGetSet:
    """Tests for get/set operations."""

    def test_get_value_valid(self, widget: HexOffsetInput) -> None:
        """get_value returns parsed integer."""
        widget.set_text("0x100")
        assert widget.get_value() == 256

    def test_get_value_invalid(self, widget: HexOffsetInput) -> None:
        """get_value returns None for invalid input."""
        widget.set_text("invalid")
        assert widget.get_value() is None

    def test_get_text_returns_raw(self, widget: HexOffsetInput) -> None:
        """get_text returns raw text as entered."""
        widget.set_text("0xABC")
        assert widget.get_text() == "0xABC"

    def test_set_text_string(self, widget: HexOffsetInput) -> None:
        """set_text accepts string."""
        widget.set_text("0x1234")
        assert widget.get_text() == "0x1234"

    def test_set_text_int(self, widget: HexOffsetInput) -> None:
        """set_text accepts int and formats as hex."""
        widget.set_text(256)
        assert widget.get_text() == "0x100"

    def test_set_text_none(self, widget: HexOffsetInput) -> None:
        """set_text with None clears input."""
        widget.set_text("0x100")
        widget.set_text(None)
        assert widget.get_text() == ""

    def test_clear(self, widget: HexOffsetInput) -> None:
        """clear() empties the input."""
        widget.set_text("0x100")
        widget.clear()
        assert widget.get_text() == ""


class TestHexOffsetInputSignals:
    """Tests for signal emission."""

    def test_value_changed_emits_on_valid(
        self, qtbot: QtBot, widget: HexOffsetInput
    ) -> None:
        """value_changed emits parsed value on valid input."""
        received_values: list[int | None] = []

        def capture(val: int | None) -> None:
            received_values.append(val)

        _ = widget.value_changed.connect(capture)

        widget.set_text("0xff")

        assert len(received_values) == 1
        assert received_values[0] == 255

    def test_value_changed_emits_none_on_invalid(
        self, qtbot: QtBot, widget: HexOffsetInput
    ) -> None:
        """value_changed emits None on invalid input."""
        received_values: list[int | None] = []

        def capture(val: int | None) -> None:
            received_values.append(val)

        _ = widget.value_changed.connect(capture)

        widget.set_text("invalid")

        assert len(received_values) == 1
        assert received_values[0] is None

    def test_text_changed_emits_raw_text(
        self, qtbot: QtBot, widget: HexOffsetInput
    ) -> None:
        """text_changed emits raw text."""
        received_texts: list[str] = []

        def capture(text: str) -> None:
            received_texts.append(text)

        _ = widget.text_changed.connect(capture)

        widget.set_text("0xABC")

        assert len(received_texts) == 1
        assert received_texts[0] == "0xABC"

    def test_external_callback_invoked(
        self, qtbot: QtBot, widget_with_callback: tuple[HexOffsetInput, Mock]
    ) -> None:
        """External callback is invoked on text change."""
        widget, callback = widget_with_callback

        widget.set_text("0x100")

        callback.assert_called_once_with("0x100")

    def test_external_callback_exception_handled(
        self, qtbot: QtBot
    ) -> None:
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

    def test_decimal_updates_on_valid_input(
        self, widget: HexOffsetInput
    ) -> None:
        """Decimal display updates on valid hex input."""
        widget.set_text("0x100")
        assert widget.decimal_label is not None
        assert widget.decimal_label.text() == "256"

    def test_decimal_shows_invalid_on_bad_input(
        self, widget: HexOffsetInput
    ) -> None:
        """Decimal display shows 'Invalid' on bad input."""
        widget.set_text("xyz")
        assert widget.decimal_label is not None
        assert widget.decimal_label.text() == "Invalid"

    def test_decimal_clears_on_empty_input(
        self, widget: HexOffsetInput
    ) -> None:
        """Decimal display clears on empty input."""
        widget.set_text("0x100")
        widget.set_text("")
        assert widget.decimal_label is not None
        assert widget.decimal_label.text() == ""

    def test_no_decimal_widget_handles_changes(
        self, widget_no_decimal: HexOffsetInput
    ) -> None:
        """Widget without decimal display still handles changes."""
        widget_no_decimal.set_text("0xff")
        assert widget_no_decimal.get_value() == 255


class TestHexOffsetInputFocus:
    """Tests for focus management."""

    def test_setFocus_without_reason(
        self, qtbot: QtBot, widget: HexOffsetInput
    ) -> None:
        """setFocus without reason sets focus on hex_edit."""
        # Need to show widget for focus to work
        widget.show()
        QApplication.processEvents()

        widget.setFocus()
        QApplication.processEvents()

        # Check that hex_edit has focus
        assert widget.hex_edit.hasFocus()

    def test_setFocus_with_reason(
        self, qtbot: QtBot, widget: HexOffsetInput
    ) -> None:
        """setFocus with reason sets focus on hex_edit."""
        widget.show()
        QApplication.processEvents()

        widget.setFocus(Qt.FocusReason.TabFocusReason)
        QApplication.processEvents()

        assert widget.hex_edit.hasFocus()

    def test_set_placeholder(self, widget: HexOffsetInput) -> None:
        """set_placeholder updates placeholder text."""
        widget.set_placeholder("Enter offset...")
        assert widget.hex_edit.placeholderText() == "Enter offset..."
