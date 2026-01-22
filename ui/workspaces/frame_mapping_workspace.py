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

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
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
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.dialogs.replace_link_dialog import (
    confirm_replace_ai_frame_link,
    confirm_replace_link,
)
from ui.frame_mapping.views.ai_frames_pane import AIFramesPane
from ui.frame_mapping.views.captures_library_pane import CapturesLibraryPane
from ui.frame_mapping.views.mapping_panel import MappingPanel
from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas
from utils.logging_config import get_logger

if TYPE_CHECKING:
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
    ) -> None:
        super().__init__(parent)
        self._message_service = message_service
        self._last_ai_dir: Path | None = None
        self._last_capture_dir: Path | None = None
        self._project_path: Path | None = None

        # ROM tracking for injection (synced from sprite editor)
        self._rom_path: Path | None = None
        self._modified_rom_path: Path | None = None

        # Selection tracking
        self._selected_ai_index: int | None = None
        self._selected_game_id: str | None = None

        # Auto-advance toggle state (default: OFF per UX spec)
        self._auto_advance_enabled = False

        # Create controller
        self._controller = FrameMappingController(self)

        self._setup_ui()
        self._connect_signals()

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
        if rom_path != self._rom_path:
            logger.info("FrameMapping ROM path updated: %s", rom_path)
            self._rom_path = rom_path
            self._modified_rom_path = None

    def _validate_rom_path(self) -> bool:
        """Validate that the current ROM path is valid and exists.

        Returns:
            True if valid, False otherwise.
        """
        if self._rom_path is None:
            QMessageBox.information(
                self,
                "Injection Requirement",
                "No ROM loaded.\n\nPlease load a ROM in the Sprite Editor workspace first.",
            )
            return False

        if not self._rom_path.exists():
            QMessageBox.warning(
                self,
                "ROM Not Found",
                f"The ROM file from Sprite Editor no longer exists:\n{self._rom_path}\n\n"
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

        self._inject_btn = QPushButton("Inject All")
        self._inject_btn.setToolTip("Inject all mapped frames into ROM")
        self._inject_btn.clicked.connect(lambda: self._on_inject_all())
        self._inject_btn.setStyleSheet("background-color: #2c5d2c; font-weight: bold;")
        toolbar.addWidget(self._inject_btn)

        layout.addWidget(toolbar)

        return header

    def _connect_signals(self) -> None:
        """Connect signals between components."""
        # Controller signals
        self._controller.project_changed.connect(self._on_project_changed)
        self._controller.ai_frames_loaded.connect(self._on_ai_frames_loaded)
        self._controller.game_frame_added.connect(self._on_game_frame_added)
        self._controller.mapping_injected.connect(self._on_mapping_injected)
        self._controller.error_occurred.connect(self._on_error)
        self._controller.status_update.connect(self._on_status_update)
        self._controller.save_requested.connect(self._auto_save_after_injection)
        self._controller.stale_entries_warning.connect(self._on_stale_entries_warning)

        # AI Frames Pane signals
        self._ai_frames_pane.ai_frame_selected.connect(self._on_ai_frame_selected)
        self._ai_frames_pane.map_requested.connect(self._on_map_selected)
        self._ai_frames_pane.auto_advance_changed.connect(self._on_auto_advance_changed)
        self._ai_frames_pane.edit_in_sprite_editor_requested.connect(self._on_edit_frame)
        self._ai_frames_pane.remove_from_project_requested.connect(self._on_remove_ai_frame)

        # Captures Library Pane signals
        self._captures_pane.game_frame_selected.connect(self._on_game_frame_selected)
        self._captures_pane.edit_in_sprite_editor_requested.connect(self._on_edit_game_frame)
        self._captures_pane.delete_capture_requested.connect(self._on_delete_capture)
        self._captures_pane.show_details_requested.connect(self._on_show_capture_details)

        # Mapping Panel (Drawer) signals
        self._mapping_panel.mapping_selected.connect(self._on_mapping_selected)
        self._mapping_panel.edit_frame_requested.connect(self._on_edit_frame)
        self._mapping_panel.remove_mapping_requested.connect(self._on_remove_mapping)
        self._mapping_panel.adjust_alignment_requested.connect(self._on_adjust_alignment)
        self._mapping_panel.drop_game_frame_requested.connect(self._on_drop_game_frame)
        self._mapping_panel.inject_mapping_requested.connect(self._on_inject_single)

        # Alignment Canvas signals
        self._alignment_canvas.alignment_changed.connect(self._on_alignment_changed)
        self._alignment_canvas.compression_type_changed.connect(self._on_compression_type_changed)

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def _on_auto_advance_changed(self, enabled: bool) -> None:
        """Handle auto-advance toggle change."""
        self._auto_advance_enabled = enabled
        logger.debug("Auto-advance %s", "enabled" if enabled else "disabled")

    def _on_project_changed(self) -> None:
        """Handle project changes."""
        # Clear canvas first to prevent stale display during reload
        self._alignment_canvas.clear()

        project = self._controller.project
        if project is None:
            self._selected_ai_index = None
            self._selected_game_id = None
            self._project_label.setText("")
            self._ai_frames_pane.clear()
            self._captures_pane.clear()
            self._mapping_panel.set_project(None)
            self._alignment_canvas.clear()
            self._update_map_button_state()
            return

        self._project_label.setText(f"- {project.name}")
        self._ai_frames_pane.set_ai_frames(project.ai_frames)
        self._captures_pane.set_game_frames(project.game_frames)
        self._mapping_panel.set_project(project)
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

    def _on_ai_frame_selected(self, index: int) -> None:
        """Handle AI frame selection in left pane.

        Syncs with drawer and canvas. If mapped, shows alignment.

        Phase 2 fix: Guard against invalid selections (index < 0).
        """
        project = self._controller.project
        if project is None:
            return

        # Phase 2: Guard against invalid selections
        if index < 0:
            self._selected_ai_index = None
            self._update_map_button_state()
            self._alignment_canvas.set_ai_frame(None)
            self._alignment_canvas.clear_alignment()
            self._mapping_panel.clear_selection()
            return

        self._selected_ai_index = index
        self._update_map_button_state()

        # Sync drawer selection
        self._mapping_panel.select_row_by_ai_index(index)

        # Load AI frame into canvas
        frame = project.get_ai_frame_by_index(index)
        self._alignment_canvas.set_ai_frame(frame)

        # Check for mapping (use index-based lookup)
        mapping = project.get_mapping_for_ai_frame_index(index)
        if mapping:
            game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
            preview = self._controller.get_game_frame_preview(mapping.game_frame_id)
            capture_result = self._controller.get_capture_result_for_game_frame(mapping.game_frame_id)
            self._alignment_canvas.set_game_frame(game_frame, preview, capture_result)
            self._alignment_canvas.set_alignment(
                mapping.offset_x, mapping.offset_y, mapping.flip_h, mapping.flip_v, mapping.scale
            )
            # Sync captures selection
            self._captures_pane.select_frame(mapping.game_frame_id)
            self._selected_game_id = mapping.game_frame_id
        else:
            self._alignment_canvas.set_game_frame(None)
            self._alignment_canvas.clear_alignment()
            self._captures_pane.clear_selection()
            self._selected_game_id = None

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
            self._selected_game_id = None
            # Phase 3a fix: Clear canvas state
            self._alignment_canvas.set_game_frame(None)
            self._alignment_canvas.clear_alignment()
            self._update_map_button_state()
            return

        self._selected_game_id = frame_id
        self._update_map_button_state()

        # Show preview in canvas if AI frame is selected
        if self._selected_ai_index is not None:
            game_frame = project.get_game_frame_by_id(frame_id)
            preview = self._controller.get_game_frame_preview(frame_id)
            capture_result = self._controller.get_capture_result_for_game_frame(frame_id)
            self._alignment_canvas.set_game_frame(game_frame, preview, capture_result)

    def _on_mapping_selected(self, ai_frame_index: int) -> None:
        """Handle mapping row selection in drawer.

        Syncs with AI frames pane and canvas.
        """
        project = self._controller.project
        if project is None:
            return

        # Sync AI frames pane
        self._ai_frames_pane.select_frame(ai_frame_index)
        self._selected_ai_index = ai_frame_index

        # Load into canvas
        ai_frame = project.get_ai_frame_by_index(ai_frame_index)
        self._alignment_canvas.set_ai_frame(ai_frame)

        # Load game frame if mapped (use index-based lookup)
        mapping = project.get_mapping_for_ai_frame_index(ai_frame_index)
        if mapping:
            game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
            preview = self._controller.get_game_frame_preview(mapping.game_frame_id)
            capture_result = self._controller.get_capture_result_for_game_frame(mapping.game_frame_id)
            self._alignment_canvas.set_game_frame(game_frame, preview, capture_result)
            self._alignment_canvas.set_alignment(
                mapping.offset_x, mapping.offset_y, mapping.flip_h, mapping.flip_v, mapping.scale
            )
            # Sync captures selection
            self._captures_pane.select_frame(mapping.game_frame_id)
            self._selected_game_id = mapping.game_frame_id
        else:
            self._alignment_canvas.set_game_frame(None)
            self._alignment_canvas.clear_alignment()

        self._update_map_button_state()

    def _on_map_selected(self) -> None:
        """Handle map button click in AI frames pane."""
        if self._selected_ai_index is None:
            QMessageBox.information(self, "Map Frames", "Please select an AI frame first.")
            return

        if self._selected_game_id is None:
            QMessageBox.information(self, "Map Frames", "Please select a game frame first.")
            return

        self._attempt_link(self._selected_ai_index, self._selected_game_id)

    def _on_drop_game_frame(self, ai_index: int, game_frame_id: str) -> None:
        """Handle game frame dropped onto drawer row."""
        self._attempt_link(ai_index, game_frame_id)

    def _on_alignment_changed(self, x: int, y: int, flip_h: bool, flip_v: bool, scale: float) -> None:
        """Handle alignment change from canvas (auto-save)."""
        if self._selected_ai_index is None:
            return

        project = self._controller.project
        if project is None:
            return

        mapping = project.get_mapping_for_ai_frame_index(self._selected_ai_index)
        if mapping is None:
            return

        # Update alignment in controller (includes scale)
        self._controller.update_mapping_alignment(self._selected_ai_index, x, y, flip_h, flip_v, scale)
        self._mapping_panel.refresh()

    def _on_compression_type_changed(self, compression_type: str) -> None:
        """Handle compression type change from canvas.

        Updates all ROM offsets in the current game frame to use the selected
        compression type ("raw" or "hal").
        """
        if self._selected_game_id is None:
            return

        project = self._controller.project
        if project is None:
            return

        game_frame = project.get_game_frame_by_id(self._selected_game_id)
        if game_frame is None:
            return

        # Update compression type for all ROM offsets in this game frame
        for rom_offset in game_frame.rom_offsets:
            game_frame.compression_types[rom_offset] = compression_type

        # Mark project as changed to trigger save
        self._controller.project_changed.emit()
        logger.info(
            "Updated compression type for game frame %s to %s (%d offsets)",
            game_frame.id,
            compression_type,
            len(game_frame.rom_offsets),
        )

    def _on_adjust_alignment(self, ai_frame_index: int) -> None:
        """Handle adjust alignment request - focus the canvas."""
        # Select the row first
        self._ai_frames_pane.select_frame(ai_frame_index)
        self._on_ai_frame_selected(ai_frame_index)

        # Focus the canvas for keyboard input
        self._alignment_canvas.focus_canvas()

        if self._message_service:
            self._message_service.show_message("Use arrow keys to adjust alignment")

    def _on_edit_frame(self, ai_frame_index: int) -> None:
        """Handle edit AI frame request."""
        project = self._controller.project
        if project is None:
            return

        ai_frame = project.get_ai_frame_by_index(ai_frame_index)
        if ai_frame is None:
            return

        mapping = project.get_mapping_for_ai_frame_index(ai_frame_index)
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

        # Find if there's a linked AI frame (use index-based method)
        linked_ai_idx = project.get_ai_frame_index_linked_to_game_frame(frame_id)
        if linked_ai_idx is not None:
            ai_frame = project.get_ai_frame_by_index(linked_ai_idx)
            if ai_frame:
                self.edit_in_sprite_editor_requested.emit(ai_frame.path, game_frame.rom_offsets)
                return

        # No linked AI frame - emit with empty path (will need handling in main window)
        if self._message_service:
            self._message_service.show_message("No AI frame linked to this capture", 3000)

    def _on_delete_capture(self, frame_id: str) -> None:
        """Handle delete capture request."""
        project = self._controller.project
        if project is None:
            return

        # Check if linked (use index-based method)
        linked_ai_idx = project.get_ai_frame_index_linked_to_game_frame(frame_id)
        if linked_ai_idx is not None:
            reply = QMessageBox.question(
                self,
                "Delete Capture",
                f"This capture is linked to AI frame #{linked_ai_idx}.\n"
                "Deleting will also remove the mapping.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Remove the game frame (also removes any associated mapping)
        if self._controller.remove_game_frame(frame_id):
            # Phase 3b fix: Clear selection if deleted frame was selected
            if self._selected_game_id == frame_id:
                self._selected_game_id = None
                self._alignment_canvas.set_game_frame(None)
                self._alignment_canvas.clear_alignment()
                self._update_map_button_state()

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

    def _on_remove_ai_frame(self, index: int) -> None:
        """Handle remove AI frame from project request."""
        # Not implemented - would need controller support
        if self._message_service:
            self._message_service.show_message("Remove AI frame (not implemented)")

    def _on_remove_mapping(self, ai_frame_index: int) -> None:
        """Handle remove mapping request."""
        self._controller.remove_mapping(ai_frame_index)
        self._refresh_mapping_status()
        self._refresh_game_frame_link_status()
        self._alignment_canvas.clear_alignment()
        # Phase 3c fix: Clear game frame from canvas and update map button
        self._alignment_canvas.set_game_frame(None)
        self._captures_pane.clear_selection()
        # Phase 3c fix: Clear selected game ID and update Map button
        self._selected_game_id = None
        self._update_map_button_state()

    def _on_inject_single(self, ai_frame_index: int) -> None:
        """Handle inject single mapping request."""
        project = self._controller.project
        if project and not project.get_mapping_for_ai_frame_index(ai_frame_index):
            QMessageBox.information(self, "Inject Frame", "Selected frame is not mapped.")
            return

        if not self._validate_rom_path():
            return

        # At this point self._rom_path is guaranteed not None and exists
        rom_path = cast(Path, self._rom_path)

        reply = QMessageBox.question(
            self,
            "Confirm Injection",
            f"Inject AI Frame {ai_frame_index}?\n\nA new copy of {rom_path.name} will be created for injection.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._controller.inject_mapping(ai_frame_index, rom_path)

    def _on_inject_all(self) -> None:
        """Handle inject all mapped frames request."""
        project = self._controller.project
        if project is None or project.mapped_count == 0:
            QMessageBox.information(self, "Inject All", "No mapped frames to inject.")
            return

        if not self._validate_rom_path():
            return

        # At this point self._rom_path is guaranteed not None and exists
        rom_path = cast(Path, self._rom_path)

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

        # Create a single copy for all injections
        target_rom = self._controller.create_injection_copy(rom_path)
        if target_rom is None:
            QMessageBox.critical(self, "Inject All", "Failed to create ROM copy for injection.")
            return

        # Inject all mapped frames into the same copy
        success_count = 0
        for ai_frame in project.ai_frames:
            mapping = project.get_mapping_for_ai_frame_index(ai_frame.index)
            if mapping:
                # Pass the created copy as output_path to avoid creating new copies
                if self._controller.inject_mapping(ai_frame.index, rom_path, output_path=target_rom):
                    success_count += 1

        if self._message_service:
            self._message_service.show_message(
                f"Injected {success_count}/{project.mapped_count} frames into {target_rom.name}"
            )

    def _on_mapping_injected(self, ai_index: int, message: str) -> None:
        """Handle successful injection signal."""
        if self._message_service:
            self._message_service.show_message(f"Injection successful for frame {ai_index}")

        self._refresh_mapping_status()
        QMessageBox.information(self, "Injection Successful", message)

    def _auto_save_after_injection(self) -> None:
        """Handle auto-save request after successful injection.

        Saves the project to the correct project file path (not ai_frames_dir).
        """
        if not self._project_path:
            logger.warning("Cannot auto-save: no project path set")
            return

        try:
            self._controller.save_project(self._project_path)
            if self._message_service:
                self._message_service.show_message("Project auto-saved", 2000)
            logger.info("Auto-saved project to %s", self._project_path)
        except Exception as e:
            logger.exception("Failed to auto-save project after injection")
            QMessageBox.warning(
                self,
                "Auto-Save Failed",
                f"Failed to save project: {e}\n\nPlease save manually.",
            )

    def _on_stale_entries_warning(self, frame_id: str) -> None:
        """Handle stale entry ID warning from controller.

        Shows a blocking dialog to inform user that stored entry selection is outdated.
        """
        QMessageBox.warning(
            self,
            "Entry Selection Stale",
            f"The stored entry selection for '{frame_id}' is outdated.\n\n"
            f"All entries from the capture will be used instead.\n\n"
            f"To fix this, reimport the capture with updated entry selection.",
        )

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _attempt_link(self, ai_index: int, game_frame_id: str) -> None:
        """Attempt to link an AI frame to a game frame.

        Handles existing link confirmation (for both AI and game frames) and auto-advance.
        Preserves alignment if mapping already exists for the same pair.
        """
        project = self._controller.project
        if project is None:
            return

        ai_frame = project.get_ai_frame_by_index(ai_index)
        ai_name = ai_frame.path.name if ai_frame else f"AI Frame {ai_index}"

        # Check if AI frame is already linked to a different game frame
        existing_game_link = self._controller.get_existing_link_for_ai_frame(ai_index)
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
        if existing_ai_link is not None and existing_ai_link != ai_index:
            existing_ai = project.get_ai_frame_by_index(existing_ai_link)
            existing_name = existing_ai.path.name if existing_ai else f"AI Frame {existing_ai_link}"

            if not confirm_replace_link(self, game_frame_id, existing_name, ai_name):
                return

        # Create the mapping
        self._controller.create_mapping(ai_index, game_frame_id)

        # Auto-center alignment
        game_preview = self._controller.get_game_frame_preview(game_frame_id)
        if ai_frame and ai_frame.path.exists() and game_preview:
            ai_pixmap = QPixmap(str(ai_frame.path))
            if not ai_pixmap.isNull():
                center_x = (game_preview.width() - ai_pixmap.width()) // 2
                center_y = (game_preview.height() - ai_pixmap.height()) // 2
                self._controller.update_mapping_alignment(ai_index, center_x, center_y, False, False, set_edited=False)

        self._refresh_mapping_status()
        self._refresh_game_frame_link_status()
        self._update_mapping_panel_previews()

        # Update canvas with alignment
        mapping = project.get_mapping_for_ai_frame_index(ai_index)
        if mapping:
            self._alignment_canvas.set_alignment(
                mapping.offset_x, mapping.offset_y, mapping.flip_h, mapping.flip_v, mapping.scale
            )

        if self._message_service:
            self._message_service.show_message(f"Linked '{ai_name}' to '{game_frame_id}'", 3000)

        # Auto-advance if enabled
        if self._auto_advance_enabled:
            next_unmapped = self._find_next_unmapped_ai_frame(ai_index)
            if next_unmapped is not None:
                self._ai_frames_pane.select_frame(next_unmapped)
                self._on_ai_frame_selected(next_unmapped)

    def _find_next_unmapped_ai_frame(self, current_index: int) -> int | None:
        """Find the next unmapped AI frame after the given index."""
        project = self._controller.project
        if project is None:
            return None

        ai_frames = project.ai_frames
        total = len(ai_frames)
        if total == 0:
            return None

        for i in range(1, total):
            check_index = (current_index + i) % total
            mapping = project.get_mapping_for_ai_frame_index(check_index)
            if mapping is None:
                return check_index

        return None

    def _update_map_button_state(self) -> None:
        """Update the Map Selected button enabled state."""
        both_selected = self._selected_ai_index is not None and self._selected_game_id is not None
        self._ai_frames_pane.set_map_button_enabled(both_selected)

    def _refresh_mapping_status(self) -> None:
        """Refresh the AI frame mapping status indicators."""
        project = self._controller.project
        if project is None:
            self._ai_frames_pane.set_mapping_status({})
            return

        status_map: dict[int, str] = {}
        for ai_frame in project.ai_frames:
            mapping = project.get_mapping_for_ai_frame_index(ai_frame.index)
            if mapping:
                status_map[ai_frame.index] = mapping.status
            else:
                status_map[ai_frame.index] = "unmapped"

        self._ai_frames_pane.set_mapping_status(status_map)
        self._mapping_panel.refresh()

    def _refresh_game_frame_link_status(self) -> None:
        """Refresh the game frame link status indicators."""
        project = self._controller.project
        if project is None:
            self._captures_pane.set_link_status({})
            return

        link_status: dict[str, int | None] = {}
        for game_frame in project.game_frames:
            linked_ai_idx = project.get_ai_frame_index_linked_to_game_frame(game_frame.id)
            link_status[game_frame.id] = linked_ai_idx

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

    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------

    def _on_load_ai_frames(self) -> None:
        """Handle load AI frames button click."""
        start_dir = str(self._last_ai_dir) if self._last_ai_dir else ""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select AI Frames Directory",
            start_dir,
        )
        if directory:
            path = Path(directory)
            self._last_ai_dir = path
            self._controller.load_ai_frames_from_directory(path)

    def _on_import_capture(self) -> None:
        """Handle import capture button click."""
        start_dir = str(self._last_capture_dir) if self._last_capture_dir else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Mesen 2 Capture",
            start_dir,
            "JSON Files (*.json);;All Files (*)",
        )
        if file_path:
            path = Path(file_path)
            self._last_capture_dir = path.parent
            self._controller.import_mesen_capture(path, parent=self)

    def _on_import_capture_dir(self) -> None:
        """Handle import capture directory button click."""
        start_dir = str(self._last_capture_dir) if self._last_capture_dir else ""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Captures Directory",
            start_dir,
        )
        if directory:
            path = Path(directory)
            self._last_capture_dir = path
            count = self._controller.import_capture_directory(path, parent=self)
            if self._message_service and count > 0:
                self._message_service.show_message(f"Imported {count} captures")

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
                self._project_path = path
                self._set_last_project_path(path)

    def _on_save_project(self) -> None:
        """Handle save project button click."""
        if not self._controller.has_project:
            QMessageBox.information(self, "Save Project", "No project to save.")
            return

        path_to_save = self._project_path

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
                self._project_path = path_to_save
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
                self._project_path = last_path
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
