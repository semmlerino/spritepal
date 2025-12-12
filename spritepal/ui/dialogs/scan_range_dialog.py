"""
Dialog for specifying custom ROM scan range.
Allows users to define specific start and end offsets for sprite scanning.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

# from typing_extensions import override


class ScanRangeDialog(QDialog):
    """Dialog for specifying custom scan range."""

    def __init__(self, rom_size: int = 0, parent: QWidget | None = None):
        """
        Initialize scan range dialog.

        Args:
            rom_size: Size of the ROM file in bytes
            parent: Parent widget
        """
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.rom_size = rom_size
        # Default to full ROM scan (matching scan_worker.py defaults)
        # Skip headers/early data, cap at reasonable max
        self.start_offset = 0x40000  # Skip headers and early data
        self.end_offset = min(rom_size, 0x400000) if rom_size > 0 else 0x200000  # Cap at 4MB for SNES

        self.setWindowTitle("Custom Scan Range")
        self.setModal(True)
        self.setFixedWidth(400)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Info label
        info_label = QLabel(
            "Specify the ROM range to scan for sprites.\n"
            "Enter offsets in hexadecimal (e.g., 0xC0000) or decimal."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Form layout for inputs
        form_layout = QFormLayout()

        # Start offset input
        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("e.g., 0xC0000 or 786432")
        if self.start_input:
            self.start_input.setText(f"0x{self.start_offset:X}")
        form_layout.addRow("Start Offset:", self.start_input)

        # End offset input
        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("e.g., 0xF0000 or 983040")
        if self.end_input:
            self.end_input.setText(f"0x{self.end_offset:X}")
        form_layout.addRow("End Offset:", self.end_input)

        # ROM size info
        if self.rom_size > 0:
            size_label = QLabel(f"ROM Size: 0x{self.rom_size:X} ({self.rom_size:,} bytes)")
            size_label.setStyleSheet("color: gray;")
            form_layout.addRow("", size_label)

        layout.addLayout(form_layout)

        # Common ranges info
        ranges_label = QLabel(
            "<b>Common Sprite Ranges:</b><br>"
            "• Full ROM: 0x40000 - ROM Size (default)<br>"
            "• Kirby US: 0xC0000 - 0xE0000<br>"
            "• Kirby PAL: 0xC0000 - 0xF0000<br>"
            "• Headers: 0x0 - 0x40000 (rarely has sprites)"
        )
        ranges_label.setStyleSheet("background-color: #f0f0f0; color: #000000; padding: 10px; margin-top: 10px;")
        layout.addWidget(ranges_label)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Add quick presets
        layout.addWidget(QLabel("<b>Quick Presets:</b>"))

        from PySide6.QtWidgets import QHBoxLayout, QPushButton

        preset_layout = QHBoxLayout()

        # Preset buttons
        presets = [
            ("Full ROM", 0x40000, min(self.rom_size, 0x400000) if self.rom_size > 0 else 0x200000),
            ("Kirby US", 0xC0000, 0xE0000),
            ("Kirby PAL", 0xC0000, 0xF0000),
            ("Headers", 0x0, 0x40000),  # Scan headers/early data if needed
        ]

        for name, start, end in presets:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, s=start, e=end: self._apply_preset(s, e))
            preset_layout.addWidget(btn)

        layout.addLayout(preset_layout)

    def _apply_preset(self, start: int, end: int):
        """Apply a preset range."""
        if self.start_input:
            self.start_input.setText(f"0x{start:X}")
        if self.end_input:
            self.end_input.setText(f"0x{end:X}")

    def _parse_offset(self, text: str) -> int:
        """
        Parse an offset from text (hex or decimal).

        Args:
            text: Input text

        Returns:
            Parsed offset value

        Raises:
            ValueError: If parsing fails
        """
        text = text.strip()
        if not text:
            raise ValueError("Empty offset")

        # Try hex first
        if text.startswith(("0x", "0X")):
            return int(text, 16)

        # Try as hex without prefix if it contains hex chars
        if any(c in text.upper() for c in "ABCDEF"):
            return int(text, 16)

        # Otherwise treat as decimal
        return int(text)

    def _validate_and_accept(self):
        """Validate inputs and accept dialog."""
        try:
            # Parse offsets
            start = self._parse_offset(self.start_input.text())
            end = self._parse_offset(self.end_input.text())

            # Validate range
            if start < 0:
                raise ValueError("Start offset cannot be negative")

            if end <= start:
                raise ValueError("End offset must be greater than start offset")

            if self.rom_size > 0:
                if start >= self.rom_size:
                    raise ValueError(f"Start offset exceeds ROM size (0x{self.rom_size:X})")
                if end > self.rom_size:
                    # Clamp to ROM size
                    end = self.rom_size
                    if self.end_input:
                        self.end_input.setText(f"0x{end:X}")

            # Ensure alignment (optional but recommended)
            if start % 0x100 != 0:
                QMessageBox.warning(
                    self,
                    "Alignment Warning",
                    f"Start offset 0x{start:X} is not aligned to 0x100.\n"
                    "This may miss some sprites. Continue anyway?"
                )

            self.start_offset = start
            self.end_offset = end
            self.accept()

        except ValueError as e:
            QMessageBox.critical(
                self,
                "Invalid Input",
                f"Error parsing offsets: {e}"
            )

    def get_range(self) -> tuple[int, int]:
        """
        Get the selected range.

        Returns:
            Tuple of (start_offset, end_offset)
        """
        return (self.start_offset, self.end_offset)
