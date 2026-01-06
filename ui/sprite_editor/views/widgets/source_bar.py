#!/usr/bin/env python3
"""
Source Bar widget for the ROM workflow.
Displays ROM path, checksum, offset, and primary action button.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from ui.styles.theme import COLORS

from .offset_line_edit import OffsetLineEdit


class SourceBar(QWidget):
    """
    Persistent bar at the top of the ROM workflow:
    [ROM: game.sfc] [Checksum: OK] [Offset: 0x1234] [Action: Preview]
    """

    # Signals
    action_clicked = Signal()
    offset_changed = Signal(int)
    browse_rom_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {COLORS['panel_background']}; border-bottom: 1px solid {COLORS['border']};"
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # ROM Path
        rom_label = QLabel("ROM:")
        rom_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-weight: bold;")
        layout.addWidget(rom_label)

        self.rom_path_edit = QLineEdit()
        self.rom_path_edit.setReadOnly(True)
        self.rom_path_edit.setPlaceholderText("No ROM selected")
        self.rom_path_edit.setMinimumWidth(200)
        self.rom_path_edit.setStyleSheet(
            f"background-color: {COLORS['input_background']}; border: 1px solid {COLORS['border']}; padding: 2px 5px;"
        )
        layout.addWidget(self.rom_path_edit)

        self.browse_btn = QPushButton("...")
        self.browse_btn.setFixedWidth(30)
        self.browse_btn.setStyleSheet(f"background-color: {COLORS['edit']}; color: white; border-radius: 2px;")
        self.browse_btn.clicked.connect(self.browse_rom_requested.emit)
        layout.addWidget(self.browse_btn)

        # Checksum / Title info
        self.info_label = QLabel("No Info")
        self.info_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        layout.addWidget(self.info_label)

        layout.addStretch(1)

        # Offset
        offset_label = QLabel("Offset:")
        offset_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-weight: bold;")
        layout.addWidget(offset_label)

        self.offset_edit = OffsetLineEdit()
        self.offset_edit.setFixedWidth(120)
        self.offset_edit.setStyleSheet(
            f"background-color: {COLORS['input_background']}; border: 1px solid {COLORS['border']}; padding: 2px 5px; font-family: monospace;"
        )
        self.offset_edit.offset_changed.connect(self.offset_changed.emit)
        layout.addWidget(self.offset_edit)

        # Primary Action
        self.action_btn = QPushButton("Open in Editor")
        self.action_btn.setStyleSheet(
            f"font-weight: bold; background-color: {COLORS['editor']}; color: white; padding: 4px 15px; border-radius: 4px;"
        )
        self.action_btn.setMinimumWidth(140)
        self.action_btn.clicked.connect(self.action_clicked.emit)
        layout.addWidget(self.action_btn)

    def set_rom_path(self, path: str) -> None:
        """Set the ROM path display."""
        self.rom_path_edit.setText(path)
        self.rom_path_edit.setToolTip(path)

    def set_info(self, text: str) -> None:
        """Set the ROM info text (checksum, title)."""
        self.info_label.setText(text)

    def set_offset(self, offset: int) -> None:
        """Set the offset value."""
        self.offset_edit.set_offset(offset)

    def set_action_text(self, text: str) -> None:
        """Set the primary action button text."""
        self.action_btn.setText(text)

        # Update styling based on action
        if "Save" in text or "Confirm" in text:
            color = COLORS["danger_action"]
        elif "Open" in text or "Editor" in text:
            color = COLORS["editor"]
        else:
            color = COLORS["browse"]

        self.action_btn.setStyleSheet(
            f"font-weight: bold; background-color: {color}; color: white; padding: 4px 15px; border-radius: 4px;"
        )
