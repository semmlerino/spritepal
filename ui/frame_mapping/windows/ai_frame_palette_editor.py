#!/usr/bin/env python3
"""
AI Frame Palette Editor Window.

A modeless window for editing AI frame palette indices before ROM injection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
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
    from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
    from ui.frame_mapping.services.async_preview_service import AsyncPreviewService

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
    """

    save_requested = Signal(str, object, str)  # ai_frame_id, np.ndarray, output_path
    closed = Signal(str)  # ai_frame_id (current, may have changed after save)
    palette_color_changed = Signal(int, tuple)  # index, (r, g, b)

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
        self._controller = PaletteEditorController(self)
        self._frame_controller = controller
        self._preview_enabled = False
        self._async_preview_service: AsyncPreviewService | None = None
        self._debounce_timer: QTimer | None = None

        self._setup_ui()
        self._setup_menu()
        self._setup_shortcuts()
        self._connect_signals()
        self._load_image()

        # Window settings
        self.setWindowTitle(f"Palette Index Editor - {ai_frame.display_name or Path(ai_frame.path).name}")
        self.resize(900, 700)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Initialize preview service if controller is available
        if self._frame_controller is not None:
            from ui.frame_mapping.services.async_preview_service import AsyncPreviewService

            self._async_preview_service = AsyncPreviewService(self)
            self._async_preview_service.preview_ready.connect(self._on_preview_ready)
            self._async_preview_service.preview_failed.connect(self._on_preview_failed)

            self._debounce_timer = QTimer()
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.setInterval(300)
            self._debounce_timer.timeout.connect(self._generate_preview)

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

        # Center section: Warning banner + Canvas
        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)

        # Duplicate color warning banner
        self._duplicate_warning_label = QLabel(
            "⚠ Duplicate colors detected in palette. During injection, pixels with the same "
            "color will be mapped to the same index, regardless of their original index."
        )
        self._duplicate_warning_label.setStyleSheet(
            "background-color: #FFF3CD; color: #856404; padding: 6px 8px; border-radius: 4px; font-size: 11px;"
        )
        self._duplicate_warning_label.setWordWrap(True)
        self._duplicate_warning_label.setVisible(False)
        center_layout.addWidget(self._duplicate_warning_label)

        # Add canvas to center layout
        center_layout.addWidget(self._canvas, 1)
        main_layout.addLayout(center_layout, 1)

        # Right: Palette panel
        self._palette_panel = EditorPalettePanel()
        self._palette_panel.set_palette(self._palette)
        self._palette_panel.set_active_index(1)
        main_layout.addWidget(self._palette_panel)

        # Far right: Preview panel (collapsible)
        self._preview_panel = self._create_preview_panel()
        self._preview_panel.setVisible(False)  # Hidden by default
        main_layout.addWidget(self._preview_panel)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._coord_label = QLabel("(-, -)")
        self._index_label = QLabel("Index: -")
        self._selection_count_label = QLabel("Selected: 0")
        self._selection_mode_label = QLabel("Mode: Replace")
        self._tool_label = QLabel("Tool: Pencil")
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
            (EditorTool.PENCIL, "Pencil", "P", "Draw with selected color (P)"),
            (EditorTool.ERASER, "Eraser", "E", "Erase to transparent (E)"),
            (EditorTool.FILL, "Fill", "F", "Flood fill area (F)"),
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

        # Select pencil by default
        self._tool_buttons[EditorTool.PENCIL].setChecked(True)

        layout.addSpacing(16)

        # Selection actions header
        actions_label = QLabel("Selection")
        actions_label.setStyleSheet("font-weight: bold; color: #AAA;")
        layout.addWidget(actions_label)

        # Fill Selection button
        self._fill_selection_btn = QPushButton("Fill Sel [Shift+F]")
        self._fill_selection_btn.setToolTip("Fill selected pixels with active color (Shift+F)")
        self._fill_selection_btn.setFixedHeight(28)
        self._fill_selection_btn.clicked.connect(self._controller.paint_selection)
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

    def _create_preview_panel(self) -> QWidget:
        """Create the collapsible preview panel."""
        panel = QWidget()
        panel.setFixedWidth(200)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QLabel("Preview")
        header.setStyleSheet("font-weight: bold; color: #AAA;")
        layout.addWidget(header)

        # Preview display area with graphics view
        self._preview_scene = QGraphicsScene(self)
        self._preview_view = QGraphicsView(self._preview_scene)
        self._preview_view.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._preview_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self._preview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._preview_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._preview_view.setStyleSheet("background-color: #2A2A2A; border: 1px solid #444;")
        self._preview_view.setMinimumHeight(150)

        # Pixmap item for preview
        self._preview_pixmap_item = QGraphicsPixmapItem()
        self._preview_scene.addItem(self._preview_pixmap_item)

        layout.addWidget(self._preview_view, 1)

        # Info label
        self._preview_info_label = QLabel("Shows quantized result\nas it appears in-game")
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

        edit_menu.addSeparator()

        replace_index = QAction("&Replace Index...", self)
        replace_index.setShortcut("Ctrl+R")
        replace_index.triggered.connect(self._show_replace_index_dialog)
        edit_menu.addAction(replace_index)

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

        # Selection action shortcuts
        QShortcut(QKeySequence("Shift+F"), self).activated.connect(self._controller.paint_selection)

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
        self._controller.active_index_changed.connect(self._on_active_index_changed)
        self._controller.color_mapping_report.connect(self._on_color_mapping_report)

        # Canvas signals
        self._canvas.pixel_clicked.connect(self._on_canvas_clicked)
        self._canvas.pixel_dragged.connect(self._on_canvas_dragged)
        self._canvas.pixel_hovered.connect(self._on_canvas_hovered)
        self._canvas.mouse_left.connect(self._on_canvas_left)
        self._canvas.drag_ended.connect(self._controller.finish_stroke)
        self._canvas.brush_size_changed.connect(self._on_brush_size_changed)

        # Palette panel signals
        self._palette_panel.index_selected.connect(self._on_palette_index_selected)
        self._palette_panel.color_changed.connect(self._on_palette_color_changed)
        self._palette_panel.merge_requested.connect(self._on_palette_merge_requested)

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

    def _on_brush_size_changed(self, size: int) -> None:
        """Handle brush size change from Ctrl+RMB drag on canvas."""
        self._controller.set_brush_size(size)

    def _on_grid_toggled(self, checked: bool) -> None:
        """Handle grid toggle."""
        self._canvas.set_show_grid(checked)

    def _on_image_changed(self) -> None:
        """Handle image data change."""
        data = self._controller.get_indexed_data()
        if data is not None:
            self._canvas.set_image(data, self._palette)
            # Refresh highlight overlay with new data
            self._canvas.set_highlight_index(self._controller.active_index)

        # Schedule preview update if enabled
        if self._preview_enabled:
            if self._frame_controller is not None:
                project = self._frame_controller.project
                if project is not None:
                    mapping = project.get_mapping_for_ai_frame(self._ai_frame.id)
                    if mapping is not None and self._debounce_timer is not None:
                        # Debounced composite preview
                        self._debounce_timer.start()
                    else:
                        # Immediate standalone preview (no async needed)
                        self._generate_standalone_preview()

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        mask = self._controller.selection_mask
        self._canvas.set_selection_mask(mask)
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
        # Update canvas highlight to show all pixels using this index
        self._canvas.set_highlight_index(index)

    def _on_color_mapping_report(self, report: dict[str, object]) -> None:
        """Handle color mapping analysis report after image load.

        Shows an informational dialog if there were colors requiring
        nearest-neighbor fallback during RGB→indexed conversion.
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

    def _on_canvas_clicked(self, x: int, y: int, button: int) -> None:
        """Handle canvas click."""
        from PySide6.QtWidgets import QApplication

        modifiers = QApplication.keyboardModifiers().value
        self._update_selection_mode_display(modifiers)
        self._controller.handle_pixel_click(x, y, button, modifiers)

    def _on_canvas_dragged(self, x: int, y: int) -> None:
        """Handle canvas drag."""
        self._controller.handle_pixel_drag(x, y)

    def _on_canvas_hovered(self, x: int, y: int) -> None:
        """Handle canvas hover."""
        from PySide6.QtWidgets import QApplication

        # Update selection mode display based on current modifiers
        modifiers = QApplication.keyboardModifiers().value
        self._update_selection_mode_display(modifiers)
        self._controller.handle_pixel_hover(x, y)

    def _on_canvas_left(self) -> None:
        """Handle mouse leaving canvas."""
        self._coord_label.setText("(-, -)")
        self._index_label.setText("Index: -")
        # Clear palette highlight
        self._palette_panel.highlight_index(None)

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

            # Check if we have a mapping (for full composite preview)
            mapping = project.get_mapping_for_ai_frame(self._ai_frame.id)

            # Show preview panel
            self._preview_panel.setVisible(True)

            if mapping is not None:
                # Full composite preview with game sprite
                self._preview_info_label.setText("In-game composite preview")
                self._generate_preview()
            else:
                # Standalone quantized preview (no mapping required)
                self._preview_info_label.setText("Quantized preview\n(no mapping - no game sprite)")
                self._generate_standalone_preview()
        else:
            # Hide preview panel
            self._preview_panel.setVisible(False)

    def _generate_preview(self) -> None:
        """Generate in-game preview asynchronously."""
        if not self._preview_enabled or self._frame_controller is None or self._async_preview_service is None:
            return

        project = self._frame_controller.project
        if project is None:
            return

        mapping = project.get_mapping_for_ai_frame(self._ai_frame.id)
        if mapping is None:
            return

        capture_result, _ = self._frame_controller.get_capture_result_for_game_frame(mapping.game_frame_id)
        if capture_result is None:
            self._status_bar.showMessage("Capture data not found", 3000)
            return

        indexed_data = self._controller.get_indexed_data()
        if indexed_data is None:
            return

        # Convert indexed to RGBA PIL Image
        from core.services.rgb_to_indexed import convert_indexed_to_rgb

        ai_image = convert_indexed_to_rgb(indexed_data, self._palette)

        from core.services.sprite_compositor import TransformParams

        transform = TransformParams(
            offset_x=mapping.offset_x,
            offset_y=mapping.offset_y,
            flip_h=mapping.flip_h,
            flip_v=mapping.flip_v,
            scale=mapping.scale,
            sharpen=mapping.sharpen,
            resampling=mapping.resampling,
        )

        self._async_preview_service.request_preview(
            ai_image=ai_image,
            capture_result=capture_result,
            transform=transform,
            uncovered_policy="transparent",
            sheet_palette=self._palette,
            ai_index_map=indexed_data,
            display_scale=1,
        )

    def _generate_standalone_preview(self) -> None:
        """Generate standalone quantized preview (no game sprite background)."""
        indexed_data = self._controller.get_indexed_data()
        if indexed_data is None:
            return

        from core.services.rgb_to_indexed import convert_indexed_to_rgb

        # Convert indexed data to RGBA using sheet palette
        ai_image = convert_indexed_to_rgb(indexed_data, self._palette)

        # Convert PIL Image to QImage and display
        from PySide6.QtGui import QImage

        # ai_image is a PIL Image in RGBA mode
        data = ai_image.tobytes("raw", "RGBA")
        qimage = QImage(data, ai_image.width, ai_image.height, QImage.Format.Format_RGBA8888)

        pixmap = QPixmap.fromImage(qimage)
        self._preview_pixmap_item.setPixmap(pixmap)
        self._preview_scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self._preview_view.fitInView(self._preview_pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _on_preview_ready(self, qimage: QImage, width: int, height: int) -> None:
        """Handle async preview completion."""
        if not self._preview_enabled:
            return

        pixmap = QPixmap.fromImage(qimage)
        self._preview_pixmap_item.setPixmap(pixmap)
        self._preview_scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self._preview_view.fitInView(self._preview_pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _on_preview_failed(self, error_message: str) -> None:
        """Handle async preview failure."""
        logger.warning("Preview generation failed: %s", error_message)
        self._status_bar.showMessage(f"Preview failed: {error_message}", 5000)
        # Clear the preview display
        self._preview_pixmap_item.setPixmap(QPixmap())

    def _on_palette_index_selected(self, index: int) -> None:
        """Handle palette panel selection."""
        self._controller.set_active_index(index)
        # Highlight all pixels using this index
        self._canvas.set_highlight_index(index)

    def _on_palette_color_changed(self, index: int, color: tuple[int, int, int]) -> None:
        """Handle palette color change from right-click."""
        # Update the palette directly to ensure synchronization
        if 0 < index < len(self._palette.colors):
            self._palette.colors[index] = color

        # Also update via controller for dirty state tracking
        self._controller.set_palette_color(index, color)

        # Refresh the canvas with the updated palette
        data = self._controller.get_indexed_data()
        if data is not None:
            self._canvas.set_image(data, self._palette)

        # Also sync the palette panel's swatch (in case signal didn't update it)
        self._palette_panel.sync_palette(self._palette)

        # Notify workspace to refresh other frames with updated palette
        self.palette_color_changed.emit(index, color)

    def _on_palette_merge_requested(self, primary_index: int, merge_index: int) -> None:
        """Handle palette merge request (Ctrl+click).

        Merges all pixels using merge_index into primary_index, freeing up
        the merge_index slot (shown as dark purple).
        """
        if self._controller.merge_palette_indices(primary_index, merge_index):
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
        from_spin.setValue(self._controller.active_index)
        form.addRow("Replace index:", from_spin)

        to_spin = QSpinBox()
        to_spin.setRange(0, 15)
        to_spin.setValue(1 if self._controller.active_index == 0 else 0)
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

            result = self._controller.replace_index(from_index, to_index)
            if result > 0:
                self._status_bar.showMessage(
                    f"Replaced {result} pixel(s): index {from_index} → {to_index}",
                    5000,
                )
            elif result == 0:
                QMessageBox.information(
                    self,
                    "No Pixels Found",
                    f"No pixels were using index {from_index}.",
                )

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

        if self._async_preview_service is not None:
            self._async_preview_service.shutdown()
        if self._debounce_timer is not None:
            self._debounce_timer.stop()

        self.closed.emit(self._ai_frame.id)
        event.accept()
