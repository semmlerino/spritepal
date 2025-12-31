"""Bookmark manager for manual offset dialog.

Handles bookmark storage, menu management, and navigation requests.
"""

from __future__ import annotations

import logging
from functools import partial

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QInputDialog, QMenu, QWidget

logger = logging.getLogger(__name__)


class BookmarkManager(QObject):
    """Manages offset bookmarks for the manual offset dialog.

    Responsibilities:
    - Stores bookmark list (offset, name pairs)
    - Creates and updates the bookmarks menu
    - Emits signals for navigation and status updates

    Signals:
        bookmark_selected: Emitted when user selects a bookmark to navigate to.
            Args: offset (int)
        status_message: Emitted when a status message should be displayed.
            Args: message (str)
    """

    bookmark_selected = Signal(int)  # offset
    status_message = Signal(str)

    def __init__(
        self,
        parent_widget: QWidget,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the bookmark manager.

        Args:
            parent_widget: Widget to use as parent for dialogs.
            parent: QObject parent for ownership.
        """
        super().__init__(parent)
        self._parent_widget = parent_widget
        self._bookmarks: list[tuple[int, str]] = []
        self._menu: QMenu | None = None

    @property
    def bookmarks(self) -> list[tuple[int, str]]:
        """Get the current bookmarks list."""
        return self._bookmarks

    def create_menu(self) -> QMenu:
        """Create and return the bookmarks menu.

        The menu is owned by the parent widget and will be updated
        automatically when bookmarks change.

        Returns:
            The bookmarks QMenu instance.
        """
        self._menu = QMenu(self._parent_widget)
        self._update_menu()
        return self._menu

    def add_bookmark(self, offset: int) -> None:
        """Add current offset to bookmarks.

        Prompts user for a bookmark name. Emits status_message with result.

        Args:
            offset: The ROM offset to bookmark.
        """
        # Check if already bookmarked
        for existing_offset, _ in self._bookmarks:
            if existing_offset == offset:
                self.status_message.emit("Offset already bookmarked")
                return

        # Prompt for bookmark name
        name, ok = QInputDialog.getText(
            self._parent_widget,
            "Add Bookmark",
            f"Name for bookmark at 0x{offset:06X}:",
            text=f"Sprite at 0x{offset:06X}",
        )

        if ok and name:
            self._bookmarks.append((offset, name))
            self._update_menu()
            self.status_message.emit(f"Bookmarked: {name}")
            logger.debug("Added bookmark: %s at 0x%06X", name, offset)

    def go_to_bookmark(self, offset: int) -> None:
        """Navigate to a bookmarked offset.

        Emits bookmark_selected signal to trigger navigation.

        Args:
            offset: The offset to navigate to.
        """
        self.bookmark_selected.emit(offset)

    def clear_bookmarks(self) -> None:
        """Clear all bookmarks."""
        if self._bookmarks:
            self._bookmarks.clear()
            logger.debug("All bookmarks cleared")
        self._update_menu()
        self.status_message.emit("Bookmarks cleared")

    def _update_menu(self) -> None:
        """Update the bookmarks menu with current bookmarks."""
        if self._menu is None:
            return

        self._menu.clear()

        if not self._bookmarks:
            action = self._menu.addAction("No bookmarks")
            action.setEnabled(False)
        else:
            for offset, name in self._bookmarks:
                action = self._menu.addAction(f"{name} (0x{offset:06X})")
                # Use functools.partial to avoid lambda closure issues
                action.triggered.connect(partial(self.go_to_bookmark, offset))

            self._menu.addSeparator()
            clear_action = self._menu.addAction("Clear All Bookmarks")
            clear_action.triggered.connect(self.clear_bookmarks)

    def cleanup(self) -> None:
        """Clean up resources.

        Call this before the parent dialog is destroyed.
        """
        if self._bookmarks:
            self._bookmarks.clear()
        self._menu = None
        logger.debug("BookmarkManager cleaned up")
