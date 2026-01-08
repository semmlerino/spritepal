"""
Mesen2 module for ROM extraction panel.

This module manages the LogWatcher lifecycle and connections between
log watcher and UI widgets, removing the need for AppContext access
in UI components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.mesen_integration.log_watcher import CapturedOffset, LogWatcher
    from ui.rom_extraction.widgets.mesen_captures_section import MesenCapturesSection

logger = get_logger(__name__)


class Mesen2Module(QObject):
    """
    Manages Mesen2 log watcher lifecycle and connections.

    Owns the LogWatcher instance and provides a clean interface
    for connecting to widgets. Removes need for AppContext access
    in UI components.

    This module:
    - Manages LogWatcher start/stop lifecycle
    - Forwards signals from LogWatcher to connected widgets
    - Handles persistent clicks loading
    - Provides clean dependency injection for panels

    Signals:
        offset_discovered: Forwarded from LogWatcher when new offset found.
                          Args: (CapturedOffset)
        watch_started: Forwarded from LogWatcher when watching begins.
        watch_stopped: Forwarded from LogWatcher when watching stops.
        error_occurred: Forwarded from LogWatcher on errors.
                       Args: (error_message: str)
    """

    # Signals forwarded from LogWatcher
    offset_discovered = Signal(object)  # CapturedOffset
    watch_started = Signal()
    watch_stopped = Signal()
    error_occurred = Signal(str)

    def __init__(
        self,
        log_watcher: LogWatcher,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the Mesen2 module.

        Args:
            log_watcher: LogWatcher instance to manage.
            parent: Parent QObject for this module.
        """
        super().__init__(parent)
        self._log_watcher = log_watcher
        self._connected_widgets: list[MesenCapturesSection] = []
        self._setup_log_watcher_signals()

        logger.debug("Mesen2Module initialized")

    def _setup_log_watcher_signals(self) -> None:
        """Connect LogWatcher signals to forward to this module's signals."""
        self._log_watcher.offset_discovered.connect(self.offset_discovered.emit)
        self._log_watcher.watch_started.connect(self.watch_started.emit)
        self._log_watcher.watch_stopped.connect(self.watch_stopped.emit)
        self._log_watcher.error_occurred.connect(self.error_occurred.emit)

    @property
    def is_watching(self) -> bool:
        """
        True if currently watching a log file.

        Returns:
            True if log watcher is active, False otherwise.
        """
        return self._log_watcher.is_watching

    def start_watching(self) -> bool:
        """
        Start watching the Mesen2 log file.

        Uses default log path (mesen2_exchange/sprite_rom_finder.log).

        Returns:
            True if watching started successfully, False otherwise.
        """
        logger.debug("Starting Mesen2 log watching")
        return self._log_watcher.start_watching()

    def stop_watching(self) -> None:
        """Stop watching the current log file."""
        logger.debug("Stopping Mesen2 log watching")
        self._log_watcher.stop_watching()

    def load_persistent_clicks(self) -> list[CapturedOffset]:
        """
        Load persistent recent clicks from recent_clicks.json.

        This file is written by sprite_rom_finder.lua and contains
        the last N clicked sprites across Mesen2 sessions.

        Returns:
            List of captured offsets from the persistent file.
        """
        captures = self._log_watcher.load_persistent_clicks()
        logger.debug("Loaded %d persistent clicks", len(captures))
        return captures

    def connect_signals(self, widget: MesenCapturesSection) -> bool:
        """
        Wire up signals between log_watcher and widget (pure wiring, no side effects).

        This method establishes the signal chain:
        - LogWatcher.offset_discovered -> widget.add_capture()
        - LogWatcher.watch_started -> widget.set_watching(True)
        - LogWatcher.watch_stopped -> widget.set_watching(False)

        Call start_and_load() separately to begin watching and load persistent data.

        Args:
            widget: MesenCapturesSection widget to connect.

        Returns:
            True if signals were connected, False if widget was already connected.
        """
        if widget in self._connected_widgets:
            logger.warning("Widget already connected, skipping")
            return False

        # Connect log_watcher signals to widget methods
        self._log_watcher.offset_discovered.connect(widget.add_capture)
        self._log_watcher.watch_started.connect(lambda: widget.set_watching(True))
        self._log_watcher.watch_stopped.connect(lambda: widget.set_watching(False))

        # Track connected widget for cleanup
        self._connected_widgets.append(widget)
        logger.debug("Connected widget to Mesen2Module signals")
        return True

    def start_and_load(self, widget: MesenCapturesSection) -> None:
        """
        Start watching and load persistent clicks into widget (explicit lifecycle).

        This should be called after connect_signals() to start the watcher
        and populate the widget with any persistent data.

        Args:
            widget: MesenCapturesSection widget to populate.
        """
        if self.is_watching:
            widget.set_watching(True)
        else:
            # Start watching and load persistent clicks
            self.start_watching()
            persistent_clicks = self.load_persistent_clicks()
            if persistent_clicks:
                widget.load_persistent(persistent_clicks)
                logger.debug("Loaded %d persistent clicks into widget", len(persistent_clicks))

    def connect_to_widget(self, widget: MesenCapturesSection) -> None:
        """
        Wire up signals AND start watching/load data (convenience method).

        Equivalent to calling connect_signals() followed by start_and_load().
        Kept for backward compatibility. Skips start_and_load if widget was
        already connected.

        Args:
            widget: MesenCapturesSection widget to connect.
        """
        if self.connect_signals(widget):
            self.start_and_load(widget)

    def disconnect_widget(self, widget: MesenCapturesSection) -> None:
        """
        Disconnect widget from log_watcher signals.

        Args:
            widget: MesenCapturesSection widget to disconnect.
        """
        if widget not in self._connected_widgets:
            logger.warning("Widget not connected, skipping disconnect")
            return

        # Disconnect signals
        try:
            self._log_watcher.offset_discovered.disconnect(widget.add_capture)
            self._log_watcher.watch_started.disconnect()
            self._log_watcher.watch_stopped.disconnect()
        except (RuntimeError, TypeError) as e:
            # Signal may already be disconnected or widget destroyed
            logger.debug("Error disconnecting widget signals: %s", e)

        # Remove from tracking
        self._connected_widgets.remove(widget)
        logger.debug("Disconnected widget from Mesen2Module")

    def cleanup(self) -> None:
        """Clean up resources when module is destroyed."""
        logger.debug("Cleaning up Mesen2Module")
        self.stop_watching()
        self._connected_widgets.clear()
