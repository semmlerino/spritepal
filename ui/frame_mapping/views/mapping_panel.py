"""Mapping Panel for viewing and managing frame mappings."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

logger = logging.getLogger(__name__)

# Status colors
STATUS_COLORS = {
    "unmapped": QColor(128, 128, 128),  # Gray
    "mapped": QColor(76, 175, 80),  # Green
    "edited": QColor(33, 150, 243),  # Blue
    "injected": QColor(156, 39, 176),  # Purple
}


class MappingPanel(QWidget):
    """Panel for displaying and managing frame mappings.

    Displays a table showing the mapping between AI frames and game frames,
    with status indicators and actions.

    Signals:
        map_selected_requested: Emitted when user clicks Map Selected
        edit_frame_requested: Emitted when user clicks Edit Frame (mapping index)
        mapping_selected: Emitted when a mapping row is selected (ai_frame_index)
        remove_mapping_requested: Emitted when user requests to remove a mapping
        adjust_alignment_requested: Emitted when user clicks Adjust Alignment (ai_frame_index)
    """

    map_selected_requested = Signal()
    edit_frame_requested = Signal(int)  # AI frame index
    mapping_selected = Signal(int)  # AI frame index
    remove_mapping_requested = Signal(int)  # AI frame index
    adjust_alignment_requested = Signal(int)  # AI frame index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Mapping table group
        table_group = QGroupBox("Mappings")
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(4, 8, 4, 4)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["AI Frame", "Game Frame", "Status"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Configure header
        header = self._table.horizontalHeader()
        if header:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        table_layout.addWidget(self._table)

        layout.addWidget(table_group, 1)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)

        self._map_button = QPushButton("Map Selected")
        self._map_button.setToolTip("Link the selected AI frame to the selected game frame")
        self._map_button.clicked.connect(self.map_selected_requested.emit)
        button_layout.addWidget(self._map_button)

        self._edit_button = QPushButton("Edit Frame")
        self._edit_button.setToolTip("Open the mapped AI frame in the sprite editor")
        self._edit_button.setEnabled(False)
        self._edit_button.clicked.connect(self._on_edit_clicked)
        button_layout.addWidget(self._edit_button)

        self._align_button = QPushButton("Adjust Alignment")
        self._align_button.setToolTip("Adjust position/flip of AI frame relative to game frame")
        self._align_button.setEnabled(False)
        self._align_button.clicked.connect(self._on_align_clicked)
        button_layout.addWidget(self._align_button)

        self._remove_button = QPushButton("Remove")
        self._remove_button.setToolTip("Remove the selected mapping")
        self._remove_button.setEnabled(False)
        self._remove_button.clicked.connect(self._on_remove_clicked)
        button_layout.addWidget(self._remove_button)

        layout.addLayout(button_layout)

        # Status summary
        self._status_label = QLabel("No project loaded")
        self._status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._status_label)

    def set_project(self, project: FrameMappingProject | None) -> None:
        """Set the project to display mappings from.

        Args:
            project: FrameMappingProject or None to clear
        """
        self._project = project
        self.refresh()

    def refresh(self) -> None:
        """Refresh the mapping table from the current project."""
        self._table.setRowCount(0)

        if self._project is None:
            self._status_label.setText("No project loaded")
            return

        # Show all AI frames with their mapping status
        for ai_frame in self._project.ai_frames:
            row = self._table.rowCount()
            self._table.insertRow(row)

            # AI Frame column
            ai_item = QTableWidgetItem(ai_frame.path.name)
            ai_item.setData(Qt.ItemDataRole.UserRole, ai_frame.index)
            self._table.setItem(row, 0, ai_item)

            # Game Frame column
            mapping = self._project.get_mapping_for_ai_frame(ai_frame.index)
            if mapping:
                game_item = QTableWidgetItem(mapping.game_frame_id)
                status = mapping.status
            else:
                game_item = QTableWidgetItem("-")
                status = "unmapped"
            self._table.setItem(row, 1, game_item)

            # Status column with color
            status_item = QTableWidgetItem(status.capitalize())
            color = STATUS_COLORS.get(status, STATUS_COLORS["unmapped"])
            status_item.setForeground(QBrush(color))
            self._table.setItem(row, 2, status_item)

        # Update status summary
        mapped = self._project.mapped_count
        total = self._project.total_ai_frames
        self._status_label.setText(f"{mapped}/{total} frames mapped")

    def get_selected_ai_frame_index(self) -> int | None:
        """Get the AI frame index of the selected mapping row."""
        selected = self._table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        ai_item = self._table.item(row, 0)
        if ai_item is None:
            return None
        return ai_item.data(Qt.ItemDataRole.UserRole)

    def _on_selection_changed(self) -> None:
        """Handle selection change in the mapping table."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is None:
            self._edit_button.setEnabled(False)
            self._align_button.setEnabled(False)
            self._remove_button.setEnabled(False)
            return

        # Check if there's a mapping for this frame
        has_mapping = False
        if self._project:
            mapping = self._project.get_mapping_for_ai_frame(ai_index)
            has_mapping = mapping is not None

        self._edit_button.setEnabled(has_mapping)
        self._align_button.setEnabled(has_mapping)
        self._remove_button.setEnabled(has_mapping)
        self.mapping_selected.emit(ai_index)

    def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is not None:
            self.edit_frame_requested.emit(ai_index)

    def _on_remove_clicked(self) -> None:
        """Handle remove button click."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is not None:
            self.remove_mapping_requested.emit(ai_index)

    def _on_align_clicked(self) -> None:
        """Handle adjust alignment button click."""
        ai_index = self.get_selected_ai_frame_index()
        if ai_index is not None:
            self.adjust_alignment_requested.emit(ai_index)

    def set_map_button_enabled(self, enabled: bool) -> None:
        """Set the enabled state of the Map Selected button.

        Args:
            enabled: Whether the button should be enabled
        """
        self._map_button.setEnabled(enabled)
