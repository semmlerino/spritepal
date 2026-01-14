"""
Tests for BookmarkManager.

Tests verify:
1. Bookmark creation and storage
2. Menu creation and updates
3. Signal emission for navigation
4. Cleanup behavior
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QWidget

pytestmark = [
    pytest.mark.integration,
    pytest.mark.headless,
    pytest.mark.no_manager_setup,
    pytest.mark.allows_registry_state(reason="BookmarkManager tests are stateless"),
]


class TestBookmarkManager:
    """Tests for BookmarkManager class."""

    @pytest.fixture
    def parent_widget(self, qtbot) -> QWidget:
        """Create a parent widget for the bookmark manager."""
        widget = QWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def bookmark_manager(self, parent_widget):
        """Create a BookmarkManager instance."""
        from ui.dialogs.services.bookmark_manager import BookmarkManager

        manager = BookmarkManager(parent_widget, parent_widget)
        return manager

    def test_initial_state(self, bookmark_manager) -> None:
        """Bookmark manager starts with empty bookmarks list."""
        assert bookmark_manager.bookmarks == []

    def test_create_menu_returns_menu(self, bookmark_manager) -> None:
        """create_menu() returns a QMenu instance."""
        from PySide6.QtWidgets import QMenu

        menu = bookmark_manager.create_menu()
        assert isinstance(menu, QMenu)

    def test_add_bookmark_emits_status(self, bookmark_manager, qtbot) -> None:
        """add_bookmark() emits status_message on success."""
        # Mock the QInputDialog to return a name
        with patch("ui.dialogs.services.bookmark_manager.QInputDialog.getText") as mock_dialog:
            mock_dialog.return_value = ("Test Bookmark", True)

            with qtbot.waitSignal(bookmark_manager.status_message, timeout=1000):
                bookmark_manager.add_bookmark(0x1000)

        assert len(bookmark_manager.bookmarks) == 1
        assert bookmark_manager.bookmarks[0] == (0x1000, "Test Bookmark")

    def test_add_bookmark_cancelled(self, bookmark_manager) -> None:
        """add_bookmark() does nothing when dialog is cancelled."""
        with patch("ui.dialogs.services.bookmark_manager.QInputDialog.getText") as mock_dialog:
            mock_dialog.return_value = ("", False)

            bookmark_manager.add_bookmark(0x1000)

        assert len(bookmark_manager.bookmarks) == 0

    def test_duplicate_bookmark_rejected(self, bookmark_manager, qtbot) -> None:
        """add_bookmark() rejects duplicate offsets."""
        with patch("ui.dialogs.services.bookmark_manager.QInputDialog.getText") as mock_dialog:
            mock_dialog.return_value = ("First Bookmark", True)
            bookmark_manager.add_bookmark(0x1000)

        # Try to add the same offset again
        with qtbot.waitSignal(bookmark_manager.status_message, timeout=1000) as blocker:
            bookmark_manager.add_bookmark(0x1000)

        assert len(bookmark_manager.bookmarks) == 1
        assert "already bookmarked" in blocker.args[0].lower()

    def test_go_to_bookmark_emits_signal(self, bookmark_manager, qtbot) -> None:
        """go_to_bookmark() emits bookmark_selected signal."""
        with qtbot.waitSignal(bookmark_manager.bookmark_selected, timeout=1000) as blocker:
            bookmark_manager.go_to_bookmark(0x2000)

        assert blocker.args[0] == 0x2000

    def test_clear_bookmarks(self, bookmark_manager, qtbot) -> None:
        """clear_bookmarks() clears all bookmarks and emits status."""
        # Add a bookmark first
        with patch("ui.dialogs.services.bookmark_manager.QInputDialog.getText") as mock_dialog:
            mock_dialog.return_value = ("Test", True)
            bookmark_manager.add_bookmark(0x1000)

        assert len(bookmark_manager.bookmarks) == 1

        # Clear bookmarks
        with qtbot.waitSignal(bookmark_manager.status_message, timeout=1000) as blocker:
            bookmark_manager.clear_bookmarks()

        assert len(bookmark_manager.bookmarks) == 0
        assert "cleared" in blocker.args[0].lower()

    def test_menu_updates_on_add(self, bookmark_manager, qtbot) -> None:
        """Menu is updated when bookmarks are added."""
        menu = bookmark_manager.create_menu()

        # Initially shows "No bookmarks"
        assert menu.actions()[0].text() == "No bookmarks"
        assert not menu.actions()[0].isEnabled()

        # Add a bookmark
        with patch("ui.dialogs.services.bookmark_manager.QInputDialog.getText") as mock_dialog:
            mock_dialog.return_value = ("My Sprite", True)
            bookmark_manager.add_bookmark(0x3000)

        # Menu should now show the bookmark
        # Note: The menu is the same object, updated in-place
        assert len(menu.actions()) >= 2  # bookmark + separator + clear
        assert "My Sprite" in menu.actions()[0].text()

    def test_cleanup(self, bookmark_manager) -> None:
        """cleanup() clears state properly."""
        with patch("ui.dialogs.services.bookmark_manager.QInputDialog.getText") as mock_dialog:
            mock_dialog.return_value = ("Test", True)
            bookmark_manager.add_bookmark(0x1000)

        bookmark_manager.cleanup()

        assert len(bookmark_manager.bookmarks) == 0

    def test_multiple_bookmarks(self, bookmark_manager) -> None:
        """Multiple bookmarks can be added and stored."""
        with patch("ui.dialogs.services.bookmark_manager.QInputDialog.getText") as mock_dialog:
            mock_dialog.return_value = ("First", True)
            bookmark_manager.add_bookmark(0x1000)

            mock_dialog.return_value = ("Second", True)
            bookmark_manager.add_bookmark(0x2000)

            mock_dialog.return_value = ("Third", True)
            bookmark_manager.add_bookmark(0x3000)

        assert len(bookmark_manager.bookmarks) == 3
        assert bookmark_manager.bookmarks[0] == (0x1000, "First")
        assert bookmark_manager.bookmarks[1] == (0x2000, "Second")
        assert bookmark_manager.bookmarks[2] == (0x3000, "Third")
