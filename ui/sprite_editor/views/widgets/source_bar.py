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

from ui.styles import get_muted_text_style, get_section_label_style
from utils.constants import RomMappingType

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
        self.setObjectName("sourceBar")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # ROM Path
        rom_label = QLabel("ROM:")
        rom_label.setStyleSheet(get_section_label_style())
        layout.addWidget(rom_label)

        self.rom_path_edit = QLineEdit()
        self.rom_path_edit.setReadOnly(True)
        self.rom_path_edit.setPlaceholderText("No ROM selected")
        self.rom_path_edit.setMinimumWidth(200)
        layout.addWidget(self.rom_path_edit)

        self.browse_btn = QPushButton("...")
        self.browse_btn.setFixedWidth(30)
        self.browse_btn.clicked.connect(self.browse_rom_requested.emit)
        layout.addWidget(self.browse_btn)

        # Checksum / Title info
        self.info_label = QLabel("No Info")
        self.info_label.setStyleSheet(get_muted_text_style())
        layout.addWidget(self.info_label)

        layout.addStretch(1)

        # Offset
        offset_label = QLabel("Offset:")
        offset_label.setStyleSheet(get_section_label_style())
        layout.addWidget(offset_label)

        self.offset_edit = OffsetLineEdit()
        self.offset_edit.setFixedWidth(120)
        self.offset_edit.offset_changed.connect(self.offset_changed.emit)
        layout.addWidget(self.offset_edit)

        # Primary Action
        self.action_btn = QPushButton("Open in Editor")
        self.action_btn.setProperty("style", "editor")
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

    def set_checksum_valid(self, valid: bool) -> None:
        """Set the checksum validity status with color coding."""
        current_text = self.info_label.text()
        # Strip existing status if present
        if " [" in current_text:
            current_text = current_text.split(" [")[0]

        if valid:
            status = '<span style="color: #4CAF50;">[Checksum: OK]</span>'
        else:
            status = '<span style="color: #F44336;">[Checksum: INVALID]</span>'

        self.info_label.setText(f"{current_text} {status}")

    def set_offset(self, offset: int) -> None:
        """Set the offset value."""
        self.offset_edit.set_offset(offset)

    def set_mapping_type(self, mapping_type: RomMappingType) -> None:
        """Set ROM mapping type for SNES address conversion (LoROM, HiROM, SA-1)."""
        self.offset_edit.set_mapping_type(mapping_type)

    def set_header_offset(self, offset: int) -> None:
        """Set SMC header offset (e.g. 512 bytes) for file-to-ROM offset conversion."""
        self.offset_edit.set_header_offset(offset)

    def set_action_text(self, text: str) -> None:
        """Set the primary action button text."""
        self.action_btn.setText(text)

        # Update styling based on action via dynamic property
        if "Save" in text or "Confirm" in text:
            self.action_btn.setProperty("style", "danger")
        elif "Open" in text or "Editor" in text:
            self.action_btn.setProperty("style", "editor")
        else:
            self.action_btn.setProperty("style", "browse")

        # Refresh style
        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)

    def set_action_enabled(self, enabled: bool) -> None:
        """Enable or disable the action button."""
        self.action_btn.setEnabled(enabled)

    def set_action_loading(self, loading: bool) -> None:
        """Show loading state on action button.

        Args:
            loading: If True, show "Loading..." and disable. If False, re-enable only.
        """
        if loading:
            self.action_btn.setText("Loading...")
            self.action_btn.setEnabled(False)
        # Note: If loading is False, we DON'T automatically re-enable here.
        # The controller should call set_action_enabled() or set_action_text()
        # to restore the proper state based on current validation/ROM state.

    def set_rom_available(self, available: bool, rom_size: int = 0) -> None:
        """Enable or disable offset-related controls based on ROM availability.

        Args:
            available: Whether a ROM is loaded.
            rom_size: Size of the ROM in bytes (for offset validation).
        """
        self.offset_edit.setEnabled(available)
        self.action_btn.setEnabled(available)

        if available:
            self.offset_edit.set_rom_bounds(rom_size)
            self.offset_edit.setPlaceholderText("Offset (0x..., $..., Bank:Addr)")
        else:
            self.offset_edit.set_rom_bounds(0)
            self.offset_edit.setPlaceholderText("Load ROM first")
            self.action_btn.setToolTip("Load a ROM file to enable")
