"""
Dialog for manually specifying a palette ROM offset.

Allows users to specify a palette location in ROM for games/sprites
where automatic palette detection is not available.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class ManualPaletteOffsetDialog(QDialog):
    """
    Dialog for entering a manual palette ROM offset.

    Users can specify:
    - Palette ROM offset (hex address where palette data starts)
    - Starting palette index (default 8 for sprites)
    - Number of palettes to load (default 8 for indices 8-15)

    Signals:
        palette_offset_selected: Emitted when user confirms a valid offset.
            Args: offset (int), start_index (int), count (int)
    """

    palette_offset_selected = Signal(int, int, int)  # offset, start_index, count

    def __init__(self, parent: QWidget | None = None, *, rom_size: int = 0) -> None:
        """Initialize the manual palette offset dialog.

        Args:
            parent: Parent widget
            rom_size: Size of the ROM in bytes (for validation)
        """
        super().__init__(parent)
        self._rom_size = rom_size
        self._setup_ui()
        self._connect_signals()
        self.setWindowTitle("Manual Palette Offset")
        self.setMinimumWidth(350)

    def _setup_ui(self) -> None:
        """Configure the dialog layout and controls."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Info label
        info_label = QLabel(
            "Enter the ROM offset where sprite palette data begins.\n"
            "SNES palettes are 32 bytes each (16 colors in BGR555 format)."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Form layout for inputs
        form_layout = QFormLayout()
        form_layout.setSpacing(8)

        # Palette offset input (hex)
        offset_container = QHBoxLayout()
        offset_container.setSpacing(4)

        prefix_label = QLabel("0x")
        self._offset_input = QLineEdit()
        self._offset_input.setPlaceholderText("e.g., 1A2B00")
        self._offset_input.setMaxLength(8)

        offset_container.addWidget(prefix_label)
        offset_container.addWidget(self._offset_input)

        offset_widget = QWidget()
        offset_widget.setLayout(offset_container)
        form_layout.addRow("Palette Offset:", offset_widget)

        # Starting palette index
        self._start_index_spin = QSpinBox()
        self._start_index_spin.setRange(0, 15)
        self._start_index_spin.setValue(8)  # Default to palette 8 (sprites)
        self._start_index_spin.setToolTip(
            "SNES sprites typically use palette indices 8-15.\nBackground tiles typically use 0-7."
        )
        form_layout.addRow("Starting Index:", self._start_index_spin)

        # Number of palettes to load
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 8)
        self._count_spin.setValue(8)  # Default to 8 palettes
        self._count_spin.setToolTip("Number of consecutive palettes to load")
        form_layout.addRow("Palette Count:", self._count_spin)

        layout.addLayout(form_layout)

        # Validation message
        self._validation_label = QLabel()
        self._validation_label.setStyleSheet("color: red;")
        layout.addWidget(self._validation_label)

        # Dialog buttons
        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self._offset_input.textChanged.connect(self._validate_input)
        self._start_index_spin.valueChanged.connect(self._validate_input)
        self._count_spin.valueChanged.connect(self._validate_input)

    def _validate_input(self) -> bool:
        """Validate the current input and update UI accordingly.

        Returns:
            True if input is valid, False otherwise.
        """
        self._validation_label.clear()
        offset_text = self._offset_input.text().strip()

        if not offset_text:
            self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return False

        # Parse hex offset
        try:
            offset = int(offset_text, 16)
        except ValueError:
            self._validation_label.setText("Invalid hex value")
            self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return False

        # Validate offset is within ROM bounds
        if offset < 0:
            self._validation_label.setText("Offset cannot be negative")
            self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return False

        if self._rom_size > 0:
            # Calculate bytes needed: count * 32 bytes per palette
            count = self._count_spin.value()
            bytes_needed = count * 32

            if offset + bytes_needed > self._rom_size:
                self._validation_label.setText(f"Offset + palette data exceeds ROM size (0x{self._rom_size:X})")
                self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
                return False

        # Validate palette index range
        start_index = self._start_index_spin.value()
        count = self._count_spin.value()
        if start_index + count > 16:
            # Adjust count automatically
            max_count = 16 - start_index
            self._count_spin.setValue(max_count)

        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        return True

    def _on_accept(self) -> None:
        """Handle OK button click."""
        if not self._validate_input():
            return

        offset_text = self._offset_input.text().strip()
        offset = int(offset_text, 16)
        start_index = self._start_index_spin.value()
        count = self._count_spin.value()

        logger.info(f"Manual palette offset selected: 0x{offset:X}, indices {start_index}-{start_index + count - 1}")

        self.palette_offset_selected.emit(offset, start_index, count)
        self.accept()

    def set_offset(self, offset: int) -> None:
        """Set the initial offset value.

        Args:
            offset: ROM offset in bytes
        """
        self._offset_input.setText(f"{offset:X}")
        self._validate_input()

    def get_offset(self) -> int | None:
        """Get the current offset value.

        Returns:
            Offset value or None if invalid
        """
        offset_text = self._offset_input.text().strip()
        if not offset_text:
            return None
        try:
            return int(offset_text, 16)
        except ValueError:
            return None

    def get_palette_range(self) -> tuple[int, int]:
        """Get the palette index range.

        Returns:
            Tuple of (start_index, count)
        """
        return (self._start_index_spin.value(), self._count_spin.value())
