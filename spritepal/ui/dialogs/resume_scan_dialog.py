"""
Dialog for resuming interrupted sprite scans
Provides options to resume from cached progress or start fresh
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.components.base import BaseDialog
from ui.styles import get_bold_text_style, get_muted_text_style


class ResumeScanDialog(BaseDialog):
    """Dialog that allows users to resume interrupted sprite scans"""

    # Dialog result codes
    RESUME: int = 1
    START_FRESH: int = 2
    CANCEL: int = 0

    def __init__(self, scan_info: dict[str, Any], parent: QWidget | None = None) -> None:
        """
        Initialize resume scan dialog.

        Args:
            scan_info: Dictionary containing:
                - found_sprites: List of found sprites
                - current_offset: Last scanned offset
                - scan_range: Dict with start, end, step
                - completed: Whether scan was completed
                - total_found: Number of sprites found
            parent: Parent widget
        """
        super().__init__(
            parent=parent,
            title="Resume Sprite Scan?",
            modal=True,
            min_size=(450, None),
            with_status_bar=False,
            with_button_box=False,  # Custom buttons
        )

        self.scan_info: dict[str, Any] = scan_info
        self.user_choice: int = self.CANCEL

        # Create main content layout
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # Header with icon
        header_layout = QHBoxLayout()

        # Info icon
        icon_label = QLabel()
        style = self.style()
        if style:
            pixmap = style.standardPixmap(
                style.StandardPixmap.SP_MessageBoxInformation
            )
            if pixmap:
                icon_label.setPixmap(
                    pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio)
                )
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label)

        # Message layout
        message_layout = QVBoxLayout()

        # Main message
        main_message = QLabel("Found incomplete sprite scan for this ROM")
        main_message.setWordWrap(True)
        main_message.setStyleSheet(get_bold_text_style("default"))
        message_layout.addWidget(main_message)

        # Progress details
        progress_info = self._format_progress_info()
        progress_label = QLabel(progress_info)
        progress_label.setWordWrap(True)
        progress_label.setStyleSheet(get_muted_text_style(color_level="dark"))
        message_layout.addWidget(progress_label)

        # Options
        options_label = QLabel(
            "Would you like to resume from where you left off, or start a fresh scan?"
        )
        options_label.setWordWrap(True)
        message_layout.addWidget(options_label)

        header_layout.addLayout(message_layout, 1)
        layout.addLayout(header_layout)

        # Set the content layout
        self.set_content_layout(layout)

        # Custom button box with three options
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Resume button (primary action)
        self.resume_button: QPushButton = QPushButton("Resume Scan")
        self.resume_button.setDefault(True)
        _ = self.resume_button.clicked.connect(self._on_resume)
        button_layout.addWidget(self.resume_button)

        # Start fresh button
        self.fresh_button: QPushButton = QPushButton("Start Fresh")
        _ = self.fresh_button.clicked.connect(self._on_start_fresh)
        button_layout.addWidget(self.fresh_button)

        # Cancel button
        self.cancel_button: QPushButton = QPushButton("Cancel")
        _ = self.cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_button)

        self.main_layout.addLayout(button_layout)

    def _format_progress_info(self) -> str:
        """Format scan progress information for display"""
        scan_range: dict[str, Any] = self.scan_info.get("scan_range", {})
        start: int = scan_range.get("start", 0)
        end: int = scan_range.get("end", 0)
        current: int = self.scan_info.get("current_offset", start)
        found: int = self.scan_info.get("total_found", 0)

        # Calculate percentage
        if end > start:
            progress: float = ((current - start) / (end - start)) * 100
        else:
            progress = 0.0

        # Format info
        info_parts = [
            f"Progress: {progress:.1f}% complete",
            f"Sprites found: {found}",
            f"Last position: 0x{current:06X}",
            f"Scan range: 0x{start:06X} - 0x{end:06X}",
        ]

        return "\n".join(info_parts)

    def _on_resume(self) -> None:
        """Handle resume button click"""
        self.user_choice = self.RESUME
        self.accept()

    def _on_start_fresh(self) -> None:
        """Handle start fresh button click"""
        self.user_choice = self.START_FRESH
        self.accept()

    def _on_cancel(self) -> None:
        """Handle cancel button click"""
        self.user_choice = self.CANCEL
        self.reject()

    def get_user_choice(self) -> int:
        """Get the user's choice after dialog closes"""
        return self.user_choice

    @staticmethod
    def show_resume_dialog(scan_info: dict[str, Any], parent: QWidget | None = None) -> int:
        """
        Convenience method to show resume dialog and get user choice.

        Args:
            scan_info: Scan progress information
            parent: Parent widget

        Returns:
            User choice: RESUME, START_FRESH, or CANCEL
        """
        dialog = ResumeScanDialog(scan_info, parent)
        _ = dialog.exec()
        return dialog.get_user_choice()
