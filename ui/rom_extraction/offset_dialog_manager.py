"""
Offset dialog manager for ROM extraction panel.

This module manages the ManualOffsetDialog lifecycle per-manager instance,
providing a clean interface for opening, closing, and tracking the dialog state.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

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
    Manages the ManualOffsetDialog lifecycle per-instance.

    This class provides a clean interface for:
    - Opening and showing the dialog
    - Tracking dialog state
    - Forwarding dialog signals
    - Proper cleanup on close

    Each OffsetDialogManager instance owns its own dialog instance.
    """

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

        # Instance-level dialog management
        self._dialog: UnifiedManualOffsetDialog | None = None
        self._dialog_lock = threading.Lock()

        logger.debug("OffsetDialogManager initialized")

    def _is_dialog_destroyed(self) -> bool:
        """Check if the dialog instance has been destroyed by Qt."""
        if self._dialog is None:
            return True
        try:
            # Try to access a property - raises RuntimeError if deleted
            _ = self._dialog.isVisible()
            return False
        except RuntimeError:
            return True

    def _create_dialog(self) -> UnifiedManualOffsetDialog:
        """Create the dialog instance with injected dependencies."""
        from core.app_context import get_app_context
        from ui.dialogs import UnifiedManualOffsetDialog

        # Get dependencies from AppContext
        context = get_app_context()
        rom_cache = context.rom_cache
        settings_manager = context.application_state_manager
        extraction_manager = context.core_operations_manager
        rom_extractor = extraction_manager.get_rom_extractor()

        dialog = UnifiedManualOffsetDialog(
            parent=self._parent_widget,
            rom_cache=rom_cache,
            settings_manager=settings_manager,
            extraction_manager=extraction_manager,
            rom_extractor=rom_extractor,
        )
        return dialog

    def get_dialog(self) -> UnifiedManualOffsetDialog | None:
        """
        Get the dialog instance, creating if needed.

        Returns:
            The dialog instance, or None if creation failed
        """
        with self._dialog_lock:
            if self._dialog is None or self._is_dialog_destroyed():
                self._dialog = self._create_dialog()
            return self._dialog

    def get_current_dialog(self) -> UnifiedManualOffsetDialog | None:
        """Get the current dialog without creating a new one."""
        with self._dialog_lock:
            if self._is_dialog_destroyed():
                return None
            return self._dialog

    def is_dialog_open(self) -> bool:
        """Check if a dialog instance exists and is not destroyed."""
        with self._dialog_lock:
            return self._dialog is not None and not self._is_dialog_destroyed()

    def reset_dialog(self) -> None:
        """Reset the dialog state, closing any open dialog."""
        with self._dialog_lock:
            if self._dialog is not None:
                try:
                    self._dialog.close()
                except RuntimeError:
                    pass  # Already deleted
            self._dialog = None

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

        dialog = self.get_dialog()
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
            self._dialog = None
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
        self.reset_dialog()
        self._signals_connected = False

    def cleanup(self) -> None:
        """Clean up resources."""
        self.close()
        self._rom_path = None
        self._extractor = None
        logger.debug("OffsetDialogManager cleaned up")
