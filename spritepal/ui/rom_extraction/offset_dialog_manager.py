"""
Offset dialog manager for ROM extraction panel.

This module manages the ManualOffsetDialog singleton lifecycle,
providing a clean interface for opening, closing, and tracking the dialog state.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, override

from PySide6.QtCore import QObject, Signal

from core.thread_safe_singleton import QtThreadSafeSingleton
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from core.protocols.manager_protocols import ExtractionManagerProtocol, ROMExtractorProtocol
    from ui.dialogs import UnifiedManualOffsetDialog

logger = get_logger(__name__)


class _ManualOffsetDialogSingleton(QtThreadSafeSingleton["UnifiedManualOffsetDialog"]):
    """
    Thread-safe application-wide singleton for manual offset dialog.

    Ensures only one dialog instance exists across the entire application.
    This singleton uses proper thread synchronization and Qt thread affinity
    checking to prevent crashes when accessed from worker threads.
    """

    _instance: UnifiedManualOffsetDialog | None = None
    _creator_manager: OffsetDialogManager | None = None
    _destroyed: bool = False
    _lock = threading.Lock()

    @classmethod
    @override
    def _create_instance(
        cls,
        *args: object,
        **kwargs: object,
    ) -> UnifiedManualOffsetDialog:
        """Create the dialog instance.

        Args:
            *args: First argument should be OffsetDialogManager if provided
            **kwargs: Ignored
        """
        from core.di_container import inject
        from core.managers.application_state_manager import ApplicationStateManager
        from core.protocols.manager_protocols import (
            ExtractionManagerProtocol,
            ROMCacheProtocol,
        )
        from ui.dialogs import UnifiedManualOffsetDialog

        manager = args[0] if args and isinstance(args[0], OffsetDialogManager) else None
        parent = manager._parent_widget if manager else None

        # Inject dependencies at singleton boundary
        rom_cache = inject(ROMCacheProtocol)
        settings_manager = inject(ApplicationStateManager)
        extraction_manager = inject(ExtractionManagerProtocol)
        rom_extractor = extraction_manager.get_rom_extractor()

        dialog = UnifiedManualOffsetDialog(
            parent=parent,
            rom_cache=rom_cache,
            settings_manager=settings_manager,
            extraction_manager=extraction_manager,
            rom_extractor=rom_extractor,
        )
        cls._creator_manager = manager
        cls._destroyed = False
        return dialog

    @classmethod
    def get_dialog(
        cls,
        manager: OffsetDialogManager | None = None,
    ) -> UnifiedManualOffsetDialog | None:
        """
        Get the singleton dialog instance.

        Args:
            manager: The OffsetDialogManager requesting the dialog

        Returns:
            The dialog instance, or None if not available
        """
        with cls._lock:
            if cls._instance is None or cls._destroyed:
                cls._instance = cls._create_instance(manager)
                cls._destroyed = False
            return cls._instance

    @classmethod
    def _on_dialog_destroyed(cls) -> None:
        """Handle dialog destruction."""
        with cls._lock:
            cls._destroyed = True
            cls._instance = None
            cls._creator_manager = None
            logger.debug("Manual offset dialog destroyed")

    @classmethod
    @override
    def reset(cls) -> None:
        """Reset the singleton state."""
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.close()
                except RuntimeError:
                    pass  # Already deleted
            cls._instance = None
            cls._destroyed = True
            cls._creator_manager = None

    @classmethod
    def is_dialog_open(cls) -> bool:
        """Check if a dialog instance exists and is not destroyed."""
        with cls._lock:
            return cls._instance is not None and not cls._destroyed

    @classmethod
    def get_current_dialog(cls) -> UnifiedManualOffsetDialog | None:
        """Get the current dialog without creating a new one."""
        with cls._lock:
            if cls._destroyed:
                return None
            return cls._instance


class OffsetDialogManager(QObject):
    """
    Manages the ManualOffsetDialog singleton lifecycle.

    This class provides a clean interface for:
    - Opening and showing the dialog
    - Tracking dialog state
    - Forwarding dialog signals
    - Proper cleanup on close
    """

    # Signals forwarded from dialog
    offset_changed = Signal(int)  # New offset value
    sprite_found = Signal(dict)  # Sprite data at offset
    dialog_closed = Signal()  # Dialog was closed
    dialog_accepted = Signal()  # Dialog was accepted

    def __init__(
        self,
        parent_widget: QWidget | None = None,
        parent: QObject | None = None,
    ) -> None:
        """
        Initialize the offset dialog manager.

        Args:
            parent_widget: Parent widget for the dialog
            parent: Parent QObject for this manager
        """
        super().__init__(parent)
        self._parent_widget = parent_widget
        self._signals_connected = False
        self._rom_path: str | None = None
        self._extractor: ROMExtractorProtocol | None = None

        logger.debug("OffsetDialogManager initialized")

    def open_dialog(
        self,
        rom_path: str,
        extractor: ROMExtractorProtocol,
        rom_size: int,
        extraction_manager: ExtractionManagerProtocol,
        initial_offset: int | None = None,
    ) -> UnifiedManualOffsetDialog | None:
        """
        Open the manual offset dialog.

        Args:
            rom_path: Path to the ROM file
            extractor: ROM extractor instance
            rom_size: Size of the ROM in bytes
            extraction_manager: Extraction manager for sprite extraction
            initial_offset: Optional initial offset to display

        Returns:
            The dialog instance, or None if opening failed
        """
        self._rom_path = rom_path
        self._extractor = extractor

        dialog = _ManualOffsetDialogSingleton.get_dialog(self)
        if dialog is None:
            logger.error("Failed to get dialog instance")
            return None

        # Configure the dialog with ROM data
        dialog.set_rom_data(rom_path, rom_size, extraction_manager)

        if initial_offset is not None:
            dialog.set_offset(initial_offset)

        # Connect signals if not already connected
        self._connect_signals(dialog)

        # Show the dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        logger.debug(f"Opened manual offset dialog for: {rom_path}")
        return dialog

    def _connect_signals(self, dialog: UnifiedManualOffsetDialog) -> None:
        """Connect dialog signals to manager signals."""
        if self._signals_connected:
            return

        try:
            # Forward dialog signals
            dialog.offset_changed.connect(self._on_offset_changed)
            dialog.sprite_found.connect(self._on_sprite_found)
            dialog.finished.connect(self._on_dialog_finished)
            dialog.destroyed.connect(self._on_dialog_destroyed)

            self._signals_connected = True
            logger.debug("Connected dialog signals")
        except Exception as e:
            logger.error(f"Failed to connect dialog signals: {e}")

    def _on_offset_changed(self, offset: int) -> None:
        """Handle offset change from dialog."""
        self.offset_changed.emit(offset)

    def _on_sprite_found(self, sprite_data: dict[str, Any]) -> None:  # pyright: ignore[reportExplicitAny] - Signal payload
        """Handle sprite found from dialog."""
        self.sprite_found.emit(sprite_data)

    def _on_dialog_finished(self, result: int) -> None:
        """Handle dialog finished."""
        from PySide6.QtWidgets import QDialog

        if result == QDialog.DialogCode.Accepted:
            self.dialog_accepted.emit()
        self.dialog_closed.emit()
        self._signals_connected = False

    def _on_dialog_destroyed(self) -> None:
        """Handle dialog destroyed."""
        _ManualOffsetDialogSingleton._on_dialog_destroyed()
        self._signals_connected = False
        self.dialog_closed.emit()

    def is_open(self) -> bool:
        """Check if the dialog is currently open."""
        return _ManualOffsetDialogSingleton.is_dialog_open()

    def get_current_dialog(self) -> UnifiedManualOffsetDialog | None:
        """Get the current dialog instance without creating a new one."""
        return _ManualOffsetDialogSingleton.get_current_dialog()

    def close(self) -> None:
        """Close the dialog if open."""
        dialog = _ManualOffsetDialogSingleton.get_current_dialog()
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                pass  # Already deleted
        _ManualOffsetDialogSingleton.reset()
        self._signals_connected = False

    def cleanup(self) -> None:
        """Clean up resources."""
        self.close()
        self._rom_path = None
        self._extractor = None
        logger.debug("OffsetDialogManager cleaned up")
