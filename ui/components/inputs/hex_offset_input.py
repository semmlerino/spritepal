"""
Hex offset input component with validation and decimal conversion

Provides a standardized hex input widget with optional decimal display,
exactly replicating the functionality from InjectionDialog.
"""

from __future__ import annotations

import builtins
import contextlib
from collections.abc import Callable
from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from utils.logging_config import get_logger

logger = get_logger(__name__)


class HexOffsetInput(QWidget):
    """
    Hex offset input widget with validation and optional decimal display.

    Features:
    - Hex input with validation (supports 0x prefix or raw hex)
    - decimal conversion display
    - Error state handling and visual feedback
    - Configurable placeholder text and width
    - Signal emission for value changes

    Exactly replicates the hex offset functionality from InjectionDialog.
    """

    # Signals
    value_changed = Signal(object)  # Emits parsed int value or None
    text_changed = Signal(str)  # Emits raw text

    def __init__(
        self,
        parent: QWidget | None = None,
        placeholder: str = "0x0",
        with_decimal_display: bool = True,
        input_width: int = 100,
        decimal_width: int = 60,
        label_prefix: str = "",
        external_change_callback: Callable[[str | None], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self._with_decimal_display = with_decimal_display
        self._external_callback = external_change_callback

        # Create UI components
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        # prefix label
        if label_prefix:
            self.prefix_label = QLabel(label_prefix)
            self._layout.addWidget(self.prefix_label)

        # Hex input field
        self.hex_edit = QLineEdit()
        self.hex_edit.setPlaceholderText(placeholder)
        self.hex_edit.setMaximumWidth(input_width)
        _ = self.hex_edit.textChanged.connect(self._on_text_changed)
        self._layout.addWidget(self.hex_edit)

        # Decimal display components (optional)
        if self._with_decimal_display:
            self.equals_label = QLabel("(hex) = ")
            self._layout.addWidget(self.equals_label)

            self.decimal_label = QLabel("")
            self.decimal_label.setMinimumWidth(decimal_width)
            self._layout.addWidget(self.decimal_label)

            self.decimal_suffix_label = QLabel("(decimal)")
            self._layout.addWidget(self.decimal_suffix_label)
        else:
            self.decimal_label = None

        # Initialize with placeholder value if applicable
        if placeholder and with_decimal_display:
            try:
                initial_value = self._parse_hex_offset(placeholder)
                if initial_value is not None and self.decimal_label:
                    self.decimal_label.setText(str(initial_value))
            except Exception:
                pass

    def _parse_hex_offset(self, text: str) -> int | None:
        """
        Parse hex offset string to integer with robust error handling.

        Exactly replicates the parsing logic from InjectionDialog._parse_hex_offset.

        Args:
            text: Hex string like "0x8000", "8000", "0X8000", etc.

        Returns:
            Integer value or None if invalid
        """
        logger.debug(f"Parsing hex offset: '{text}'")

        if not text:
            logger.debug("Empty text, returning None")
            return None

        # Strip whitespace
        text = text.strip()
        if not text:
            logger.debug("Empty text after strip, returning None")
            return None

        try:
            # Handle both 0x prefixed and non-prefixed hex
            if text.lower().startswith(("0x", "0X")):
                logger.debug(f"Parsing as prefixed hex: '{text}'")
                result = int(text, 16)
                logger.debug(f"Successfully parsed prefixed hex: 0x{result:X} ({result})")
                return result
            # Assume hex if no prefix
            logger.debug(f"Parsing as non-prefixed hex: '{text}'")
            result = int(text, 16)
            logger.debug(f"Successfully parsed non-prefixed hex: 0x{result:X} ({result})")
            return result
        except ValueError as e:
            logger.debug(f"Failed to parse hex offset '{text}': {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error parsing hex offset '{text}': {e}")
            return None

    def _on_text_changed(self, text: str) -> None:
        """
        Handle text change events.

        Exactly replicates the logic from InjectionDialog._on_offset_changed.
        """
        logger.debug(f"Hex offset changed to: '{text}'")
        try:
            value = self._parse_hex_offset(text)
            logger.debug(f"Parsed hex offset: {value}")

            if self._with_decimal_display and self.decimal_label:
                if value is not None:
                    decimal_str = str(value)
                    logger.debug(f"Setting decimal label to: {decimal_str}")
                    if self.decimal_label:
                        self.decimal_label.setText(decimal_str)
                    logger.debug(f"Valid hex offset: 0x{value:X} ({value} decimal)")
                else:
                    display_text = "Invalid" if text.strip() else ""
                    logger.debug(f"Setting decimal label to: '{display_text}'")
                    if self.decimal_label:
                        self.decimal_label.setText(display_text)
                    if text.strip():
                        logger.warning(f"Invalid hex offset format: '{text}'")

            logger.debug("Hex offset change handled successfully")

            # Emit signals
            self.value_changed.emit(value)
            self.text_changed.emit(text)

            # Call external callback if provided
            if self._external_callback:
                try:
                    self._external_callback(text)
                except Exception:
                    logger.exception("Error in external change callback")

        except Exception:
            logger.exception("Error in hex offset change handler")
            # Try to set error state
            if self._with_decimal_display and self.decimal_label:
                with contextlib.suppress(builtins.BaseException):
                    if self.decimal_label:
                        self.decimal_label.setText("Error")
            # Don't re-raise to prevent crash

    def get_value(self) -> int | None:
        """Get the current parsed integer value"""
        return self._parse_hex_offset(self.hex_edit.text())

    def get_text(self) -> str:
        """Get the current raw text value"""
        return self.hex_edit.text()

    def set_text(self, text: str | int | None) -> None:
        """Set the input text (triggers validation)"""
        if text is None:
            converted_text = ""
        elif isinstance(text, int):
            converted_text = f"0x{text:X}"
        else:
            # Convert any other type to string
            converted_text = str(text)

        if self.hex_edit:
            self.hex_edit.setText(converted_text)

    def set_placeholder(self, placeholder: str) -> None:
        """Set the placeholder text"""
        self.hex_edit.setPlaceholderText(placeholder)

    def clear(self) -> None:
        """Clear the input"""
        if self.hex_edit:
            self.hex_edit.clear()

    def is_valid(self) -> bool:
        """Check if current value is valid"""
        return self.get_value() is not None or not self.get_text().strip()

    @override
    def setFocus(self, reason: Qt.FocusReason | None = None) -> None:
        """Set focus to the input field"""
        if reason is not None:
            self.hex_edit.setFocus(reason)
        else:
            self.hex_edit.setFocus()
