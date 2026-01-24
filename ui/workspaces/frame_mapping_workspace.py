"""Frame Mapping Workspace.

Provides a dedicated workspace for mapping AI-generated sprite frames
to game animation frames captured from Mesen 2.

Four-zone layout:
┌─────────────────────────────────────────────────────────────────────────────┐
│ Toolbar: [Load AI Frames] [Import Capture] [Import Dir] [Load] [Save] [Inject] │
├────────────────┬─────────────────────────────┬─────────────────────────────┤
│                │                             │                             │
│  AI FRAMES     │     ALIGNMENT CANVAS        │   CAPTURES LIBRARY          │
│  (Left Pane)   │     (Center Top)            │   (Right Pane)              │
│                │                             │                             │
├────────────────┼─────────────────────────────┤                             │
│                │                             │                             │
│                │   MAPPINGS DRAWER           │                             │
│                │   (Center Bottom)           │                             │
│                │                             │                             │
└────────────────┴─────────────────────────────┴─────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from PIL import Image
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.app_context import get_app_context
from core.services.tile_sampling_service import calculate_auto_alignment
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.dialog_coordinator import DialogCoordinator
from ui.frame_mapping.dialogs.replace_link_dialog import (
    confirm_replace_ai_frame_link,
    confirm_replace_link,
)
from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane
from ui.frame_mapping.views.mapping_panel import MappingPanel
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas
from ui.frame_mapping.windows import AIFramePaletteEditorWindow
from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.mesen_integration.click_extractor import CaptureResult
    from ui.managers.status_bar_manager import StatusBarManager

logger = get_logger(__name__)


class FrameMappingWorkspace(QWidget):
    """Main workspace for frame mapping functionality.

    Signals:
        edit_in_sprite_editor_requested: Request to edit a frame (ai_frame_path, rom_offsets)
    """

    edit_in_sprite_editor_requested = Signal(Path, list)  # ai_path, rom_offsets

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        message_service: StatusBarManager | None = None,
        controller: FrameMappingController | None = None,
    ) -> None:
        super().__init__(parent)
        self._message_service = message_service

        # State manager for UI state
        self._state = WorkspaceStateManager()

        # Track open palette editor windows (frame_id -> editor window)
        self._palette_editors: dict[str, AIFramePaletteEditorWindow] = {}

        # Dialog coordinator for capture imports and confirmations
        self._dialog_coordinator = DialogCoordinator(self)

        # Create or inject controller
        self._controller = controller or self._create_default_controller()

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

        # Auto-load last project if available
        self._auto_load_last_project()

        logger.debug("FrameMappingWorkspace initialized with 4-zone layout")

    def set_message_service(self, service: StatusBarManager | None) -> None:
        """Set the message service for status updates."""
        self._message_service = service

    def set_rom_path(self, rom_path: Path | None) -> None:
        """Set ROM path for injection.

        Called when switching from sprite editor workspace.
        Resets the modified ROM path since a new original ROM is being used.

        Args:
            rom_path: Path to the ROM file, or None to clear.
        """
        if rom_path != self._state.rom_path:
            logger.info("FrameMapping ROM path updated: %s", rom_path)
            self._state.rom_path = rom_path
            self._state.modified_rom_path = None

    def _create_default_controller(self) -> FrameMappingController:
        """Create controller with workspace as parent for Qt ownership.

        Returns:
            FrameMappingController instance
        """
        return FrameMappingController(parent=self)

    def _validate_rom_path(self) -> bool:
        """Validate that the current ROM path is valid and exists.

        Returns:
            True if valid, False otherwise.
        """
        if self._state.rom_path is None:
            QMessageBox.information(
                self,
                "Injection Requirement",
                "No ROM loaded.\n\nPlease load a ROM in the Sprite Editor workspace first.",
            )
            return False

        if not self._state.is_rom_valid():
            QMessageBox.warning(
                self,
                "ROM Not Found",
                f"The ROM file from Sprite Editor no longer exists:\n{self._state.rom_path}\n\n"
                "Please reload the ROM in the Sprite Editor workspace.",
            )
            return False

        return True

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with title and toolbar
        header = self._create_header()
        layout.addWidget(header)

        # Main content: 4-zone layout using nested splitters
        # Horizontal splitter: [Left Pane | Center Column | Right Pane]
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Left Pane: AI Frames
        self._ai_frames_pane = AIFramesPane()
        self._main_splitter.addWidget(self._ai_frames_pane)

        # Center Column: Vertical splitter [Canvas | Drawer]
        self._center_splitter = QSplitter(Qt.Orientation.Vertical)

        # Center Top: Workbench Canvas (interactive alignment)
        self._alignment_canvas = WorkbenchCanvas()
        self._center_splitter.addWidget(self._alignment_canvas)

        # Center Bottom: Mappings Drawer
        self._mapping_panel = MappingPanel()
        self._center_splitter.addWidget(self._mapping_panel)

        # Set center splitter proportions (roughly 1:1)
        self._center_splitter.setSizes([400, 300])

        self._main_splitter.addWidget(self._center_splitter)

        # Right Pane: Captures Library
        self._captures_pane = CapturesLibraryPane()
        self._main_splitter.addWidget(self._captures_pane)

        # Set main splitter sizes (roughly 1:2:1 ratio)
        self._main_splitter.setSizes([220, 560, 220])

        layout.addWidget(self._main_splitter, 1)

    def _create_header(self) -> QWidget:
        """Create the header widget with title and toolbar."""
        header = QWidget()
        header.setObjectName("frameMappingHeader")
        header.setStyleSheet("""
            #frameMappingHeader {
                background-color: #333;
                border-bottom: 1px solid #444;
            }
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Title
        title = QLabel("Frame Mapping")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff;")
        layout.addWidget(title)

        # Project name (updated dynamically)
        self._project_label = QLabel("")
        self._project_label.setStyleSheet("font-size: 12px; color: #888;")
        layout.addWidget(self._project_label)

        layout.addStretch()

        # Toolbar
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setStyleSheet("QToolBar { border: none; background: transparent; }")

        self._load_ai_btn = QPushButton("Load AI Frames")
        self._load_ai_btn.setToolTip("Load AI-generated frames from a directory")
        self._load_ai_btn.clicked.connect(lambda: self._on_load_ai_frames())
        toolbar.addWidget(self._load_ai_btn)

        self._import_capture_btn = QPushButton("Import Capture")
        self._import_capture_btn.setToolTip("Import a single Mesen 2 capture file")
        self._import_capture_btn.clicked.connect(lambda: self._on_import_capture())
        toolbar.addWidget(self._import_capture_btn)

        self._import_dir_btn = QPushButton("Import Directory")
        self._import_dir_btn.setToolTip("Import all captures from a directory")
        self._import_dir_btn.clicked.connect(lambda: self._on_import_capture_dir())
        toolbar.addWidget(self._import_dir_btn)

        toolbar.addSeparator()

        self._load_btn = QPushButton("Load")
        self._load_btn.setToolTip("Load a frame mapping project")
        self._load_btn.clicked.connect(lambda: self._on_load_project())
        toolbar.addWidget(self._load_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setToolTip("Save the current project")
        self._save_btn.clicked.connect(lambda: self._on_save_project())
        toolbar.addWidget(self._save_btn)

        toolbar.addSeparator()

        self._reuse_rom_checkbox = QCheckBox("Reuse Last ROM")
        self._reuse_rom_checkbox.setToolTip("Inject into last injected ROM instead of creating a new copy")
        self._reuse_rom_checkbox.setChecked(False)
        toolbar.addWidget(self._reuse_rom_checkbox)

        self._inject_btn = QPushButton("Inject All")
        self._inject_btn.setToolTip("Inject all mapped frames into ROM")
        self._inject_btn.clicked.connect(lambda: self._on_inject_all())
        self._inject_btn.setStyleSheet("background-color: #2c5d2c; font-weight: bold;")
        toolbar.addWidget(self._inject_btn)

        layout.addWidget(toolbar)

        return header

    def _connect_signals(self) -> None:
        """Connect signals between components.

        Signal flow documentation: docs/frame_mapping_signals.md
        """
        # Controller signals
        self._controller.project_changed.connect(self._on_project_changed)
        self._controller.ai_frames_loaded.connect(self._on_ai_frames_loaded)
        self._controller.game_frame_added.connect(self._on_game_frame_added)
        self._controller.mapping_injected.connect(self._on_mapping_injected)
        self._controller.error_occurred.connect(self._on_error)
        self._controller.status_update.connect(self._on_status_update)
        self._controller.save_requested.connect(self._auto_save_after_injection)
        self._controller.stale_entries_warning.connect(self._on_stale_entries_warning)
        self._controller.alignment_updated.connect(self._on_alignment_updated)
        self._controller.preview_cache_invalidated.connect(self._on_preview_cache_invalidated)
        self._controller.capture_import_requested.connect(self._on_capture_import_requested)

        # Dialog coordinator signals
        self._dialog_coordinator.queue_processing_finished.connect(self._on_capture_queue_finished)

        # AI Frames Pane signals
        self._ai_frames_pane.ai_frame_selected.connect(self._on_ai_frame_selected)
        self._ai_frames_pane.map_requested.connect(self._on_map_selected)
        self._ai_frames_pane.auto_advance_changed.connect(self._on_auto_advance_changed)
        self._ai_frames_pane.edit_in_sprite_editor_requested.connect(self._on_edit_frame)
        self._ai_frames_pane.edit_frame_palette_requested.connect(self._on_edit_frame_palette)
        self._ai_frames_pane.remove_from_project_requested.connect(self._on_remove_ai_frame)
        # Sheet palette signals
        self._ai_frames_pane.palette_edit_requested.connect(self._on_palette_edit_requested)
        self._ai_frames_pane.palette_extract_requested.connect(self._on_palette_extract_requested)
        self._ai_frames_pane.palette_clear_requested.connect(self._on_palette_clear_requested)
        self._controller.sheet_palette_changed.connect(self._on_sheet_palette_changed)
        # Bidirectional palette highlighting signals
        self._alignment_canvas.pixel_hovered.connect(self._on_pixel_hovered)
        self._alignment_canvas.pixel_left.connect(self._on_pixel_left)
        self._alignment_canvas.eyedropper_picked.connect(self._on_eyedropper_picked)
        self._ai_frames_pane.palette_color_changed.connect(self._on_palette_color_changed)
        self._ai_frames_pane.palette_swatch_hovered.connect(self._on_palette_swatch_hovered)
        # Drag-drop and tab signals
        self._ai_frames_pane.folder_dropped.connect(self._on_ai_folder_dropped)
        self._ai_frames_pane.tab_folder_changed.connect(self._on_ai_tab_folder_changed)
        # Frame organization signals (V4)
        self._ai_frames_pane.frame_rename_requested.connect(self._on_frame_rename_requested)
        self._ai_frames_pane.frame_tag_toggled.connect(self._on_frame_tag_toggled)
        self._controller.frame_renamed.connect(self._on_frame_organization_changed)
        self._controller.frame_tags_changed.connect(self._on_frame_organization_changed)
        self._controller.capture_renamed.connect(self._on_capture_organization_changed)

        # Captures Library Pane signals
        self._captures_pane.game_frame_selected.connect(self._on_game_frame_selected)
        self._captures_pane.edit_in_sprite_editor_requested.connect(self._on_edit_game_frame)
        self._captures_pane.delete_capture_requested.connect(self._on_delete_capture)
        self._captures_pane.show_details_requested.connect(self._on_show_capture_details)
        self._captures_pane.capture_rename_requested.connect(self._on_capture_rename_requested)

        # Mapping Panel (Drawer) signals - ID-based
        self._mapping_panel.mapping_selected.connect(self._on_mapping_selected)
        self._mapping_panel.edit_frame_requested.connect(self._on_edit_frame)
        self._mapping_panel.remove_mapping_requested.connect(self._on_remove_mapping)
        self._mapping_panel.adjust_alignment_requested.connect(self._on_adjust_alignment)
        self._mapping_panel.drop_game_frame_requested.connect(self._on_drop_game_frame)
        self._mapping_panel.inject_mapping_requested.connect(self._on_inject_single)
        self._mapping_panel.inject_selected_requested.connect(self._on_inject_selected)

        # Alignment Canvas signals
        self._alignment_canvas.alignment_changed.connect(self._on_alignment_changed)
        self._alignment_canvas.compression_type_changed.connect(self._on_compression_type_changed)
        self._alignment_canvas.apply_transforms_to_all_requested.connect(self._on_apply_transforms_to_all)

    def _setup_shortcuts(self) -> None:
        """Setup keyboard shortcuts for undo/redo."""
        # Undo: Ctrl+Z
        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self._on_undo)

        # Redo: Ctrl+Y / Ctrl+Shift+Z
        redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        redo_shortcut.activated.connect(self._on_redo)

    # -------------------------------------------------------------------------
    # Selection State Helpers (Panes as Source of Truth)
    # -------------------------------------------------------------------------

    def _get_selected_ai_frame_id(self) -> str | None:
        """Get the currently selected AI frame ID.

        Queries AIFramesPane first (source of truth), falls back to cached state.
        Use this when you need fresh selection state.

        Returns:
            AI frame ID (filename) or None if no selection
        """
        # Query pane (source of truth)
        pane_selection = self._ai_frames_pane.get_selected_id()
        if pane_selection is not None:
            return pane_selection
        # Fallback to cached state if pane not available or returns None
        return self._state.selected_ai_frame_id

    def _get_selected_game_id(self) -> str | None:
        """Get the currently selected game frame ID.

        Queries CapturesLibraryPane first (source of truth), falls back to cached state.
        Use this when you need fresh selection state.

        Returns:
            Game frame ID or None if no selection
        """
        # Query pane (source of truth)
        pane_selection = self._captures_pane.get_selected_id()
        if pane_selection is not None:
            return pane_selection
        # Fallback to cached state if pane not available or returns None
        return self._state.selected_game_id

    def _on_undo(self) -> None:
        """Handle Ctrl+Z - undo last action."""
        desc = self._controller.undo()
        if desc:
            if self._message_service:
                self._message_service.show_message(f"Undo: {desc}", 2000)
            # Refresh UI after undo
            self._refresh_mapping_status()
            self._refresh_game_frame_link_status()
            self._update_mapping_panel_previews()
            # Sync canvas alignment with restored model state
            self._sync_canvas_alignment_from_model()
        elif self._message_service:
            self._message_service.show_message("Nothing to undo", 1500)

    def _on_redo(self) -> None:
        """Handle Ctrl+Y - redo last undone action."""
        desc = self._controller.redo()
        if desc:
            if self._message_service:
                self._message_service.show_message(f"Redo: {desc}", 2000)
            # Refresh UI after redo
            self._refresh_mapping_status()
            self._refresh_game_frame_link_status()
            self._update_mapping_panel_previews()
            # Sync canvas alignment with restored model state
            self._sync_canvas_alignment_from_model()
        elif self._message_service:
            self._message_service.show_message("Nothing to redo", 1500)

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def _on_auto_advance_changed(self, enabled: bool) -> None:
        """Handle auto-advance toggle change."""
        self._state.auto_advance_enabled = enabled
        logger.debug("Auto-advance %s", "enabled" if enabled else "disabled")

    def _on_project_changed(self) -> None:
        """Handle project changes.

        Only clears canvas when project identity changes (new/load),
        not on content updates within the same project.
        """
        project = self._controller.project

        # Check if project identity changed (new project loaded vs content update)
        current_project_id = id(project) if project is not None else None
        project_identity_changed = current_project_id != self._state.previous_project_id
        self._state.previous_project_id = current_project_id

        # Only clear canvas on actual project change, not content updates
        if project_identity_changed:
            self._alignment_canvas.clear()

        if project is None:
            self._state.selected_ai_frame_id = None
            self._state.selected_game_id = None
            self._project_label.setText("")
            self._ai_frames_pane.clear()
            self._captures_pane.clear()
            self._mapping_panel.set_project(None)
            self._mapping_panel.set_sheet_palette(None)  # Clear mapping panel palette
            self._alignment_canvas.clear()
            self._alignment_canvas.set_sheet_palette(None)  # Clear canvas palette
            self._update_map_button_state()
            return

        self._project_label.setText(f"- {project.name}")
        self._ai_frames_pane.set_ai_frames(project.ai_frames)
        # Sync tab folder from project if current tab is empty
        if project.ai_frames_dir and self._ai_frames_pane.get_current_tab_folder() is None:
            self._ai_frames_pane.set_current_tab_folder(project.ai_frames_dir)
        self._ai_frames_pane.set_sheet_palette(project.sheet_palette)  # Load sheet palette
        self._alignment_canvas.set_sheet_palette(project.sheet_palette)  # Sync canvas palette
        self._captures_pane.set_game_frames(project.game_frames)
        self._mapping_panel.set_project(project)
        self._mapping_panel.set_sheet_palette(project.sheet_palette)  # Sync mapping panel palette
        self._update_map_button_state()
        self._refresh_mapping_status()
        self._refresh_game_frame_link_status()
        self._update_mapping_panel_previews()

    def _on_ai_frames_loaded(self, count: int) -> None:
        """Handle AI frames loaded."""
        if self._message_service:
            self._message_service.show_message(f"Loaded {count} AI frames")

    def _on_game_frame_added(self, frame_id: str) -> None:
        """Handle game frame added."""
        if self._message_service:
            self._message_service.show_message(f"Imported game frame: {frame_id}")

    def _on_error(self, message: str) -> None:
        """Handle error from controller."""
        logger.error("Frame mapping error: %s", message)
        QMessageBox.warning(self, "Error", message)

    def _on_status_update(self, message: str) -> None:
        """Handle status update from controller."""
        logger.info("Frame mapping status received: %s", message)
        if self._message_service:
            logger.debug("Showing message via status bar: %s", message)
            self._message_service.show_message(message, 5000)
        else:
            logger.warning("No message service set - status update not shown in UI")

    def _on_ai_frame_selected(self, frame_id: str) -> None:
        """Handle AI frame selection in left pane.

        Syncs with drawer and canvas. If mapped, shows alignment.

        Args:
            frame_id: The AI frame ID (filename), or empty string for cleared selection.
        """
        project = self._controller.project
        if project is None:
            return

        # Guard against cleared selection
        if not frame_id:
            self._state.selected_ai_frame_id = None
            self._update_map_button_state()
            self._alignment_canvas.set_ai_frame(None)
            self._alignment_canvas.clear_alignment()
            self._mapping_panel.clear_selection()
            self._captures_pane.clear_selection()
            self._state.selected_game_id = None
            self._state.current_canvas_game_id = None
            return

        self._state.selected_ai_frame_id = frame_id
        self._update_map_button_state()

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
                mapping.offset_x, mapping.offset_y, mapping.flip_h, mapping.flip_v, mapping.scale
            )
            # Sync captures selection and track canvas state
            self._captures_pane.select_frame(mapping.game_frame_id)
            self._state.selected_game_id = mapping.game_frame_id
            self._state.current_canvas_game_id = mapping.game_frame_id
        else:
            self._alignment_canvas.set_game_frame(None)
            self._alignment_canvas.clear_alignment()
            self._captures_pane.clear_selection()
            self._state.selected_game_id = None
            self._state.current_canvas_game_id = None

        self._update_map_button_state()

    def _on_game_frame_selected(self, frame_id: str) -> None:
        """Handle game frame selection in captures library.

        Updates preview in canvas if an AI frame is selected.
        Note: No longer auto-links - linking requires explicit user action.
        """
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
            self._update_map_button_state()
            return

        self._state.selected_game_id = frame_id
        self._update_map_button_state()

        # Show preview in canvas if AI frame is selected
        if self._state.selected_ai_frame_id is not None:
            game_frame = project.get_game_frame_by_id(frame_id)
            preview = self._controller.get_game_frame_preview(frame_id)
            capture_result, used_fallback = self._controller.get_capture_result_for_game_frame(frame_id)
            self._alignment_canvas.set_game_frame(game_frame, preview, capture_result, used_fallback)
            self._state.current_canvas_game_id = frame_id

    def _on_mapping_selected(self, ai_frame_id: str) -> None:
        """Handle mapping row selection in drawer.

        Syncs with AI frames pane and canvas.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        project = self._controller.project
        if project is None:
            return

        # Get AI frame by ID
        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            return

        # Sync AI frames pane (uses index for scroll/selection)
        self._ai_frames_pane.select_frame(ai_frame.index)
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
                mapping.offset_x, mapping.offset_y, mapping.flip_h, mapping.flip_v, mapping.scale
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

        self._update_map_button_state()

    def _on_map_selected(self) -> None:
        """Handle map button click in AI frames pane."""
        # Query fresh selection state from panes (source of truth)
        ai_frame_id = self._get_selected_ai_frame_id()
        game_id = self._get_selected_game_id()

        if ai_frame_id is None:
            QMessageBox.information(self, "Map Frames", "Please select an AI frame first.")
            return

        if game_id is None:
            QMessageBox.information(self, "Map Frames", "Please select a game frame first.")
            return

        self._attempt_link(ai_frame_id, game_id)

    def _on_drop_game_frame(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Handle game frame dropped onto drawer row.

        Args:
            ai_frame_id: AI frame ID (filename)
            game_frame_id: Game frame ID
        """
        self._attempt_link(ai_frame_id, game_frame_id)

    def _on_alignment_changed(self, x: int, y: int, flip_h: bool, flip_v: bool, scale: float) -> None:
        """Handle alignment change from canvas (auto-save).

        Alignment changes are only applied when the canvas is displaying the same
        game frame as the existing mapping. This prevents accidental edits when
        the user is previewing a different capture.
        """
        # Query fresh selection state from pane (source of truth)
        ai_frame_id = self._get_selected_ai_frame_id()
        if ai_frame_id is None:
            return

        project = self._controller.project
        if project is None:
            return

        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return

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
            return

        # Update alignment in controller (includes scale)
        # This emits alignment_updated signal which triggers _on_alignment_updated()
        # which handles updating the mapping panel row
        self._controller.update_mapping_alignment(ai_frame_id, x, y, flip_h, flip_v, scale)

    def _on_compression_type_changed(self, compression_type: str) -> None:
        """Handle compression type change from canvas.

        Routes compression changes through the controller instead of
        directly mutating game frame state.

        Uses _current_canvas_game_id (what canvas displays) rather than
        _selected_game_id (what user clicked in library), because the user
        is editing what they see on the canvas.
        """
        if self._state.current_canvas_game_id is None:
            return

        # Route through controller for proper signal emission and auto-save
        self._controller.update_game_frame_compression(self._state.current_canvas_game_id, compression_type)

    def _on_apply_transforms_to_all(self, offset_x: int, offset_y: int, scale: float) -> None:
        """Handle apply transformations to all request from canvas.

        Shows confirmation dialog with count of affected mappings,
        then applies position and scale to all mappings except the current one.

        Args:
            offset_x: X offset to apply
            offset_y: Y offset to apply
            scale: Scale factor to apply (0.1 - 1.0)
        """
        project = self._controller.project
        if project is None or project.mapped_count == 0:
            if self._message_service:
                self._message_service.show_message("No mapped frames to update", 2000)
            return

        # Get current AI frame to exclude
        current_ai_frame_id = self._alignment_canvas.get_current_ai_frame_id()

        # Count how many mappings will be affected (exclude current)
        affected_count = sum(1 for m in project.mappings if m.ai_frame_id != current_ai_frame_id)

        if affected_count == 0:
            if self._message_service:
                self._message_service.show_message("No other mappings to update", 2000)
            return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Apply Transformations to All",
            f"Apply position ({offset_x}, {offset_y}) and scale {scale:.0%} to {affected_count} other mapped frames?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Apply transformations to all mappings except current
        updated_count = self._controller.apply_transforms_to_all_mappings(
            offset_x, offset_y, scale, current_ai_frame_id
        )

        if self._message_service:
            self._message_service.show_message(f"Applied transformations to {updated_count} mappings", 3000)

        # Refresh UI
        self._mapping_panel.refresh()
        self._refresh_mapping_status()

    def _on_adjust_alignment(self, ai_frame_id: str) -> None:
        """Handle adjust alignment request - focus the canvas.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        project = self._controller.project
        if project is None:
            return

        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            return

        # Select the frame first (using index for backward-compat select_frame method)
        self._ai_frames_pane.select_frame(ai_frame.index)
        self._on_ai_frame_selected(ai_frame_id)

        # Focus the canvas for keyboard input
        self._alignment_canvas.focus_canvas()

        if self._message_service:
            self._message_service.show_message("Use arrow keys to adjust alignment")

    def _on_edit_frame(self, ai_frame_id: str) -> None:
        """Handle edit AI frame request.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
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

        self.edit_in_sprite_editor_requested.emit(ai_frame.path, rom_offsets)

    def _on_edit_game_frame(self, frame_id: str) -> None:
        """Handle edit game frame request from captures library."""
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
            if ai_frame:
                self.edit_in_sprite_editor_requested.emit(ai_frame.path, game_frame.rom_offsets)
                return

        # No linked AI frame - emit with empty path (will need handling in main window)
        if self._message_service:
            self._message_service.show_message("No AI frame linked to this capture", 3000)

    def _on_edit_frame_palette(self, ai_frame_id: str) -> None:
        """Handle edit frame palette request - open palette index editor.

        Opens a modeless window for editing palette indices of the AI frame
        before ROM injection.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        logger.info("_on_edit_frame_palette called with: %s", ai_frame_id)
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
                self,
                "No Palette Set",
                "Please set a sheet palette before editing palette indices.\n\n"
                "Right-click on the palette panel and choose 'Edit Palette...' "
                "or 'Extract from Capture...' to set one.",
            )
            return

        # Create the editor window
        editor = AIFramePaletteEditorWindow(ai_frame, sheet_palette, self)

        # Track the editor window
        self._palette_editors[ai_frame_id] = editor

        # Connect signals
        editor.save_requested.connect(self._on_palette_editor_save)
        editor.closed.connect(lambda fid=ai_frame_id: self._on_palette_editor_closed(fid))
        editor.palette_color_changed.connect(self._on_editor_palette_color_changed)

        # Show the editor
        editor.show()

        logger.info("Opened palette editor for: %s", ai_frame_id)

    def _on_palette_editor_save(self, ai_frame_id: str, indexed_data: object, output_path: str) -> None:
        """Handle save from palette editor.

        Updates the AIFrame path and refreshes the workspace.
        When the path changes (e.g., sprite_00.png -> sprite_00_edited.png),
        all references to the frame ID must be updated.

        Args:
            ai_frame_id: AI frame ID (old filename)
            indexed_data: Numpy array of indexed pixel data (unused here)
            output_path: Path to the saved edited PNG
        """
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

        # Mark project as modified (will auto-save on next operation)
        self._controller.project_changed.emit()

        # Refresh the AI frames pane to show updated preview
        self._ai_frames_pane.refresh_frame(new_id)

        # Refresh the mapping panel to show the updated frame
        self._mapping_panel.refresh()

        # Update workbench if this frame is selected
        if self._state.selected_ai_frame_id == new_id:
            self._on_ai_frame_selected(new_id)

        if self._message_service:
            self._message_service.show_message(f"Saved edited palette: {Path(output_path).name}", 3000)

    def _on_palette_editor_closed(self, ai_frame_id: str) -> None:
        """Handle palette editor window closed.

        Removes the editor from tracking dict.

        Args:
            ai_frame_id: AI frame ID of the closed editor
        """
        if ai_frame_id in self._palette_editors:
            del self._palette_editors[ai_frame_id]
            logger.debug("Palette editor closed for: %s", ai_frame_id)

    def _on_editor_palette_color_changed(self, index: int, color: tuple[int, int, int]) -> None:
        """Handle palette color change from palette editor window.

        Routes the change through the controller to update the project
        and trigger refresh of all affected UI components.

        Args:
            index: Palette index that changed
            color: New RGB color tuple
        """
        self._controller.set_sheet_palette_color(index, color)

    def _on_delete_capture(self, frame_id: str) -> None:
        """Handle delete capture request."""
        project = self._controller.project
        if project is None:
            return

        # Check if linked (use ID-based method)
        linked_ai_id = project.get_ai_frame_linked_to_game_frame(frame_id)
        if linked_ai_id is not None:
            ai_frame = project.get_ai_frame_by_id(linked_ai_id)
            ai_name = ai_frame.name if ai_frame else linked_ai_id
            reply = QMessageBox.question(
                self,
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
                self._update_map_button_state()

            # Clear canvas if deleted frame was currently displayed
            # (may be displayed without being selected, e.g., during preview)
            if self._state.current_canvas_game_id == frame_id:
                self._state.current_canvas_game_id = None
                self._alignment_canvas.set_game_frame(None)
                self._alignment_canvas.clear_alignment()

            if self._message_service:
                self._message_service.show_message(f"Deleted capture: {frame_id}")

    def _on_show_capture_details(self, frame_id: str) -> None:
        """Handle show details request for capture."""
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

        QMessageBox.information(self, "Capture Details", "\n".join(details))

    def _on_remove_ai_frame(self, ai_frame_id: str) -> None:
        """Handle remove AI frame from project request."""
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
                self,
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
                self._alignment_canvas.set_ai_frame(None)
                self._alignment_canvas.set_game_frame(None)  # Also clear game frame since context is lost
                self._alignment_canvas.clear_alignment()
                self._update_map_button_state()

            if self._message_service:
                self._message_service.show_message(f"Removed: {frame_name}")

    def _on_remove_mapping(self, ai_frame_id: str) -> None:
        """Handle remove mapping request.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        self._controller.remove_mapping(ai_frame_id)
        self._refresh_mapping_status()
        self._refresh_game_frame_link_status()
        self._mapping_panel.refresh()  # Refresh table after mapping removal
        self._alignment_canvas.clear_alignment()
        # Phase 3c fix: Clear game frame from canvas and update map button
        self._alignment_canvas.set_game_frame(None)
        self._captures_pane.clear_selection()
        # Phase 3c fix: Clear selected game ID and update Map button
        self._state.selected_game_id = None
        self._state.current_canvas_game_id = None
        self._update_map_button_state()

    def _on_inject_single(self, ai_frame_id: str) -> None:
        """Handle inject single mapping request.

        Args:
            ai_frame_id: AI frame ID (filename)
        """
        project = self._controller.project
        if project is None:
            return

        if not project.get_mapping_for_ai_frame(ai_frame_id):
            QMessageBox.information(self, "Inject Frame", "Selected frame is not mapped.")
            return

        if not self._validate_rom_path():
            return

        # At this point self._state.rom_path is guaranteed not None and exists
        rom_path = cast(Path, self._state.rom_path)

        # Check if we should reuse the last injected ROM
        reuse_enabled = self._reuse_rom_checkbox.isChecked()
        can_reuse = (
            reuse_enabled and self._state.last_injected_rom is not None and self._state.last_injected_rom.exists()
        )

        if can_reuse:
            target_rom = cast(Path, self._state.last_injected_rom)
            reply = QMessageBox.question(
                self,
                "Confirm Injection",
                f"Inject AI Frame '{ai_frame_id}'?\n\nReusing existing ROM: {target_rom.name}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            reply = QMessageBox.question(
                self,
                "Confirm Injection",
                f"Inject AI Frame '{ai_frame_id}'?\n\nA new copy of {rom_path.name} will be created for injection.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Clear stale entry tracking before injection
        self._state.stale_entry_frame_id = None

        # Either reuse existing ROM or let inject_mapping create a new copy
        if can_reuse:
            target_rom = cast(Path, self._state.last_injected_rom)
        else:
            # Create a new copy for injection
            target_rom = self._controller.create_injection_copy(rom_path)
            if target_rom is None:
                QMessageBox.critical(self, "Inject Frame", "Failed to create ROM copy for injection.")
                return

        # Try injection with strict entry validation (no fallback)
        success = self._controller.inject_mapping(ai_frame_id, rom_path, output_path=target_rom)

        # If injection failed due to stale entries, offer to retry with fallback
        if not success and self._state.stale_entry_frame_id is not None:
            retry_reply = QMessageBox.question(
                self,
                "Entry Selection Outdated",
                f"The stored entry selection for '{self._state.stale_entry_frame_id}' no longer "
                f"matches the capture file.\n\n"
                f"Would you like to inject using ROM offset filtering instead?\n\n"
                f"Note: This may include unintended sprite entries. "
                f"To avoid this, reimport the capture with updated entry selection.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if retry_reply == QMessageBox.StandardButton.Yes:
                # Retry with allow_fallback=True
                success = self._controller.inject_mapping(
                    ai_frame_id, rom_path, output_path=target_rom, allow_fallback=True
                )

        # Track the successfully used ROM for future reuse
        if success:
            self._state.last_injected_rom = target_rom

    def _on_inject_selected(self) -> None:
        """Handle inject selected frames request from mapping panel."""
        selected_ids = self._mapping_panel.get_selected_for_injection()

        if not selected_ids:
            QMessageBox.information(self, "Inject Selected", "No frames selected for injection.")
            return

        if not self._validate_rom_path():
            return

        # At this point self._state.rom_path is guaranteed not None and exists
        rom_path = cast(Path, self._state.rom_path)

        # Check if we should reuse the last injected ROM
        reuse_enabled = self._reuse_rom_checkbox.isChecked()
        can_reuse = (
            reuse_enabled and self._state.last_injected_rom is not None and self._state.last_injected_rom.exists()
        )

        frame_count = len(selected_ids)
        if can_reuse:
            target_rom = cast(Path, self._state.last_injected_rom)
            reply = QMessageBox.question(
                self,
                "Confirm Injection",
                f"Inject {frame_count} selected frames?\n\nReusing existing ROM: {target_rom.name}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            reply = QMessageBox.question(
                self,
                "Confirm Injection",
                f"Inject {frame_count} selected frames?\n\n"
                f"A new copy of {rom_path.name} will be created for injection.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Either reuse existing ROM or create a new copy
        if can_reuse:
            target_rom = cast(Path, self._state.last_injected_rom)
        else:
            target_rom = self._controller.create_injection_copy(rom_path)
            if target_rom is None:
                QMessageBox.critical(self, "Inject Selected", "Failed to create ROM copy for injection.")
                return

        # Clear stale entry tracking before batch injection
        self._state.stale_entry_frame_id = None

        # Inject selected frames into the same copy
        # Use emit_project_changed=False to avoid N emissions, emit once after batch
        success_count = 0
        failed_due_to_stale = 0
        for ai_frame_id in selected_ids:
            self._state.stale_entry_frame_id = None  # Reset for each frame
            if self._controller.inject_mapping(
                ai_frame_id, rom_path, output_path=target_rom, emit_project_changed=False
            ):
                success_count += 1
            elif self._state.stale_entry_frame_id is not None:
                failed_due_to_stale += 1

        # Emit project_changed once for the entire batch if any succeeded
        if success_count > 0:
            self._controller.project_changed.emit()
            self._state.last_injected_rom = target_rom

        # Report results
        msg = f"Injected {success_count}/{frame_count} selected frames into {target_rom.name}"
        if failed_due_to_stale > 0:
            msg += f"\n{failed_due_to_stale} frame(s) skipped due to outdated entry selection."
        if self._message_service:
            self._message_service.show_message(msg)

    def _on_inject_all(self) -> None:
        """Handle inject all mapped frames request."""
        project = self._controller.project
        if project is None or project.mapped_count == 0:
            QMessageBox.information(self, "Inject All", "No mapped frames to inject.")
            return

        if not self._validate_rom_path():
            return

        # At this point self._state.rom_path is guaranteed not None and exists
        rom_path = cast(Path, self._state.rom_path)

        # Check if we should reuse the last injected ROM
        reuse_enabled = self._reuse_rom_checkbox.isChecked()
        can_reuse = (
            reuse_enabled and self._state.last_injected_rom is not None and self._state.last_injected_rom.exists()
        )

        if can_reuse:
            target_rom = cast(Path, self._state.last_injected_rom)
            reply = QMessageBox.question(
                self,
                "Confirm Injection",
                f"Inject {project.mapped_count} mapped frames?\n\nReusing existing ROM: {target_rom.name}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            reply = QMessageBox.question(
                self,
                "Confirm Injection",
                f"Inject {project.mapped_count} mapped frames?\n\n"
                f"A new copy of {rom_path.name} will be created for injection.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Either reuse existing ROM or create a new copy
        if can_reuse:
            target_rom = cast(Path, self._state.last_injected_rom)
        else:
            target_rom = self._controller.create_injection_copy(rom_path)
            if target_rom is None:
                QMessageBox.critical(self, "Inject All", "Failed to create ROM copy for injection.")
                return

        # Clear stale entry tracking before batch injection
        self._state.stale_entry_frame_id = None

        # Inject all mapped frames into the same copy
        # Use emit_project_changed=False to avoid N emissions, emit once after batch
        success_count = 0
        failed_due_to_stale = 0
        for ai_frame in project.ai_frames:
            mapping = project.get_mapping_for_ai_frame(ai_frame.id)
            if mapping:
                self._state.stale_entry_frame_id = None  # Reset for each frame
                # Pass the created copy as output_path to avoid creating new copies
                if self._controller.inject_mapping(
                    ai_frame.id, rom_path, output_path=target_rom, emit_project_changed=False
                ):
                    success_count += 1
                elif self._state.stale_entry_frame_id is not None:
                    failed_due_to_stale += 1

        # Emit project_changed once for the entire batch if any succeeded
        if success_count > 0:
            self._controller.project_changed.emit()
            self._state.last_injected_rom = target_rom

        # Report results
        msg = f"Injected {success_count}/{project.mapped_count} frames into {target_rom.name}"
        if failed_due_to_stale > 0:
            msg += f"\n{failed_due_to_stale} frame(s) skipped due to outdated entry selection."
        if self._message_service:
            self._message_service.show_message(msg)

    def _on_mapping_injected(self, ai_frame_id: str, message: str) -> None:
        """Handle successful injection signal."""
        if self._message_service:
            self._message_service.show_message(f"Injection successful for frame {ai_frame_id}")

        self._refresh_mapping_status()
        self._mapping_panel.refresh()  # Refresh table to show updated status
        QMessageBox.information(self, "Injection Successful", message)

    def _auto_save_after_injection(self) -> None:
        """Handle auto-save request after successful injection.

        Saves the project to the correct project file path (not ai_frames_dir).
        """
        if not self._state.project_path:
            logger.warning("Cannot auto-save: no project path set")
            return

        try:
            self._controller.save_project(self._state.project_path)
            if self._message_service:
                self._message_service.show_message("Project auto-saved", 2000)
            logger.info("Auto-saved project to %s", self._state.project_path)
        except Exception as e:
            logger.exception("Failed to auto-save project after injection")
            QMessageBox.warning(
                self,
                "Auto-Save Failed",
                f"Failed to save project: {e}\n\nPlease save manually.",
            )

    def _on_stale_entries_warning(self, frame_id: str) -> None:
        """Handle stale entry ID warning from controller.

        Tracks the frame ID for potential retry with allow_fallback=True.
        The injection will abort by default, and the caller can offer a retry option.

        Also updates the canvas warning label if the frame matches the current selection.
        """
        logger.info("Stale entries detected for frame '%s'", frame_id)
        self._state.stale_entry_frame_id = frame_id

        # Update canvas warning label if this is the currently selected game frame
        if self._state.selected_game_id == frame_id:
            self._alignment_canvas.set_stale_entries_warning_visible(True)

    def _on_alignment_updated(self, ai_frame_id: str) -> None:
        """Handle alignment-only update from controller.

        This is a targeted signal that avoids the full project_changed refresh,
        which would blank the canvas. Only updates status indicators.
        """
        # Update mapping panel row (preserves checkbox state)
        project = self._controller.project
        if project is None:
            return
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping:
            self._mapping_panel.update_row_alignment(
                ai_frame_id, mapping.offset_x, mapping.offset_y, mapping.flip_h, mapping.flip_v
            )
            # Also update the status column (alignment changes set status="edited")
            self._mapping_panel.update_row_status(ai_frame_id, mapping.status)
        # Refresh status indicators (doesn't touch canvas)
        self._refresh_mapping_status()

    # -------------------------------------------------------------------------
    # Sheet Palette Handlers
    # -------------------------------------------------------------------------

    def _on_palette_edit_requested(self) -> None:
        """Handle request to edit the sheet palette."""
        from ui.frame_mapping.dialogs.sheet_palette_mapping_dialog import SheetPaletteMappingDialog

        # Extract colors from all AI frames
        sheet_colors = self._controller.extract_sheet_colors()
        if not sheet_colors:
            QMessageBox.information(
                self,
                "No AI Frames",
                "No AI frames loaded. Please load AI frames first to extract colors.",
            )
            return

        # Get current palette and available game palettes
        current_palette = self._controller.get_sheet_palette()
        game_palettes = self._controller.get_game_palettes()

        # Open dialog
        dialog = SheetPaletteMappingDialog(
            sheet_colors=sheet_colors,
            current_palette=current_palette,
            game_palettes=game_palettes,
            parent=self,
        )

        if dialog.exec():
            # Apply the result
            new_palette = dialog.get_result()
            self._controller.set_sheet_palette(new_palette)
            if self._message_service:
                self._message_service.show_message(
                    f"Sheet palette applied ({len(new_palette.color_mappings)} color mappings)"
                )

    def _on_palette_extract_requested(self) -> None:
        """Handle request to extract palette from AI sheet."""
        sheet_colors = self._controller.extract_sheet_colors()
        if not sheet_colors:
            QMessageBox.information(
                self,
                "No AI Frames",
                "No AI frames loaded. Please load AI frames first.",
            )
            return

        # Generate palette
        new_palette = self._controller.generate_sheet_palette_from_colors(sheet_colors)
        self._controller.set_sheet_palette(new_palette)

        if self._message_service:
            self._message_service.show_message(f"Extracted 16-color palette from {len(sheet_colors)} unique colors")

    def _on_palette_clear_requested(self) -> None:
        """Handle request to clear the sheet palette."""
        if self._controller.get_sheet_palette() is None:
            return

        reply = QMessageBox.question(
            self,
            "Clear Sheet Palette",
            "Clear the sheet palette?\n\nInjections will use capture palettes instead.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._controller.set_sheet_palette(None)
            if self._message_service:
                self._message_service.show_message("Sheet palette cleared")

    def _on_sheet_palette_changed(self) -> None:
        """Handle sheet palette change from controller."""
        palette = self._controller.get_sheet_palette()
        self._ai_frames_pane.set_sheet_palette(palette)
        # Also update the workbench canvas for pixel inspection
        self._alignment_canvas.set_sheet_palette(palette)
        # Also update mapping panel to show quantized AI frame thumbnails
        self._mapping_panel.set_sheet_palette(palette)

    def _on_pixel_hovered(self, x: int, y: int, rgb: object, palette_index: int) -> None:
        """Handle pixel hover on workbench - highlight palette swatch."""
        self._ai_frames_pane.highlight_palette_index(palette_index)

    def _on_pixel_left(self) -> None:
        """Handle mouse leaving workbench - clear palette highlight."""
        self._ai_frames_pane.highlight_palette_index(None)

    def _on_eyedropper_picked(self, rgb: object, palette_index: int) -> None:
        """Handle eyedropper pick - select palette swatch."""
        self._ai_frames_pane.select_palette_index(palette_index)

    def _on_palette_color_changed(self, index: int, rgb: object) -> None:
        """Handle palette color change - update controller."""
        if isinstance(rgb, tuple) and len(rgb) >= 3:
            rgb_tuple = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
            self._controller.set_sheet_palette_color(index, rgb_tuple)

    def _on_palette_swatch_hovered(self, index: object) -> None:
        """Handle palette swatch hover - highlight pixels on canvas."""
        if index is None or isinstance(index, int):
            self._alignment_canvas.highlight_pixels_by_index(index)

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _attempt_link(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Attempt to link an AI frame to a game frame.

        Handles existing link confirmation (for both AI and game frames) and auto-advance.
        Preserves alignment if mapping already exists for the same pair.

        Args:
            ai_frame_id: AI frame ID (filename)
            game_frame_id: Game frame ID
        """
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
            if not confirm_replace_ai_frame_link(self, ai_name, existing_game_link, game_frame_id):
                return

        # Check if game frame is already linked to a different AI frame
        existing_ai_link = self._controller.get_existing_link_for_game_frame(game_frame_id)
        if existing_ai_link is not None and existing_ai_link != ai_frame_id:
            existing_ai = project.get_ai_frame_by_id(existing_ai_link)
            existing_name = existing_ai.path.name if existing_ai else existing_ai_link

            if not confirm_replace_link(self, game_frame_id, existing_name, ai_name):
                return

        # Create the mapping
        self._controller.create_mapping(ai_frame_id, game_frame_id)

        # Auto-align using bounding box alignment (center AI content over game content)
        if ai_frame and ai_frame.path.exists():
            capture_result, _used_fallback = self._controller.get_capture_result_for_game_frame(game_frame_id)
            if capture_result and capture_result.has_entries:
                try:
                    ai_pil = Image.open(ai_frame.path).convert("RGBA")
                    bbox = capture_result.bounding_box
                    # Use (0, 0) for game bbox position since that's where it's displayed on canvas
                    # (not the screen-relative capture coordinates)
                    offset_x, offset_y = calculate_auto_alignment(ai_pil, 0, 0, bbox.width, bbox.height)
                    self._controller.update_mapping_alignment(
                        ai_frame_id, offset_x, offset_y, False, False, set_edited=False
                    )
                except Exception as e:
                    logger.warning("Auto-alignment failed, using center: %s", e)
                    # Fallback to simple centering
                    game_preview = self._controller.get_game_frame_preview(game_frame_id)
                    if game_preview:
                        ai_pixmap = QPixmap(str(ai_frame.path))
                        if not ai_pixmap.isNull():
                            center_x = (game_preview.width() - ai_pixmap.width()) // 2
                            center_y = (game_preview.height() - ai_pixmap.height()) // 2
                            self._controller.update_mapping_alignment(
                                ai_frame_id, center_x, center_y, False, False, set_edited=False
                            )
            else:
                # No capture result - fallback to simple centering
                game_preview = self._controller.get_game_frame_preview(game_frame_id)
                if game_preview:
                    ai_pixmap = QPixmap(str(ai_frame.path))
                    if not ai_pixmap.isNull():
                        center_x = (game_preview.width() - ai_pixmap.width()) // 2
                        center_y = (game_preview.height() - ai_pixmap.height()) // 2
                        self._controller.update_mapping_alignment(
                            ai_frame_id, center_x, center_y, False, False, set_edited=False
                        )

        self._refresh_mapping_status()
        self._refresh_game_frame_link_status()
        self._update_mapping_panel_previews()

        # Update canvas with alignment using ID-based lookup (O(1))
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping:
            self._alignment_canvas.set_alignment(
                mapping.offset_x, mapping.offset_y, mapping.flip_h, mapping.flip_v, mapping.scale
            )

        if self._message_service:
            self._message_service.show_message(f"Linked '{ai_name}' to '{game_frame_id}'", 3000)

        # Auto-advance if enabled
        if self._state.auto_advance_enabled and ai_frame:
            next_unmapped_id = self._find_next_unmapped_ai_frame(ai_frame.index)
            if next_unmapped_id is not None:
                next_frame = project.get_ai_frame_by_id(next_unmapped_id)
                if next_frame:
                    self._ai_frames_pane.select_frame(next_frame.index)
                    self._on_ai_frame_selected(next_unmapped_id)

    def _find_next_unmapped_ai_frame(self, current_index: int) -> str | None:
        """Find the next unmapped AI frame after the given index.

        Args:
            current_index: Current AI frame index

        Returns:
            AI frame ID of the next unmapped frame, or None if all are mapped
        """
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

    def _update_map_button_state(self) -> None:
        """Update the Map Selected button enabled state."""
        # Query fresh selection state from panes (source of truth)
        ai_frame_id = self._get_selected_ai_frame_id()
        game_id = self._get_selected_game_id()
        both_selected = ai_frame_id is not None and game_id is not None
        self._ai_frames_pane.set_map_button_enabled(both_selected)

    def _refresh_mapping_status(self) -> None:
        """Refresh the AI frame mapping status indicators.

        Note: This only updates status indicators. Callers that also need
        to refresh the mapping panel table should call _update_mapping_panel_previews()
        or _mapping_panel.refresh() separately.
        """
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

    def _refresh_game_frame_link_status(self) -> None:
        """Refresh the game frame link status indicators."""
        project = self._controller.project
        if project is None:
            self._captures_pane.set_link_status({})
            return

        link_status: dict[str, str | None] = {}
        for game_frame in project.game_frames:
            linked_ai_id = project.get_ai_frame_linked_to_game_frame(game_frame.id)
            link_status[game_frame.id] = linked_ai_id

        self._captures_pane.set_link_status(link_status)

    def _update_mapping_panel_previews(self) -> None:
        """Update the mapping panel with game frame preview pixmaps."""
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

    def _sync_canvas_alignment_from_model(self) -> None:
        """Sync the canvas alignment display with the current model state.

        Called after undo/redo to ensure the canvas reflects restored values.
        Queries the current AI frame's mapping and updates the canvas if a mapping exists.
        """
        ai_frame_id = self._get_selected_ai_frame_id()
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
        else:
            # No mapping - clear alignment
            self._alignment_canvas.clear_alignment()

    def _on_preview_cache_invalidated(self, frame_id: str) -> None:
        """Handle preview cache invalidation for a specific game frame.

        Updates the mapping panel, captures pane, and workbench canvas (if displaying
        the invalidated frame) with the fresh preview.

        Args:
            frame_id: The game frame ID whose preview was regenerated
        """
        preview = self._controller.get_game_frame_preview(frame_id)
        if preview:
            # Update mapping panel with the fresh preview
            self._mapping_panel.update_game_frame_preview(frame_id, preview)
            # Update captures pane thumbnail
            self._captures_pane.update_frame_preview(frame_id, preview)

            # Also update workbench canvas if this frame is currently displayed
            if self._state.current_canvas_game_id == frame_id:
                project = self._controller.project
                if project:
                    game_frame = project.get_game_frame_by_id(frame_id)
                    if game_frame:
                        capture_result, used_fallback = self._controller.get_capture_result_for_game_frame(frame_id)
                        self._alignment_canvas.set_game_frame(game_frame, preview, capture_result, used_fallback)

            logger.debug("Updated thumbnails for invalidated preview: %s", frame_id)

    # -------------------------------------------------------------------------
    # Capture Import Handler
    # -------------------------------------------------------------------------

    def _on_capture_import_requested(self, capture_result: CaptureResult, capture_path: object) -> None:
        """Handle capture import request - delegate to dialog coordinator.

        For single imports, shows dialog immediately.
        For directory imports, queues the capture and processes sequentially.

        Args:
            capture_result: Parsed capture result from controller
            capture_path: Path to the capture file (typed as object due to Signal limitation)
        """
        if not isinstance(capture_path, Path):
            return

        # Queue the capture via dialog coordinator
        self._dialog_coordinator.queue_capture_import(capture_result, capture_path)

        # If this is the only pending capture, process it immediately
        if self._dialog_coordinator.get_queue_size() == 1:
            self._dialog_coordinator.process_capture_import_queue(self, self._controller)

    def _on_capture_queue_finished(self, import_count: int) -> None:
        """Handle completion of capture import queue.

        Args:
            import_count: Number of successfully imported captures
        """
        if self._message_service and import_count > 0:
            self._message_service.show_message(f"Imported {import_count} captures")

    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------

    def _on_load_ai_frames(self) -> None:
        """Handle load AI frames button click."""
        start_dir = str(self._state.last_ai_dir) if self._state.last_ai_dir else ""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select AI Frames Directory",
            start_dir,
        )
        if directory:
            path = Path(directory)
            self._state.last_ai_dir = path
            # Update the current tab to associate with this folder
            self._ai_frames_pane.set_current_tab_folder(path)
            self._controller.load_ai_frames_from_directory(path)

    def _on_ai_folder_dropped(self, path: object) -> None:
        """Load AI frames from dropped folder.

        Args:
            path: Path object (typed as object due to Signal limitation)
        """
        if not isinstance(path, Path) or not path.is_dir():
            return
        self._state.last_ai_dir = path

        # If current tab is empty, update it; otherwise add new tab
        if self._ai_frames_pane.get_current_tab_folder() is None:
            self._ai_frames_pane.set_current_tab_folder(path)
        else:
            self._ai_frames_pane.add_folder_tab(path)
            # Note: add_folder_tab emits tab_folder_changed which will load frames
            return

        self._controller.load_ai_frames_from_directory(path)

    def _on_ai_tab_folder_changed(self, path: object) -> None:
        """Reload frames when tab changes.

        Args:
            path: Path | None (typed as object due to Signal limitation)
        """
        if path is not None and isinstance(path, Path) and path.is_dir():
            self._state.last_ai_dir = path
            self._controller.load_ai_frames_from_directory(path)
        elif self._controller.project is not None:
            # Empty tab - clear frames and orphaned mappings
            self._controller.project.replace_ai_frames([], None)
            self._controller.project.filter_mappings_by_valid_ai_ids(set())
            self._controller.project_changed.emit()

    def _on_frame_rename_requested(self, frame_id: str, display_name: str) -> None:
        """Handle frame rename request from AI Frames pane.

        Args:
            frame_id: ID of the frame to rename
            display_name: New display name (empty string clears)
        """
        # Empty string means clear display name
        name = display_name if display_name else None
        self._controller.rename_frame(frame_id, name)

    def _on_frame_tag_toggled(self, frame_id: str, tag: str) -> None:
        """Handle frame tag toggle request from AI Frames pane.

        Args:
            frame_id: ID of the frame
            tag: Tag to toggle
        """
        self._controller.toggle_frame_tag(frame_id, tag)

    def _on_frame_organization_changed(self, frame_id: str) -> None:
        """Handle frame rename/tag change - refresh UI.

        Args:
            frame_id: ID of the frame that changed
        """
        self._ai_frames_pane.refresh_frame(frame_id)

    def _on_capture_rename_requested(self, frame_id: str, new_name: str) -> None:
        """Handle capture rename request from Captures Library pane.

        Args:
            frame_id: ID of the capture to rename
            new_name: New display name (empty to clear)
        """
        self._controller.rename_capture(frame_id, new_name)

    def _on_capture_organization_changed(self, frame_id: str) -> None:
        """Handle capture rename - refresh UI.

        Args:
            frame_id: ID of the capture that changed
        """
        self._captures_pane.refresh_frame(frame_id)

    def _on_import_capture(self) -> None:
        """Handle import capture button click."""
        start_dir = str(self._state.last_capture_dir) if self._state.last_capture_dir else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Mesen 2 Capture",
            start_dir,
            "JSON Files (*.json);;All Files (*)",
        )
        if file_path:
            path = Path(file_path)
            self._state.last_capture_dir = path.parent
            # Controller will emit capture_import_requested, handled by _on_capture_import_requested
            self._controller.import_mesen_capture(path)

    def _on_import_capture_dir(self) -> None:
        """Handle import capture directory button click."""
        start_dir = str(self._state.last_capture_dir) if self._state.last_capture_dir else ""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Captures Directory",
            start_dir,
        )
        if directory:
            path = Path(directory)
            self._state.last_capture_dir = path
            # Clear queue for this batch
            self._dialog_coordinator.clear_queue()
            # Controller will emit capture_import_requested for each capture
            # _on_capture_import_requested queues them via dialog coordinator
            self._controller.import_capture_directory(path)

    def _on_load_project(self) -> None:
        """Handle load project button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Frame Mapping Project",
            "",
            "Frame Mapping Projects (*.spritepal-mapping.json);;All Files (*)",
        )
        if file_path:
            path = Path(file_path)
            if self._controller.load_project(path):
                self._state.project_path = path
                self._set_last_project_path(path)

    def _on_save_project(self) -> None:
        """Handle save project button click."""
        if not self._controller.has_project:
            QMessageBox.information(self, "Save Project", "No project to save.")
            return

        path_to_save = self._state.project_path

        if not path_to_save:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Frame Mapping Project",
                "mapping.spritepal-mapping.json",
                "Frame Mapping Projects (*.spritepal-mapping.json);;All Files (*)",
            )
            if file_path:
                path_to_save = Path(file_path)

        if path_to_save:
            if self._controller.save_project(path_to_save):
                self._state.project_path = path_to_save
                self._set_last_project_path(path_to_save)
                if self._message_service:
                    self._message_service.show_message(f"Project saved to {path_to_save.name}")

    # -------------------------------------------------------------------------
    # Project Persistence
    # -------------------------------------------------------------------------

    def _auto_load_last_project(self) -> None:
        """Auto-load the last used project on startup."""
        last_path = self._get_last_project_path()
        if last_path and last_path.exists():
            logger.info("Auto-loading last project: %s", last_path)
            if self._controller.load_project(last_path):
                self._state.project_path = last_path
            else:
                logger.warning("Failed to auto-load last project")

    def _get_last_project_path(self) -> Path | None:
        """Get the last used project path from settings."""
        ctx = get_app_context()
        path_str = ctx.application_state_manager.get("frame_mapping", "last_project_path")
        if path_str and isinstance(path_str, str):
            return Path(path_str)
        return None

    def _set_last_project_path(self, path: Path) -> None:
        """Save the last used project path to settings."""
        ctx = get_app_context()
        ctx.application_state_manager.set("frame_mapping", "last_project_path", str(path))

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def controller(self) -> FrameMappingController:
        """Get the frame mapping controller."""
        return self._controller

    def cleanup(self) -> None:
        """Cleanup resources."""
        logger.debug("FrameMappingWorkspace cleanup")
