#!/usr/bin/env python3
"""
AI Frame Palette Editor Window.

A modeless window for editing AI frame palette indices before ROM injection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.frame_mapping.controllers.palette_editor_controller import (
    EditorTool,
    PaletteEditorController,
)
from ui.frame_mapping.views.editor_palette_panel import EditorPalettePanel
from ui.frame_mapping.views.indexed_canvas import IndexedCanvas

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, FrameMapping, SheetPalette
    from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController

logger = logging.getLogger(__name__)


def _has_duplicate_colors(colors: list[tuple[int, int, int]]) -> bool:
    """Check if a palette has duplicate colors (excluding index 0).

    Index 0 is typically transparent, so we ignore it in duplicate detection.

    Args:
        colors: List of RGB tuples

    Returns:
        True if there are duplicate colors in indices 1-15
    """
    # Only check non-transparent colors (indices 1+)
    non_transparent = colors[1:] if len(colors) > 1 else []
    return len(non_transparent) != len(set(non_transparent))


class AIFramePaletteEditorWindow(QMainWindow):
    """Modeless window for editing AI frame palette indices.

    Allows users to correct quantization errors by painting with
    specific palette indices before ROM injection.

    Signals:
        save_requested: (ai_frame_id, indexed_data, output_path) - Request to save
        closed: (ai_frame_id) - Editor window was closed
        palette_color_changed: (index, rgb) - Palette color was edited via right-click
        ingame_saved: (ai_frame_id, ingame_edited_path) - In-game edit was saved
    """

    save_requested = Signal(str, object, str)  # ai_frame_id, np.ndarray, output_path
    closed = Signal(str)  # ai_frame_id (current, may have changed after save)
    palette_color_changed = Signal(int, tuple)  # index, (r, g, b)
    ingame_saved = Signal(str, str)  # ai_frame_id, ingame_edited_path

    def __init__(
        self,
        ai_frame: AIFrame,
        palette: SheetPalette,
        parent: QWidget | None = None,
        controller: FrameMappingController | None = None,
    ) -> None:
        super().__init__(parent)
        self._ai_frame = ai_frame
        self._palette = palette
        self._main_controller = PaletteEditorController(self)
        self._frame_controller = controller
        self._preview_enabled = False
        self._ingame_controller: PaletteEditorController | None = None
        self._ingame_canvas: IndexedCanvas | None = None
        self._active_canvas: str = "main"  # "main" or "ingame"

        self._setup_ui()
        self._setup_menu()
        self._setup_shortcuts()
        self._connect_signals()
        self._load_image()

        # Window settings
        self.setWindowTitle(f"Palette Index Editor - {ai_frame.display_name or Path(ai_frame.path).name}")
        self.resize(900, 700)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def _setup_ui(self) -> None:
        """Set up the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Center: Canvas (created first - tool panel references it)
        self._main_canvas = IndexedCanvas()
        self._main_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Left: Tool panel
        self._tool_panel = self._create_tool_panel()
        main_layout.addWidget(self._tool_panel)

        # Center section: Warning banner + Canvas
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        # Duplicate color warning banner
        self._duplicate_warning_label = QLabel(
            "\u26a0 Duplicate colors detected in palette. During injection, pixels with the same "
            "color will be mapped to the same index, regardless of their original index."
        )
        self._duplicate_warning_label.setStyleSheet(
            "background-color: #FFF3CD; color: #856404; padding: 6px 8px; border-radius: 4px; font-size: 11px;"
        )
        self._duplicate_warning_label.setWordWrap(True)
        self._duplicate_warning_label.setVisible(False)
        center_layout.addWidget(self._duplicate_warning_label)

        # Add canvas to center layout
        center_layout.addWidget(self._main_canvas, 1)

        # Right side: Palette panel + In-game preview panel (stacked)
        right_side = QWidget()
        right_layout = QVBoxLayout(right_side)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self._palette_panel = EditorPalettePanel()
        self._palette_panel.set_palette(self._palette)
        self._palette_panel.set_active_index(1)
        right_layout.addWidget(self._palette_panel)

        # In-game preview panel (collapsible)
        self._preview_panel = self._create_preview_panel()
        self._preview_panel.setVisible(False)  # Hidden by default
        right_layout.addWidget(self._preview_panel, 1)

        # Use QSplitter so user can resize center vs right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_side)
        splitter.setStretchFactor(0, 3)  # Center gets more space
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._coord_label = QLabel("(-, -)")
        self._index_label = QLabel("Index: -")
        self._selection_count_label = QLabel("Selected: 0")
        self._selection_mode_label = QLabel("Mode: Replace")
        self._tool_label = QLabel("Tool: Brush")
        self._dirty_label = QLabel("")

        self._status_bar.addWidget(self._coord_label)
        self._status_bar.addWidget(self._index_label)
        self._status_bar.addWidget(self._selection_count_label)
        self._status_bar.addWidget(self._selection_mode_label)
        self._status_bar.addPermanentWidget(self._tool_label)
        self._status_bar.addPermanentWidget(self._dirty_label)

    def _create_tool_panel(self) -> QWidget:
        """Create the tool selection panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Tools header
        tools_label = QLabel("Tools")
        tools_label.setStyleSheet("font-weight: bold; color: #AAA;")
        layout.addWidget(tools_label)

        # Tool buttons
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)

        tools = [
            (EditorTool.BRUSH, "Brush", "B", "Draw with selected color (B)"),
            (EditorTool.ERASER, "Eraser", "E", "Erase to transparent (E)"),
            (EditorTool.FILL, "Fill", "F", "Flood fill area (F)"),
            (EditorTool.PICKER, "Picker", "I", "Pick color from image (I)"),
            (
                EditorTool.CONTIGUOUS_SELECT,
                "Select",
                "W",
                "Select connected pixels (W)\n[Shift: Add, Ctrl: Subtract]",
            ),
            (
                EditorTool.GLOBAL_SELECT,
                "Sel All",
                "G",
                "Select all pixels of color (G)\n[Shift: Add, Ctrl: Subtract]",
            ),
        ]

        self._tool_buttons: dict[EditorTool, QToolButton] = {}

        for tool, label, shortcut_key, tooltip in tools:
            btn = QToolButton()
            btn.setText(f"{label} [{shortcut_key}]")
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setFixedHeight(28)
            btn.setMinimumWidth(90)
            btn.setStyleSheet("""
                QToolButton {
                    font-size: 11px;
                    border: 1px solid #555;
                    border-radius: 4px;
                    background: #333;
                    padding: 2px 6px;
                    text-align: left;
                }
                QToolButton:checked {
                    background: #555;
                    border-color: #88F;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background: #444;
                }
            """)

            self._tool_group.addButton(btn)
            self._tool_buttons[tool] = btn
            layout.addWidget(btn)

            # Connect to tool selection
            btn.clicked.connect(lambda checked, t=tool: self._on_tool_button_clicked(t))

        # Select brush by default
        self._tool_buttons[EditorTool.BRUSH].setChecked(True)

        layout.addSpacing(8)

        # Brush size
        brush_size_label = QLabel("Brush Size")
        brush_size_label.setStyleSheet("font-weight: bold; color: #AAA;")
        layout.addWidget(brush_size_label)

        self._brush_size_spinbox = QSpinBox()
        self._brush_size_spinbox.setRange(1, 16)
        self._brush_size_spinbox.setValue(1)
        self._brush_size_spinbox.setSuffix(" px")
        self._brush_size_spinbox.setToolTip("Brush size in pixels (Ctrl+/- to adjust)")
        self._brush_size_spinbox.setFixedHeight(28)
        self._brush_size_spinbox.valueChanged.connect(self._on_brush_spinbox_changed)
        layout.addWidget(self._brush_size_spinbox)

        layout.addSpacing(16)

        # Selection actions header
        actions_label = QLabel("Selection")
        actions_label.setStyleSheet("font-weight: bold; color: #AAA;")
        layout.addWidget(actions_label)

        # Fill Selection button
        self._fill_selection_btn = QPushButton("Fill Sel [Shift+F]")
        self._fill_selection_btn.setToolTip("Fill selected pixels with active color (Shift+F)")
        self._fill_selection_btn.setFixedHeight(28)
        self._fill_selection_btn.clicked.connect(self._main_controller.paint_selection)
        layout.addWidget(self._fill_selection_btn)

        layout.addSpacing(8)

        # Grid toggle
        self._grid_btn = QPushButton("Grid")
        self._grid_btn.setCheckable(True)
        self._grid_btn.setToolTip("Toggle 8x8 grid overlay")
        self._grid_btn.clicked.connect(self._on_grid_toggled)
        layout.addWidget(self._grid_btn)

        # Preview section
        layout.addSpacing(16)
        preview_label = QLabel("Preview")
        preview_label.setStyleSheet("font-weight: bold; color: #AAA;")
        layout.addWidget(preview_label)

        self._preview_checkbox = QCheckBox("In-Game")
        self._preview_checkbox.setToolTip(
            "Show preview (quantized to sheet palette)\nWith mapping: shows in-game composite"
        )
        self._preview_checkbox.toggled.connect(self._on_preview_toggled)
        layout.addWidget(self._preview_checkbox)

        # Disable if no controller
        if self._frame_controller is None:
            self._preview_checkbox.setEnabled(False)
            self._preview_checkbox.setToolTip("Preview unavailable (no frame mapping context)")

        layout.addStretch()

        # Zoom controls
        zoom_label = QLabel("Zoom")
        zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(zoom_label)

        zoom_in = QPushButton("+")
        zoom_in.setToolTip("Zoom in (+)")
        zoom_in.clicked.connect(self._main_canvas.zoom_in)
        layout.addWidget(zoom_in)

        zoom_out = QPushButton("-")
        zoom_out.setToolTip("Zoom out (-)")
        zoom_out.clicked.connect(self._main_canvas.zoom_out)
        layout.addWidget(zoom_out)

        zoom_fit = QPushButton("Fit")
        zoom_fit.setToolTip("Fit in view")
        zoom_fit.clicked.connect(self._main_canvas.zoom_fit)
        layout.addWidget(zoom_fit)

        zoom_100 = QPushButton("1:1")
        zoom_100.setToolTip("100% zoom")
        zoom_100.clicked.connect(self._main_canvas.zoom_100)
        layout.addWidget(zoom_100)

        return panel

    def _create_preview_panel(self) -> QWidget:
        """Create the in-game preview/edit panel."""
        panel = QWidget()
        panel.setMinimumWidth(200)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QLabel("In-Game Canvas")
        header.setStyleSheet("font-weight: bold; color: #AAA;")
        layout.addWidget(header)

        # In-game canvas (editable)
        self._ingame_canvas = IndexedCanvas()
        self._ingame_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._ingame_canvas.setStyleSheet("border: 1px solid #444;")
        layout.addWidget(self._ingame_canvas, 1)

        # Connect in-game canvas signals
        self._ingame_canvas.pixel_clicked.connect(self._on_ingame_canvas_clicked)
        self._ingame_canvas.pixel_dragged.connect(self._on_ingame_canvas_dragged)
        self._ingame_canvas.pixel_hovered.connect(self._on_ingame_canvas_hovered)
        self._ingame_canvas.mouse_left.connect(self._on_canvas_left)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self._refresh_ingame_btn = QPushButton("Refresh")
        self._refresh_ingame_btn.setToolTip("Re-generate from current AI frame edits")
        self._refresh_ingame_btn.clicked.connect(self._on_refresh_ingame)
        btn_layout.addWidget(self._refresh_ingame_btn)

        self._save_ingame_btn = QPushButton("Save In-Game")
        self._save_ingame_btn.setToolTip("Save in-game edits as separate indexed PNG")
        self._save_ingame_btn.setEnabled(False)
        self._save_ingame_btn.clicked.connect(self._on_save_ingame)
        btn_layout.addWidget(self._save_ingame_btn)

        layout.addLayout(btn_layout)

        # Info label
        self._preview_info_label = QLabel("Edit the composited in-game result directly")
        self._preview_info_label.setStyleSheet("color: #666; font-size: 10px;")
        self._preview_info_label.setWordWrap(True)
        layout.addWidget(self._preview_info_label)

        return panel

    def _setup_menu(self) -> None:
        """Set up the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        close_action = QAction("&Close", self)
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self._undo_action = QAction("&Undo", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.triggered.connect(lambda: self._get_active_controller().undo())
        self._undo_action.setEnabled(False)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(lambda: self._get_active_controller().redo())
        self._redo_action.setEnabled(False)
        edit_menu.addAction(self._redo_action)

        edit_menu.addSeparator()

        select_all = QAction("Select &All", self)
        select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all.triggered.connect(self._main_controller.select_all)
        edit_menu.addAction(select_all)

        deselect = QAction("&Deselect", self)
        deselect.setShortcut("Ctrl+D")
        deselect.triggered.connect(self._main_controller.deselect_all)
        edit_menu.addAction(deselect)

        invert_sel = QAction("&Invert Selection", self)
        invert_sel.setShortcut("Ctrl+I")
        invert_sel.triggered.connect(self._main_controller.invert_selection)
        edit_menu.addAction(invert_sel)

        edit_menu.addSeparator()

        erase_sel = QAction("&Erase Selection", self)
        erase_sel.setShortcut("Delete")
        erase_sel.triggered.connect(self._main_controller.erase_selection)
        edit_menu.addAction(erase_sel)

        edit_menu.addSeparator()

        replace_index = QAction("&Replace Index...", self)
        replace_index.setShortcut("Ctrl+R")
        replace_index.triggered.connect(self._show_replace_index_dialog)
        edit_menu.addAction(replace_index)

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        # Tool shortcuts
        shortcuts = [
            ("B", EditorTool.BRUSH),
            ("E", EditorTool.ERASER),
            ("F", EditorTool.FILL),
            ("I", EditorTool.PICKER),
            ("W", EditorTool.CONTIGUOUS_SELECT),
            ("G", EditorTool.GLOBAL_SELECT),
        ]

        for key, tool in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda t=tool: self._select_tool(t))

        # Palette index shortcuts (1-9, 0 for indices 0-9)
        for i in range(10):
            key = str(i) if i > 0 else "0"
            idx = i
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda index=idx: self._select_index(index))

        # Shift+1-6 for indices 10-15
        for i in range(6):
            key = f"Shift+{i + 1}"
            idx = 10 + i
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda index=idx: self._select_index(index))

        # Selection action shortcuts
        QShortcut(QKeySequence("Shift+F"), self).activated.connect(self._main_controller.paint_selection)

        # Brush size shortcuts (Ctrl+Plus/Minus)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self._decrease_brush)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self._increase_brush)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self._increase_brush)

        # Zoom shortcuts (without Ctrl)
        QShortcut(QKeySequence("+"), self).activated.connect(self._main_canvas.zoom_in)
        QShortcut(QKeySequence("="), self).activated.connect(self._main_canvas.zoom_in)
        QShortcut(QKeySequence("-"), self).activated.connect(self._main_canvas.zoom_out)

    def _connect_signals(self) -> None:
        """Connect controller and widget signals."""
        # Main controller signals
        self._main_controller.image_changed.connect(self._on_main_image_changed)
        self._main_controller.selection_changed.connect(self._on_selection_changed)
        self._main_controller.undo_state_changed.connect(self._on_undo_state_changed)
        self._main_controller.pixel_info.connect(self._on_pixel_info)
        self._main_controller.dirty_changed.connect(self._on_dirty_changed)
        self._main_controller.active_index_changed.connect(self._on_active_index_changed)
        self._main_controller.tool_changed.connect(self._on_tool_changed)
        self._main_controller.color_mapping_report.connect(self._on_color_mapping_report)

        # Main canvas signals
        self._main_canvas.pixel_clicked.connect(self._on_main_canvas_clicked)
        self._main_canvas.pixel_dragged.connect(self._on_main_canvas_dragged)
        self._main_canvas.pixel_hovered.connect(self._on_main_canvas_hovered)
        self._main_canvas.mouse_left.connect(self._on_canvas_left)
        self._main_canvas.drag_ended.connect(self._main_controller.finish_stroke)
        self._main_canvas.brush_size_changed.connect(self._on_brush_size_changed)

        # Palette panel signals
        self._palette_panel.index_selected.connect(self._on_palette_index_selected)
        self._palette_panel.color_changed.connect(self._on_palette_color_changed)
        self._palette_panel.merge_requested.connect(self._on_palette_merge_requested)

    def _load_image(self) -> None:
        """Load the AI frame image."""
        path = Path(self._ai_frame.path)
        if self._main_controller.load_image(path, self._palette):
            # Update canvas
            data = self._main_controller.get_indexed_data()
            if data is not None:
                self._main_canvas.set_image(data, self._palette)
                # Initialize brush cursor
                self._main_canvas.set_brush_size(self._main_controller.brush_size)

            # Check for duplicate colors in palette and show warning if found
            self._update_duplicate_warning()
        else:
            QMessageBox.warning(
                self,
                "Load Error",
                f"Failed to load image: {path}",
            )
            self.close()

    def _update_duplicate_warning(self) -> None:
        """Update the duplicate color warning visibility based on palette."""
        has_duplicates = _has_duplicate_colors(self._palette.colors)
        self._duplicate_warning_label.setVisible(has_duplicates)

    def has_duplicate_color_warning(self) -> bool:
        """Check if the duplicate color warning is currently shown.

        Returns:
            True if the warning is visible (palette has duplicate colors)
        """
        return self._duplicate_warning_label.isVisible()

    # --- Active Canvas Tracking ---

    def _set_active_canvas(self, which: str) -> None:
        """Set which canvas is active and apply visual highlight."""
        self._active_canvas = which
        if which == "main":
            self._main_canvas.setStyleSheet("border: 2px solid #4A90D9;")
            if self._ingame_canvas is not None:
                self._ingame_canvas.setStyleSheet("border: 1px solid #444;")
        else:
            self._main_canvas.setStyleSheet("border: 1px solid #444;")
            if self._ingame_canvas is not None:
                self._ingame_canvas.setStyleSheet("border: 2px solid #4A90D9;")

    def _get_active_controller(self) -> PaletteEditorController:
        """Return the controller for the currently active canvas."""
        if self._active_canvas == "ingame" and self._ingame_controller is not None:
            return self._ingame_controller
        return self._main_controller

    # --- Event Handlers ---

    def _on_tool_button_clicked(self, tool: EditorTool) -> None:
        """Handle tool button click."""
        self._select_tool(tool)

    def _select_tool(self, tool: EditorTool) -> None:
        """Select a tool via controller."""
        self._main_controller.set_tool(tool)
        if self._ingame_controller is not None:
            self._ingame_controller.set_tool(tool)

    def _on_tool_changed(self, tool: EditorTool) -> None:
        """Handle tool change from controller (e.g., auto-switch after pick)."""
        self._tool_buttons[tool].setChecked(True)
        self._tool_label.setText(f"Tool: {tool.name.replace('_', ' ').title()}")

    def _select_index(self, index: int) -> None:
        """Select a palette index."""
        self._main_controller.set_active_index(index)
        if self._ingame_controller is not None:
            self._ingame_controller.set_active_index(index)
        self._palette_panel.set_active_index(index)

    def _decrease_brush(self) -> None:
        """Decrease brush size."""
        self._brush_size_spinbox.setValue(self._brush_size_spinbox.value() - 1)

    def _increase_brush(self) -> None:
        """Increase brush size."""
        self._brush_size_spinbox.setValue(self._brush_size_spinbox.value() + 1)

    def _on_brush_spinbox_changed(self, size: int) -> None:
        """Handle brush size spinbox value change."""
        self._main_controller.set_brush_size(size)
        self._main_canvas.set_brush_size(size)
        if self._ingame_controller is not None:
            self._ingame_controller.set_brush_size(size)
        if self._ingame_canvas is not None:
            self._ingame_canvas.set_brush_size(size)

    def _on_brush_size_changed(self, size: int) -> None:
        """Handle brush size change from Ctrl+RMB drag on canvas."""
        self._main_controller.set_brush_size(size)
        if self._ingame_controller is not None:
            self._ingame_controller.set_brush_size(size)
        self._brush_size_spinbox.blockSignals(True)
        self._brush_size_spinbox.setValue(size)
        self._brush_size_spinbox.blockSignals(False)

    def _on_grid_toggled(self, checked: bool) -> None:
        """Handle grid toggle."""
        self._main_canvas.set_show_grid(checked)

    def _on_main_image_changed(self) -> None:
        """Handle main image data change."""
        data = self._main_controller.get_indexed_data()
        if data is not None:
            self._main_canvas.set_image(data, self._palette)
            # Refresh highlight overlay with new data
            self._main_canvas.set_highlight_index(self._main_controller.active_index)

    def _on_ingame_image_changed(self) -> None:
        """Handle in-game image data change."""
        if self._ingame_controller is None or self._ingame_canvas is None:
            return
        data = self._ingame_controller.get_indexed_data()
        if data is not None:
            self._ingame_canvas.set_image(data, self._palette)
            self._ingame_canvas.set_highlight_index(self._ingame_controller.active_index)

    def _on_ingame_dirty_changed(self, dirty: bool) -> None:
        """Handle in-game dirty state change."""
        self._save_ingame_btn.setEnabled(dirty)

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        mask = self._main_controller.selection_mask
        self._main_canvas.set_selection_mask(mask)
        # Update selection count in status bar
        count = mask.get_selection_count() if mask is not None else 0
        self._selection_count_label.setText(f"Selected: {count}")

    def _on_undo_state_changed(self, can_undo: bool, can_redo: bool) -> None:
        """Handle undo/redo state change."""
        self._undo_action.setEnabled(can_undo)
        self._redo_action.setEnabled(can_redo)

    def _on_pixel_info(self, x: int, y: int, index: int) -> None:
        """Handle pixel info update."""
        self._coord_label.setText(f"({x}, {y})")
        self._index_label.setText(f"Index: {index}")
        # Highlight the corresponding palette swatch
        self._palette_panel.highlight_index(index)

    def _update_selection_mode_display(self, modifiers: Qt.KeyboardModifier | int) -> None:
        """Update the selection mode indicator based on keyboard modifiers.

        Args:
            modifiers: Current keyboard modifiers (Qt.KeyboardModifier flags)
        """
        # Convert to Qt.KeyboardModifier if int
        if isinstance(modifiers, int):
            modifiers = Qt.KeyboardModifier(modifiers)

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            mode_text = "Add"
        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            mode_text = "Subtract"
        else:
            mode_text = "Replace"

        self._selection_mode_label.setText(f"Mode: {mode_text}")

    def _on_dirty_changed(self, is_dirty: bool) -> None:
        """Handle dirty state change."""
        self._dirty_label.setText("*" if is_dirty else "")
        title = f"Palette Index Editor - {self._ai_frame.display_name or Path(self._ai_frame.path).name}"
        if is_dirty:
            title += " *"
        self.setWindowTitle(title)

    def _on_active_index_changed(self, index: int) -> None:
        """Handle active index change from controller (e.g., right-click pick)."""
        self._palette_panel.set_active_index(index)
        if self._ingame_controller is not None:
            self._ingame_controller.set_active_index(index)
        highlight = None if index == -1 else index
        self._main_canvas.set_highlight_index(highlight)
        if self._ingame_canvas is not None:
            self._ingame_canvas.set_highlight_index(highlight)

    def _on_color_mapping_report(self, report: dict[str, object]) -> None:
        """Handle color mapping analysis report after image load.

        Shows an informational dialog if there were colors requiring
        nearest-neighbor fallback during RGB->indexed conversion.
        """
        unmapped_count = report.get("unmapped_count", 0)
        exact_count = report.get("exact_count", 0)
        distance_stats = report.get("distance_stats", {})

        # Only show dialog if there were fallback matches
        if unmapped_count and isinstance(unmapped_count, int) and unmapped_count > 0:
            avg_dist = 0.0
            max_dist = 0.0
            if isinstance(distance_stats, dict):
                avg_dist = float(distance_stats.get("avg", 0))
                max_dist = float(distance_stats.get("max", 0))

            # Show informational message in status bar
            msg = f"Color mapping: {exact_count} exact, {unmapped_count} nearest-neighbor (avg dist: {avg_dist:.1f})"
            self._status_bar.showMessage(msg, 5000)  # Show for 5 seconds

            # Log details
            logger.info(
                "Color mapping report: %d exact matches, %d fallbacks (avg: %.1f, max: %.1f)",
                exact_count,
                unmapped_count,
                avg_dist,
                max_dist,
            )

    # --- Canvas Click/Drag/Hover Handlers ---

    def _on_main_canvas_clicked(self, x: int, y: int, button: int) -> None:
        """Handle main canvas click."""
        from PySide6.QtWidgets import QApplication

        self._set_active_canvas("main")
        modifiers = QApplication.keyboardModifiers().value
        self._update_selection_mode_display(modifiers)
        self._main_controller.handle_pixel_click(x, y, button, modifiers)

    def _on_main_canvas_dragged(self, x: int, y: int) -> None:
        """Handle main canvas drag."""
        self._main_controller.handle_pixel_drag(x, y)

    def _on_main_canvas_hovered(self, x: int, y: int) -> None:
        """Handle main canvas hover."""
        from PySide6.QtWidgets import QApplication

        modifiers = QApplication.keyboardModifiers().value
        self._update_selection_mode_display(modifiers)
        self._main_controller.handle_pixel_hover(x, y)

    def _on_ingame_canvas_clicked(self, x: int, y: int, button: int) -> None:
        """Handle in-game canvas click."""
        if self._ingame_controller is None:
            return
        from PySide6.QtWidgets import QApplication

        self._set_active_canvas("ingame")
        modifiers = QApplication.keyboardModifiers().value
        self._update_selection_mode_display(modifiers)
        self._ingame_controller.handle_pixel_click(x, y, button, modifiers)

    def _on_ingame_canvas_dragged(self, x: int, y: int) -> None:
        """Handle in-game canvas drag."""
        if self._ingame_controller is None:
            return
        self._ingame_controller.handle_pixel_drag(x, y)

    def _on_ingame_canvas_hovered(self, x: int, y: int) -> None:
        """Handle in-game canvas hover."""
        if self._ingame_controller is None:
            return
        from PySide6.QtWidgets import QApplication

        modifiers = QApplication.keyboardModifiers().value
        self._update_selection_mode_display(modifiers)
        self._ingame_controller.handle_pixel_hover(x, y)

    def _on_canvas_left(self) -> None:
        """Handle mouse leaving canvas."""
        self._coord_label.setText("(-, -)")
        self._index_label.setText("Index: -")
        # Clear palette highlight
        self._palette_panel.highlight_index(None)

    # --- Preview / In-Game Canvas ---

    def _on_preview_toggled(self, checked: bool) -> None:
        """Handle preview toggle."""
        self._preview_enabled = checked

        if checked:
            if self._frame_controller is None:
                self._preview_checkbox.setChecked(False)
                return

            project = self._frame_controller.project
            if project is None:
                QMessageBox.warning(self, "No Project", "No project loaded.")
                self._preview_checkbox.setChecked(False)
                return

            mapping = project.get_mapping_for_ai_frame(self._ai_frame.id)

            # Show preview panel
            self._preview_panel.setVisible(True)

            if mapping is None:
                self._preview_info_label.setText("No mapping - in-game canvas unavailable")
                if self._ingame_canvas is not None:
                    self._ingame_canvas.setEnabled(False)
                self._refresh_ingame_btn.setEnabled(False)
                self._save_ingame_btn.setEnabled(False)
                return

            # Check for saved in-game edits
            if mapping.ingame_edited_path:
                ingame_path = Path(mapping.ingame_edited_path)
                if ingame_path.exists():
                    self._load_ingame_from_file(ingame_path)
                    self._preview_info_label.setText("Loaded saved in-game edits")
                    return

            # Generate from compositor
            self._generate_ingame_canvas(mapping)
            self._preview_info_label.setText("Edit the composited in-game result")
        else:
            # Check for unsaved in-game edits
            if self._ingame_controller is not None and self._ingame_controller.is_dirty:
                result = QMessageBox.question(
                    self,
                    "Unsaved In-Game Edits",
                    "You have unsaved in-game edits. Discard?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if result == QMessageBox.StandardButton.No:
                    self._preview_checkbox.setChecked(True)
                    return

            # Hide preview panel
            self._preview_panel.setVisible(False)

    def _generate_ingame_canvas(self, mapping: FrameMapping) -> None:
        """Generate in-game canvas from current AI frame via compositor."""
        if self._frame_controller is None:
            return

        capture_result, _ = self._frame_controller.get_capture_result_for_game_frame(mapping.game_frame_id)
        if capture_result is None:
            self._status_bar.showMessage("Capture data not found", 3000)
            return

        indexed_data = self._main_controller.get_indexed_data()
        if indexed_data is None:
            return

        from core.services.rgb_to_indexed import convert_indexed_to_rgb
        from core.services.sprite_compositor import SpriteCompositor, TransformParams

        ai_image = convert_indexed_to_rgb(indexed_data, self._palette)

        transform = TransformParams(
            offset_x=mapping.offset_x,
            offset_y=mapping.offset_y,
            flip_h=mapping.flip_h,
            flip_v=mapping.flip_v,
            scale=mapping.scale,
            sharpen=mapping.sharpen,
            resampling=mapping.resampling,
        )

        compositor = SpriteCompositor(uncovered_policy="transparent")
        composite_result = compositor.composite_frame(
            ai_image=ai_image,
            capture_result=capture_result,
            transform=transform,
            quantize=False,
            sheet_palette=self._palette,
            ai_index_map=indexed_data,
        )

        index_map = composite_result.index_map
        if index_map is None:
            self._status_bar.showMessage("Failed to generate in-game index map", 3000)
            return

        self._setup_ingame_canvas(index_map)

    def _load_ingame_from_file(self, path: Path) -> None:
        """Load in-game canvas from a saved indexed PNG."""
        from core.services.rgb_to_indexed import load_image_preserving_indices

        index_map, _ = load_image_preserving_indices(path, sheet_palette=self._palette)
        if index_map is None:
            self._status_bar.showMessage("Failed to load in-game edits (not indexed)", 3000)
            return

        self._setup_ingame_canvas(index_map)

    def _setup_ingame_canvas(self, index_map: object) -> None:
        """Initialize or update the in-game canvas with an index map.

        Args:
            index_map: numpy ndarray of palette indices (H, W), uint8
        """
        import numpy as np

        if not isinstance(index_map, np.ndarray):
            return

        if self._ingame_controller is None:
            self._ingame_controller = PaletteEditorController(self)
            self._ingame_controller.image_changed.connect(self._on_ingame_image_changed)
            self._ingame_controller.dirty_changed.connect(self._on_ingame_dirty_changed)
            self._ingame_controller.pixel_info.connect(self._on_pixel_info)
            self._ingame_controller.active_index_changed.connect(self._on_active_index_changed)
            if self._ingame_canvas is not None:
                self._ingame_canvas.drag_ended.connect(self._ingame_controller.finish_stroke)

        self._ingame_controller.load_indexed_data(index_map, self._palette)

        if self._ingame_canvas is not None:
            self._ingame_canvas.set_image(index_map, self._palette)
            self._ingame_canvas.setEnabled(True)
            self._ingame_canvas.set_highlight_index(self._main_controller.active_index)

        # Sync tool/brush state from main controller
        self._ingame_controller.set_tool(self._main_controller.current_tool)
        self._ingame_controller.set_active_index(self._main_controller.active_index)
        self._ingame_controller.set_brush_size(self._main_controller.brush_size)
        if self._ingame_canvas is not None:
            self._ingame_canvas.set_brush_size(self._main_controller.brush_size)

        self._refresh_ingame_btn.setEnabled(True)
        self._save_ingame_btn.setEnabled(False)  # Not dirty yet

    def _on_save_ingame(self) -> None:
        """Save in-game edits as a separate indexed PNG."""
        if self._ingame_controller is None or not self._ingame_controller.is_dirty:
            return

        original = Path(self._ai_frame.path)
        output_path = original.parent / f"{original.stem}_ingame.png"

        if self._ingame_controller.save(output_path):
            if self._frame_controller is not None:
                project = self._frame_controller.project
                if project is not None:
                    mapping = project.get_mapping_for_ai_frame(self._ai_frame.id)
                    if mapping is not None:
                        mapping.ingame_edited_path = str(output_path)
                        self._frame_controller.save_requested.emit()
            self.ingame_saved.emit(self._ai_frame.id, str(output_path))
            logger.info("Saved in-game edits: %s", output_path)
            self._status_bar.showMessage(f"Saved: {output_path.name}", 3000)
        else:
            QMessageBox.warning(self, "Save Error", f"Failed to save to: {output_path}")

    def _on_refresh_ingame(self) -> None:
        """Re-generate in-game canvas from current AI frame edits."""
        if self._ingame_controller is not None and self._ingame_controller.is_dirty:
            result = QMessageBox.question(
                self,
                "Discard In-Game Edits",
                "Re-generating will discard your in-game edits. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result == QMessageBox.StandardButton.No:
                return

        if self._frame_controller is None:
            return

        project = self._frame_controller.project
        if project is None:
            return

        mapping = project.get_mapping_for_ai_frame(self._ai_frame.id)
        if mapping is None:
            return

        self._generate_ingame_canvas(mapping)
        self._status_bar.showMessage("In-game canvas refreshed", 3000)

    # --- Palette Panel Handlers ---

    def _on_palette_index_selected(self, index: int) -> None:
        """Handle palette panel selection."""
        self._main_controller.set_active_index(index)
        if self._ingame_controller is not None:
            self._ingame_controller.set_active_index(index)
        highlight = None if index == -1 else index
        self._main_canvas.set_highlight_index(highlight)
        if self._ingame_canvas is not None:
            self._ingame_canvas.set_highlight_index(highlight)

    def _on_palette_color_changed(self, index: int, color: tuple[int, int, int]) -> None:
        """Handle palette color change from right-click."""
        # Update the palette directly to ensure synchronization
        if 0 < index < len(self._palette.colors):
            self._palette.colors[index] = color

        # Also update via controller for dirty state tracking
        self._main_controller.set_palette_color(index, color)

        # Refresh the canvas with the updated palette
        data = self._main_controller.get_indexed_data()
        if data is not None:
            self._main_canvas.set_image(data, self._palette)

        # Also sync the palette panel's swatch (in case signal didn't update it)
        self._palette_panel.sync_palette(self._palette)

        # Notify workspace to refresh other frames with updated palette
        self.palette_color_changed.emit(index, color)

    def _on_palette_merge_requested(self, primary_index: int, merge_index: int) -> None:
        """Handle palette merge request (Ctrl+click).

        Merges all pixels using merge_index into primary_index, freeing up
        the merge_index slot (shown as dark purple).
        """
        if self._main_controller.merge_palette_indices(primary_index, merge_index):
            # Mark the merged slot as free in the palette panel
            self._palette_panel.mark_slot_free(merge_index)
            logger.info(f"Merged palette index {merge_index} into {primary_index}")

    def _show_replace_index_dialog(self) -> None:
        """Show dialog to replace all pixels of one index with another.

        Unlike merge, this does not mark the source slot as free.
        Both palette colors remain valid.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Replace Index")
        dialog.setMinimumWidth(250)

        layout = QVBoxLayout(dialog)

        # Instructions
        info = QLabel(
            "Replace all pixels using one palette index with another.\nBoth palette colors will remain valid."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888;")
        layout.addWidget(info)

        # Form for from/to indices
        form = QFormLayout()

        from_spin = QSpinBox()
        from_spin.setRange(0, 15)
        from_spin.setValue(self._main_controller.active_index)
        form.addRow("Replace index:", from_spin)

        to_spin = QSpinBox()
        to_spin.setRange(0, 15)
        to_spin.setValue(1 if self._main_controller.active_index == 0 else 0)
        form.addRow("With index:", to_spin)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            from_index = from_spin.value()
            to_index = to_spin.value()

            if from_index == to_index:
                QMessageBox.information(
                    self,
                    "No Change",
                    "Source and target indices are the same.",
                )
                return

            result = self._main_controller.replace_index(from_index, to_index)
            if result > 0:
                self._status_bar.showMessage(
                    f"Replaced {result} pixel(s): index {from_index} \u2192 {to_index}",
                    5000,
                )
            elif result == 0:
                QMessageBox.information(
                    self,
                    "No Pixels Found",
                    f"No pixels were using index {from_index}.",
                )

    # --- Save / Close ---

    def _on_save(self) -> None:
        """Handle save action."""
        if not self._main_controller.is_dirty:
            return

        # Generate output path
        original = Path(self._ai_frame.path)
        stem = original.stem
        if stem.endswith("_edited"):
            output_path = original
        else:
            output_path = original.parent / f"{stem}_edited.png"

        if self._main_controller.save(output_path):
            data = self._main_controller.get_indexed_data()
            self.save_requested.emit(self._ai_frame.id, data, str(output_path))
            logger.info("Saved edited image: %s", output_path)
        else:
            QMessageBox.warning(
                self,
                "Save Error",
                f"Failed to save to: {output_path}",
            )

    @override
    def closeEvent(self, event: object) -> None:
        """Handle window close with unsaved changes prompt."""
        from PySide6.QtGui import QCloseEvent

        if not isinstance(event, QCloseEvent):
            return

        # Check main controller dirty state
        if self._main_controller.is_dirty:
            result = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes to the AI frame. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )

            if result == QMessageBox.StandardButton.Save:
                self._on_save()
                if self._main_controller.is_dirty:  # Save failed
                    event.ignore()
                    return
            elif result == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

        # Check in-game controller dirty state
        if self._ingame_controller is not None and self._ingame_controller.is_dirty:
            result = QMessageBox.question(
                self,
                "Unsaved In-Game Edits",
                "You have unsaved in-game edits. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )

            if result == QMessageBox.StandardButton.Save:
                self._on_save_ingame()
                if self._ingame_controller.is_dirty:  # Save failed
                    event.ignore()
                    return
            elif result == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

        self.closed.emit(self._ai_frame.id)
        event.accept()
