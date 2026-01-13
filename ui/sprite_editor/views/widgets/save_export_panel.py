#!/usr/bin/env python3
"""
Save & Export panel widget for the sprite editor.
Provides buttons to save modified sprites back to ROM and export as PNG.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import BUTTON_HEIGHT, SPACING_MEDIUM, SPACING_STANDARD
from ui.styles import get_button_style, get_prominent_action_button_style


class SaveExportPanel(QWidget):
    """
    Panel for saving and exporting sprite data.

    Provides two main actions:
    - Save to ROM: Write modified sprite data back to the loaded ROM
    - Export PNG: Export the current sprite as a PNG file

    Optionally displays size information showing original vs modified byte counts.
    """

    # Signals
    saveToRomClicked = Signal()
    exportPngClicked = Signal()
    saveProjectClicked = Signal()
    loadProjectClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialize the Save & Export panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("saveExportPanel")

        # Instance variables for size info
        self._original_bytes: int | None = None
        self._modified_bytes: int | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI layout and controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING_STANDARD)

        # Main group box
        group = QGroupBox("SAVE & EXPORT")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM)
        group_layout.setSpacing(SPACING_STANDARD)

        # Save to ROM button (prominent)
        self.save_to_rom_btn = QPushButton("SAVE TO ROM")
        self.save_to_rom_btn.setStyleSheet(get_prominent_action_button_style())
        self.save_to_rom_btn.setMinimumHeight(BUTTON_HEIGHT)
        self.save_to_rom_btn.clicked.connect(self.saveToRomClicked.emit)
        self.save_to_rom_btn.setEnabled(False)
        group_layout.addWidget(self.save_to_rom_btn)

        # Export PNG button (secondary)
        self.export_png_btn = QPushButton("Export PNG...")
        self.export_png_btn.setStyleSheet(get_button_style("secondary"))
        self.export_png_btn.clicked.connect(self.exportPngClicked.emit)
        self.export_png_btn.setEnabled(False)
        group_layout.addWidget(self.export_png_btn)

        # Save Project button
        self.save_project_btn = QPushButton("Save Project...")
        self.save_project_btn.setStyleSheet(get_button_style("secondary"))
        self.save_project_btn.clicked.connect(self.saveProjectClicked.emit)
        self.save_project_btn.setEnabled(False)
        group_layout.addWidget(self.save_project_btn)

        # Load Project button
        self.load_project_btn = QPushButton("Load Project...")
        self.load_project_btn.setStyleSheet(get_button_style("secondary"))
        self.load_project_btn.clicked.connect(self.loadProjectClicked.emit)
        group_layout.addWidget(self.load_project_btn)

        # Size info container (initially hidden)
        self.size_info_widget = QWidget()
        size_info_layout = QVBoxLayout(self.size_info_widget)
        size_info_layout.setContentsMargins(0, SPACING_STANDARD, 0, 0)
        size_info_layout.setSpacing(SPACING_MEDIUM)

        self.original_size_label = QLabel("Original: - bytes")
        self.original_size_label.setObjectName("originalSizeLabel")
        size_info_layout.addWidget(self.original_size_label)

        self.modified_size_label = QLabel("Modified: - bytes")
        self.modified_size_label.setObjectName("modifiedSizeLabel")
        size_info_layout.addWidget(self.modified_size_label)

        self.size_info_widget.setVisible(False)
        group_layout.addWidget(self.size_info_widget)

        # Add stretch to push everything to top
        group_layout.addStretch(1)

        layout.addWidget(group)

    def set_save_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the "Save to ROM" button.

        Args:
            enabled: Whether the button should be enabled
        """
        self.save_to_rom_btn.setEnabled(enabled)

    def set_export_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the "Export PNG" button.

        Args:
            enabled: Whether the button should be enabled
        """
        self.export_png_btn.setEnabled(enabled)

    def set_save_visible(self, visible: bool) -> None:
        """
        Show or hide the "Save to ROM" button.

        Args:
            visible: Whether the button should be visible
        """
        self.save_to_rom_btn.setVisible(visible)

    def set_export_visible(self, visible: bool) -> None:
        """
        Show or hide the "Export PNG" button.

        Args:
            visible: Whether the button should be visible
        """
        self.export_png_btn.setVisible(visible)

    def set_save_project_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the "Save Project" button.

        Args:
            enabled: Whether the button should be enabled
        """
        self.save_project_btn.setEnabled(enabled)

    def set_load_project_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the "Load Project" button.

        Args:
            enabled: Whether the button should be enabled
        """
        self.load_project_btn.setEnabled(enabled)

    def set_size_info(self, original_bytes: int, modified_bytes: int) -> None:
        """
        Set and display size information for the sprite data.

        Args:
            original_bytes: Number of bytes in the original sprite
            modified_bytes: Number of bytes in the modified sprite
        """
        self._original_bytes = original_bytes
        self._modified_bytes = modified_bytes

        self.original_size_label.setText(f"Original: {original_bytes} bytes")
        self.modified_size_label.setText(f"Modified: {modified_bytes} bytes")

        self.size_info_widget.setVisible(True)

    def hide_size_info(self) -> None:
        """Hide the size information display."""
        self.size_info_widget.setVisible(False)

    def show_size_info(self) -> None:
        """Show the size information display if data is available."""
        if self._original_bytes is not None and self._modified_bytes is not None:
            self.size_info_widget.setVisible(True)
