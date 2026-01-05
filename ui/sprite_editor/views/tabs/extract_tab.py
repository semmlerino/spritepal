#!/usr/bin/env python3
"""
Extract tab for the sprite editor.
Handles sprite extraction from VRAM dumps.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..widgets import HexLineEdit


class ExtractTab(QWidget):
    """Tab for extracting sprites from ROM."""

    # Signals
    browse_vram_requested = Signal()
    browse_cgram_requested = Signal()
    extract_requested = Signal()
    extractionRequested = Signal(str, dict)  # oam_path, settings

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the extraction tab UI."""
        layout = QVBoxLayout(self)

        # File selection group
        file_group = QGroupBox("VRAM File")
        file_layout = QHBoxLayout()

        self.vram_file_edit = QLineEdit()
        self.vram_file_edit.setReadOnly(True)
        self.vram_file_btn = QPushButton("Browse...")
        self.vram_file_btn.clicked.connect(self.browse_vram_requested.emit)

        file_layout.addWidget(QLabel("File:"))
        file_layout.addWidget(self.vram_file_edit)
        file_layout.addWidget(self.vram_file_btn)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # Extraction settings group
        settings_group = QGroupBox("Extraction Settings")
        settings_layout = QGridLayout()

        # Offset
        self.extract_offset_edit = HexLineEdit("0xC000")
        settings_layout.addWidget(QLabel("Offset:"), 0, 0)
        settings_layout.addWidget(self.extract_offset_edit, 0, 1)
        settings_layout.addWidget(QLabel("(VRAM $6000)"), 0, 2)

        # Size
        self.extract_size_edit = HexLineEdit("0x4000")
        settings_layout.addWidget(QLabel("Size:"), 1, 0)
        settings_layout.addWidget(self.extract_size_edit, 1, 1)
        settings_layout.addWidget(QLabel("(16KB)"), 1, 2)

        # Tiles per row
        self.tiles_per_row_spin = QSpinBox()
        self.tiles_per_row_spin.setRange(1, 64)
        self.tiles_per_row_spin.setValue(16)
        settings_layout.addWidget(QLabel("Tiles/Row:"), 2, 0)
        settings_layout.addWidget(self.tiles_per_row_spin, 2, 1)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Palette settings group
        palette_group = QGroupBox("Palette (Optional)")
        palette_layout = QGridLayout()

        self.use_palette_check = QCheckBox("Apply CGRAM Palette")
        self.cgram_file_edit = QLineEdit()
        self.cgram_file_edit.setReadOnly(True)
        self.cgram_browse_btn = QPushButton("Browse...")
        self.cgram_browse_btn.clicked.connect(self.browse_cgram_requested.emit)

        self.palette_combo = QComboBox()
        for i in range(16):
            self.palette_combo.addItem(f"Palette {i}")
        self.palette_combo.setCurrentIndex(8)

        palette_layout.addWidget(self.use_palette_check, 0, 0, 1, 3)
        palette_layout.addWidget(QLabel("CGRAM:"), 1, 0)
        palette_layout.addWidget(self.cgram_file_edit, 1, 1)
        palette_layout.addWidget(self.cgram_browse_btn, 1, 2)
        palette_layout.addWidget(QLabel("Palette:"), 2, 0)
        palette_layout.addWidget(self.palette_combo, 2, 1)

        palette_group.setLayout(palette_layout)
        layout.addWidget(palette_group)

        # Extract button
        self.extract_btn = QPushButton("Extract Sprites")
        self.extract_btn.clicked.connect(self.extract_requested.emit)
        layout.addWidget(self.extract_btn)

        # Output group
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()

        self.extract_output_text = QTextEdit()
        self.extract_output_text.setReadOnly(True)
        self.extract_output_text.setMinimumHeight(100)
        output_layout.addWidget(self.extract_output_text)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

    def get_extraction_params(self) -> dict[str, object]:
        """Get the current extraction parameters."""
        return {
            "vram_file": self.vram_file_edit.text(),
            "offset": self.extract_offset_edit.value(),
            "size": self.extract_size_edit.value(),
            "tiles_per_row": self.tiles_per_row_spin.value(),
            "use_palette": self.use_palette_check.isChecked(),
            "cgram_file": self.cgram_file_edit.text(),
            "palette_num": self.palette_combo.currentIndex(),
        }

    def validate_params(self) -> tuple[bool, str]:
        """Validate extraction parameters.

        Returns:
            Tuple of (is_valid, error_message). Error message is empty if valid.
        """
        errors: list[str] = []

        if not self.vram_file_edit.text().strip():
            errors.append("VRAM file is required")

        if not self.extract_offset_edit.isValid():
            errors.append("Invalid extraction offset")

        if not self.extract_size_edit.isValid():
            errors.append("Invalid extraction size")
        elif self.extract_size_edit.value() <= 0:
            errors.append("Extraction size must be greater than 0")

        # Check CGRAM file if palette is enabled
        if self.use_palette_check.isChecked():
            if not self.cgram_file_edit.text().strip():
                errors.append("CGRAM file required when using palette")

        return (True, "") if not errors else (False, "\n".join(errors))

    def set_vram_file(self, file_path: str) -> None:
        """Set the VRAM file path."""
        self.vram_file_edit.setText(file_path)

    def set_cgram_file(self, file_path: str) -> None:
        """Set the CGRAM file path."""
        self.cgram_file_edit.setText(file_path)

    def append_output(self, text: str) -> None:
        """Append text to the output area."""
        self.extract_output_text.append(text)

    def clear_output(self) -> None:
        """Clear the output area."""
        self.extract_output_text.clear()

    def set_extract_enabled(self, enabled: bool) -> None:
        """Enable/disable the extract button."""
        self.extract_btn.setEnabled(enabled)
