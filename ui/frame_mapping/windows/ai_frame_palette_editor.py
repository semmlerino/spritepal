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
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
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
    from core.frame_mapping_project import AIFrame, SheetPalette

logger = logging.getLogger(__name__)


class AIFramePaletteEditorWindow(QMainWindow):
    """Modeless window for editing AI frame palette indices.

    Allows users to correct quantization errors by painting with
    specific palette indices before ROM injection.

    Signals:
        save_requested: (ai_frame_id, indexed_data, output_path) - Request to save
        closed: Editor window was closed
    """

    save_requested = Signal(str, object, str)  # ai_frame_id, np.ndarray, output_path
    closed = Signal()

    def __init__(
        self,
        ai_frame: AIFrame,
        palette: SheetPalette,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ai_frame = ai_frame
        self._palette = palette
        self._controller = PaletteEditorController(self)

        self._setup_ui()
        self._setup_menu()
        self._setup_shortcuts()
        self._connect_signals()
        self._load_image()

        # Window settings
        self.setWindowTitle(f"Palette Editor - {ai_frame.display_name or Path(ai_frame.path).name}")
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
        self._canvas = IndexedCanvas()
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Left: Tool panel
        self._tool_panel = self._create_tool_panel()
        main_layout.addWidget(self._tool_panel)

        # Add canvas to layout
        main_layout.addWidget(self._canvas, 1)

        # Right: Palette panel
        self._palette_panel = EditorPalettePanel()
        self._palette_panel.set_palette(self._palette)
        self._palette_panel.set_active_index(1)
        main_layout.addWidget(self._palette_panel)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._coord_label = QLabel("(-, -)")
        self._index_label = QLabel("Index: -")
        self._tool_label = QLabel("Tool: Pencil")
        self._dirty_label = QLabel("")

        self._status_bar.addWidget(self._coord_label)
        self._status_bar.addWidget(self._index_label)
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
            (EditorTool.PENCIL, "Pencil", "P", "Draw with selected color (P)"),
            (EditorTool.ERASER, "Eraser", "E", "Erase to transparent (E)"),
            (EditorTool.FILL, "Fill", "F", "Flood fill area (F)"),
            (EditorTool.CONTIGUOUS_SELECT, "Select", "W", "Select connected pixels (W)"),
            (EditorTool.GLOBAL_SELECT, "Sel All", "G", "Select all pixels of color (G)"),
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

        # Select pencil by default
        self._tool_buttons[EditorTool.PENCIL].setChecked(True)

        layout.addSpacing(16)

        # Grid toggle
        self._grid_btn = QPushButton("Grid")
        self._grid_btn.setCheckable(True)
        self._grid_btn.setToolTip("Toggle 8x8 grid overlay")
        self._grid_btn.clicked.connect(self._on_grid_toggled)
        layout.addWidget(self._grid_btn)

        layout.addStretch()

        # Zoom controls
        zoom_label = QLabel("Zoom")
        zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(zoom_label)

        zoom_in = QPushButton("+")
        zoom_in.setToolTip("Zoom in (+)")
        zoom_in.clicked.connect(self._canvas.zoom_in)
        layout.addWidget(zoom_in)

        zoom_out = QPushButton("-")
        zoom_out.setToolTip("Zoom out (-)")
        zoom_out.clicked.connect(self._canvas.zoom_out)
        layout.addWidget(zoom_out)

        zoom_fit = QPushButton("Fit")
        zoom_fit.setToolTip("Fit in view")
        zoom_fit.clicked.connect(self._canvas.zoom_fit)
        layout.addWidget(zoom_fit)

        zoom_100 = QPushButton("1:1")
        zoom_100.setToolTip("100% zoom")
        zoom_100.clicked.connect(self._canvas.zoom_100)
        layout.addWidget(zoom_100)

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
        self._undo_action.triggered.connect(self._controller.undo)
        self._undo_action.setEnabled(False)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(self._controller.redo)
        self._redo_action.setEnabled(False)
        edit_menu.addAction(self._redo_action)

        edit_menu.addSeparator()

        select_all = QAction("Select &All", self)
        select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all.triggered.connect(self._controller.select_all)
        edit_menu.addAction(select_all)

        deselect = QAction("&Deselect", self)
        deselect.setShortcut("Ctrl+D")
        deselect.triggered.connect(self._controller.deselect_all)
        edit_menu.addAction(deselect)

        invert_sel = QAction("&Invert Selection", self)
        invert_sel.setShortcut("Ctrl+I")
        invert_sel.triggered.connect(self._controller.invert_selection)
        edit_menu.addAction(invert_sel)

        edit_menu.addSeparator()

        erase_sel = QAction("&Erase Selection", self)
        erase_sel.setShortcut("Delete")
        erase_sel.triggered.connect(self._controller.erase_selection)
        edit_menu.addAction(erase_sel)

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        # Tool shortcuts
        shortcuts = [
            ("P", EditorTool.PENCIL),
            ("E", EditorTool.ERASER),
            ("F", EditorTool.FILL),
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

        # Brush size shortcuts (Ctrl+Plus/Minus)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self._decrease_brush)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self._increase_brush)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self._increase_brush)

        # Zoom shortcuts (without Ctrl)
        QShortcut(QKeySequence("+"), self).activated.connect(self._canvas.zoom_in)
        QShortcut(QKeySequence("="), self).activated.connect(self._canvas.zoom_in)
        QShortcut(QKeySequence("-"), self).activated.connect(self._canvas.zoom_out)

    def _connect_signals(self) -> None:
        """Connect controller and widget signals."""
        # Controller signals
        self._controller.image_changed.connect(self._on_image_changed)
        self._controller.selection_changed.connect(self._on_selection_changed)
        self._controller.undo_state_changed.connect(self._on_undo_state_changed)
        self._controller.pixel_info.connect(self._on_pixel_info)
        self._controller.dirty_changed.connect(self._on_dirty_changed)

        # Canvas signals
        self._canvas.pixel_clicked.connect(self._on_canvas_clicked)
        self._canvas.pixel_dragged.connect(self._on_canvas_dragged)
        self._canvas.pixel_hovered.connect(self._on_canvas_hovered)
        self._canvas.mouse_left.connect(self._on_canvas_left)

        # Palette panel signals
        self._palette_panel.index_selected.connect(self._on_palette_index_selected)
        self._palette_panel.color_changed.connect(self._on_palette_color_changed)

    def _load_image(self) -> None:
        """Load the AI frame image."""
        path = Path(self._ai_frame.path)
        if self._controller.load_image(path, self._palette):
            # Update canvas
            data = self._controller.get_indexed_data()
            if data is not None:
                self._canvas.set_image(data, self._palette)
                # Initialize brush cursor
                self._canvas.set_brush_size(self._controller.brush_size)
        else:
            QMessageBox.warning(
                self,
                "Load Error",
                f"Failed to load image: {path}",
            )
            self.close()

    # --- Event Handlers ---

    def _on_tool_button_clicked(self, tool: EditorTool) -> None:
        """Handle tool button click."""
        self._select_tool(tool)

    def _select_tool(self, tool: EditorTool) -> None:
        """Select a tool."""
        self._controller.set_tool(tool)
        self._tool_buttons[tool].setChecked(True)
        self._tool_label.setText(f"Tool: {tool.name.replace('_', ' ').title()}")

    def _select_index(self, index: int) -> None:
        """Select a palette index."""
        self._controller.set_active_index(index)
        self._palette_panel.set_active_index(index)

    def _decrease_brush(self) -> None:
        """Decrease brush size."""
        new_size = max(1, self._controller.brush_size - 1)
        self._controller.set_brush_size(new_size)
        self._canvas.set_brush_size(new_size)

    def _increase_brush(self) -> None:
        """Increase brush size."""
        new_size = min(5, self._controller.brush_size + 1)
        self._controller.set_brush_size(new_size)
        self._canvas.set_brush_size(new_size)

    def _on_grid_toggled(self, checked: bool) -> None:
        """Handle grid toggle."""
        self._canvas.set_show_grid(checked)

    def _on_image_changed(self) -> None:
        """Handle image data change."""
        data = self._controller.get_indexed_data()
        if data is not None:
            self._canvas.set_image(data, self._palette)

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        self._canvas.set_selection_mask(self._controller.selection_mask)

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

    def _on_dirty_changed(self, is_dirty: bool) -> None:
        """Handle dirty state change."""
        self._dirty_label.setText("*" if is_dirty else "")
        title = f"Palette Editor - {self._ai_frame.display_name or Path(self._ai_frame.path).name}"
        if is_dirty:
            title += " *"
        self.setWindowTitle(title)

    def _on_canvas_clicked(self, x: int, y: int, button: int) -> None:
        """Handle canvas click."""
        from PySide6.QtWidgets import QApplication

        modifiers = QApplication.keyboardModifiers().value
        self._controller.handle_pixel_click(x, y, button, modifiers)

    def _on_canvas_dragged(self, x: int, y: int) -> None:
        """Handle canvas drag."""
        self._controller.handle_pixel_drag(x, y)

    def _on_canvas_hovered(self, x: int, y: int) -> None:
        """Handle canvas hover."""
        self._controller.handle_pixel_hover(x, y)

    def _on_canvas_left(self) -> None:
        """Handle mouse leaving canvas."""
        self._coord_label.setText("(-, -)")
        self._index_label.setText("Index: -")
        # Clear palette highlight
        self._palette_panel.highlight_index(None)

    def _on_palette_index_selected(self, index: int) -> None:
        """Handle palette panel selection."""
        self._controller.set_active_index(index)

    def _on_palette_color_changed(self, index: int, color: tuple[int, int, int]) -> None:
        """Handle palette color change from right-click."""
        self._controller.set_palette_color(index, color)

    def _on_save(self) -> None:
        """Handle save action."""
        if not self._controller.is_dirty:
            return

        # Generate output path
        original = Path(self._ai_frame.path)
        stem = original.stem
        if stem.endswith("_edited"):
            output_path = original
        else:
            output_path = original.parent / f"{stem}_edited.png"

        if self._controller.save(output_path):
            data = self._controller.get_indexed_data()
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

        if self._controller.is_dirty:
            result = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )

            if result == QMessageBox.StandardButton.Save:
                self._on_save()
                if self._controller.is_dirty:  # Save failed
                    event.ignore()
                    return
            elif result == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

        self.closed.emit()
        event.accept()
