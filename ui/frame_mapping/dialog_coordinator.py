"""Dialog coordination for Frame Mapping workspace.

Manages dialog interactions for capture imports and user confirmations.
Extracts dialog orchestration logic from FrameMappingWorkspace to reduce complexity.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from ui.frame_mapping.dialogs.sprite_selection_dialog import SpriteSelectionDialog
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.mesen_integration.click_extractor import CaptureResult, OAMEntry
    from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController

logger = get_logger(__name__)


class DialogCoordinator(QObject):
    """Coordinates dialog interactions for Frame Mapping workspace.

    Handles:
    - Sprite selection dialogs for capture imports
    - Confirmation dialogs for injection and link replacement
    - Sequential processing of batch capture imports

    Signals:
        queue_processing_finished: Emitted when batch import queue completes (import_count)
    """

    queue_processing_finished = Signal(int)  # import_count

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the dialog coordinator.

        Args:
            parent: Parent QObject for Qt ownership
        """
        super().__init__(parent)

        # Queue for pending capture imports (for directory imports with sequential dialogs)
        self._pending_captures: list[tuple[CaptureResult, Path]] = []
        self._import_count: int = 0  # Track successful imports for directory import feedback

    # -------------------------------------------------------------------------
    # Dialog Methods
    # -------------------------------------------------------------------------

    def show_sprite_selection(
        self,
        parent: QWidget,
        capture_result: CaptureResult,
        capture_path: Path,
    ) -> list[OAMEntry] | None:
        """Show sprite selection dialog for capture import.

        Args:
            parent: Parent widget for the dialog
            capture_result: Parsed capture result from Mesen 2
            capture_path: Path to the capture file

        Returns:
            List of selected OAM entries if user accepted, None if cancelled
        """
        dialog = SpriteSelectionDialog(capture_result, parent=parent)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_entries = dialog.selected_entries
            if selected_entries:
                return selected_entries

        return None


    # -------------------------------------------------------------------------
    # Queue Management
    # -------------------------------------------------------------------------

    def queue_capture_import(self, capture_result: CaptureResult, capture_path: Path) -> None:
        """Queue a capture for import.

        Used for batch directory imports to process captures sequentially.

        Args:
            capture_result: Parsed capture result from Mesen 2
            capture_path: Path to the capture file
        """
        self._pending_captures.append((capture_result, capture_path))
        logger.debug("Queued capture for import: %s (queue size: %d)", capture_path.name, len(self._pending_captures))

    def process_capture_import_queue(self, parent: QWidget, controller: FrameMappingController) -> None:
        """Process all queued captures sequentially.

        Shows sprite selection dialog for each capture and completes the import
        via the controller. Emits queue_processing_finished when done.

        Args:
            parent: Parent widget for dialogs
            controller: Frame mapping controller to complete imports
        """
        if not self._pending_captures:
            # Queue empty - emit finished signal with count (even if 0)
            self.queue_processing_finished.emit(self._import_count)
            self._import_count = 0
            return

        # Process next capture
        capture_result, capture_path = self._pending_captures[0]

        # Show sprite selection dialog
        selected_entries = self.show_sprite_selection(parent, capture_result, capture_path)

        if selected_entries:
            # Complete the import via controller
            frame = controller.complete_capture_import(capture_path, capture_result, selected_entries)
            if frame is not None:
                self._import_count += 1

        # Remove processed capture and continue to next
        self._pending_captures.pop(0)

        # Recursive call to process next in queue
        self.process_capture_import_queue(parent, controller)

    def clear_queue(self) -> None:
        """Clear the pending capture import queue.

        Resets both the queue and import counter.
        """
        self._pending_captures.clear()
        self._import_count = 0
        logger.debug("Cleared capture import queue")

    def get_queue_size(self) -> int:
        """Get the current size of the capture import queue.

        Returns:
            Number of pending captures in queue
        """
        return len(self._pending_captures)
