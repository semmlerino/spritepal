"""Sidebar widget for the Manual Offset Browser.

Contains History, Scan Results, and Bookmarks panels in a collapsible layout.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.spacing_constants import SPACING_SMALL
from ui.styles.theme import COLORS

if TYPE_CHECKING:
    from ui.dialogs.services.bookmark_manager import BookmarkManager

logger = logging.getLogger(__name__)


class OffsetBrowserSidebar(QWidget):
    """Sidebar for the Manual Offset Browser with History, Scan Results, and Bookmarks.

    Signals:
        history_offset_selected: Emitted when a history item is clicked.
            Args: offset (int)
        history_offset_applied: Emitted when a history item is double-clicked.
            Args: offset (int)
        scan_result_selected: Emitted when a scan result is clicked.
            Args: offset (int)
        scan_result_applied: Emitted when a scan result is double-clicked.
            Args: offset (int)
        bookmark_selected: Emitted when a bookmark is clicked.
            Args: offset (int)
    """

    history_offset_selected = Signal(int)
    history_offset_applied = Signal(int)
    scan_result_selected = Signal(int)
    scan_result_applied = Signal(int)
    bookmark_selected = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        bookmark_manager: BookmarkManager | None = None,
    ) -> None:
        """Initialize the sidebar.

        Args:
            parent: Parent widget.
            bookmark_manager: Optional bookmark manager for bookmark display.
        """
        super().__init__(parent)
        self._bookmark_manager = bookmark_manager

        # History tracking
        self._history_offsets: list[int] = []
        self._max_history_items = 50

        # Scan results
        self._scan_results: list[dict[str, int | float]] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the sidebar UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_SMALL)
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)

        # History panel - starts collapsed, expands on first navigation
        self._history_panel = CollapsibleGroupBox("History", collapsed=True)
        self._history_list = QListWidget()
        self._history_list.setMaximumHeight(150)
        self._history_list.itemClicked.connect(self._on_history_item_clicked)
        self._history_list.itemDoubleClicked.connect(self._on_history_item_double_clicked)
        self._history_panel.add_widget(self._history_list)

        # History controls
        history_controls = QHBoxLayout()
        clear_history_btn = QPushButton("Clear")
        clear_history_btn.setFixedHeight(24)
        clear_history_btn.clicked.connect(self.clear_history)
        history_controls.addWidget(clear_history_btn)
        history_controls.addStretch()
        self._history_panel.add_layout(history_controls)

        layout.addWidget(self._history_panel)

        # Scan Results panel - hidden until scan completes
        self._scan_panel = CollapsibleGroupBox("Scan Results", collapsed=True)
        self._scan_label = QLabel("No scan performed")
        self._scan_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        self._scan_panel.add_widget(self._scan_label)

        self._scan_list = QListWidget()
        self._scan_list.setMaximumHeight(200)
        self._scan_list.itemClicked.connect(self._on_scan_item_clicked)
        self._scan_list.itemDoubleClicked.connect(self._on_scan_item_double_clicked)
        self._scan_list.hide()
        self._scan_panel.add_widget(self._scan_list)

        # Scan controls
        scan_controls = QHBoxLayout()
        self._clear_scan_btn = QPushButton("Clear")
        self._clear_scan_btn.setFixedHeight(24)
        self._clear_scan_btn.clicked.connect(self.clear_scan_results)
        self._clear_scan_btn.setEnabled(False)
        scan_controls.addWidget(self._clear_scan_btn)
        scan_controls.addStretch()
        self._scan_panel.add_layout(scan_controls)

        layout.addWidget(self._scan_panel)

        # Bookmarks panel - visible if bookmarks exist
        self._bookmarks_panel = CollapsibleGroupBox("Bookmarks", collapsed=True)
        self._bookmarks_list = QListWidget()
        self._bookmarks_list.setMaximumHeight(150)
        self._bookmarks_list.itemClicked.connect(self._on_bookmark_item_clicked)
        self._bookmarks_panel.add_widget(self._bookmarks_list)

        # Bookmark controls
        bookmark_controls = QHBoxLayout()
        self._add_bookmark_btn = QPushButton("Add Current")
        self._add_bookmark_btn.setFixedHeight(24)
        self._add_bookmark_btn.clicked.connect(self._on_add_bookmark_clicked)
        bookmark_controls.addWidget(self._add_bookmark_btn)
        bookmark_controls.addStretch()
        self._bookmarks_panel.add_layout(bookmark_controls)

        layout.addWidget(self._bookmarks_panel)

        # Stretch at bottom to push panels up
        layout.addStretch()

        # Set minimum width for sidebar
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    # ============= History Management =============

    def add_to_history(self, offset: int) -> None:
        """Add an offset to the history.

        Args:
            offset: The offset to add.
        """
        # Don't add duplicates of the most recent item
        if self._history_offsets and self._history_offsets[0] == offset:
            return

        # Add to front of list
        self._history_offsets.insert(0, offset)

        # Enforce max size
        if len(self._history_offsets) > self._max_history_items:
            self._history_offsets = self._history_offsets[: self._max_history_items]

        # Update UI
        self._update_history_list()

        # Expand history panel on first entry
        if len(self._history_offsets) == 1:
            self._history_panel.set_collapsed(False)

    def _update_history_list(self) -> None:
        """Update the history list widget."""
        self._history_list.clear()
        for offset in self._history_offsets:
            item = QListWidgetItem(f"0x{offset:06X}")
            item.setData(256, offset)  # Qt.ItemDataRole.UserRole = 256
            self._history_list.addItem(item)

    def clear_history(self) -> None:
        """Clear all history items."""
        self._history_offsets.clear()
        self._history_list.clear()

    def get_history_offsets(self) -> list[int]:
        """Get the list of history offsets.

        Returns:
            List of offsets in history (most recent first).
        """
        return list(self._history_offsets)

    def _on_history_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle history item single click."""
        offset = item.data(256)
        if offset is not None:
            self.history_offset_selected.emit(offset)

    def _on_history_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle history item double click."""
        offset = item.data(256)
        if offset is not None:
            self.history_offset_applied.emit(offset)

    # ============= Scan Results Management =============

    def set_scan_results(self, results: list[dict[str, int | float]]) -> None:
        """Set scan results.

        Args:
            results: List of dicts with 'offset' and optionally 'quality' keys.
        """
        self._scan_results = results
        self._update_scan_list()

        # Show/expand panel if results exist
        if results:
            self._scan_label.hide()
            self._scan_list.show()
            self._scan_panel.set_collapsed(False)
            self._clear_scan_btn.setEnabled(True)
        else:
            self._scan_label.setText("No sprites found")
            self._scan_label.show()
            self._scan_list.hide()
            self._clear_scan_btn.setEnabled(False)

    def _update_scan_list(self) -> None:
        """Update the scan results list widget."""
        self._scan_list.clear()
        self._scan_label.setText(f"{len(self._scan_results)} sprites found")

        for result in self._scan_results:
            offset = result.get("offset", 0)
            quality = result.get("quality", 0.0)
            if isinstance(offset, int):
                text = f"0x{offset:06X}"
                if isinstance(quality, float) and quality > 0:
                    text += f" ({quality:.1%})"
                item = QListWidgetItem(text)
                item.setData(256, offset)
                self._scan_list.addItem(item)

    def clear_scan_results(self) -> None:
        """Clear all scan results."""
        self._scan_results.clear()
        self._scan_list.clear()
        self._scan_label.setText("No scan performed")
        self._scan_label.show()
        self._scan_list.hide()
        self._clear_scan_btn.setEnabled(False)

    def _on_scan_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle scan result single click."""
        offset = item.data(256)
        if offset is not None:
            self.scan_result_selected.emit(offset)

    def _on_scan_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle scan result double click."""
        offset = item.data(256)
        if offset is not None:
            self.scan_result_applied.emit(offset)

    # ============= Bookmarks Management =============

    def refresh_bookmarks(self) -> None:
        """Refresh the bookmarks list from the bookmark manager."""
        self._bookmarks_list.clear()

        if self._bookmark_manager is None:
            return

        bookmarks = self._bookmark_manager.bookmarks
        for offset, name in bookmarks:
            display_name = name if name else f"0x{offset:06X}"
            item = QListWidgetItem(f"★ {display_name}")
            item.setData(256, offset)
            self._bookmarks_list.addItem(item)

        # Show/hide panel based on bookmark count
        if bookmarks:
            self._bookmarks_panel.set_collapsed(False)

    def _on_bookmark_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle bookmark item click."""
        offset = item.data(256)
        if offset is not None:
            self.bookmark_selected.emit(offset)

    def _on_add_bookmark_clicked(self) -> None:
        """Handle add bookmark button click.

        This should be connected to the parent dialog's current offset.
        """
        # The parent dialog should handle this via signal connection
        pass

    def set_bookmark_manager(self, manager: BookmarkManager) -> None:
        """Set the bookmark manager.

        Args:
            manager: The bookmark manager to use.
        """
        self._bookmark_manager = manager
        self.refresh_bookmarks()
