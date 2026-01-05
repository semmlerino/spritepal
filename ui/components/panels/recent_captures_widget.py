"""
Recent Captures Widget for Mesen2 sprite offset discovery.

Displays a list of recently discovered ROM offsets from Mesen2's sprite_rom_finder.lua,
allowing users to quickly jump to discovered sprites without manual copy-paste.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_SMALL, SPACING_TINY
from ui.common.widget_helpers import create_styled_label
from ui.styles import get_panel_style
from ui.styles.theme import COLORS

if TYPE_CHECKING:
    from core.mesen_integration.log_watcher import CapturedOffset

logger = logging.getLogger(__name__)


class RecentCapturesWidget(QWidget):
    """
    Widget displaying recently discovered sprite ROM offsets from Mesen2.

    Shows a list of offsets with timestamps. Users can:
    - Single-click to select and preview offset
    - Double-click to jump directly to offset in ROM browser
    - Right-click for context menu (copy, save to library)

    Signals:
        offset_selected: Emitted when user selects an offset.
                        Args: (offset: int)
        offset_activated: Emitted when user double-clicks an offset.
                         Args: (offset: int)
        save_to_library_requested: Emitted when user requests to save offset.
                                   Args: (offset: int)
    """

    offset_selected = Signal(int)
    offset_activated = Signal(int)
    save_to_library_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(get_panel_style())

        self._captures: list[CapturedOffset] = []
        self._max_items: int = 20

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialize the widget UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)
        layout.setSpacing(SPACING_TINY)

        # Header with title and status indicator
        header_layout = QHBoxLayout()
        header_layout.setSpacing(SPACING_TINY)

        title_label = create_styled_label("Mesen2 Captures", style="section", parent=self)
        header_layout.addWidget(title_label)

        self._status_indicator = QLabel(parent=self)
        self._status_indicator.setFixedSize(8, 8)
        self._update_status_indicator(watching=False)
        header_layout.addWidget(self._status_indicator)

        header_layout.addStretch()

        self._clear_btn = QPushButton("Clear", parent=self)
        self._clear_btn.setFixedWidth(50)
        self._clear_btn.setToolTip("Clear all captured offsets")
        header_layout.addWidget(self._clear_btn)

        layout.addLayout(header_layout)

        # List widget for captures
        self._list_widget = QListWidget(parent=self)
        self._list_widget.setAlternatingRowColors(True)
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.setMinimumHeight(100)
        self._list_widget.setMaximumHeight(200)

        # Style the list
        self._list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS['background']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                font-family: monospace;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 4px 8px;
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['accent']};
                color: {COLORS['background']};
            }}
            QListWidget::item:hover:!selected {{
                background-color: {COLORS['panel_background']};
            }}
        """)

        layout.addWidget(self._list_widget)

        # Empty state message
        self._empty_label = QLabel("No captures yet.\nStart Mesen2 with sprite_rom_finder.lua", parent=self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px;")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._update_empty_state()

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self._clear_btn.clicked.connect(self.clear)

    def add_capture(self, capture: CapturedOffset) -> None:
        """
        Add a new captured offset to the list.

        Args:
            capture: The captured offset from LogWatcher.
        """
        # Insert at beginning (most recent first)
        self._captures.insert(0, capture)

        # Create list item
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, capture.offset)

        # Format: "0x3C6EF1  12:34:56"
        time_str = capture.timestamp.strftime("%H:%M:%S")
        frame_str = f" (f{capture.frame})" if capture.frame else ""
        item.setText(f"{capture.offset_hex}  {time_str}{frame_str}")
        item.setToolTip(f"ROM Offset: {capture.offset_hex}\nFrame: {capture.frame or 'N/A'}\n{capture.raw_line}")

        self._list_widget.insertItem(0, item)

        # Trim excess items
        while self._list_widget.count() > self._max_items:
            self._list_widget.takeItem(self._list_widget.count() - 1)
            if len(self._captures) > self._max_items:
                self._captures.pop()

        self._update_empty_state()
        logger.debug("Added capture: %s", capture.offset_hex)

    def set_watching(self, watching: bool) -> None:
        """Update the status indicator to show whether log is being watched."""
        self._update_status_indicator(watching)

    def clear(self) -> None:
        """Clear all captured offsets."""
        self._list_widget.clear()
        self._captures.clear()
        self._update_empty_state()
        logger.debug("Cleared captures list")

    def get_selected_offset(self) -> int | None:
        """Get the currently selected offset, if any."""
        current_item = self._list_widget.currentItem()
        if current_item is not None:  # type: ignore[reportUnnecessaryComparison]
            return current_item.data(Qt.ItemDataRole.UserRole)
        return None

    def _update_status_indicator(self, watching: bool) -> None:
        """Update the status indicator color."""
        color = COLORS["success"] if watching else COLORS["text_secondary"]
        self._status_indicator.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)
        self._status_indicator.setToolTip("Watching log file" if watching else "Not watching")

    def _update_empty_state(self) -> None:
        """Show/hide empty state message based on list contents."""
        has_items = self._list_widget.count() > 0
        self._list_widget.setVisible(has_items)
        self._empty_label.setVisible(not has_items)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle single-click on list item."""
        offset = item.data(Qt.ItemDataRole.UserRole)
        if offset is not None:
            self.offset_selected.emit(offset)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on list item."""
        offset = item.data(Qt.ItemDataRole.UserRole)
        if offset is not None:
            self.offset_activated.emit(offset)

    def _show_context_menu(self, position: QPoint) -> None:
        """Show context menu for list item."""
        item = self._list_widget.itemAt(position)
        if item is None:  # type: ignore[reportUnnecessaryComparison]
            return

        offset = item.data(Qt.ItemDataRole.UserRole)
        if offset is None:
            return

        menu = QMenu(self)

        copy_action = QAction("Copy Offset", self)
        copy_action.triggered.connect(lambda: self._copy_offset(offset))
        menu.addAction(copy_action)

        jump_action = QAction("Jump to Offset", self)
        jump_action.triggered.connect(lambda: self.offset_activated.emit(offset))
        menu.addAction(jump_action)

        menu.addSeparator()

        save_action = QAction("Save to Library...", self)
        save_action.triggered.connect(lambda: self.save_to_library_requested.emit(offset))
        menu.addAction(save_action)

        menu.exec(self._list_widget.mapToGlobal(position))

    def _copy_offset(self, offset: int) -> None:
        """Copy offset to clipboard."""
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:  # type: ignore[reportUnnecessaryComparison]
            clipboard.setText(f"0x{offset:06X}")
            logger.debug("Copied offset to clipboard: 0x%06X", offset)
