"""Dialog coordination for Frame Mapping workspace.

Manages dialog interactions for capture imports and user confirmations.
Extracts dialog orchestration logic from FrameMappingWorkspace to reduce complexity.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from ui.frame_mapping.dialogs.replace_link_dialog import (
    confirm_replace_ai_frame_link,
    confirm_replace_link,
)
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
        dialog_completed: Emitted when a dialog completes (dialog_type, result)
        capture_import_completed: Emitted when capture import succeeds (game_frame_id, sprite_config)
        queue_processing_finished: Emitted when batch import queue completes (import_count)
    """

    dialog_completed = Signal(str, object)  # dialog_type, result
    capture_import_completed = Signal(str, object)  # game_frame_id, SpriteConfig
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
                self.dialog_completed.emit("sprite_selection", selected_entries)
                return selected_entries

        self.dialog_completed.emit("sprite_selection", None)
        return None

    def confirm_injection(self, parent: QWidget, frame_count: int) -> bool:
        """Show confirmation dialog for injection operation.

        Args:
            parent: Parent widget for the dialog
            frame_count: Number of frames to inject

        Returns:
            True if user confirmed, False if cancelled
        """
        reply = QMessageBox.question(
            parent,
            "Confirm Injection",
            f"Inject {frame_count} frame(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        confirmed = reply == QMessageBox.StandardButton.Yes
        self.dialog_completed.emit("injection_confirm", confirmed)
        return confirmed

    def confirm_replace_link(
        self,
        parent: QWidget,
        game_frame_id: str,
        old_ai_frame_name: str,
        new_ai_frame_name: str,
    ) -> bool:
        """Show confirmation dialog for replacing a game frame link.

        Args:
            parent: Parent widget for the dialog
            game_frame_id: ID of the game frame being relinked
            old_ai_frame_name: Name of currently linked AI frame
            new_ai_frame_name: Name of new AI frame to link

        Returns:
            True if user confirmed replacement, False if cancelled
        """
        confirmed = confirm_replace_link(parent, game_frame_id, old_ai_frame_name, new_ai_frame_name)
        self.dialog_completed.emit("replace_link", confirmed)
        return confirmed

    def confirm_replace_ai_frame_link(
        self,
        parent: QWidget,
        ai_frame_name: str,
        old_game_frame_id: str,
        new_game_frame_id: str,
    ) -> bool:
        """Show confirmation dialog for replacing an AI frame link.

        Args:
            parent: Parent widget for the dialog
            ai_frame_name: Name of AI frame being remapped
            old_game_frame_id: ID of currently linked game frame
            new_game_frame_id: ID of new game frame to link

        Returns:
            True if user confirmed replacement, False if cancelled
        """
        confirmed = confirm_replace_ai_frame_link(parent, ai_frame_name, old_game_frame_id, new_game_frame_id)
        self.dialog_completed.emit("replace_ai_frame_link", confirmed)
        return confirmed

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
                self.capture_import_completed.emit(frame.id, None)  # Emit with frame ID

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
