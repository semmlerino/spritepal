"""Frame Mapping Workspace.

Provides a dedicated workspace for mapping AI-generated sprite frames
to game animation frames captured from Mesen 2.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
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

from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.dialogs.alignment_dialog import AlignmentDialog
from ui.frame_mapping.views.comparison_panel import ComparisonPanel
from ui.frame_mapping.views.frame_browser_panel import FrameBrowserPanel
from ui.frame_mapping.views.mapping_panel import MappingPanel

if TYPE_CHECKING:
    from ui.managers.status_bar_manager import StatusBarManager

logger = logging.getLogger(__name__)


class FrameMappingWorkspace(QWidget):
    """Main workspace for frame mapping functionality.

    Layout:
        +-----------------------------------------------------------+
        | Toolbar: [Load AI] [Import Capture] [Import Dir] | [Save] |
        +-------------------+-------------------+-------------------+
        | Frame Browser     | Comparison Panel  | Mapping Panel     |
        | - AI Frames       | [Game] | [AI]     | Table + Actions   |
        | - Game Frames     |                   |                   |
        +-------------------+-------------------+-------------------+

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

        # Create controller
        self._controller = FrameMappingController(self)

        self._setup_ui()
        self._connect_signals()

        logger.debug("FrameMappingWorkspace initialized")

    def set_message_service(self, service: StatusBarManager | None) -> None:
        """Set the message service for status updates."""
        self._message_service = service

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header with title and toolbar
        header = self._create_header()
        layout.addWidget(header)

        # Main content with three-panel splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Left panel: Frame Browser
        self._frame_browser = FrameBrowserPanel()
        self._splitter.addWidget(self._frame_browser)

        # Center panel: Comparison
        self._comparison_panel = ComparisonPanel()
        self._splitter.addWidget(self._comparison_panel)

        # Right panel: Mapping
        self._mapping_panel = MappingPanel()
        self._splitter.addWidget(self._mapping_panel)

        # Set initial splitter sizes (roughly 1:2:1 ratio)
        self._splitter.setSizes([250, 500, 250])

        layout.addWidget(self._splitter, 1)

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
        self._load_ai_btn.clicked.connect(self._on_load_ai_frames)
        toolbar.addWidget(self._load_ai_btn)

        self._import_capture_btn = QPushButton("Import Capture")
        self._import_capture_btn.setToolTip("Import a single Mesen 2 capture file")
        self._import_capture_btn.clicked.connect(self._on_import_capture)
        toolbar.addWidget(self._import_capture_btn)

        self._import_dir_btn = QPushButton("Import Capture Directory")
        self._import_dir_btn.setToolTip("Import all captures from a directory")
        self._import_dir_btn.clicked.connect(self._on_import_capture_dir)
        toolbar.addWidget(self._import_dir_btn)

        toolbar.addSeparator()

        self._load_btn = QPushButton("Load")
        self._load_btn.setToolTip("Load a frame mapping project")
        self._load_btn.clicked.connect(self._on_load_project)
        toolbar.addWidget(self._load_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setToolTip("Save the current project")
        self._save_btn.clicked.connect(self._on_save_project)
        toolbar.addWidget(self._save_btn)

        layout.addWidget(toolbar)

        return header

    def _connect_signals(self) -> None:
        """Connect signals between components."""
        # Controller signals
        self._controller.project_changed.connect(self._on_project_changed)
        self._controller.ai_frames_loaded.connect(self._on_ai_frames_loaded)
        self._controller.game_frame_added.connect(self._on_game_frame_added)
        self._controller.error_occurred.connect(self._on_error)

        # Frame browser signals
        self._frame_browser.ai_frame_selected.connect(self._on_ai_frame_selected)
        self._frame_browser.game_frame_selected.connect(self._on_game_frame_selected)

        # Mapping panel signals
        self._mapping_panel.map_selected_requested.connect(self._on_map_selected)
        self._mapping_panel.edit_frame_requested.connect(self._on_edit_frame)
        self._mapping_panel.remove_mapping_requested.connect(self._on_remove_mapping)
        self._mapping_panel.mapping_selected.connect(self._on_mapping_selected)
        self._mapping_panel.adjust_alignment_requested.connect(self._on_adjust_alignment)

    def _on_project_changed(self) -> None:
        """Handle project changes."""
        project = self._controller.project
        if project is None:
            self._project_label.setText("")
            self._frame_browser.clear_all()
            self._mapping_panel.set_project(None)
            return

        self._project_label.setText(f"- {project.name}")
        self._frame_browser.set_ai_frames(project.ai_frames)
        self._frame_browser.set_game_frames(project.game_frames)
        self._mapping_panel.set_project(project)

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

    def _on_ai_frame_selected(self, index: int) -> None:
        """Handle AI frame selection."""
        project = self._controller.project
        if project is None:
            return

        frame = project.get_ai_frame_by_index(index)
        self._comparison_panel.set_ai_frame(frame)

    def _on_game_frame_selected(self, frame_id: str) -> None:
        """Handle game frame selection."""
        project = self._controller.project
        if project is None:
            return

        frame = project.get_game_frame_by_id(frame_id)
        preview = self._controller.get_game_frame_preview(frame_id)
        self._comparison_panel.set_game_frame(frame, preview)

    def _on_mapping_selected(self, ai_frame_index: int) -> None:
        """Handle mapping row selection."""
        project = self._controller.project
        if project is None:
            return

        # Show AI frame in comparison
        ai_frame = project.get_ai_frame_by_index(ai_frame_index)
        self._comparison_panel.set_ai_frame(ai_frame)

        # Show game frame if mapped
        mapping = project.get_mapping_for_ai_frame(ai_frame_index)
        if mapping:
            game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
            preview = self._controller.get_game_frame_preview(mapping.game_frame_id)
            self._comparison_panel.set_game_frame(game_frame, preview)

    def _on_map_selected(self) -> None:
        """Handle map selected button click."""
        ai_index = self._frame_browser.get_selected_ai_frame_index()
        game_id = self._frame_browser.get_selected_game_frame_id()

        if ai_index is None:
            QMessageBox.information(self, "Map Frames", "Please select an AI frame first.")
            return

        if game_id is None:
            QMessageBox.information(self, "Map Frames", "Please select a game frame first.")
            return

        self._controller.create_mapping(ai_index, game_id)

    def _on_edit_frame(self, ai_frame_index: int) -> None:
        """Handle edit frame request."""
        project = self._controller.project
        if project is None:
            return

        ai_frame = project.get_ai_frame_by_index(ai_frame_index)
        if ai_frame is None:
            return

        mapping = project.get_mapping_for_ai_frame(ai_frame_index)
        rom_offsets: list[int] = []
        if mapping:
            game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
            if game_frame:
                rom_offsets = game_frame.rom_offsets

        self.edit_in_sprite_editor_requested.emit(ai_frame.path, rom_offsets)

    def _on_remove_mapping(self, ai_frame_index: int) -> None:
        """Handle remove mapping request."""
        self._controller.remove_mapping(ai_frame_index)

    def _on_adjust_alignment(self, ai_frame_index: int) -> None:
        """Handle adjust alignment request."""
        project = self._controller.project
        if project is None:
            return

        ai_frame = project.get_ai_frame_by_index(ai_frame_index)
        if ai_frame is None:
            return

        mapping = project.get_mapping_for_ai_frame(ai_frame_index)
        if mapping is None:
            return

        game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
        if game_frame is None:
            return

        # Get game frame preview pixmap
        game_pixmap = self._controller.get_game_frame_preview(mapping.game_frame_id)

        # Open alignment dialog with current values
        dialog = AlignmentDialog(
            game_frame_pixmap=game_pixmap,
            ai_frame_path=ai_frame.path,
            initial_offset_x=mapping.offset_x,
            initial_offset_y=mapping.offset_y,
            initial_flip_h=mapping.flip_h,
            initial_flip_v=mapping.flip_v,
            parent=self,
        )

        if dialog.exec():
            # User accepted - save alignment
            offset_x, offset_y, flip_h, flip_v = dialog.get_alignment()
            self._controller.update_mapping_alignment(ai_frame_index, offset_x, offset_y, flip_h, flip_v)
            if self._message_service:
                self._message_service.show_message(f"Alignment updated: offset=({offset_x}, {offset_y})")

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

    def _on_save_project(self) -> None:
        """Handle save project button click."""
        if not self._controller.has_project:
            QMessageBox.information(self, "Save Project", "No project to save.")
            return

        if self._project_path:
            # Save to existing path
            self._controller.save_project(self._project_path)
        else:
            # Save as new file
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Frame Mapping Project",
                "mapping.spritepal-mapping.json",
                "Frame Mapping Projects (*.spritepal-mapping.json);;All Files (*)",
            )
            if file_path:
                path = Path(file_path)
                if self._controller.save_project(path):
                    self._project_path = path

    @property
    def controller(self) -> FrameMappingController:
        """Get the frame mapping controller."""
        return self._controller

    def cleanup(self) -> None:
        """Cleanup resources."""
        logger.debug("FrameMappingWorkspace cleanup")
