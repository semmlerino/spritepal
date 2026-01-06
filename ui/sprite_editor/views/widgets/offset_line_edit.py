#!/usr/bin/env python3
"""
Smart offset line edit widget for flexible ROM offset input.
Supports various formats: 0x..., $..., $bank:addr, Mesen2 format, etc.
"""

import re
from typing import override

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QLineEdit, QWidget

from utils.rom_utils import snes_to_pc


class OffsetLineEdit(QLineEdit):
    """
    Specialized QLineEdit for ROM offsets supporting multiple formats:
    - 0x1234, $1234 (Hex)
    - 1234 (Decimal or hex depending on context, here we assume hex if digits)
    - $C0:1234 (SNES Bank:Address)
    - "FILE OFFSET: 0x1234" (Mesen2 clipboard format)
    """

    # Signal emitted when a valid value is entered
    offset_changed = Signal(int)

    # Signal emitted when user presses Enter
    return_pressed_with_offset = Signal(int)

    def __init__(self, default: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_valid_offset = default
        self.setPlaceholderText("Offset (0x..., $..., Bank:Addr)")
        self.setToolTip("Supports Hex (0x/$, SNES ($C0:1234), or Mesen2 paste")

        self.textChanged.connect(self._on_text_changed)
        self.returnPressed.connect(self._on_return_pressed)

        if default > 0:
            self.set_offset(default)

    def _on_text_changed(self, text: str) -> None:
        """Parse text and update visual state."""
        offset = self._parse_offset(text)
        if offset is not None:
            self.setStyleSheet("")
            self._last_valid_offset = offset
            self.offset_changed.emit(offset)
        elif text.strip():
            self.setStyleSheet("background-color: #442222;")
        else:
            self.setStyleSheet("")

    def _on_return_pressed(self) -> None:
        """Handle enter key."""
        offset = self._parse_offset(self.text())
        if offset is not None:
            self.return_pressed_with_offset.emit(offset)

    def _parse_offset(self, text: str) -> int | None:
        """Parse various offset formats."""
        text = text.strip()
        if not text:
            return 0

        # 1. Mesen2 format: "FILE OFFSET: 0x1234"
        mesen_match = re.search(r"FILE OFFSET:\s*(?:0x)?([0-9a-fA-F]+)", text, re.IGNORECASE)
        if mesen_match:
            try:
                return int(mesen_match.group(1), 16)
            except ValueError:
                pass

        # 2. SNES format: $C0:1234 or C0:1234
        snes_match = re.search(r"\$?([0-9a-fA-F]{2}):([0-9a-fA-F]{4})", text)
        if snes_match:
            try:
                bank = int(snes_match.group(1), 16)
                addr = int(snes_match.group(2), 16)
                return snes_to_pc(bank, addr)
            except (ValueError, TypeError):
                pass

        # 3. Hex with prefix: 0x1234 or $1234
        hex_match = re.match(r"^(?:0x|\$)([0-9a-fA-F]+)$", text, re.IGNORECASE)
        if hex_match:
            try:
                return int(hex_match.group(1), 16)
            except ValueError:
                pass

        # 4. Plain hex or decimal?
        # For offsets in this tool, we generally prefer hex.
        if re.match(r"^[0-9a-fA-F]+$", text):
            try:
                # If it looks like hex (contains A-F) or is long, treat as hex
                if any(c in "abcdefABCDEF" for c in text) or len(text) > 4:
                    return int(text, 16)
                # Ambiguous: could be decimal. Let's try hex first as it's more common for offsets.
                return int(text, 16)
            except ValueError:
                pass

        return None

    def offset(self) -> int:
        """Get current valid offset."""
        return self._last_valid_offset

    def set_offset(self, offset: int) -> None:
        """Set offset value and update text."""
        self.setText(f"0x{offset:06X}")
        self._last_valid_offset = offset

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Ctrl+V to strip formatting if needed."""
        if event.matches(QKeySequence.StandardKey.Paste):
            # Normal paste works fine because _parse_offset handles it
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
