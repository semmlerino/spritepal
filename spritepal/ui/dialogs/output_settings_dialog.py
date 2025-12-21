"""
Output settings dialog for extraction configuration.

This dialog is shown before extraction to configure output name and options,
removing the need for a permanent output settings panel in the main window.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_STANDARD
from ui.components.base import BaseDialog
from ui.styles import get_muted_text_style
from ui.styles.theme import COLORS


class OutputSettings(NamedTuple):
    """Settings returned by the output settings dialog."""

    output_name: str
    export_palette_files: bool
    include_metadata: bool


class OutputSettingsDialog(BaseDialog):
    """Dialog for configuring extraction output settings.

    This dialog is shown before extraction begins, allowing users to:
    - Set the output filename
    - Choose whether to export palette files
    - Choose whether to include metadata

    Usage:
        dialog = OutputSettingsDialog(parent, suggested_name="sprite_name")
        if dialog.exec():
            settings = dialog.get_settings()
            # Proceed with extraction using settings
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        suggested_name: str = "",
        is_rom_mode: bool = False,
        default_directory: str = "",
    ):
        """Initialize the output settings dialog.

        Args:
            parent: Parent widget
            suggested_name: Pre-filled output name suggestion
            is_rom_mode: If True, palette and metadata options are locked on
            default_directory: Default directory for browse dialog
        """
        # Declare instance variables BEFORE super().__init__()
        self.output_name_edit: QLineEdit | None = None
        self.browse_button: QPushButton | None = None
        self.palette_check: QCheckBox | None = None
        self.metadata_check: QCheckBox | None = None
        self.info_label: QLabel | None = None

        self._suggested_name = suggested_name
        self._is_rom_mode = is_rom_mode
        self._default_directory = default_directory

        super().__init__(
            parent=parent,
            title="Output Settings",
            modal=True,
            min_size=(450, None),
            with_button_box=True,
        )

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout()
        layout.setSpacing(SPACING_STANDARD)

        # Output name section
        self._create_output_name_section(layout)

        # Options section
        self._create_options_section(layout)

        # Info label
        self._create_info_section(layout)

        self.set_content_layout(layout)

        # Update info label based on initial state
        self._update_info_label()

    def _create_output_name_section(self, layout: QVBoxLayout) -> None:
        """Create the output name input row."""
        name_layout = QHBoxLayout()

        name_label = QLabel("Output Name:")
        name_label.setMinimumWidth(100)
        name_layout.addWidget(name_label)

        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("e.g., cave_sprites")
        self.output_name_edit.setText(self._suggested_name)
        self.output_name_edit.textChanged.connect(self._update_info_label)
        name_layout.addWidget(self.output_name_edit, 1)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse_output)
        name_layout.addWidget(self.browse_button)

        layout.addLayout(name_layout)

    def _create_options_section(self, layout: QVBoxLayout) -> None:
        """Create the output options checkboxes."""
        self.palette_check = QCheckBox("Export palette files (.pal.json)")
        self.palette_check.setChecked(True)
        self.palette_check.toggled.connect(self._update_info_label)

        if self._is_rom_mode:
            self.palette_check.setEnabled(False)
            self.palette_check.setToolTip("Palette files are always created in ROM extraction mode")
        else:
            self.palette_check.setToolTip(
                "Creates 8 separate palette files for applying different color schemes.\n"
                "Required for palette switching in the editor."
            )
        layout.addWidget(self.palette_check)

        self.metadata_check = QCheckBox("Include palette metadata")
        self.metadata_check.setChecked(True)
        self.metadata_check.toggled.connect(self._update_info_label)

        if self._is_rom_mode:
            self.metadata_check.setEnabled(False)
            self.metadata_check.setToolTip("Metadata is always created in ROM extraction mode")
        else:
            self.metadata_check.setToolTip(
                "Creates a .metadata.json file that enables palette switching.\n"
                "Without this, you can only use the default palette."
            )
        layout.addWidget(self.metadata_check)

    def _create_info_section(self, layout: QVBoxLayout) -> None:
        """Create the info label showing files to be created."""
        self.info_label = QLabel("")
        self.info_label.setStyleSheet(get_muted_text_style(italic=True))
        layout.addWidget(self.info_label)

    def _update_info_label(self) -> None:
        """Update the label showing which files will be created."""
        if not self.info_label:
            return

        output_name = self.output_name_edit.text() if self.output_name_edit else ""
        if not output_name:
            self.info_label.setText("Enter an output name to see files that will be created")
            self.info_label.setStyleSheet(f"color: {COLORS['warning']}; font-style: italic;")
            return

        files = [f"{output_name}.png"]
        if self.palette_check and self.palette_check.isChecked():
            files.append(f"{output_name}.pal.json (x8)")
        if self.metadata_check and self.metadata_check.isChecked():
            files.append(f"{output_name}.metadata.json")

        self.info_label.setText(f"Files to create: {', '.join(files)}")
        self.info_label.setStyleSheet(get_muted_text_style(italic=True))

    def _browse_output(self) -> None:
        """Open file browser for output location."""
        current_name = self.output_name_edit.text() if self.output_name_edit else ""
        suggested_path = str(Path(self._default_directory) / f"{current_name}.png")

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Sprites As",
            suggested_path,
            "PNG Files (*.png)",
        )

        if filename and self.output_name_edit:
            # Update output name without extension
            base_name = Path(filename).stem
            self.output_name_edit.setText(base_name)
            # Update default directory for next browse
            self._default_directory = str(Path(filename).parent)

    def get_settings(self) -> OutputSettings:
        """Get the configured output settings.

        Returns:
            OutputSettings namedtuple with output_name, export_palette_files, include_metadata
        """
        return OutputSettings(
            output_name=self.output_name_edit.text() if self.output_name_edit else "",
            export_palette_files=self.palette_check.isChecked() if self.palette_check else True,
            include_metadata=self.metadata_check.isChecked() if self.metadata_check else True,
        )

    def get_output_name(self) -> str:
        """Get the configured output name.

        Returns:
            The output name string
        """
        return self.output_name_edit.text() if self.output_name_edit else ""

    @staticmethod
    def get_output_settings(
        parent: QWidget | None,
        suggested_name: str = "",
        is_rom_mode: bool = False,
        default_directory: str = "",
    ) -> OutputSettings | None:
        """Static factory method to show dialog and get settings.

        Args:
            parent: Parent widget
            suggested_name: Pre-filled output name suggestion
            is_rom_mode: If True, palette and metadata options are locked on
            default_directory: Default directory for browse dialog

        Returns:
            OutputSettings if user accepted, None if cancelled
        """
        dialog = OutputSettingsDialog(
            parent=parent,
            suggested_name=suggested_name,
            is_rom_mode=is_rom_mode,
            default_directory=default_directory,
        )
        if dialog.exec():
            return dialog.get_settings()
        return None
