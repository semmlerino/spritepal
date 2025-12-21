"""
Output settings management for MainWindow
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles import get_muted_text_style
from ui.styles.theme import COLORS


class OutputSettingsActionsProtocol(Protocol):
    """Protocol defining the interface for output settings actions"""

    def get_current_vram_path(self) -> str:
        """Get current VRAM path for browse dialog default directory"""
        ...

class OutputSettingsManager(QObject):
    """Manages output settings section for MainWindow"""

    # Signals
    output_name_changed = Signal(str)
    grayscale_toggled = Signal(bool)
    metadata_toggled = Signal(bool)

    def __init__(self, parent: QWidget, actions_handler: OutputSettingsActionsProtocol) -> None:
        """Initialize output settings manager

        Args:
            parent: Parent widget
            actions_handler: Handler for output settings actions
        """
        super().__init__(parent)
        self.parent_widget = parent
        self.actions_handler = actions_handler

        # Widget references
        self.output_group: QGroupBox
        self.output_name_edit: QLineEdit
        self.browse_button: QPushButton
        self.grayscale_check: QCheckBox
        self.metadata_check: QCheckBox
        self.output_info_label: QLabel

    def create_output_settings_group(self) -> QGroupBox:
        """Create and return the output settings group box"""
        self.output_group = QGroupBox("Output Settings")
        output_layout = QVBoxLayout()

        # Output name section
        self._create_output_name_section(output_layout)

        # Output options section
        self._create_output_options_section(output_layout)

        # Output info label
        self._create_output_info_section(output_layout)

        self.output_group.setLayout(output_layout)
        self._connect_signals()

        return self.output_group

    def _create_output_name_section(self, layout: QVBoxLayout) -> None:
        """Create output name input section"""
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:", self.parent_widget))

        self.output_name_edit = QLineEdit(self.parent_widget)
        self.output_name_edit.setPlaceholderText("e.g., cave_sprites_editor")
        # Store default style for later restore
        self._default_output_style = ""
        self._highlight_output_style = f"""
            QLineEdit {{
                border: 2px solid {COLORS["warning"]};
                background-color: rgba(255, 215, 0, 0.1);
            }}
            QLineEdit:focus {{
                border: 2px solid {COLORS["highlight"]};
            }}
        """
        name_layout.addWidget(self.output_name_edit)

        self.browse_button = QPushButton("Browse...")
        name_layout.addWidget(self.browse_button)

        layout.addLayout(name_layout)

    def _create_output_options_section(self, layout: QVBoxLayout) -> None:
        """Create output options checkboxes"""
        self.grayscale_check = QCheckBox("Export palette files (.pal.json)")
        self.grayscale_check.setChecked(True)
        self.grayscale_check.setToolTip(
            "Creates 8 separate palette files for applying different color schemes.\n"
            "Required for palette switching in the editor."
        )
        layout.addWidget(self.grayscale_check)

        self.metadata_check = QCheckBox("Include palette metadata")
        self.metadata_check.setChecked(True)
        self.metadata_check.setToolTip(
            "Creates a .metadata.json file that enables palette switching.\n"
            "Without this, you can only use the default palette."
        )
        layout.addWidget(self.metadata_check)

    def _create_output_info_section(self, layout: QVBoxLayout) -> None:
        """Create output files info label"""
        self.output_info_label = QLabel("Files to create: Loading...")
        self.output_info_label.setStyleSheet(get_muted_text_style(italic=True))
        layout.addWidget(self.output_info_label)

    def _connect_signals(self) -> None:
        """Connect internal widget signals"""
        self.output_name_edit.textChanged.connect(self._on_output_name_changed)
        self.browse_button.clicked.connect(self._browse_output)
        self.grayscale_check.toggled.connect(self._on_grayscale_toggled)
        self.metadata_check.toggled.connect(self._on_metadata_toggled)

    def _on_output_name_changed(self, text: str) -> None:
        """Handle output name change"""
        self.output_name_changed.emit(text)

    def _on_grayscale_toggled(self, checked: bool) -> None:
        """Handle grayscale checkbox toggle"""
        self.grayscale_toggled.emit(checked)

    def _on_metadata_toggled(self, checked: bool) -> None:
        """Handle metadata checkbox toggle"""
        self.metadata_toggled.emit(checked)

    def _browse_output(self) -> None:
        """Browse for output location"""
        # Get current directory from session
        current_vram_path = self.actions_handler.get_current_vram_path()
        if current_vram_path:
            default_dir = str(Path(current_vram_path).parent)
        else:
            default_dir = str(Path.cwd())

        suggested_path = str(
            Path(default_dir) / (self.output_name_edit.text() + ".png")
        )

        filename, _ = QFileDialog.getSaveFileName(
            self.parent_widget,
            "Save Sprites As",
            suggested_path,
            "PNG Files (*.png)"
        )

        if filename:
            # Update output name without extension
            base_name = Path(filename).stem
            self.output_name_edit.setText(base_name)

    def get_output_name(self) -> str:
        """Get current output name"""
        return self.output_name_edit.text()

    def set_output_name(self, name: str) -> None:
        """Set output name without triggering signals"""
        # Temporarily disconnect to avoid signal loops
        self.output_name_edit.textChanged.disconnect()
        self.output_name_edit.setText(name)
        self.output_name_edit.textChanged.connect(self._on_output_name_changed)

    def get_grayscale_enabled(self) -> bool:
        """Get grayscale checkbox state"""
        return self.grayscale_check.isChecked()

    def set_grayscale_enabled(self, enabled: bool) -> None:
        """Set grayscale checkbox state"""
        self.grayscale_check.setChecked(enabled)

    def get_metadata_enabled(self) -> bool:
        """Get metadata checkbox state"""
        return self.metadata_check.isChecked()

    def set_metadata_enabled(self, enabled: bool) -> None:
        """Set metadata checkbox state"""
        self.metadata_check.setChecked(enabled)

    def update_output_info_label(self, is_vram_tab: bool, is_grayscale_mode: bool) -> None:
        """Update the label showing which files will be created

        Args:
            is_vram_tab: Whether VRAM extraction tab is active
            is_grayscale_mode: Whether in grayscale-only mode
        """
        if not is_vram_tab:
            return

        if is_grayscale_mode:
            self.output_info_label.setText("Files to create: grayscale PNG only")
        else:
            files = ["PNG"]
            if self.grayscale_check.isChecked():
                files.append("8 palette files (.pal.json)")
            if self.metadata_check.isChecked():
                files.append("metadata.json")
            self.output_info_label.setText(f"Files to create: {', '.join(files)}")

    def set_rom_extraction_mode(self) -> None:
        """Configure for ROM extraction mode - all outputs enabled and forced on"""
        # Force checkboxes on and disable them - ROM mode always creates all outputs
        self.grayscale_check.setChecked(True)
        self.grayscale_check.setEnabled(False)
        self.grayscale_check.setToolTip(
            "Palette files are always created in ROM extraction mode."
        )

        self.metadata_check.setChecked(True)
        self.metadata_check.setEnabled(False)
        self.metadata_check.setToolTip(
            "Metadata is always created in ROM extraction mode."
        )

        self.output_info_label.setText(
            "ROM extraction always creates: PNG, palette files, metadata"
        )

        self.output_group.setTitle("Output Settings (ROM Mode)")

    def set_vram_extraction_mode(self) -> None:
        """Configure for VRAM extraction mode - checkboxes enabled for user control"""
        # Re-enable checkboxes with original tooltips
        self.grayscale_check.setEnabled(True)
        self.grayscale_check.setToolTip(
            "Creates 8 separate palette files for applying different color schemes.\n"
            "Required for palette switching in the editor."
        )

        self.metadata_check.setEnabled(True)
        self.metadata_check.setToolTip(
            "Creates a .metadata.json file that enables palette switching.\n"
            "Without this, you can only use the default palette."
        )

        # Update info label to reflect current checkbox state
        files = ["PNG"]
        if self.grayscale_check.isChecked():
            files.append("palette files (.pal.json)")
        if self.metadata_check.isChecked():
            files.append("metadata.json")
        self.output_info_label.setText(f"Files to create: {', '.join(files)}")

        self.output_group.setTitle("Output Settings")

    def set_extraction_mode_options(self, is_grayscale_mode: bool) -> None:
        """Update options based on extraction mode

        Args:
            is_grayscale_mode: Whether in grayscale-only mode
        """
        # Disable palette-related options in grayscale mode
        self.grayscale_check.setEnabled(not is_grayscale_mode)
        self.metadata_check.setEnabled(not is_grayscale_mode)

        # Update tooltips to explain why they're disabled
        if is_grayscale_mode:
            self.grayscale_check.setToolTip(
                "Not available in Grayscale Only mode.\n"
                "Palette files are only created with color extraction."
            )
            self.metadata_check.setToolTip(
                "Not available in Grayscale Only mode.\n"
                "Metadata is only created with color extraction."
            )
        else:
            self.grayscale_check.setToolTip(
                "Creates 8 separate palette files for applying different color schemes.\n"
                "Required for palette switching in the editor."
            )
            self.metadata_check.setToolTip(
                "Creates a .metadata.json file that enables palette switching.\n"
                "Without this, you can only use the default palette."
            )

    def clear_output_name(self) -> None:
        """Clear output name field"""
        self.output_name_edit.clear()

    def set_output_needs_attention(self, needs_attention: bool) -> None:
        """Highlight or unhighlight the output name field.

        Call this when extraction is blocked waiting for output name.

        Args:
            needs_attention: True to highlight (warning style), False to restore default
        """
        if needs_attention and not self.output_name_edit.text():
            # Only highlight if field is actually empty
            self.output_name_edit.setStyleSheet(self._highlight_output_style)
        else:
            # Restore default style
            self.output_name_edit.setStyleSheet(self._default_output_style)
