#!/usr/bin/env python3
"""
Hex line edit widget for hexadecimal input.
Provides a specialized QLineEdit for entering hex values.
"""

from PySide6.QtWidgets import QLineEdit


class HexLineEdit(QLineEdit):
    """Line edit for hexadecimal input with validation and conversion utilities."""

    def __init__(self, default: str = "0x0000") -> None:
        """Initialize the hex line edit.

        Args:
            default: Default hex value to display
        """
        super().__init__(default)
        self.setMaxLength(8)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Configure the widget appearance and behavior."""
        self.setPlaceholderText("Enter hex value (e.g., 0x1234)")
        self.setToolTip("Enter a hexadecimal value")

    def value(self) -> int:
        """Get the hex value as integer.

        Returns:
            The hex value converted to integer, or 0 if invalid
        """
        try:
            text = self.text().strip()
            if text.startswith(("0x", "0X")):
                return int(text, 16)
            # Assume hex even without 0x prefix
            return int(text, 16)
        except ValueError:
            return 0

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
            self.value()
            return True
        except (ValueError, TypeError, AttributeError):
            return False
