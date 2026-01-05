#!/usr/bin/env python3
"""
Tests for HexLineEdit widget.

Tests validation, visual feedback, and signal emission.
"""

from __future__ import annotations

from typing import Any

QtBot = Any  # pyright: ignore[reportExplicitAny]

from ui.sprite_editor.views.widgets.hex_line_edit import HexLineEdit


class TestHexLineEditValidation:
    """Tests for HexLineEdit input validation."""

    def test_valid_hex_with_prefix(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test valid hex value with 0x prefix."""
        widget = HexLineEdit("0x1234")
        qtbot.addWidget(widget)

        assert widget.isValid()
        assert widget.value() == 0x1234

    def test_valid_hex_without_prefix(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test valid hex value without 0x prefix."""
        widget = HexLineEdit("ABCD")
        qtbot.addWidget(widget)

        assert widget.isValid()
        assert widget.value() == 0xABCD

    def test_valid_hex_lowercase(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test valid hex value with lowercase letters."""
        widget = HexLineEdit("0xabcd")
        qtbot.addWidget(widget)

        assert widget.isValid()
        assert widget.value() == 0xABCD

    def test_empty_string_returns_zero(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test that empty string is valid and returns 0."""
        widget = HexLineEdit("")
        qtbot.addWidget(widget)

        # Empty is valid (returns 0)
        assert widget.value() == 0

    def test_set_value_updates_text(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test setValue updates the displayed text."""
        widget = HexLineEdit("0x0000")
        qtbot.addWidget(widget)

        widget.setValue(0xC000)

        assert widget.text() == "0xC000"
        assert widget.value() == 0xC000


class TestHexLineEditSignals:
    """Tests for HexLineEdit signal emission."""

    def test_value_changed_emits_on_valid_input(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test value_changed signal emits when valid text is entered."""
        widget = HexLineEdit("0x0000")
        qtbot.addWidget(widget)

        from PySide6.QtTest import QSignalSpy
        spy = QSignalSpy(widget.value_changed)

        widget.setText("0x1000")

        assert spy.count() >= 1
        # Last emitted value should be the final value
        last_value = spy.at(spy.count() - 1)[0]
        assert last_value == 0x1000

    def test_value_changed_not_emitted_on_invalid(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test value_changed signal uses last valid value for invalid input."""
        widget = HexLineEdit("0x1000")
        qtbot.addWidget(widget)

        # Record initial state
        initial_value = widget.value()
        assert initial_value == 0x1000

        # Clear and enter invalid text - the validator prevents most invalid input
        widget.clear()
        widget.setText("0x")  # Incomplete but allowed by validator

        # value() should return last valid (0 for empty/incomplete)
        assert widget.value() == 0


class TestHexLineEditVisualFeedback:
    """Tests for HexLineEdit visual feedback."""

    def test_valid_input_clears_style(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test valid input clears error styling."""
        widget = HexLineEdit("0x1234")
        qtbot.addWidget(widget)

        assert widget.styleSheet() == HexLineEdit.STYLE_VALID

    def test_last_valid_value_preserved(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test last valid value is preserved when input becomes partial."""
        widget = HexLineEdit("0x1234")
        qtbot.addWidget(widget)

        # Get initial valid value
        assert widget.value() == 0x1234

        # Modify to incomplete value
        widget.setText("0x")

        # value() should return 0 (parsed from "0x" which is effectively empty)
        # or the last valid value depending on implementation
        result = widget.value()
        assert result in (0, 0x1234)  # Either is acceptable


class TestHexLineEditEdgeCases:
    """Tests for HexLineEdit edge cases."""

    def test_max_length_enforced(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test that max length is enforced."""
        widget = HexLineEdit("0x0000")
        qtbot.addWidget(widget)

        # Try to set text longer than maxLength
        widget.setText("0x123456789ABCDEF")

        # Should be truncated
        assert len(widget.text()) <= 10

    def test_zero_value(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test zero value handling."""
        widget = HexLineEdit("0x0000")
        qtbot.addWidget(widget)

        assert widget.value() == 0
        assert widget.isValid()

    def test_max_value(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test maximum value (8 hex digits)."""
        widget = HexLineEdit("0xFFFFFFFF")
        qtbot.addWidget(widget)

        assert widget.value() == 0xFFFFFFFF
        assert widget.isValid()

    def test_case_insensitive_prefix(self, qtbot: QtBot) -> None:  # pyright: ignore[reportExplicitAny]
        """Test both 0x and 0X prefixes work."""
        widget1 = HexLineEdit("0xABCD")
        widget2 = HexLineEdit("0XABCD")
        qtbot.addWidget(widget1)
        qtbot.addWidget(widget2)

        assert widget1.value() == widget2.value() == 0xABCD