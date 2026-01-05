#!/usr/bin/env python3
"""
Extract tab for the sprite editor.
Handles sprite extraction from VRAM dumps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Signal
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

from ui.widgets.drop_zone import DropZone

from ..widgets import HexLineEdit

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager


class ExtractTab(QWidget):
    """Tab for extracting sprites from ROM."""

    # Signals
    browse_vram_requested = Signal()
    browse_cgram_requested = Signal()
    browse_rom_requested = Signal()
    extract_requested = Signal()
    load_rom_requested = Signal()
    extractionRequested = Signal(str, dict)  # oam_path, settings

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_manager: ApplicationStateManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the extraction tab UI."""
        layout = QVBoxLayout(self)

        # File selection (Drop Zones for consistency)
        self.vram_drop = DropZone("VRAM", settings_manager=self.settings_manager, required=True)  # type: ignore[arg-type]
        self.vram_drop.file_dropped.connect(lambda p: self.set_vram_file(p))
        layout.addWidget(self.vram_drop)

        # ROM Selection (Hidden by default)
        self.rom_group = QGroupBox("ROM File")
        rom_layout = QHBoxLayout()
        self.rom_path_edit = QLineEdit()
        self.browse_rom_btn = QPushButton("Browse...")
        self.browse_rom_btn.clicked.connect(self.browse_rom_requested.emit)
        rom_layout.addWidget(self.rom_path_edit)
        rom_layout.addWidget(self.browse_rom_btn)
        self.rom_group.setLayout(rom_layout)
        self.rom_group.hide()
        layout.addWidget(self.rom_group)

        # Extraction settings group
        settings_group = QGroupBox("Extraction Settings")
        settings_layout = QGridLayout()

        # Offset
        self.extract_offset_edit = HexLineEdit("0xC000")
        settings_layout.addWidget(QLabel("Offset:"), 0, 0)
        settings_layout.addWidget(self.extract_offset_edit, 0, 1)

        offset_hint = QLabel("(VRAM $6000)")
        offset_hint.setWordWrap(True)
        settings_layout.addWidget(offset_hint, 0, 2)

        # Size
        self.extract_size_edit = HexLineEdit("0x4000")
        settings_layout.addWidget(QLabel("Size:"), 1, 0)
        settings_layout.addWidget(self.extract_size_edit, 1, 1)

        size_hint = QLabel("(16KB)")
        size_hint.setWordWrap(True)
        settings_layout.addWidget(size_hint, 1, 2)

        # Tiles per row
        self.tiles_per_row_spin = QSpinBox()
        self.tiles_per_row_spin.setRange(1, 64)
        self.tiles_per_row_spin.setValue(16)
        settings_layout.addWidget(QLabel("Tiles/Row:"), 2, 0)
        settings_layout.addWidget(self.tiles_per_row_spin, 2, 1)

        # Allow column 2 (hints) to wrap and take available space
        settings_layout.setColumnStretch(2, 1)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Palette settings group
        palette_group = QGroupBox("Palette (Optional)")
        palette_layout = QGridLayout()

        self.use_palette_check = QCheckBox("Apply CGRAM Palette")
        self.use_palette_check.toggled.connect(self._on_palette_toggle)

        self.cgram_drop = DropZone("CGRAM", settings_manager=self.settings_manager, required=False)  # type: ignore[arg-type]
        self.cgram_drop.file_dropped.connect(lambda p: self.set_cgram_file(p))

        self.palette_combo = QComboBox()
        for i in range(16):
            self.palette_combo.addItem(f"Palette {i}")
        self.palette_combo.setCurrentIndex(8)

        palette_layout.addWidget(self.use_palette_check, 0, 0, 1, 3)
        palette_layout.addWidget(self.cgram_drop, 1, 0, 1, 3)
        palette_layout.addWidget(QLabel("Palette:"), 2, 0)
        palette_layout.addWidget(self.palette_combo, 2, 1)

        palette_group.setLayout(palette_layout)
        layout.addWidget(palette_group)

        # Initialize palette control states
        self._on_palette_toggle(self.use_palette_check.isChecked())

        # Extract button
        self.extract_btn = QPushButton("Extract Sprites")
        self.extract_btn.clicked.connect(self.extract_requested.emit)
        layout.addWidget(self.extract_btn)

        # Load from ROM button (Hidden by default)
        self.load_rom_btn = QPushButton("Load from ROM")
        self.load_rom_btn.clicked.connect(self.load_rom_requested.emit)
        self.load_rom_btn.hide()
        layout.addWidget(self.load_rom_btn)

        # Output group
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()

        self.extract_output_text = QTextEdit()
        self.extract_output_text.setReadOnly(True)
        self.extract_output_text.setMinimumHeight(100)
        output_layout.addWidget(self.extract_output_text)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

    def set_mode(self, mode: str) -> None:
        """Set the extraction mode ('vram' or 'rom')."""
        is_rom = mode == "rom"
        self.vram_drop.setVisible(not is_rom)
        self.rom_group.setVisible(is_rom)
        self.extract_btn.setVisible(not is_rom)
        self.load_rom_btn.setVisible(is_rom)

        # Update hints if needed (could be improved)
        if is_rom:
            self.vram_drop.set_required(False)
        else:
            self.vram_drop.set_required(True)

    def set_rom_file(self, path: str) -> None:
        """Set the ROM file path."""
        self.rom_path_edit.setText(path)

    def get_extraction_params(self) -> dict[str, object]:
        """Get the current extraction parameters."""
        return {
            "vram_file": self.vram_drop.get_file_path(),
            "rom_file": self.rom_path_edit.text(),
            "offset": self.extract_offset_edit.value(),
            "size": self.extract_size_edit.value(),
            "tiles_per_row": self.tiles_per_row_spin.value(),
            "use_palette": self.use_palette_check.isChecked(),
            "cgram_file": self.cgram_drop.get_file_path(),
            "palette_num": self.palette_combo.currentIndex(),
        }

    def validate_params(self) -> tuple[bool, str]:
        """Validate extraction parameters.

        Returns:
            Tuple of (is_valid, error_message). Error message is empty if valid.
        """
        errors: list[str] = []

        if not self.vram_drop.has_file():
            errors.append("VRAM file is required")

        if not self.extract_offset_edit.isValid():
            errors.append("Invalid extraction offset")

        if not self.extract_size_edit.isValid():
            errors.append("Invalid extraction size")
        elif self.extract_size_edit.value() <= 0:
            errors.append("Extraction size must be greater than 0")

        # Check CGRAM file if palette is enabled
        if self.use_palette_check.isChecked():
            if not self.cgram_drop.has_file():
                errors.append("CGRAM file required when using palette")

        return (True, "") if not errors else (False, "\n".join(errors))

    def set_offset(self, offset: int | str) -> None:
        """Set the extraction offset.

        Args:
            offset: Offset value (int or hex string)
        """
        if isinstance(offset, int):
            self.extract_offset_edit.setValue(offset)
        else:
            self.extract_offset_edit.setText(str(offset))

    def set_vram_file(self, file_path: str) -> None:
        """Set the VRAM file path."""
        # Block signals to prevent feedback loop (signal → set → emit → signal)
        _blocker = QSignalBlocker(self.vram_drop)
        if file_path:
            self.vram_drop.set_file(file_path)
        else:
            self.vram_drop.clear()

    def set_cgram_file(self, file_path: str) -> None:
        """Set the CGRAM file path."""
        # Block signals to prevent feedback loop (signal → set → emit → signal)
        _blocker = QSignalBlocker(self.cgram_drop)
        if file_path:
            self.cgram_drop.set_file(file_path)
        else:
            self.cgram_drop.clear()

    def append_output(self, text: str) -> None:
        """Append text to the output area."""
        self.extract_output_text.append(text)

    def clear_output(self) -> None:
        """Clear the output area."""
        self.extract_output_text.clear()

    def set_extract_enabled(self, enabled: bool) -> None:
        """Enable/disable the extract button."""
        self.extract_btn.setEnabled(enabled)

    def _on_palette_toggle(self, checked: bool) -> None:
        """Enable/disable CGRAM widgets based on checkbox state.

        Args:
            checked: Whether the "Apply CGRAM Palette" checkbox is checked.
        """
        self.cgram_drop.setEnabled(checked)
        self.palette_combo.setEnabled(checked)
