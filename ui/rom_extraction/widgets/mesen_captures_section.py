"""Mesen2 captures section widget for ROM extraction panel.

Presentational wrapper for RecentCapturesWidget with clean interface
for parent to wire up log watcher connections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui.common.spacing_constants import SPACING_SMALL
from ui.components.panels.recent_captures_widget import RecentCapturesWidget

if TYPE_CHECKING:
    from core.mesen_integration.log_watcher import CapturedOffset


class MesenCapturesSection(QWidget):
    """Presentational wrapper for Mesen2 captures widget.

    Delegates to RecentCapturesWidget but exposes a clean interface
    for the parent to wire up log watcher connections.

    The parent (ROMExtractionPanel or future Mesen2Module) is responsible for:
    - Getting the log_watcher from AppContext
    - Connecting log_watcher signals to this widget's methods
    - Managing persistent clicks loading on startup

    Signals:
        offset_selected: Emitted when user selects an offset (single-click).
                        Args: (offset: int)
        offset_activated: Emitted when user double-clicks an offset.
                         Args: (offset: int)
        save_to_library_requested: Emitted when user requests to save offset.
                                   Args: (offset: int)
        watching_changed: Emitted when watching state changes (for status bar).
                         Args: (is_watching: bool)
    """

    # Signals forwarded from RecentCapturesWidget
    offset_selected = Signal(int)
    offset_activated = Signal(int)
    save_to_library_requested = Signal(int)
    thumbnail_requested = Signal(int)  # Forwarded: capture needs thumbnail

    # Additional signal for status bar integration
    watching_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Initialize the widget UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING_SMALL)

        # Create the actual captures widget
        self._captures_widget = RecentCapturesWidget(parent=self)
        layout.addWidget(self._captures_widget)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Connect internal signals to forward from RecentCapturesWidget."""
        self._captures_widget.offset_selected.connect(self.offset_selected.emit)
        self._captures_widget.offset_activated.connect(self.offset_activated.emit)
        self._captures_widget.save_to_library_requested.connect(self.save_to_library_requested.emit)
        self._captures_widget.thumbnail_requested.connect(self.thumbnail_requested.emit)

    # Public methods for parent to call

    def add_capture(self, capture: CapturedOffset) -> None:
        """Add a new captured offset to the list.

        Args:
            capture: The captured offset from LogWatcher.
        """
        self._captures_widget.add_capture(capture)

    def load_persistent(self, captures: list[CapturedOffset]) -> None:
        """Load persistent captures from file.

        This is called on startup to restore the last N clicked sprites
        from previous Mesen2 sessions.

        Args:
            captures: List of captured offsets to load.
        """
        self._captures_widget.load_persistent(captures)

    def set_watching(self, is_watching: bool) -> None:
        """Update the watching state indicator.

        Args:
            is_watching: True if log file is being watched, False otherwise.
        """
        self._captures_widget.set_watching(is_watching)
        self.watching_changed.emit(is_watching)

    def get_selected_offset(self) -> int | None:
        """Get the currently selected offset, if any.

        Returns:
            The selected offset as an integer, or None if no selection.
        """
        return self._captures_widget.get_selected_offset()

    def get_capture_count(self) -> int:
        """Get the number of captured offsets.

        Returns:
            The number of captured offsets currently displayed.
        """
        return self._captures_widget.get_capture_count()

    def clear(self) -> None:
        """Clear all captured offsets."""
        self._captures_widget.clear()

    def set_thumbnail(self, offset: int, thumbnail: QPixmap) -> None:
        """Set thumbnail for a capture.

        Args:
            offset: ROM offset to match
            thumbnail: Thumbnail pixmap to display
        """
        self._captures_widget.set_thumbnail(offset, thumbnail)

    def request_all_thumbnails(self) -> None:
        """Request thumbnails for all current captures."""
        self._captures_widget.request_all_thumbnails()
