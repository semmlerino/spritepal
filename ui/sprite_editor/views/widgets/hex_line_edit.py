#!/usr/bin/env python3
"""
Hex line edit widget for hexadecimal input.
Provides a specialized QLineEdit for entering hex values with validation.
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QLineEdit


class HexLineEdit(QLineEdit):
    """Line edit for hexadecimal input with validation and visual feedback."""

    # Signal emitted when a valid value is entered
    value_changed = Signal(int)

    # Style constants
    STYLE_VALID = ""
    STYLE_INVALID = "background-color: #ffcccc;"

    def __init__(self, default: str = "0x0000") -> None:
        """Initialize the hex line edit.

        Args:
            default: Default hex value to display
        """
        super().__init__(default)
        self.setMaxLength(10)  # 0x + 8 hex digits
        self._last_valid_value = 0
        self._setup_ui()
        self._setup_validation()

        # Parse initial value
        if self.isValid():
            self._last_valid_value = self._parse_value(self.text())

    def _setup_ui(self) -> None:
        """Configure the widget appearance and behavior."""
        self.setPlaceholderText("Enter hex value (e.g., 0x1234)")
        self.setToolTip("Enter a hexadecimal value (with or without 0x prefix)")

    def _setup_validation(self) -> None:
        """Set up input validation."""
        # Accept 0x prefix (optional) followed by hex digits
        from PySide6.QtCore import QRegularExpression

        regex = QRegularExpression(r"^(0[xX])?[0-9a-fA-F]{0,8}$")
        validator = QRegularExpressionValidator(regex, self)
        self.setValidator(validator)
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        """Update visual feedback on text change."""
        if self.isValid():
            self.setStyleSheet(self.STYLE_VALID)
            self._last_valid_value = self._parse_value(text)
            self.value_changed.emit(self._last_valid_value)
        else:
            self.setStyleSheet(self.STYLE_INVALID)

    def _parse_value(self, text: str) -> int:
        """Parse hex value from text.

        Args:
            text: Text to parse

        Returns:
            Parsed integer value

        Raises:
            ValueError: If text is not a valid hex value
        """
        text = text.strip()
        if not text:
            return 0
        if text.startswith(("0x", "0X")):
            return int(text, 16)
        return int(text, 16)

    def value(self) -> int:
        """Get the hex value as integer.

        Returns:
            The hex value if valid, otherwise the last valid value.
            This ensures we always return a usable value.

        Note:
            Use value_or_none() to detect invalid input.
            Use isValid() to check validity before calling value().
        """
        try:
            return self._parse_value(self.text())
        except ValueError:
            return self._last_valid_value

    def value_or_none(self) -> int | None:
        """Get the hex value if valid, None otherwise.

        Unlike value(), this does not fall back to the last valid value.
        Use this when you need to detect invalid input and handle it explicitly.

        Returns:
            The hex value if valid, None if invalid.
        """
        try:
            return self._parse_value(self.text())
        except ValueError:
            return None

    def setValue(self, value: int) -> None:
        """Set value from integer.

        Args:
            value: Integer value to convert to hex and display
        """
        self.setText(f"0x{value:04X}")

    def isValid(self) -> bool:
        """Check if the current text is a valid hex value.

        Returns:
            True if valid hex, False otherwise
        """
        try:
            self._parse_value(self.text())
            return True
        except ValueError:
            return False
