#!/usr/bin/env python3
"""
Inject tab for the sprite editor.
Handles sprite injection into VRAM dumps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.drop_zone import DropZone

from ..widgets import HexLineEdit

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager


class InjectTab(QWidget):
    """Tab widget for sprite injection functionality."""

    # Signals
    inject_requested = Signal()
    browse_png_requested = Signal()
    browse_vram_requested = Signal()

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
        """Create the injection tab UI."""
        layout = QVBoxLayout(self)

        # PNG file selection (Drop Zone)
        self.png_drop = DropZone("PNG", settings_manager=self.settings_manager, required=True)  # type: ignore[arg-type]
        self.png_drop.file_dropped.connect(lambda p: self.set_png_file(p))
        layout.addWidget(self.png_drop)

        # Validation group
        validation_group = QGroupBox("PNG Validation")
        validation_layout = QVBoxLayout()

        self.validation_text = QLabel("No PNG selected")
        self.validation_text.setWordWrap(True)
        self.validation_text.setStyleSheet("color: #888888;")
        validation_layout.addWidget(self.validation_text)

        validation_group.setLayout(validation_layout)
        layout.addWidget(validation_group)

        # Target settings group
        target_group = QGroupBox("Target Settings")
        target_layout = QGridLayout()

        # VRAM file (Drop Zone)
        self.vram_drop = DropZone("VRAM", settings_manager=self.settings_manager, required=True)  # type: ignore[arg-type]
        self.vram_drop.file_dropped.connect(lambda p: self.set_vram_file(p))
        target_layout.addWidget(self.vram_drop, 0, 0, 1, 3)

        # Offset
        self.inject_offset_edit = HexLineEdit("0xC000")
        target_layout.addWidget(QLabel("Offset:"), 1, 0)
        target_layout.addWidget(self.inject_offset_edit, 1, 1)

        # Output file
        self.output_file_edit = QLineEdit("VRAM_edited.dmp")
        target_layout.addWidget(QLabel("Output:"), 2, 0)
        target_layout.addWidget(self.output_file_edit, 2, 1)

        self.output_hint = QLabel("Relative paths saved next to VRAM file")
        self.output_hint.setStyleSheet("color: #888888; font-size: 11px;")
        target_layout.addWidget(self.output_hint, 2, 2)

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
            "png_file": self.png_drop.get_file_path(),
            "vram_file": self.vram_drop.get_file_path(),
            "offset": self.inject_offset_edit.value(),
            "output_file": self.output_file_edit.text(),
        }

    def validate_params(self) -> tuple[bool, str]:
        """Validate injection parameters.

        Returns:
            Tuple of (is_valid, error_message). Error message is empty if valid.
        """
        errors: list[str] = []

        if not self.png_drop.has_file():
            errors.append("PNG file is required")

        if not self.vram_drop.has_file():
            errors.append("VRAM file is required")

        if not self.inject_offset_edit.isValid():
            errors.append("Invalid injection offset")

        if not self.output_file_edit.text().strip():
            errors.append("Output file name is required")

        return (True, "") if not errors else (False, "\n".join(errors))

    def set_png_file(self, file_path: str) -> None:
        """Set the PNG file path and reset validation state."""
        # Reset validation state - will be re-validated by controller
        self.inject_btn.setEnabled(False)
        self.set_validation_text("Validating...", is_valid=False)

        # Block signals to prevent feedback loop (signal → set → emit → signal)
        _blocker = QSignalBlocker(self.png_drop)
        if file_path:
            self.png_drop.set_file(file_path)
        else:
            self.png_drop.clear()
            self.set_validation_text("No PNG selected", is_valid=False)

    def set_vram_file(self, file_path: str) -> None:
        """Set the VRAM file path."""
        # Block signals to prevent feedback loop (signal → set → emit → signal)
        _blocker = QSignalBlocker(self.vram_drop)
        if file_path:
            self.vram_drop.set_file(file_path)
        else:
            self.vram_drop.clear()

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

    def set_controller(self, controller: object) -> None:
        """Set the injection controller and connect signals.

        Args:
            controller: InjectionController instance (typed as object to avoid circular import)
        """
        # Import locally to avoid circular dependency
        from ...controllers.injection_controller import InjectionController

        if isinstance(controller, InjectionController):
            controller.validation_completed.connect(self._on_validation_result)

    def _on_validation_result(self, is_valid: bool, message: str) -> None:
        """Handle validation result from controller.

        Args:
            is_valid: Whether validation passed
            message: Validation message to display
        """
        self.set_validation_text(message, is_valid)
        self.inject_btn.setEnabled(is_valid)
