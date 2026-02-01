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
from typing import TYPE_CHECKING, override

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
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
from core.types import CompressionType
from ui.components.inputs.file_selector import FileSelector
from ui.frame_mapping.auto_save_manager import AutoSaveManager
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.dialog_coordinator import DialogCoordinator
from ui.frame_mapping.frame_operations_coordinator import FrameOperationsCoordinator
from ui.frame_mapping.injection_coordinator import InjectionCoordinator
from ui.frame_mapping.palette_coordinator import PaletteCoordinator
from ui.frame_mapping.signal_error_handling import signal_error_boundary
from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane
from ui.frame_mapping.views.mapping_panel import MappingPanel
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas
from ui.frame_mapping.views.workbench_types import AlignmentState
from ui.frame_mapping.workspace_logic_helper import WorkspaceLogicHelper
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

        # Dialog coordinator for capture imports and confirmations
        self._dialog_coordinator = DialogCoordinator(self)

        # Create or inject controller
        self._controller = controller or self._create_default_controller()

        # Auto-save debounce timer (500ms delay to avoid saving on every nudge)
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(500)

        # Auto-save manager handles the save logic
        self._auto_save_manager = AutoSaveManager(
            timer=self._auto_save_timer,
            get_project_path=lambda: self._state.project_path,
            save_project=self._controller.save_project,
            parent_widget=self,
            on_save_success=lambda: setattr(self._state, "dirty", False),
        )
        self._auto_save_timer.timeout.connect(self._auto_save_manager.perform_save)

        # Logic helper handles operations spanning multiple panes
        self._logic = WorkspaceLogicHelper()
        self._logic.set_controller(self._controller)
        self._logic.set_state(self._state)
        self._logic.set_parent_widget(self)

        # Injection coordinator handles ROM injection operations
        self._injection = InjectionCoordinator()
        self._injection.set_controller(self._controller)
        self._injection.set_state(self._state)
        self._injection.set_parent_widget(self)

        # Palette coordinator handles palette dialogs and editor windows
        self._palette = PaletteCoordinator()
        self._palette.set_controller(self._controller)
        self._palette.set_state(self._state)
        self._palette.set_parent_widget(self)

        # Frame operations coordinator handles delete, remove, edit operations
        self._frame_ops = FrameOperationsCoordinator()
        self._frame_ops.set_controller(self._controller)
        self._frame_ops.set_state(self._state)
        self._frame_ops.set_parent_widget(self)

        # Wire message service to coordinators if provided at construction time
        if message_service is not None:
            self._auto_save_manager.set_message_service(message_service.show_message)
            self._logic.set_message_service(message_service)
            self._injection.set_message_service(message_service)
            self._palette.set_message_service(message_service)
            self._frame_ops.set_message_service(message_service)

        self._setup_ui()

        # Inject panes into logic helper after UI setup
        self._logic.set_panes(
            self._ai_frames_pane,
            self._captures_pane,
            self._mapping_panel,
            self._alignment_canvas,
        )

        # Inject panes into coordinators after UI setup
        self._injection.set_mapping_panel(self._mapping_panel)
        self._injection.set_alignment_canvas(self._alignment_canvas)
        self._injection.set_ui_callbacks(
            get_reuse_rom_enabled=lambda: self._reuse_rom_checkbox.isChecked(),
            update_frame_status=self._update_single_ai_frame_status,
        )

        self._palette.set_panes(
            self._ai_frames_pane,
            self._mapping_panel,
            self._alignment_canvas,
        )
        self._palette.set_workspace_callbacks(
            on_ai_frame_selected=self._on_ai_frame_selected,
        )

        self._frame_ops.set_panes(self._alignment_canvas, self._captures_pane)
        self._frame_ops.set_callbacks(
            update_map_button_state=self._update_map_button_state,
            request_edit_in_sprite_editor=self.edit_in_sprite_editor_requested.emit,
        )

        self._connect_signals()
        self._setup_shortcuts()

        # Auto-load last project if available
        self._auto_load_last_project()

        # Auto-load last ROM if not set by MainWindow
        self._auto_load_rom()

        logger.debug("FrameMappingWorkspace initialized with 4-zone layout")

    def set_message_service(self, service: StatusBarManager | None) -> None:
        """Set the message service for status updates."""
        self._message_service = service
        self._auto_save_manager.set_message_service(service.show_message if service else None)
        self._logic.set_message_service(service)
        self._injection.set_message_service(service)
        self._palette.set_message_service(service)
        self._frame_ops.set_message_service(service)

    def set_rom_path(self, rom_path: Path | None) -> None:
        """Set ROM path for injection.

        Called when switching from sprite editor workspace or user selection.
        Resets the modified ROM path since a new original ROM is being used.

        Args:
            rom_path: Path to the ROM file, or None to clear.
        """
        if rom_path != self._state.rom_path:
            logger.info("FrameMapping ROM path updated: %s", rom_path)
            self._state.rom_path = rom_path
            self._state.modified_rom_path = None

            # Sync widget display if ROM selector exists
            if hasattr(self, "_rom_selector"):
                self._rom_selector.set_path(str(rom_path) if rom_path else "")

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
                "No ROM loaded.\n\nPlease select a ROM using the ROM selector in the header.",
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

    @signal_error_boundary()
    def _on_rom_selector_changed(self, path_str: str) -> None:
        """Handle ROM selection from header widget."""
        if not path_str:
            return

        rom_path = Path(path_str)

        # Validate file exists
        if not rom_path.exists():
            QMessageBox.warning(self, "Invalid ROM", f"File not found: {rom_path}")
            return

        # Validate extension
        if rom_path.suffix.lower() not in (".sfc", ".smc", ".bin"):
            QMessageBox.warning(self, "Invalid ROM", "File must be .sfc, .smc, or .bin")
            return

        # Update state
        self._state.rom_path = rom_path
        self._state.modified_rom_path = None  # Clear - new source = fresh start
        self._state.last_injected_rom = None

        # Persist to settings
        context = get_app_context()
        context.application_state_manager.set("rom_injection", "last_input_rom", str(rom_path))

        logger.info("ROM selected from header: %s", rom_path)

    def _auto_load_rom(self) -> None:
        """Auto-load last used ROM if not set by MainWindow."""
        if self._state.rom_path is not None:
            # Already set by MainWindow - sync display
            self._rom_selector.set_path(str(self._state.rom_path))
            return

        # Try to load from settings
        context = get_app_context()
        last_rom_str = str(context.application_state_manager.get("rom_injection", "last_input_rom", ""))

        if last_rom_str:
            last_rom = Path(last_rom_str)
            if last_rom.exists():
                self._state.rom_path = last_rom
                self._rom_selector.set_path(last_rom_str)
                logger.info("Auto-loaded ROM from settings: %s", last_rom)

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

        # Save status indicator (hidden by default, shown on save failure)
        self._save_status_label = QLabel("⚠ Save Failed")
        self._save_status_label.setStyleSheet(
            "background-color: #a33; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;"
        )
        self._save_status_label.hide()
        layout.addWidget(self._save_status_label)

        # Separator before ROM selector
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet("color: #666;")
        layout.addWidget(separator)

        # ROM selector
        rom_label = QLabel("ROM:")
        rom_label.setStyleSheet("color: #aaa;")
        layout.addWidget(rom_label)

        context = get_app_context()
        self._rom_selector = FileSelector(
            parent=header,
            placeholder="No ROM selected",
            dialog_title="Select ROM File",
            file_filter="SNES ROM Files (*.sfc *.smc);;All Files (*.*)",
            mode="open",
            read_only=True,  # Browse only, no typing
            settings_manager=context.application_state_manager,
        )
        self._rom_selector.setMinimumWidth(200)
        self._rom_selector.setMaximumWidth(400)
        self._rom_selector.path_changed.connect(self._on_rom_selector_changed)
        layout.addWidget(self._rom_selector)

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
        # Auto-save manager signals
        self._auto_save_manager.save_failed.connect(self._on_save_failed)
        self._auto_save_manager.save_succeeded.connect(self._on_save_succeeded)

        # Controller signals
        self._controller.project_changed.connect(self._on_project_changed)
        self._controller.ai_frames_loaded.connect(self._on_ai_frames_loaded)
        self._controller.game_frame_added.connect(self._on_game_frame_added)
        self._controller.mapping_created.connect(self._on_mapping_created)
        self._controller.mapping_removed.connect(self._on_mapping_removed)
        self._controller.mapping_injected.connect(self._on_mapping_injected)
        self._controller.error_occurred.connect(self._on_error)
        self._controller.status_update.connect(self._on_status_update)
        self._controller.save_requested.connect(self._auto_save_manager.schedule_save)
        self._controller.save_requested.connect(self._state.mark_dirty)
        self._controller.stale_entries_warning.connect(self._on_stale_entries_warning)
        self._controller.stale_entries_on_load.connect(self._on_stale_entries_detected_on_load)
        self._controller.alignment_updated.connect(self._on_alignment_updated)
        self._controller.preview_cache_invalidated.connect(self._on_preview_cache_invalidated)
        self._controller.capture_import_requested.connect(self._on_capture_import_requested)
        self._controller.directory_import_started.connect(self._on_directory_import_started)
        self._controller.directory_import_finished.connect(self._on_directory_import_finished)
        self._controller.game_frame_removed.connect(self._on_game_frame_removed)
        # Async game frame preview signals (Phase 6 perf improvement)
        self._controller.game_frame_preview_ready.connect(self._on_game_frame_preview_ready)
        self._controller.game_frame_previews_finished.connect(self._on_game_frame_previews_finished)
        # Async injection signals (Issue 8 perf improvement)
        self._controller.async_injection_started.connect(self._on_async_injection_started)
        self._controller.async_injection_progress.connect(self._on_async_injection_progress)
        self._controller.async_injection_finished.connect(self._on_async_injection_finished)

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
        self._ai_frames_pane.file_dropped.connect(self._on_ai_file_dropped)
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
        self._mapping_panel.row_reorder_requested.connect(self._on_row_reorder_requested)
        self._controller.ai_frame_moved.connect(self._on_ai_frame_moved)
        self._controller.ai_frame_added.connect(self._on_ai_frame_added)

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
        """Get the currently selected AI frame ID."""
        return self._logic.get_selected_ai_frame_id()

    def _get_selected_game_id(self) -> str | None:
        """Get the currently selected game frame ID."""
        return self._logic.get_selected_game_id()

    @signal_error_boundary()
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

    @signal_error_boundary()
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

    @signal_error_boundary()
    def _on_save_failed(self) -> None:
        """Handle save failure - show persistent indicator."""
        self._save_status_label.show()
        logger.debug("Save failure indicator displayed")

    @signal_error_boundary()
    def _on_save_succeeded(self) -> None:
        """Handle save success - hide failure indicator."""
        self._save_status_label.hide()
        logger.debug("Save failure indicator hidden")

    @signal_error_boundary()
    def _on_auto_advance_changed(self, enabled: bool) -> None:
        """Handle auto-advance toggle change."""
        self._state.auto_advance_enabled = enabled
        logger.debug("Auto-advance %s", "enabled" if enabled else "disabled")

    @signal_error_boundary()
    def _on_project_changed(self) -> None:
        """Handle project changes.

        Only clears canvas when project identity changes (new/load),
        not on content updates within the same project.
        """
        project = self._controller.project

        # Check if project identity changed (new project loaded vs content update)
        current_project_id = id(project) if project is not None else None
        project_identity_changed = current_project_id != self._state.previous_project_id
        logger.debug(
            "_on_project_changed: prev_id=%s, curr_id=%s, identity_changed=%s",
            self._state.previous_project_id,
            current_project_id,
            project_identity_changed,
        )
        self._state.previous_project_id = current_project_id

        # Only clear canvas on actual project change, not content updates
        if project_identity_changed:
            logger.debug("_on_project_changed: identity changed - will call set_project()")
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
        # Only call set_project on identity change to avoid resetting checkbox state
        if project_identity_changed:
            self._mapping_panel.set_project(project)
        self._mapping_panel.set_sheet_palette(project.sheet_palette)  # Sync mapping panel palette
        self._update_map_button_state()
        self._refresh_mapping_status()
        self._refresh_game_frame_link_status()
        self._update_mapping_panel_previews()

    @signal_error_boundary()
    def _on_ai_frames_loaded(self, count: int) -> None:
        """Handle AI frames loaded."""
        # Reset batch selection to defaults (all mapped = checked)
        self._mapping_panel.reset_batch_selection()
        if self._message_service:
            self._message_service.show_message(f"Loaded {count} AI frames")

    @signal_error_boundary()
    def _on_game_frame_added(self, frame_id: str) -> None:
        """Handle game frame added."""
        if self._message_service:
            self._message_service.show_message(f"Imported game frame: {frame_id}")

    @signal_error_boundary()
    def _on_game_frame_removed(self, frame_id: str) -> None:
        """Handle game frame removed - remove from captures pane.

        Args:
            frame_id: ID of the game frame that was removed
        """
        self._captures_pane.remove_game_frame(frame_id)

    @signal_error_boundary()
    def _on_mapping_created(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Handle mapping created - targeted UI update.

        Only updates the specific UI elements affected by the mapping creation,
        avoiding full list rebuilds for better performance.

        Args:
            ai_frame_id: The AI frame ID that was mapped
            game_frame_id: The game frame ID it was mapped to
        """
        self._update_map_button_state()
        # Use targeted single-item updates instead of full refresh
        self._update_single_ai_frame_status(ai_frame_id)
        self._update_single_game_frame_link_status(game_frame_id)
        self._update_single_mapping_panel_row(ai_frame_id)

    @signal_error_boundary()
    def _on_mapping_removed(self, ai_frame_id: str) -> None:
        """Handle mapping removed - targeted UI update.

        Only updates the UI elements affected by mapping removal,
        avoiding full project refresh for better performance.

        Note: We use full refresh for game frame link status because
        the mapping has already been removed and we don't have the
        game_frame_id that was unlinked.
        """
        self._update_map_button_state()
        # Use targeted update for AI frame status (we know which one changed)
        self._update_single_ai_frame_status(ai_frame_id)
        # Must use full refresh for captures - we don't know which game frame was unlinked
        self._refresh_game_frame_link_status()
        # Use targeted clear instead of full refresh (avoids regenerating all thumbnails)
        self._mapping_panel.clear_row_mapping(ai_frame_id)

        # Clear browsing mode if the removed mapping was for the selected AI frame
        # When a mapping is removed, there's nothing to "browse away from"
        if ai_frame_id == self._state.selected_ai_frame_id:
            self._alignment_canvas.set_browsing_mode(False)

    @signal_error_boundary()
    def _on_error(self, message: str) -> None:
        """Handle error from controller."""
        logger.error("Frame mapping error: %s", message)
        QMessageBox.warning(self, "Error", message)

    @signal_error_boundary()
    def _on_status_update(self, message: str) -> None:
        """Handle status update from controller."""
        logger.info("Frame mapping status received: %s", message)
        if self._message_service:
            logger.debug("Showing message via status bar: %s", message)
            self._message_service.show_message(message, 5000)
        else:
            logger.warning("No message service set - status update not shown in UI")

    @signal_error_boundary()
    def _on_ai_frame_selected(self, frame_id: str) -> None:
        """Handle AI frame selection in left pane."""
        self._logic.handle_ai_frame_selected(frame_id)

    @signal_error_boundary()
    def _on_game_frame_selected(self, frame_id: str) -> None:
        """Handle game frame selection in captures library."""
        self._logic.handle_game_frame_selected(frame_id)

    @signal_error_boundary()
    def _on_mapping_selected(self, ai_frame_id: str) -> None:
        """Handle mapping row selection in drawer."""
        self._logic.handle_mapping_selected(ai_frame_id)

    @signal_error_boundary()
    def _on_map_selected(self) -> None:
        """Handle map button click in AI frames pane."""
        self._logic.handle_map_selected()

    @signal_error_boundary()
    def _on_drop_game_frame(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Handle game frame dropped onto drawer row."""
        self._logic.handle_drop_game_frame(ai_frame_id, game_frame_id)

    @signal_error_boundary()
    def _on_alignment_changed(self, state: AlignmentState) -> None:
        """Handle alignment change from canvas (auto-save)."""
        self._logic.handle_alignment_changed(state)

    @signal_error_boundary()
    def _on_compression_type_changed(self, compression_type: CompressionType) -> None:
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

    @signal_error_boundary()
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

    @signal_error_boundary()
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

        # Select the frame and trigger handler via signal (P2: unified signal pattern)
        # Use ID-based selection (stable across reordering)
        self._ai_frames_pane.select_frame_by_id(ai_frame_id, emit_signal=True)

        # Focus the canvas for keyboard input
        self._alignment_canvas.focus_canvas()

        if self._message_service:
            self._message_service.show_message("Use arrow keys to adjust alignment")

    @signal_error_boundary()
    def _on_edit_frame(self, ai_frame_id: str) -> None:
        """Handle edit AI frame request."""
        self._frame_ops.handle_edit_frame(ai_frame_id)

    @signal_error_boundary()
    def _on_edit_game_frame(self, frame_id: str) -> None:
        """Handle edit game frame request from captures library."""
        self._frame_ops.handle_edit_game_frame(frame_id)

    @signal_error_boundary()
    def _on_edit_frame_palette(self, ai_frame_id: str) -> None:
        """Handle edit frame palette request. Delegates to PaletteCoordinator."""
        self._palette.handle_edit_frame_palette(ai_frame_id)

    # -------------------------------------------------------------------------
    # Palette Editor Properties (for backward compatibility)
    # -------------------------------------------------------------------------

    @property
    def _palette_editors(self) -> dict:  # type: ignore[type-arg]
        """Access palette editors dict via PaletteCoordinator.

        Note: This property allows existing code referencing self._palette_editors
        to continue working. New code should use self._palette.palette_editors.
        """
        return self._palette.palette_editors

    @signal_error_boundary()
    def _on_editor_palette_color_changed(self, index: int, color: tuple[int, int, int]) -> None:
        """Handle palette color change from palette editor window. Delegates to PaletteCoordinator."""
        self._palette._handle_editor_palette_color_changed(index, color)

    @signal_error_boundary()
    def _on_delete_capture(self, frame_id: str) -> None:
        """Handle delete capture request."""
        self._frame_ops.handle_delete_capture(frame_id)

    @signal_error_boundary()
    def _on_show_capture_details(self, frame_id: str) -> None:
        """Handle show details request for capture."""
        self._frame_ops.handle_show_capture_details(frame_id)

    @signal_error_boundary()
    def _on_remove_ai_frame(self, ai_frame_id: str) -> None:
        """Handle remove AI frame from project request."""
        self._frame_ops.handle_remove_ai_frame(ai_frame_id)

    @signal_error_boundary()
    def _on_remove_mapping(self, ai_frame_id: str) -> None:
        """Handle remove mapping request."""
        self._frame_ops.handle_remove_mapping(ai_frame_id)

    @signal_error_boundary()
    def _on_row_reorder_requested(self, ai_frame_id: str, target_index: int) -> None:
        """Handle row reorder request from mapping panel drag/drop.

        Args:
            ai_frame_id: ID of the AI frame being moved.
            target_index: Target position (0-based).
        """
        self._controller.reorder_ai_frame(ai_frame_id, target_index)

    @signal_error_boundary()
    def _on_ai_frame_moved(self, ai_frame_id: str, from_index: int, to_index: int) -> None:
        """Handle AI frame moved signal from controller.

        Uses targeted move_row/move_item instead of full refresh for performance.

        Args:
            ai_frame_id: ID of the moved frame
            from_index: Original position
            to_index: New position
        """
        # Use targeted move methods instead of full refresh
        self._ai_frames_pane.move_item(from_index, to_index)
        self._mapping_panel.move_row(from_index, to_index)

        # Update state to track the moved frame
        self._state.selected_ai_frame_id = ai_frame_id

    @signal_error_boundary()
    def _on_ai_frame_added(self, ai_frame_id: str) -> None:
        """Handle single AI frame added signal from controller.

        Uses targeted add methods instead of full refresh for performance.

        Args:
            ai_frame_id: ID of the added frame
        """
        project = self._controller.project
        if project is None:
            return

        # Find the newly added frame
        frame = project.get_ai_frame_by_id(ai_frame_id)
        if frame is None:
            return

        # Use targeted add methods instead of full refresh
        self._ai_frames_pane.add_single_item(frame)
        self._mapping_panel.add_row(frame)

        # Update mapping status (frame is unmapped by default)
        self._refresh_mapping_status()

    @signal_error_boundary()
    def _on_inject_single(self, ai_frame_id: str) -> None:
        """Handle inject single mapping request (async). Delegates to InjectionCoordinator."""
        self._injection.inject_single(ai_frame_id)

    @signal_error_boundary()
    def _on_inject_selected(self) -> None:
        """Handle inject selected frames request (async). Delegates to InjectionCoordinator."""
        selected_ids = self._mapping_panel.get_selected_for_injection()
        self._injection.inject_selected(selected_ids)

    @signal_error_boundary()
    def _on_inject_all(self) -> None:
        """Handle inject all mapped frames request (async). Delegates to InjectionCoordinator."""
        self._injection.inject_all()

    @signal_error_boundary()
    def _on_mapping_injected(self, ai_frame_id: str, message: str) -> None:
        """Handle successful injection signal. Delegates to InjectionCoordinator."""
        self._injection.handle_mapping_injected(ai_frame_id, message)

    @signal_error_boundary()
    def _on_stale_entries_warning(self, frame_id: str) -> None:
        """Handle stale entry ID warning from controller. Delegates to InjectionCoordinator."""
        self._injection.handle_stale_entries_warning(frame_id)

    @signal_error_boundary()
    def _on_stale_entries_detected_on_load(self, stale_frame_ids: list[str]) -> None:
        """Show warning when project loads with stale capture entries. Delegates to InjectionCoordinator."""
        self._injection.handle_stale_entries_on_load(stale_frame_ids)

    # -------------------------------------------------------------------------
    # Async Injection Handlers (Issue 8 Performance Fix)
    # -------------------------------------------------------------------------

    @signal_error_boundary()
    def _on_async_injection_started(self, ai_frame_id: str) -> None:
        """Handle async injection started signal. Delegates to InjectionCoordinator."""
        self._injection.handle_async_injection_started(ai_frame_id)

    @signal_error_boundary()
    def _on_async_injection_progress(self, ai_frame_id: str, message: str) -> None:
        """Handle async injection progress signal. Delegates to InjectionCoordinator."""
        self._injection.handle_async_injection_progress(ai_frame_id, message)

    @signal_error_boundary()
    def _on_async_injection_finished(self, ai_frame_id: str, success: bool, message: str) -> None:
        """Handle async injection completion signal. Delegates to InjectionCoordinator."""
        self._injection.handle_async_injection_finished(ai_frame_id, success, message)

    @signal_error_boundary()
    def _on_alignment_updated(self, ai_frame_id: str) -> None:
        """Handle alignment-only update from controller.

        This is a targeted signal that avoids the full project_changed refresh,
        which would blank the canvas. Only updates status indicators and syncs
        canvas if the modified frame is currently selected.
        """
        # Update mapping panel row (preserves checkbox state)
        project = self._controller.project
        if project is None:
            return
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping:
            # Delegate to logic helper for consistent update logic
            self._logic.update_single_mapping_panel_row(ai_frame_id)

        # Fix P1: Update canvas if the modified frame is currently selected
        # This ensures programmatic alignment changes (not from user drag) are visible
        if self._state.selected_ai_frame_id == ai_frame_id:
            self._sync_canvas_alignment_from_model()

        # Use targeted single-item update instead of full refresh
        # Only the specific AI frame's status indicator needs updating
        self._update_single_ai_frame_status(ai_frame_id)

    # -------------------------------------------------------------------------
    # Sheet Palette Handlers (delegated to PaletteCoordinator)
    # -------------------------------------------------------------------------

    @signal_error_boundary()
    def _on_palette_edit_requested(self) -> None:
        """Handle request to edit the sheet palette. Delegates to PaletteCoordinator."""
        self._palette.handle_palette_edit_requested()

    @signal_error_boundary()
    def _on_palette_extract_requested(self) -> None:
        """Handle request to extract palette from AI sheet. Delegates to PaletteCoordinator."""
        self._palette.handle_palette_extract_requested()

    @signal_error_boundary()
    def _on_palette_clear_requested(self) -> None:
        """Handle request to clear the sheet palette. Delegates to PaletteCoordinator."""
        self._palette.handle_palette_clear_requested()

    @signal_error_boundary()
    def _on_sheet_palette_changed(self) -> None:
        """Handle sheet palette change from controller. Delegates to PaletteCoordinator."""
        self._palette.handle_sheet_palette_changed()

    @signal_error_boundary()
    def _on_pixel_hovered(self, x: int, y: int, rgb: object, palette_index: int) -> None:
        """Handle pixel hover on workbench. Delegates to PaletteCoordinator."""
        self._palette.handle_pixel_hovered(x, y, rgb, palette_index)

    @signal_error_boundary()
    def _on_pixel_left(self) -> None:
        """Handle mouse leaving workbench. Delegates to PaletteCoordinator."""
        self._palette.handle_pixel_left()

    @signal_error_boundary()
    def _on_eyedropper_picked(self, rgb: object, palette_index: int) -> None:
        """Handle eyedropper pick. Delegates to PaletteCoordinator."""
        self._palette.handle_eyedropper_picked(rgb, palette_index)

    @signal_error_boundary()
    def _on_palette_color_changed(self, index: int, rgb: object) -> None:
        """Handle palette color change. Delegates to PaletteCoordinator."""
        self._palette.handle_palette_color_changed(index, rgb)

    @signal_error_boundary()
    def _on_palette_swatch_hovered(self, index: object) -> None:
        """Handle palette swatch hover. Delegates to PaletteCoordinator."""
        self._palette.handle_palette_swatch_hovered(index)

    # -------------------------------------------------------------------------
    # Helper Methods (delegated to WorkspaceLogicHelper)
    # -------------------------------------------------------------------------

    def _update_map_button_state(self) -> None:
        """Update the Map Selected button enabled state."""
        self._logic.update_map_button_state()

    def _refresh_mapping_status(self) -> None:
        """Refresh the AI frame mapping status indicators."""
        self._logic.refresh_mapping_status()

    def _refresh_game_frame_link_status(self) -> None:
        """Refresh the game frame link status indicators."""
        self._logic.refresh_game_frame_link_status()

    def _update_mapping_panel_previews(self) -> None:
        """Update the mapping panel with game frame preview pixmaps."""
        self._logic.update_mapping_panel_previews()

    def _update_single_ai_frame_status(self, ai_frame_id: str) -> None:
        """Update status for one AI frame only (performance optimization)."""
        self._logic.update_single_ai_frame_status(ai_frame_id)

    def _update_single_game_frame_link_status(self, game_frame_id: str) -> None:
        """Update link status for one game frame only (performance optimization)."""
        self._logic.update_single_game_frame_link_status(game_frame_id)

    def _update_single_mapping_panel_row(self, ai_frame_id: str) -> None:
        """Update one mapping panel row (performance optimization)."""
        self._logic.update_single_mapping_panel_row(ai_frame_id)

    def _sync_canvas_alignment_from_model(self) -> None:
        """Sync the canvas alignment display with the current model state."""
        self._logic.sync_canvas_alignment_from_model()

    @signal_error_boundary()
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

    @signal_error_boundary()
    def _on_game_frame_preview_ready(self, frame_id: str, pixmap: object) -> None:
        """Handle async game frame preview completion.

        Updates the mapping panel and captures pane with the newly generated preview.

        Args:
            frame_id: The game frame ID
            pixmap: The generated preview pixmap (typed as object due to Signal limitation)
        """
        from PySide6.QtGui import QPixmap

        if not isinstance(pixmap, QPixmap):
            logger.debug("_on_game_frame_preview_ready: pixmap is not QPixmap for %s", frame_id)
            return

        logger.debug("_on_game_frame_preview_ready: %s, pixmap null=%s", frame_id, pixmap.isNull())
        # Update mapping panel with the fresh preview
        self._mapping_panel.update_game_frame_preview(frame_id, pixmap)
        # Update captures pane thumbnail
        self._captures_pane.update_frame_preview(frame_id, pixmap)

    @signal_error_boundary()
    def _on_game_frame_previews_finished(self) -> None:
        """Handle async game frame preview batch completion.

        Currently just logs completion - UI updates happen incrementally
        via _on_game_frame_preview_ready.
        """
        logger.debug("Async game frame preview batch completed")

    # -------------------------------------------------------------------------
    # Capture Import Handler
    # -------------------------------------------------------------------------

    @signal_error_boundary()
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

    @signal_error_boundary()
    def _on_capture_queue_finished(self, import_count: int) -> None:
        """Handle completion of capture import queue.

        Args:
            import_count: Number of successfully imported captures
        """
        if self._message_service and import_count > 0:
            self._message_service.show_message(f"Imported {import_count} captures")

    @signal_error_boundary()
    def _on_directory_import_started(self, total_files: int) -> None:
        """Handle directory import started signal.

        Args:
            total_files: Total number of files to parse
        """
        if self._message_service:
            self._message_service.show_message(
                f"Parsing {total_files} capture file{'s' if total_files != 1 else ''}..."
            )

    @signal_error_boundary()
    def _on_directory_import_finished(self, parsed_count: int) -> None:
        """Handle directory import finished signal.

        Args:
            parsed_count: Number of successfully parsed captures
        """
        if self._message_service:
            if parsed_count > 0:
                self._message_service.show_message(f"Parsed {parsed_count} capture{'s' if parsed_count != 1 else ''}")
            else:
                self._message_service.show_message("No valid captures found in directory")

    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------

    @signal_error_boundary()
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

    @signal_error_boundary()
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

    @signal_error_boundary()
    def _on_ai_file_dropped(self, path: object) -> None:
        """Add a single AI frame from dropped PNG file.

        Args:
            path: Path object (typed as object due to Signal limitation)
        """
        if not isinstance(path, Path) or not path.is_file():
            return
        self._controller.add_ai_frame_from_file(path)

    @signal_error_boundary()
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
            self._controller.clear_undo_history()  # Clear undo: old commands reference deleted frames
            self._controller.project_changed.emit()

    @signal_error_boundary()
    def _on_frame_rename_requested(self, frame_id: str, display_name: str) -> None:
        """Handle frame rename request from AI Frames pane.

        Args:
            frame_id: ID of the frame to rename
            display_name: New display name (empty string clears)
        """
        # Empty string means clear display name
        name = display_name if display_name else None
        self._controller.rename_frame(frame_id, name)

    @signal_error_boundary()
    def _on_frame_tag_toggled(self, frame_id: str, tag: str) -> None:
        """Handle frame tag toggle request from AI Frames pane.

        Args:
            frame_id: ID of the frame
            tag: Tag to toggle
        """
        self._controller.toggle_frame_tag(frame_id, tag)

    @signal_error_boundary()
    def _on_frame_organization_changed(self, frame_id: str) -> None:
        """Handle frame rename/tag change - refresh UI.

        Args:
            frame_id: ID of the frame that changed
        """
        self._ai_frames_pane.refresh_frame(frame_id)

    @signal_error_boundary()
    def _on_capture_rename_requested(self, frame_id: str, new_name: str) -> None:
        """Handle capture rename request from Captures Library pane.

        Args:
            frame_id: ID of the capture to rename
            new_name: New display name (empty to clear)
        """
        self._controller.rename_capture(frame_id, new_name)

    @signal_error_boundary()
    def _on_capture_organization_changed(self, frame_id: str) -> None:
        """Handle capture rename - refresh UI.

        Args:
            frame_id: ID of the capture that changed
        """
        self._captures_pane.refresh_frame(frame_id)

    @signal_error_boundary()
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

    @signal_error_boundary()
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

    @signal_error_boundary()
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

    @signal_error_boundary()
    def _on_save_project(self) -> None:
        """Handle save project button click."""
        if not self._controller.has_project:
            QMessageBox.information(self, "Save Project", "No project to save.")
            return

        # Check if auto-save is in progress
        if self._auto_save_manager.is_save_in_progress:
            if self._message_service:
                self._message_service.show_message("Auto-save in progress, please wait...", 2000)
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
            # Acquire lock before saving to prevent auto-save from running
            if not self._auto_save_manager.try_acquire_save_lock():
                if self._message_service:
                    self._message_service.show_message("Save in progress, please wait...", 2000)
                return

            try:
                if self._controller.save_project(path_to_save):
                    self._state.project_path = path_to_save
                    self._set_last_project_path(path_to_save)
                    self._state.dirty = False  # Clear dirty flag on successful save
                    if self._message_service:
                        self._message_service.show_message(f"Project saved to {path_to_save.name}")
            finally:
                # Always release lock, even if save fails
                self._auto_save_manager.release_save_lock()

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
    # Close Event Handler
    # -------------------------------------------------------------------------

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle workspace close event with unsaved changes check.

        Shows a dialog if there are unsaved changes, offering Save/Discard/Cancel options.
        Skips the dialog if the widget is not visible (e.g., during test teardown).

        Args:
            event: The close event
        """
        # Skip dialog if widget isn't visible (e.g., during test teardown)
        # or if there are no unsaved changes
        if not self.isVisible() or not self._state.dirty:
            event.accept()
            return

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Do you want to save before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )

        if reply == QMessageBox.StandardButton.Save:
            # Trigger manual save
            self._on_save_project()
            # Only accept close if save succeeded (dirty flag cleared)
            if not self._state.dirty:
                event.accept()
            else:
                event.ignore()
        elif reply == QMessageBox.StandardButton.Discard:
            # Discard changes and close
            event.accept()
        else:  # Cancel
            # Abort close
            event.ignore()

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
        self._alignment_canvas.cleanup()
        self._ai_frames_pane.cleanup()
