"""
Offset dialog manager for ROM extraction panel.

This module manages the ManualOffsetDialog singleton lifecycle,
providing a clean interface for opening, closing, and tracking the dialog state.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, ClassVar

from PySide6.QtCore import QObject, Signal

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from core.managers.core_operations_manager import CoreOperationsManager
    from core.rom_extractor import ROMExtractor
    from ui.dialogs import UnifiedManualOffsetDialog

logger = get_logger(__name__)


class OffsetDialogManager(QObject):
    """
    Manages the ManualOffsetDialog singleton lifecycle.

    This class provides a clean interface for:
    - Opening and showing the dialog
    - Tracking dialog state
    - Forwarding dialog signals
    - Proper cleanup on close

    The dialog instance is managed at the class level to ensure only one
    exists across the entire application.
    """

    # Class-level singleton management
    _dialog_instance: ClassVar[UnifiedManualOffsetDialog | None] = None
    _dialog_lock: ClassVar[threading.Lock] = threading.Lock()
    _creator_manager: ClassVar[OffsetDialogManager | None] = None

    # Signals forwarded from dialog
    offset_changed = Signal(int)  # New offset value
    sprite_found = Signal(object)  # Sprite data dict at offset (use object to avoid PySide6 copy warning)
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
        self._extractor: ROMExtractor | None = None

        logger.debug("OffsetDialogManager initialized")

    @classmethod
    def _is_dialog_destroyed(cls) -> bool:
        """Check if the dialog instance has been destroyed by Qt."""
        if cls._dialog_instance is None:
            return True
        try:
            # Try to access a property - raises RuntimeError if deleted
            _ = cls._dialog_instance.isVisible()
            return False
        except RuntimeError:
            return True

    @classmethod
    def _create_dialog(cls, manager: OffsetDialogManager | None) -> UnifiedManualOffsetDialog:
        """Create the dialog instance with injected dependencies."""
        from core.app_context import get_app_context
        from ui.dialogs import UnifiedManualOffsetDialog

        parent = manager._parent_widget if manager else None

        # Get dependencies from AppContext
        context = get_app_context()
        rom_cache = context.rom_cache
        settings_manager = context.application_state_manager
        extraction_manager = context.core_operations_manager
        rom_extractor = extraction_manager.get_rom_extractor()

        dialog = UnifiedManualOffsetDialog(
            parent=parent,
            rom_cache=rom_cache,
            settings_manager=settings_manager,
            extraction_manager=extraction_manager,
            rom_extractor=rom_extractor,
        )
        cls._creator_manager = manager
        return dialog

    @classmethod
    def get_dialog(cls, manager: OffsetDialogManager | None = None) -> UnifiedManualOffsetDialog | None:
        """
        Get the singleton dialog instance, creating if needed.

        Args:
            manager: The OffsetDialogManager requesting the dialog

        Returns:
            The dialog instance, or None if creation failed
        """
        with cls._dialog_lock:
            if cls._dialog_instance is None or cls._is_dialog_destroyed():
                cls._dialog_instance = cls._create_dialog(manager)
            return cls._dialog_instance

    @classmethod
    def get_current_dialog(cls) -> UnifiedManualOffsetDialog | None:
        """Get the current dialog without creating a new one."""
        with cls._dialog_lock:
            if cls._is_dialog_destroyed():
                return None
            return cls._dialog_instance

    @classmethod
    def is_dialog_open(cls) -> bool:
        """Check if a dialog instance exists and is not destroyed."""
        with cls._dialog_lock:
            return cls._dialog_instance is not None and not cls._is_dialog_destroyed()

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the singleton state, closing any open dialog."""
        with cls._dialog_lock:
            if cls._dialog_instance is not None:
                try:
                    cls._dialog_instance.close()
                except RuntimeError:
                    pass  # Already deleted
            cls._dialog_instance = None
            cls._creator_manager = None

    def open_dialog(
        self,
        rom_path: str,
        extractor: ROMExtractor,
        rom_size: int,
        extraction_manager: CoreOperationsManager,
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

        dialog = self.get_dialog(self)
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

    def _on_sprite_found(self, offset: int, name: str) -> None:
        """Handle sprite found from dialog.

        Converts (offset, name) from dialog to dict for downstream consumers.
        """
        sprite_data: dict[str, object] = {"offset": offset, "name": name}
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
        with self._dialog_lock:
            OffsetDialogManager._dialog_instance = None
            OffsetDialogManager._creator_manager = None
        self._signals_connected = False
        self.dialog_closed.emit()
        logger.debug("Manual offset dialog destroyed")

    def is_open(self) -> bool:
        """Check if the dialog is currently open."""
        return self.is_dialog_open()

    def close(self) -> None:
        """Close the dialog if open."""
        dialog = self.get_current_dialog()
        if dialog is not None:
            try:
                dialog.close()
            except RuntimeError:
                pass  # Already deleted
        self.reset_singleton()
        self._signals_connected = False

    def cleanup(self) -> None:
        """Clean up resources."""
        self.close()
        self._rom_path = None
        self._extractor = None
        logger.debug("OffsetDialogManager cleaned up")
