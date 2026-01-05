#!/usr/bin/env python3
"""
Inject tab for the sprite editor.
Handles sprite injection into VRAM dumps.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..widgets import HexLineEdit


class InjectTab(QWidget):
    """Tab widget for sprite injection functionality."""

    # Signals
    inject_requested = Signal()
    browse_png_requested = Signal()
    browse_vram_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the injection tab UI."""
        layout = QVBoxLayout(self)

        # PNG file group
        png_group = QGroupBox("PNG File to Inject")
        png_layout = QHBoxLayout()

        self.png_file_edit = QLineEdit()
        self.png_file_edit.setReadOnly(True)
        self.png_browse_btn = QPushButton("Browse...")
        self.png_browse_btn.clicked.connect(self.browse_png_requested.emit)

        png_layout.addWidget(QLabel("File:"))
        png_layout.addWidget(self.png_file_edit)
        png_layout.addWidget(self.png_browse_btn)
        png_group.setLayout(png_layout)
        layout.addWidget(png_group)

        # Validation group
        validation_group = QGroupBox("PNG Validation")
        validation_layout = QVBoxLayout()

        self.validation_text = QTextEdit()
        self.validation_text.setReadOnly(True)
        self.validation_text.setMinimumHeight(80)
        validation_layout.addWidget(self.validation_text)

        validation_group.setLayout(validation_layout)
        layout.addWidget(validation_group)

        # Target settings group
        target_group = QGroupBox("Target Settings")
        target_layout = QGridLayout()

        # VRAM file
        self.inject_vram_edit = QLineEdit()
        self.inject_vram_edit.setReadOnly(True)
        self.inject_vram_btn = QPushButton("Browse...")
        self.inject_vram_btn.clicked.connect(self.browse_vram_requested.emit)

        target_layout.addWidget(QLabel("VRAM:"), 0, 0)
        target_layout.addWidget(self.inject_vram_edit, 0, 1)
        target_layout.addWidget(self.inject_vram_btn, 0, 2)

        # Offset
        self.inject_offset_edit = HexLineEdit("0xC000")
        target_layout.addWidget(QLabel("Offset:"), 1, 0)
        target_layout.addWidget(self.inject_offset_edit, 1, 1)

        # Output file
        self.output_file_edit = QLineEdit("VRAM_edited.dmp")
        target_layout.addWidget(QLabel("Output:"), 2, 0)
        target_layout.addWidget(self.output_file_edit, 2, 1)

        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

        # Inject button
        self.inject_btn = QPushButton("Inject Sprites")
        self.inject_btn.clicked.connect(self.inject_requested.emit)
        layout.addWidget(self.inject_btn)

        # Output group
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()

        self.inject_output_text = QTextEdit()
        self.inject_output_text.setReadOnly(True)
        self.inject_output_text.setMinimumHeight(100)
        output_layout.addWidget(self.inject_output_text)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

    def get_injection_params(self) -> dict[str, object]:
        """Get the current injection parameters."""
        return {
            "png_file": self.png_file_edit.text(),
            "vram_file": self.inject_vram_edit.text(),
            "offset": self.inject_offset_edit.value(),
            "output_file": self.output_file_edit.text(),
        }

    def validate_params(self) -> tuple[bool, str]:
        """Validate injection parameters.

        Returns:
            Tuple of (is_valid, error_message). Error message is empty if valid.
        """
        errors: list[str] = []

        if not self.png_file_edit.text().strip():
            errors.append("PNG file is required")

        if not self.inject_vram_edit.text().strip():
            errors.append("VRAM file is required")

        if not self.inject_offset_edit.isValid():
            errors.append("Invalid injection offset")

        if not self.output_file_edit.text().strip():
            errors.append("Output file name is required")

        return (True, "") if not errors else (False, "\n".join(errors))

    def set_png_file(self, file_path: str) -> None:
        """Set the PNG file path."""
        self.png_file_edit.setText(file_path)

    def set_vram_file(self, file_path: str) -> None:
        """Set the VRAM file path."""
        self.inject_vram_edit.setText(file_path)

    def set_validation_text(self, text: str, is_valid: bool = True) -> None:
        """Set validation message with appropriate styling."""
        if is_valid:
            self.validation_text.setStyleSheet("color: #00ff00;")
        else:
            self.validation_text.setStyleSheet("color: #ff0000;")
        self.validation_text.setText(text)

    def append_output(self, text: str) -> None:
        """Append text to the output area."""
        self.inject_output_text.append(text)

    def clear_output(self) -> None:
        """Clear the output area."""
        self.inject_output_text.clear()

    def set_inject_enabled(self, enabled: bool) -> None:
        """Enable/disable the inject button."""
        self.inject_btn.setEnabled(enabled)
