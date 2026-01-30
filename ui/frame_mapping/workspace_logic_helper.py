"""Business logic extracted from FrameMappingWorkspace.

Handles operations spanning multiple panes. Dependencies injected via setters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMessageBox

from ui.frame_mapping.dialogs.replace_link_dialog import (
    confirm_replace_ai_frame_link,
    confirm_replace_link,
)
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from ui.frame_mapping.controllers.frame_mapping_controller import (
        FrameMappingController,
    )
    from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
    from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane
    from ui.frame_mapping.views.mapping_panel import MappingPanel
    from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas
    from ui.frame_mapping.views.workbench_types import AlignmentState
    from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager
    from ui.managers.status_bar_manager import StatusBarManager

logger = get_logger(__name__)


class WorkspaceLogicHelper:
    """Business logic extracted from FrameMappingWorkspace.

    Handles operations spanning multiple panes. Dependencies injected via setters
    to support Qt's UI creation order (UI before services).

    Usage:
        helper = WorkspaceLogicHelper()
        helper.set_controller(controller)
        helper.set_state(state_manager)
        helper.set_panes(ai_pane, captures_pane, mapping_panel, canvas)
        # Optional: helper.set_message_service(service)
    """

    def __init__(self) -> None:
        """Initialize with no dependencies (set via setters)."""
        self._controller: FrameMappingController | None = None
        self._state: WorkspaceStateManager | None = None
        self._ai_frames_pane: AIFramesPane | None = None
        self._captures_pane: CapturesLibraryPane | None = None
        self._mapping_panel: MappingPanel | None = None
        self._alignment_canvas: WorkbenchCanvas | None = None
        self._message_service: StatusBarManager | None = None
        self._parent_widget: QWidget | None = None
        # Flag to prevent feedback loop: canvas change → model update → canvas sync
        # When True, sync_canvas_alignment_from_model() skips the sync since canvas
        # already has the correct values (avoids int truncation drift during slider interaction)
        self._canvas_change_in_progress: bool = False

    # ===== Setters for deferred injection =====

    def set_controller(self, controller: FrameMappingController) -> None:
        """Set the controller for project operations."""
        self._controller = controller

    def set_state(self, state: WorkspaceStateManager) -> None:
        """Set the state manager for UI state."""
        self._state = state

    def set_panes(
        self,
        ai_pane: AIFramesPane,
        captures_pane: CapturesLibraryPane,
        mapping_panel: MappingPanel,
        canvas: WorkbenchCanvas,
    ) -> None:
        """Set all pane references."""
        self._ai_frames_pane = ai_pane
        self._captures_pane = captures_pane
        self._mapping_panel = mapping_panel
        self._alignment_canvas = canvas

    def set_message_service(self, service: StatusBarManager | None) -> None:
        """Set the message service for status updates."""
        self._message_service = service

    def set_parent_widget(self, widget: QWidget) -> None:
        """Set the parent widget for dialogs."""
        self._parent_widget = widget

    # ===== Phase 2a: Selection helpers =====

    def get_selected_ai_frame_id(self) -> str | None:
        """Get the currently selected AI frame ID.

        Returns the state manager value directly. This ensures selection is
        preserved even when filters hide the selected item in the pane.

        Returns:
            AI frame ID (filename) or None if no selection
        """
        if self._state is None:
            return None
        return self._state.selected_ai_frame_id

    def get_selected_game_id(self) -> str | None:
        """Get the currently selected game frame ID.

        Returns the state manager value directly. This ensures selection is
        preserved even when filters hide the selected item in the pane.

        Returns:
            Game frame ID or None if no selection
        """
        if self._state is None:
            return None
        return self._state.selected_game_id

    def update_map_button_state(self) -> None:
        """Update the Map Selected button enabled state."""
        if self._ai_frames_pane is None:
            return
        ai_frame_id = self.get_selected_ai_frame_id()
        game_id = self.get_selected_game_id()
        both_selected = ai_frame_id is not None and game_id is not None
        self._ai_frames_pane.set_map_button_enabled(both_selected)

    # ===== Phase 2b: Refresh helpers =====

    def refresh_mapping_status(self) -> None:
        """Refresh the AI frame mapping status indicators.

        Note: This only updates status indicators. Callers that also need
        to refresh the mapping panel table should call _update_mapping_panel_previews()
        or _mapping_panel.refresh() separately.
        """
        if self._controller is None or self._ai_frames_pane is None:
            return

        project = self._controller.project
        if project is None:
            self._ai_frames_pane.set_mapping_status({})
            return

        # Use ID-keyed status map (stable across reloads/reordering)
        status_map: dict[str, str] = {}
        for ai_frame in project.ai_frames:
            mapping = project.get_mapping_for_ai_frame(ai_frame.id)
            if mapping:
                status_map[ai_frame.id] = mapping.status
            else:
                status_map[ai_frame.id] = "unmapped"

        self._ai_frames_pane.set_mapping_status(status_map)

    def refresh_game_frame_link_status(self) -> None:
        """Refresh the game frame link status indicators."""
        if self._controller is None or self._captures_pane is None:
            return

        project = self._controller.project
        if project is None:
            self._captures_pane.set_link_status({})
            return

        link_status: dict[str, str | None] = {}
        for game_frame in project.game_frames:
            linked_ai_id = project.get_ai_frame_linked_to_game_frame(game_frame.id)
            link_status[game_frame.id] = linked_ai_id

        self._captures_pane.set_link_status(link_status)

    def update_mapping_panel_previews(self) -> None:
        """Update the mapping panel with game frame preview pixmaps."""
        if self._controller is None or self._mapping_panel is None:
            return
        if self._captures_pane is None:
            return

        project = self._controller.project
        if project is None:
            return

        previews: dict[str, QPixmap] = {}
        for game_frame in project.game_frames:
            preview = self._controller.get_game_frame_preview(game_frame.id)
            if preview:
                previews[game_frame.id] = preview

        self._mapping_panel.set_game_frame_previews(previews)
        self._mapping_panel.refresh()

        # Also update captures pane with previews for thumbnails
        self._captures_pane.set_game_frame_previews(previews)

    # ===== Targeted single-item update methods (performance optimization) =====

    def update_single_ai_frame_status(self, ai_frame_id: str) -> None:
        """Update status for one AI frame only (no full refresh).

        This is more efficient than refresh_mapping_status() when only a single
        frame's mapping has changed.

        Args:
            ai_frame_id: The AI frame ID to update
        """
        if self._controller is None or self._ai_frames_pane is None:
            return

        project = self._controller.project
        if project is None:
            return

        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        status = mapping.status if mapping else "unmapped"
        self._ai_frames_pane.update_single_item_status(ai_frame_id, status)

    def update_single_game_frame_link_status(self, game_frame_id: str) -> None:
        """Update link status for one game frame only (no full refresh).

        This is more efficient than refresh_game_frame_link_status() when only
        a single frame's link has changed.

        Args:
            game_frame_id: The game frame ID to update
        """
        if self._controller is None or self._captures_pane is None:
            return

        project = self._controller.project
        if project is None:
            return

        linked_ai_id = project.get_ai_frame_linked_to_game_frame(game_frame_id)
        self._captures_pane.update_single_item_link_status(game_frame_id, linked_ai_id)

    def update_single_mapping_panel_row(self, ai_frame_id: str) -> None:
        """Update one mapping panel row (alignment + status + preview).

        This is more efficient than update_mapping_panel_previews() when only
        a single mapping has changed.

        Args:
            ai_frame_id: The AI frame ID whose row to update
        """
        if self._controller is None or self._mapping_panel is None:
            return

        project = self._controller.project
        if project is None:
            return

        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return

        # Update alignment and flip columns
        self._mapping_panel.update_row_alignment(
            ai_frame_id,
            mapping.offset_x,
            mapping.offset_y,
            mapping.flip_h,
            mapping.flip_v,
        )

        # Update status column
        self._mapping_panel.update_row_status(ai_frame_id, mapping.status)

        # Update game frame preview if applicable
        if mapping.game_frame_id:
            preview = self._controller.get_game_frame_preview(mapping.game_frame_id)
            if preview:
                self._mapping_panel.update_game_frame_preview(mapping.game_frame_id, preview)

    # ===== Phase 2c: Selection handlers =====

    def handle_ai_frame_selected(self, frame_id: str) -> None:
        """Handle AI frame selection in left pane.

        Syncs with drawer and canvas. If mapped, shows alignment.

        Args:
            frame_id: The AI frame ID (filename), or empty string for cleared selection.
        """
        if self._controller is None or self._state is None:
            return
        if self._alignment_canvas is None or self._mapping_panel is None:
            return
        if self._captures_pane is None or self._ai_frames_pane is None:
            return

        project = self._controller.project
        if project is None:
            return

        # Guard against cleared selection
        if not frame_id:
            self._state.selected_ai_frame_id = None
            self.update_map_button_state()
            self._alignment_canvas.set_ai_frame(None)
            self._alignment_canvas.clear_alignment()
            self._mapping_panel.clear_selection()
            self._captures_pane.clear_selection()
            self._state.selected_game_id = None
            self._state.current_canvas_game_id = None
            return

        self._state.selected_ai_frame_id = frame_id
        self.update_map_button_state()

        # Sync drawer selection by ID
        self._mapping_panel.select_row_by_ai_id(frame_id)

        # Load AI frame into canvas
        frame = project.get_ai_frame_by_id(frame_id)
        self._alignment_canvas.set_ai_frame(frame)

        # Check for mapping using ID-based lookup (O(1))
        mapping = project.get_mapping_for_ai_frame(frame_id) if frame else None
        if mapping:
            game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
            preview = self._controller.get_game_frame_preview(mapping.game_frame_id)
            capture_result, used_fallback = self._controller.get_capture_result_for_game_frame(mapping.game_frame_id)
            self._alignment_canvas.set_game_frame(game_frame, preview, capture_result, used_fallback)
            self._alignment_canvas.set_alignment(
                mapping.offset_x,
                mapping.offset_y,
                mapping.flip_h,
                mapping.flip_v,
                mapping.scale,
                mapping.sharpen,
                mapping.resampling,
            )
            # Sync captures selection and track canvas state
            self._captures_pane.select_frame(mapping.game_frame_id)
            self._state.selected_game_id = mapping.game_frame_id
            self._state.current_canvas_game_id = mapping.game_frame_id
            # Clear browsing mode - canvas now shows the mapped capture
            self._alignment_canvas.set_browsing_mode(False)
        else:
            self._alignment_canvas.set_game_frame(None)
            self._alignment_canvas.clear_alignment()
            self._captures_pane.clear_selection()
            self._state.selected_game_id = None
            self._state.current_canvas_game_id = None
            # Clear browsing mode - no mapping exists
            self._alignment_canvas.set_browsing_mode(False)

        self.update_map_button_state()

    def handle_game_frame_selected(self, frame_id: str) -> None:
        """Handle game frame selection in captures library.

        Updates preview in canvas if an AI frame is selected.
        Note: No longer auto-links - linking requires explicit user action.
        """
        if self._controller is None or self._state is None:
            return
        if self._alignment_canvas is None:
            return

        project = self._controller.project
        if project is None:
            return

        # Guard against invalid selections
        if not frame_id:
            self._state.selected_game_id = None
            self._state.current_canvas_game_id = None
            # Phase 3a fix: Clear canvas state
            self._alignment_canvas.set_game_frame(None)
            self._alignment_canvas.clear_alignment()
            self.update_map_button_state()
            return

        self._state.selected_game_id = frame_id
        self.update_map_button_state()

        # Show preview in canvas if AI frame is selected
        if self._state.selected_ai_frame_id is not None:
            game_frame = project.get_game_frame_by_id(frame_id)
            preview = self._controller.get_game_frame_preview(frame_id)
            capture_result, used_fallback = self._controller.get_capture_result_for_game_frame(frame_id)
            self._alignment_canvas.set_game_frame(game_frame, preview, capture_result, used_fallback)
            self._state.current_canvas_game_id = frame_id

            # Check if we're browsing (viewing different capture than mapping)
            mapping = project.get_mapping_for_ai_frame(self._state.selected_ai_frame_id)
            is_browsing = mapping is not None and frame_id != mapping.game_frame_id
            self._alignment_canvas.set_browsing_mode(is_browsing)

    def handle_mapping_selected(self, ai_frame_id: str) -> None:
        """Handle mapping row selection in drawer.

        Syncs with AI frames pane and canvas.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        if self._controller is None or self._state is None:
            return
        if self._alignment_canvas is None or self._ai_frames_pane is None:
            return
        if self._captures_pane is None:
            return

        project = self._controller.project
        if project is None:
            return

        # Get AI frame by ID
        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            return

        # Sync AI frames pane (uses ID-based selection, stable across reordering)
        self._ai_frames_pane.select_frame_by_id(ai_frame_id)
        self._state.selected_ai_frame_id = ai_frame_id

        # Load into canvas
        self._alignment_canvas.set_ai_frame(ai_frame)

        # Load game frame if mapped (use ID-based lookup)
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping:
            game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
            preview = self._controller.get_game_frame_preview(mapping.game_frame_id)
            capture_result, used_fallback = self._controller.get_capture_result_for_game_frame(mapping.game_frame_id)
            self._alignment_canvas.set_game_frame(game_frame, preview, capture_result, used_fallback)
            self._alignment_canvas.set_alignment(
                mapping.offset_x,
                mapping.offset_y,
                mapping.flip_h,
                mapping.flip_v,
                mapping.scale,
                mapping.sharpen,
                mapping.resampling,
            )
            # Sync captures selection
            self._captures_pane.select_frame(mapping.game_frame_id)
            self._state.selected_game_id = mapping.game_frame_id
            self._state.current_canvas_game_id = mapping.game_frame_id
        else:
            self._alignment_canvas.set_game_frame(None)
            self._alignment_canvas.clear_alignment()
            self._captures_pane.clear_selection()
            self._state.selected_game_id = None
            self._state.current_canvas_game_id = None

        self.update_map_button_state()

    # ===== Phase 2d: Linking logic =====

    def handle_map_selected(self) -> None:
        """Handle map button click in AI frames pane."""
        ai_frame_id = self.get_selected_ai_frame_id()
        game_id = self.get_selected_game_id()

        if ai_frame_id is None:
            QMessageBox.information(
                self._parent_widget,
                "Map Frames",
                "Please select an AI frame first.",
            )
            return

        if game_id is None:
            QMessageBox.information(
                self._parent_widget,
                "Map Frames",
                "Please select a game frame first.",
            )
            return

        self.attempt_link(ai_frame_id, game_id)

    def handle_drop_game_frame(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Handle game frame dropped onto drawer row.

        Args:
            ai_frame_id: AI frame ID (filename)
            game_frame_id: Game frame ID
        """
        self.attempt_link(ai_frame_id, game_frame_id)

    def attempt_link(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Attempt to link an AI frame to a game frame.

        Handles existing link confirmation (for both AI and game frames) and auto-advance.
        Preserves alignment if mapping already exists for the same pair.
        After creating a new mapping, automatically aligns with scale optimization.

        Args:
            ai_frame_id: AI frame ID (filename)
            game_frame_id: Game frame ID
        """
        if self._controller is None or self._state is None:
            return
        if self._alignment_canvas is None or self._ai_frames_pane is None:
            return

        project = self._controller.project
        if project is None:
            return

        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        ai_name = ai_frame.path.name if ai_frame else ai_frame_id

        # Check if AI frame is already linked to a different game frame
        existing_game_link = self._controller.get_existing_link_for_ai_frame(ai_frame_id)
        if existing_game_link is not None:
            if existing_game_link == game_frame_id:
                # Same pair - no-op, preserve existing alignment
                if self._message_service:
                    self._message_service.show_message(f"'{ai_name}' is already linked to '{game_frame_id}'", 2000)
                return

            # Different game frame - confirm replacement
            if not confirm_replace_ai_frame_link(
                self._parent_widget,
                ai_name,
                existing_game_link,
                game_frame_id,
            ):
                return

        # Check if game frame is already linked to a different AI frame
        existing_ai_link = self._controller.get_existing_link_for_game_frame(game_frame_id)
        if existing_ai_link is not None and existing_ai_link != ai_frame_id:
            existing_ai = project.get_ai_frame_by_id(existing_ai_link)
            existing_name = existing_ai.path.name if existing_ai else existing_ai_link

            if not confirm_replace_link(
                self._parent_widget,
                game_frame_id,
                existing_name,
                ai_name,
            ):
                return

        # Create the mapping
        self._controller.create_mapping(ai_frame_id, game_frame_id)

        # Load the game frame into the canvas for auto-alignment
        game_frame = project.get_game_frame_by_id(game_frame_id)
        preview = self._controller.get_game_frame_preview(game_frame_id)
        capture_result, used_fallback = self._controller.get_capture_result_for_game_frame(game_frame_id)
        self._alignment_canvas.set_game_frame(game_frame, preview, capture_result, used_fallback)

        # Update state tracking so alignment changes are saved to the correct mapping
        self._state.selected_game_id = game_frame_id
        self._state.current_canvas_game_id = game_frame_id

        # Auto-align with scale optimization (emits alignment_changed signal)
        self._alignment_canvas.auto_align(with_scale=True)

        self.refresh_mapping_status()
        self.refresh_game_frame_link_status()
        self.update_mapping_panel_previews()

        if self._message_service:
            self._message_service.show_message(f"Linked '{ai_name}' to '{game_frame_id}'", 3000)

        # Auto-advance if enabled (P2: unified signal pattern)
        if self._state.auto_advance_enabled and ai_frame:
            next_unmapped_id = self.find_next_unmapped_ai_frame(ai_frame.index)
            if next_unmapped_id is not None:
                # Use ID-based selection (stable across reordering)
                self._ai_frames_pane.select_frame_by_id(next_unmapped_id, emit_signal=True)

    def find_next_unmapped_ai_frame(self, current_index: int) -> str | None:
        """Find the next unmapped AI frame after the given index.

        Args:
            current_index: Current AI frame index

        Returns:
            AI frame ID of the next unmapped frame, or None if all are mapped
        """
        if self._controller is None:
            return None

        project = self._controller.project
        if project is None:
            return None

        ai_frames = project.ai_frames
        total = len(ai_frames)
        if total == 0:
            return None

        for i in range(1, total):
            check_index = (current_index + i) % total
            # Find frame at this index
            for frame in ai_frames:
                if frame.index == check_index:
                    if project.get_mapping_for_ai_frame(frame.id) is None:
                        return frame.id
                    break

        return None

    # ===== Phase 2e: Alignment coordination =====

    def handle_alignment_changed(self, state: AlignmentState) -> bool:
        """Handle alignment change from canvas (auto-save).

        Alignment changes are only applied when the canvas is displaying the same
        game frame as the existing mapping. This prevents accidental edits when
        the user is previewing a different capture.

        Args:
            state: AlignmentState dataclass with all alignment parameters

        Returns:
            True if alignment was applied, False if blocked
        """
        if self._controller is None or self._state is None:
            return False
        if self._alignment_canvas is None:
            return False

        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is None:
            return False

        project = self._controller.project
        if project is None:
            return False

        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return False

        # Block alignment edit if canvas is showing a different game frame than the mapping
        # This prevents accidentally modifying the mapping when previewing other captures
        if self._state.current_canvas_game_id != mapping.game_frame_id:
            logger.debug(
                f"Blocking alignment change: canvas shows {self._state.current_canvas_game_id}, "
                f"mapping points to {mapping.game_frame_id}"
            )
            # Provide user feedback about why the edit was blocked
            if self._message_service:
                self._message_service.show_message(
                    "Alignment not saved - canvas shows a different capture than the mapping"
                )
            return False

        # Get drag start alignment for single undo command (if from drag operation)
        drag_start = self._alignment_canvas.get_drag_start_alignment()
        self._alignment_canvas.clear_drag_start_alignment()  # Consume it

        # Update alignment in controller (includes scale, sharpen, resampling)
        # This emits alignment_updated signal which triggers _on_alignment_updated()
        # which handles updating the mapping panel row
        # Set flag to prevent feedback loop (canvas already has correct float position,
        # don't overwrite with truncated int from model)
        self._canvas_change_in_progress = True
        try:
            self._controller.update_mapping_alignment(
                ai_frame_id,
                state.offset_x,
                state.offset_y,
                state.flip_h,
                state.flip_v,
                state.scale,
                state.sharpen,
                state.resampling,
                drag_start_alignment=drag_start,
            )
        finally:
            self._canvas_change_in_progress = False
        return True

    def sync_canvas_alignment_from_model(self) -> None:
        """Sync the canvas alignment display with the current model state.

        Called after undo/redo to ensure the canvas reflects restored values.
        Queries the current AI frame's mapping and updates the canvas if a mapping exists.

        Note: Skips sync when _canvas_change_in_progress is True to prevent
        feedback loop during slider interaction (canvas has float precision,
        model has int-truncated values).
        """
        # Skip sync if change originated from canvas - canvas already has correct
        # float-precision position, syncing would overwrite with truncated int
        if self._canvas_change_in_progress:
            return
        if self._controller is None or self._state is None:
            return
        if self._alignment_canvas is None:
            return

        ai_frame_id = self.get_selected_ai_frame_id()
        if ai_frame_id is None:
            return

        project = self._controller.project
        if project is None:
            return

        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is not None:
            # Update canvas with restored alignment values
            self._alignment_canvas.set_alignment(
                mapping.offset_x,
                mapping.offset_y,
                mapping.flip_h,
                mapping.flip_v,
                mapping.scale,
                mapping.sharpen,
                mapping.resampling,
                has_mapping=True,
            )
            # Ensure canvas is showing the mapped game frame
            if self._state.current_canvas_game_id != mapping.game_frame_id:
                game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
                if game_frame:
                    preview = self._controller.get_game_frame_preview(mapping.game_frame_id)
                    capture_result, used_fallback = self._controller.get_capture_result_for_game_frame(
                        mapping.game_frame_id
                    )
                    self._alignment_canvas.set_game_frame(game_frame, preview, capture_result, used_fallback)
                    self._state.current_canvas_game_id = mapping.game_frame_id

            # Always sync selection state and UI when mapping exists (undo/redo)
            self._state.selected_game_id = mapping.game_frame_id
            if self._captures_pane:
                self._captures_pane.select_frame(mapping.game_frame_id)
        else:
            # No mapping - clear alignment
            self._alignment_canvas.clear_alignment()
