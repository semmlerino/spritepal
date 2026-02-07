"""Palette Coordinator for Frame Mapping Workspace.

Coordinates palette operations (edit, extract, clear), palette editor windows,
and bidirectional palette highlighting between canvas and palette swatches.
Acts as a passive helper that receives method calls from the workspace.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox, QWidget

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
    from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
    from ui.frame_mapping.views.mapping_panel import MappingPanel
    from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas
    from ui.frame_mapping.windows import AIFramePaletteEditorWindow
    from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager
    from ui.managers.status_bar_manager import StatusBarManager

logger = get_logger(__name__)


class PaletteCoordinator:
    """Coordinates palette operations and editor windows.

    This is a passive helper that:
    - Handles sheet palette dialog operations (edit, extract, clear)
    - Manages palette editor windows (open, save, close)
    - Routes bidirectional palette highlighting
    - Syncs palette changes across UI components (BUG-3 fix pattern)

    Signal connections remain in the workspace's _connect_signals().
    """

    def __init__(self) -> None:
        """Initialize with no dependencies (set via setters)."""
        self._controller: FrameMappingController | None = None
        self._state: WorkspaceStateManager | None = None
        self._ai_frames_pane: AIFramesPane | None = None
        self._mapping_panel: MappingPanel | None = None
        self._alignment_canvas: WorkbenchCanvas | None = None
        self._message_service: StatusBarManager | None = None
        self._parent_widget: QWidget | None = None
        # Track open palette editor windows (frame_id -> editor window)
        self._palette_editors: dict[str, AIFramePaletteEditorWindow] = {}
        # Callbacks for workspace-level operations
        self._on_ai_frame_selected: Callable[[str], None] | None = None

    # -------------------------------------------------------------------------
    # Dependency Injection (Deferred)
    # -------------------------------------------------------------------------

    def set_controller(self, controller: FrameMappingController) -> None:
        """Set the controller for palette operations."""
        self._controller = controller

    def set_state(self, state: WorkspaceStateManager) -> None:
        """Set the state manager for selection state."""
        self._state = state

    def set_panes(
        self,
        ai_frames_pane: AIFramesPane,
        mapping_panel: MappingPanel,
        alignment_canvas: WorkbenchCanvas,
    ) -> None:
        """Set all pane references."""
        self._ai_frames_pane = ai_frames_pane
        self._mapping_panel = mapping_panel
        self._alignment_canvas = alignment_canvas

    def set_message_service(self, service: StatusBarManager | None) -> None:
        """Set the message service for status updates."""
        self._message_service = service

    def set_parent_widget(self, widget: QWidget) -> None:
        """Set the parent widget for dialogs."""
        self._parent_widget = widget

    def set_workspace_callbacks(
        self,
        on_ai_frame_selected: Callable[[str], None],
    ) -> None:
        """Set callbacks for workspace-level operations.

        Args:
            on_ai_frame_selected: Called when AI frame selection should be triggered
        """
        self._on_ai_frame_selected = on_ai_frame_selected

    # -------------------------------------------------------------------------
    # Sheet Palette Dialog Operations
    # -------------------------------------------------------------------------

    def handle_palette_edit_requested(self) -> None:
        """Handle request to edit the sheet palette."""
        if self._controller is None or self._parent_widget is None:
            return

        from ui.frame_mapping.dialogs.sheet_palette_mapping_dialog import SheetPaletteMappingDialog

        # Extract colors from all AI frames
        sheet_colors = self._controller.extract_sheet_colors()
        if not sheet_colors:
            QMessageBox.information(
                self._parent_widget,
                "No AI Frames",
                "No AI frames loaded. Please load AI frames first to extract colors.",
            )
            return

        # Get current palette and available game palettes
        current_palette = self._controller.get_sheet_palette()
        game_palettes = self._controller.get_game_palettes()

        # Find a sample AI frame for preview
        sample_ai_frame_path = self._get_sample_ai_frame_path()

        # Open dialog
        dialog = SheetPaletteMappingDialog(
            sheet_colors=sheet_colors,
            current_palette=current_palette,
            game_palettes=game_palettes,
            parent=self._parent_widget,
            sample_ai_frame_path=sample_ai_frame_path,
        )

        if dialog.exec():
            # Apply the result
            new_palette = dialog.get_result()
            self._controller.set_sheet_palette(new_palette)
            if self._message_service:
                self._message_service.show_message(
                    f"Sheet palette applied ({len(new_palette.color_mappings)} color mappings)"
                )

    def handle_palette_extract_requested(self) -> None:
        """Handle request to extract palette from AI sheet."""
        if self._controller is None or self._parent_widget is None:
            return

        from ui.frame_mapping.dialogs.sheet_palette_mapping_dialog import SheetPaletteMappingDialog

        sheet_colors = self._controller.extract_sheet_colors()
        if not sheet_colors:
            QMessageBox.information(
                self._parent_widget,
                "No AI Frames",
                "No AI frames loaded. Please load AI frames first.",
            )
            return

        # Pre-extract palette for dialog
        extracted_palette = self._controller.generate_sheet_palette_from_colors(sheet_colors)

        # Get game palettes for dialog
        game_palettes = self._controller.get_game_palettes()

        # Find a sample AI frame for preview
        sample_ai_frame_path = self._get_sample_ai_frame_path()

        # Open dialog with pre-populated palette (same as handle_palette_edit_requested)
        dialog = SheetPaletteMappingDialog(
            sheet_colors=sheet_colors,
            current_palette=extracted_palette,  # Pre-populate with extracted
            game_palettes=game_palettes,
            parent=self._parent_widget,
            sample_ai_frame_path=sample_ai_frame_path,
        )

        if dialog.exec():
            new_palette = dialog.get_result()
            self._controller.set_sheet_palette(new_palette)
            if self._message_service:
                self._message_service.show_message(
                    f"Palette applied ({len(new_palette.color_mappings)} color mappings)"
                )

    def handle_palette_clear_requested(self) -> None:
        """Handle request to clear the sheet palette."""
        if self._controller is None or self._parent_widget is None:
            return

        if self._controller.get_sheet_palette() is None:
            return

        reply = QMessageBox.question(
            self._parent_widget,
            "Clear Sheet Palette",
            "Clear the sheet palette?\n\nInjections will use capture palettes instead.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._controller.set_sheet_palette(None)
            if self._message_service:
                self._message_service.show_message("Sheet palette cleared")

    def handle_sheet_palette_changed(self) -> None:
        """Handle sheet palette change from controller.

        BUG-3 FIX: Must explicitly sync all open palette editors because the
        editor's _on_external_palette_changed uses identity check (is not)
        which fails when the same palette object is modified in-place.
        """
        if self._controller is None:
            return

        palette = self._controller.get_sheet_palette()

        if self._ai_frames_pane:
            self._ai_frames_pane.set_sheet_palette(palette)
        # Also update the workbench canvas for pixel inspection
        if self._alignment_canvas:
            self._alignment_canvas.set_sheet_palette(palette)
        # Also update mapping panel to show quantized AI frame thumbnails
        if self._mapping_panel:
            self._mapping_panel.set_sheet_palette(palette)

        # BUG-3 FIX: Explicitly sync ALL open palette editors
        # This handles the case where palette colors changed in-place
        # (same object reference, but different content)
        if palette is not None:
            for editor in self._palette_editors.values():
                # Always update palette reference and refresh UI
                # (regardless of identity check, since colors may have changed)
                editor._palette = palette
                editor._palette_panel.set_palette(palette)
                editor._update_duplicate_warning()
                # Refresh canvas with new palette colors
                data = editor._main_controller.get_indexed_data()
                if data is not None:
                    editor._main_canvas.set_image(data, palette)

        # Request regeneration of game frame previews
        project = self._controller.project
        if project is not None:
            frame_ids = [gf.id for gf in project.game_frames]
            if frame_ids:
                self._controller.request_game_frame_previews_async(frame_ids)

    # -------------------------------------------------------------------------
    # Bidirectional Palette Highlighting
    # -------------------------------------------------------------------------

    def handle_pixel_hovered(self, x: int, y: int, rgb: object, palette_index: int) -> None:
        """Handle pixel hover on workbench - highlight palette swatch.

        Args:
            x: Pixel X coordinate
            y: Pixel Y coordinate
            rgb: RGB color tuple
            palette_index: Palette index of the pixel
        """
        if self._ai_frames_pane:
            self._ai_frames_pane.highlight_palette_index(palette_index)

    def handle_pixel_left(self) -> None:
        """Handle mouse leaving workbench - clear palette highlight."""
        if self._ai_frames_pane:
            self._ai_frames_pane.highlight_palette_index(None)

    def handle_eyedropper_picked(self, rgb: object, palette_index: int) -> None:
        """Handle eyedropper pick - select palette swatch.

        Args:
            rgb: RGB color tuple
            palette_index: Palette index of the picked pixel
        """
        if self._ai_frames_pane:
            self._ai_frames_pane.select_palette_index(palette_index)

    def handle_palette_color_changed(self, index: int, rgb: object) -> None:
        """Handle palette color change from AI frames pane - update controller.

        Args:
            index: Palette index that changed
            rgb: New RGB color tuple
        """
        if self._controller is None:
            return

        if isinstance(rgb, tuple) and len(rgb) >= 3:
            rgb_tuple = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
            self._controller.set_sheet_palette_color(index, rgb_tuple)

    def handle_palette_swatch_hovered(self, index: object) -> None:
        """Handle palette swatch hover - highlight pixels on canvas.

        Args:
            index: Palette index being hovered, or None to clear
        """
        if self._alignment_canvas is None:
            return

        if index is None or isinstance(index, int):
            self._alignment_canvas.highlight_pixels_by_index(index)

    # -------------------------------------------------------------------------
    # Palette Editor Window Management
    # -------------------------------------------------------------------------

    def handle_edit_frame_palette(self, ai_frame_id: str) -> None:
        """Handle edit frame palette request - open palette index editor.

        Opens a modeless window for editing palette indices of the AI frame
        before ROM injection.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        if self._controller is None or self._parent_widget is None:
            return

        from ui.frame_mapping.windows import AIFramePaletteEditorWindow

        logger.info("handle_edit_frame_palette called with: %s", ai_frame_id)
        project = self._controller.project
        if project is None:
            logger.warning("No project loaded")
            return

        # Check if editor is already open for this frame
        if ai_frame_id in self._palette_editors:
            editor = self._palette_editors[ai_frame_id]
            editor.raise_()
            editor.activateWindow()
            return

        # Get the AI frame
        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            logger.warning("AI frame not found: %s", ai_frame_id)
            return

        # Get the sheet palette - required for palette editing
        sheet_palette = project.sheet_palette
        if sheet_palette is None:
            QMessageBox.warning(
                self._parent_widget,
                "No Palette Set",
                "Please set a sheet palette before editing palette indices.\n\n"
                "Use the 'Map Colors...' or 'Extract from Sheet' buttons in the "
                "Sheet Palette panel to create a palette first.",
            )
            return

        # Create the editor window
        editor = AIFramePaletteEditorWindow(ai_frame, sheet_palette, self._parent_widget, controller=self._controller)

        # Track the editor window
        self._palette_editors[ai_frame_id] = editor

        # Connect signals - these go back to coordinator methods
        editor.save_requested.connect(self._handle_palette_editor_save)
        editor.closed.connect(self._handle_palette_editor_closed)
        editor.palette_color_changed.connect(self._handle_editor_palette_color_changed)
        editor.ingame_saved.connect(self._handle_ingame_saved)

        # Show the editor
        editor.show()

        logger.info("Opened palette editor for: %s", ai_frame_id)

    def _handle_palette_editor_save(self, ai_frame_id: str, indexed_data: object, output_path: str) -> None:
        """Handle save from palette editor.

        Updates the AIFrame path and refreshes the workspace.
        When the path changes (e.g., sprite_00.png -> sprite_00_edited.png),
        all references to the frame ID must be updated.

        Args:
            ai_frame_id: AI frame ID (old filename)
            indexed_data: Numpy array of indexed pixel data (unused here)
            output_path: Path to the saved edited PNG
        """
        if self._controller is None or self._state is None:
            return

        project = self._controller.project
        if project is None:
            return

        # Use project method to update path and fix all references
        new_id = project.update_ai_frame_path(ai_frame_id, Path(output_path))
        if new_id is None:
            logger.warning("Failed to update AI frame path: frame %s not found", ai_frame_id)
            return

        # Update workspace tracking if ID changed
        if new_id != ai_frame_id:
            # Update palette editor tracking
            if ai_frame_id in self._palette_editors:
                editor = self._palette_editors.pop(ai_frame_id)
                self._palette_editors[new_id] = editor

            # Update selection tracking
            if self._state.selected_ai_frame_id == ai_frame_id:
                self._state.selected_ai_frame_id = new_id

        # Mark project as modified and trigger autosave
        self._controller.emit_project_changed()
        self._controller.emit_save_requested()

        # Refresh the AI frames pane to show updated preview
        if self._ai_frames_pane:
            self._ai_frames_pane.refresh_frame(new_id)

        # Refresh the mapping panel to show the updated frame
        if self._mapping_panel:
            if new_id != ai_frame_id:
                # ID changed - need full refresh to update stored IDs in table
                self._mapping_panel.refresh()
            else:
                # Just thumbnail changed - lightweight refresh is sufficient
                self._mapping_panel.refresh_thumbnails_only()

        # Update workbench if this frame is selected
        if self._state.selected_ai_frame_id == new_id and self._on_ai_frame_selected:
            self._on_ai_frame_selected(new_id)

        if self._message_service:
            self._message_service.show_message(f"Saved edited palette: {Path(output_path).name}", 3000)

    def _handle_palette_editor_closed(self, ai_frame_id: str) -> None:
        """Handle palette editor window closed.

        Removes the editor from tracking dict.

        Args:
            ai_frame_id: AI frame ID of the closed editor
        """
        if ai_frame_id in self._palette_editors:
            del self._palette_editors[ai_frame_id]
            logger.debug("Palette editor closed for: %s", ai_frame_id)

    def _handle_editor_palette_color_changed(self, index: int, color: tuple[int, int, int]) -> None:
        """Handle palette color change from palette editor window.

        Routes the change through the controller to update the project
        and trigger refresh of all affected UI components.

        Args:
            index: Palette index that changed
            color: New RGB color tuple
        """
        if self._controller:
            self._controller.set_sheet_palette_color(index, color)

    def _handle_ingame_saved(self, ai_frame_id: str, ingame_edited_path: str) -> None:
        """Handle in-game edit saved from palette editor.

        Forwards composite path to canvas for index extraction and AI frame
        overwrite, then triggers project save (AI frame file changed on disk).
        """
        if self._state is not None and self._state.selected_ai_frame_id == ai_frame_id:
            if self._alignment_canvas is not None:
                self._alignment_canvas.set_ingame_edited_path(ingame_edited_path)
        # AI frame file was updated — persist project
        if self._controller is not None:
            self._controller.emit_save_requested()

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _get_sample_ai_frame_path(self) -> Path | None:
        """Get path to a sample AI frame for preview.

        Returns the first AI frame that has a valid image path,
        or None if no AI frames are loaded.
        """
        if self._controller is None:
            return None

        project = self._controller.project
        if project is None:
            return None

        for ai_frame in project.ai_frames:
            if ai_frame.path.exists():
                return ai_frame.path

        return None

    # -------------------------------------------------------------------------
    # Public Access for Workspace
    # -------------------------------------------------------------------------

    @property
    def palette_editors(self) -> dict[str, AIFramePaletteEditorWindow]:
        """Get the palette editors dict for workspace access.

        Note: This is exposed for the workspace to check open editors.
        Prefer using coordinator methods for editor management.
        """
        return self._palette_editors
