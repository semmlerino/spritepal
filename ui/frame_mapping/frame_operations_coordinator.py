"""Frame Operations Coordinator for Frame Mapping Workspace.

Coordinates frame lifecycle operations (delete, remove, edit, show details).
Acts as a passive helper that receives method calls from the workspace -
does not connect signals itself.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox, QWidget

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
    from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane
    from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas
    from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager
    from ui.managers.status_bar_manager import StatusBarManager

logger = get_logger(__name__)


class FrameOperationsCoordinator:
    """Coordinates frame lifecycle operations.

    This is a passive helper that:
    - Handles delete/remove confirmations and cleanup
    - Manages canvas/selection state after operations
    - Relays edit requests to sprite editor

    Signal connections remain in the workspace's _connect_signals().
    """

    def __init__(self) -> None:
        """Initialize with no dependencies (set via setters)."""
        self._controller: FrameMappingController | None = None
        self._state: WorkspaceStateManager | None = None
        self._parent_widget: QWidget | None = None
        self._alignment_canvas: WorkbenchCanvas | None = None
        self._captures_pane: CapturesLibraryPane | None = None
        self._message_service: StatusBarManager | None = None
        # Callbacks for workspace-level operations
        self._update_map_button_state: Callable[[], None] | None = None
        self._request_edit_in_sprite_editor: Callable[[Path, list[int]], None] | None = None

    def set_controller(self, controller: FrameMappingController) -> None:
        """Set the frame mapping controller."""
        self._controller = controller

    def set_state(self, state: WorkspaceStateManager) -> None:
        """Set the workspace state manager."""
        self._state = state

    def set_parent_widget(self, widget: QWidget) -> None:
        """Set the parent widget for dialogs."""
        self._parent_widget = widget

    def set_message_service(self, service: StatusBarManager | None) -> None:
        """Set the status bar manager for messages."""
        self._message_service = service

    def set_panes(
        self, alignment_canvas: WorkbenchCanvas, captures_pane: CapturesLibraryPane
    ) -> None:
        """Set the UI panes needed for state updates."""
        self._alignment_canvas = alignment_canvas
        self._captures_pane = captures_pane

    def set_callbacks(
        self,
        update_map_button_state: Callable[[], None],
        request_edit_in_sprite_editor: Callable[[Path, list[int]], None],
    ) -> None:
        """Set callbacks for workspace-level operations."""
        self._update_map_button_state = update_map_button_state
        self._request_edit_in_sprite_editor = request_edit_in_sprite_editor

    def handle_delete_capture(self, frame_id: str) -> None:
        """Handle delete capture request.

        Args:
            frame_id: Game frame ID to delete
        """
        if self._controller is None or self._state is None:
            return
        project = self._controller.project
        if project is None:
            return

        # Check if linked (use ID-based method) - capture before deletion
        linked_ai_id = project.get_ai_frame_linked_to_game_frame(frame_id)
        was_mapped_to_selected = (
            linked_ai_id is not None and linked_ai_id == self._state.selected_ai_frame_id
        )

        if linked_ai_id is not None:
            ai_frame = project.get_ai_frame_by_id(linked_ai_id)
            ai_name = ai_frame.name if ai_frame else linked_ai_id
            reply = QMessageBox.question(
                self._parent_widget,
                "Delete Capture",
                f"This capture is linked to AI frame '{ai_name}'.\nDeleting will also remove the mapping.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Remove the game frame (also removes any associated mapping)
        if self._controller.remove_game_frame(frame_id):
            # Clear selection if deleted frame was selected
            if self._state.selected_game_id == frame_id:
                self._state.selected_game_id = None
                if self._update_map_button_state:
                    self._update_map_button_state()

            # Clear canvas if deleted frame was currently displayed
            # (may be displayed without being selected, e.g., during preview)
            if self._state.current_canvas_game_id == frame_id and self._alignment_canvas:
                self._state.current_canvas_game_id = None
                self._alignment_canvas.set_game_frame(None)
                self._alignment_canvas.clear_alignment()

            # Clear browsing mode if the deleted capture was mapped to the selected AI frame
            # This handles the case where user is browsing a different capture and deletes
            # the mapped capture - the mapping is now gone so there's nothing to browse from
            if was_mapped_to_selected and self._alignment_canvas:
                self._alignment_canvas.set_browsing_mode(False)

            if self._message_service:
                self._message_service.show_message(f"Deleted capture: {frame_id}")

    def handle_remove_ai_frame(self, ai_frame_id: str) -> None:
        """Handle remove AI frame from project request.

        Args:
            ai_frame_id: AI frame ID to remove
        """
        if self._controller is None or self._state is None:
            return
        project = self._controller.project
        if project is None:
            return

        # Get frame info for display and confirmation
        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            return

        frame_name = ai_frame.name

        # Check if frame is mapped - warn user
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is not None:
            reply = QMessageBox.question(
                self._parent_widget,
                "Remove Mapped Frame?",
                f"'{frame_name}' is mapped to a game capture.\n\n"
                "Removing it will also delete the mapping.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Remove the AI frame (also removes mapping)
        if self._controller.remove_ai_frame(ai_frame_id):
            # Clear canvas and selection if deleted frame was selected
            if self._state.selected_ai_frame_id == ai_frame_id:
                self._state.selected_ai_frame_id = None
                self._state.current_canvas_game_id = None
                if self._alignment_canvas:
                    self._alignment_canvas.set_ai_frame(None)
                    self._alignment_canvas.set_game_frame(None)  # Also clear game frame since context is lost
                    self._alignment_canvas.clear_alignment()
                if self._update_map_button_state:
                    self._update_map_button_state()

            if self._message_service:
                self._message_service.show_message(f"Removed: {frame_name}")

    def handle_remove_mapping(self, ai_frame_id: str) -> None:
        """Handle remove mapping request.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        if self._controller is None or self._state is None:
            return

        # remove_mapping() emits mapping_removed signal which triggers _on_mapping_removed()
        # That handler already does: map button state, AI frame status, game frame link status,
        # and mapping panel row clear. We only need the canvas/state cleanup here.
        self._controller.remove_mapping(ai_frame_id)
        if self._alignment_canvas:
            self._alignment_canvas.clear_alignment()
            self._alignment_canvas.set_game_frame(None)
        if self._captures_pane:
            self._captures_pane.clear_selection()
        self._state.selected_game_id = None
        self._state.current_canvas_game_id = None

    def handle_edit_frame(self, ai_frame_id: str) -> None:
        """Handle edit AI frame request.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        if self._controller is None:
            return
        project = self._controller.project
        if project is None:
            return

        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            return

        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        rom_offsets: list[int] = []
        if mapping:
            game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
            if game_frame:
                rom_offsets = game_frame.rom_offsets

        if self._request_edit_in_sprite_editor:
            self._request_edit_in_sprite_editor(ai_frame.path, rom_offsets)

    def handle_edit_game_frame(self, frame_id: str) -> None:
        """Handle edit game frame request from captures library."""
        if self._controller is None:
            return
        project = self._controller.project
        if project is None:
            return

        game_frame = project.get_game_frame_by_id(frame_id)
        if game_frame is None:
            return

        # Find if there's a linked AI frame (use ID-based method)
        linked_ai_id = project.get_ai_frame_linked_to_game_frame(frame_id)
        if linked_ai_id is not None:
            ai_frame = project.get_ai_frame_by_id(linked_ai_id)
            if ai_frame and self._request_edit_in_sprite_editor:
                self._request_edit_in_sprite_editor(ai_frame.path, game_frame.rom_offsets)
                return

        # No linked AI frame - show message
        if self._message_service:
            self._message_service.show_message("No AI frame linked to this capture", 3000)

    def handle_show_capture_details(self, frame_id: str) -> None:
        """Handle show details request for capture."""
        if self._controller is None:
            return
        project = self._controller.project
        if project is None:
            return

        game_frame = project.get_game_frame_by_id(frame_id)
        if game_frame is None:
            return

        # Build details text
        details = [f"ID: {game_frame.id}"]
        if game_frame.capture_path:
            details.append(f"Source: {game_frame.capture_path.name}")
        if game_frame.rom_offsets:
            offset_str = ", ".join(f"0x{o:06X}" for o in game_frame.rom_offsets)
            details.append(f"ROM Offsets: {offset_str}")
        if game_frame.width and game_frame.height:
            details.append(f"Size: {game_frame.width}x{game_frame.height}")

        QMessageBox.information(self._parent_widget, "Capture Details", "\n".join(details))
