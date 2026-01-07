#!/usr/bin/env python3
"""
Reusable editing workspace containing tool panels and pixel canvas.

This component can be embedded in both VRAM mode (via EditTab wrapper)
and ROM mode (directly in ROMWorkflowPage), eliminating the need for
widget reparenting when switching modes.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.common.signal_utils import safe_disconnect
from ui.common.spacing_constants import PANEL_PADDING, SPACING_MEDIUM, SPACING_SMALL

from ..panels import PalettePanel, PreviewPanel
from ..widgets import EditorStatusBar, IconToolbar, PixelCanvas, SaveExportPanel

if TYPE_CHECKING:
    from ...controllers.editing_controller import EditingController


class EditWorkspace(QWidget):
    """Reusable workspace with tool panels and pixel canvas.

    This workspace provides the core editing UI:
    - Top: IconToolbar (horizontal, spans full width)
    - Center-Left: Pixel canvas in scroll area (majority of space)
    - Center-Right: Palette, Preview, and Save/Export panels (vertical stack)
    - Bottom: EditorStatusBar (spans full width)

    The workspace connects to an EditingController for signal wiring.
    Multiple EditWorkspace instances can share the same controller,
    enabling mode switching without reparenting widgets.
    """

    # Signals
    detach_requested = Signal()
    image_modified = Signal()
    ready_for_inject = Signal()
    saveToRomRequested = Signal()
    exportPngRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller: EditingController | None = None
        self._canvas: PixelCanvas | None = None
        self._setup_ui()
        # Ensure workspace expands to fill parent container
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Set minimum width at workspace root (tool panel + canvas)
        self.setMinimumWidth(600)

    def _setup_ui(self) -> None:
        """Create the workspace UI with tool panels and canvas."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(PANEL_PADDING, PANEL_PADDING, PANEL_PADDING, PANEL_PADDING)
        main_layout.setSpacing(SPACING_MEDIUM)

        # Top: Icon toolbar (horizontal, spans full width)
        self._icon_toolbar = IconToolbar()
        main_layout.addWidget(self._icon_toolbar)

        # Center: Splitter for canvas (left) and panels (right)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Left side of splitter: Canvas in scroll area
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._scroll_area.setStyleSheet("QScrollArea { background-color: #303030; border: none; }")

        # Container for canvas - must expand to fill scroll area
        self._canvas_container = QWidget()
        self._canvas_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._canvas_layout = QVBoxLayout(self._canvas_container)
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Canvas placeholder (will be replaced when controller is set)
        self._canvas_placeholder = QWidget()
        self._canvas_placeholder.setMinimumSize(400, 400)
        self._canvas_layout.addWidget(self._canvas_placeholder)

        self._scroll_area.setWidget(self._canvas_container)
        self._splitter.addWidget(self._scroll_area)

        # Right side of splitter: Panel stack
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(SPACING_SMALL)

        # Palette panel
        self._palette_panel = PalettePanel()
        right_layout.addWidget(self._palette_panel)

        # Preview panel
        self._preview_panel = PreviewPanel()
        right_layout.addWidget(self._preview_panel)

        # Save/Export panel
        self._save_export_panel = SaveExportPanel()
        right_layout.addWidget(self._save_export_panel)

        # Action buttons (detach and ready for inject)
        self._detach_btn = QPushButton("Pop Out Editor")
        self._detach_btn.setToolTip("Open editor in a separate window")
        self._detach_btn.clicked.connect(self.detach_requested.emit)
        right_layout.addWidget(self._detach_btn)

        self._inject_btn = QPushButton("Ready for Inject")
        self._inject_btn.setToolTip("Save changes and switch to Inject tab")
        self._inject_btn.clicked.connect(self.ready_for_inject.emit)
        right_layout.addWidget(self._inject_btn)

        right_layout.addStretch()

        # Wrap right panel in scroll area for small screens
        self._right_scroll = QScrollArea()
        self._right_scroll.setWidgetResizable(True)
        self._right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._right_scroll.setWidget(right_panel)
        # Allow user to resize, set reasonable min width
        self._right_scroll.setMinimumWidth(200)
        self._right_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._splitter.addWidget(self._right_scroll)

        # Set splitter sizes (canvas: majority, right panel: 250px)
        self._splitter.setSizes([700, 250])
        self._splitter.setStretchFactor(0, 1)  # Canvas stretches
        self._splitter.setStretchFactor(1, 0)  # Right panel fixed

        main_layout.addWidget(self._splitter, 1)

        # Bottom: Status bar (spans full width)
        self._status_bar = EditorStatusBar()
        main_layout.addWidget(self._status_bar)

        # Connect SaveExportPanel signals
        self._save_export_panel.saveToRomClicked.connect(self.saveToRomRequested.emit)
        self._save_export_panel.exportPngClicked.connect(self.exportPngRequested.emit)

    # Public panel accessors (for external signal connections)
    @property
    def icon_toolbar(self) -> IconToolbar:
        """Access the icon toolbar."""
        return self._icon_toolbar

    @property
    def palette_panel(self) -> PalettePanel:
        """Access the palette panel."""
        return self._palette_panel

    @property
    def preview_panel(self) -> PreviewPanel:
        """Access the preview panel."""
        return self._preview_panel

    @property
    def save_export_panel(self) -> SaveExportPanel:
        """Access the save/export panel."""
        return self._save_export_panel

    @property
    def status_bar(self) -> EditorStatusBar:
        """Access the status bar."""
        return self._status_bar

    @property
    def scroll_area(self) -> QScrollArea:
        """Access the canvas scroll area."""
        return self._scroll_area

    @property
    def canvas_layout(self) -> QVBoxLayout:
        """Access the canvas layout."""
        return self._canvas_layout

    @property
    def controller(self) -> "EditingController | None":
        """Get the current controller."""
        return self._controller

    def get_canvas(self) -> PixelCanvas | None:
        """Get the pixel canvas widget."""
        return self._canvas

    def set_canvas(self, canvas: PixelCanvas) -> None:
        """Set the pixel canvas widget."""
        self._canvas = canvas
        # Clear previous items
        while self._canvas_layout.count():
            item = self._canvas_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._canvas_layout.addWidget(canvas)

    def _disconnect_signals(self) -> None:
        """Disconnect all controller signals before reconnection.

        This prevents signal accumulation when set_controller() is called
        multiple times (e.g., when switching between sprites).
        """
        # Disconnect canvas signals (canvas is created in set_controller)
        if self._canvas is not None:
            safe_disconnect(self._canvas.pixelPressed)
            safe_disconnect(self._canvas.pixelMoved)
            safe_disconnect(self._canvas.pixelReleased)
            safe_disconnect(self._canvas.zoomRequested)
            safe_disconnect(self._canvas.hoverPositionChanged)

        # Disconnect icon toolbar signals
        safe_disconnect(self._icon_toolbar.toolChanged)
        safe_disconnect(self._icon_toolbar.zoomInClicked)
        safe_disconnect(self._icon_toolbar.zoomOutClicked)
        safe_disconnect(self._icon_toolbar.gridToggled)
        safe_disconnect(self._icon_toolbar.tileGridToggled)
        safe_disconnect(self._icon_toolbar.palettePreviewToggled)

        # Disconnect palette panel signals
        safe_disconnect(self._palette_panel.colorSelected)

        # Disconnect controller signals (bidirectional sync)
        if self._controller is not None:
            safe_disconnect(self._controller.toolChanged)
            safe_disconnect(self._controller.colorChanged)
            safe_disconnect(self._controller.paletteChanged)
            safe_disconnect(self._controller.imageChanged)

    def set_controller(self, controller: "EditingController") -> None:
        """Set the editing controller, create canvas, and connect signals."""
        # Disconnect any existing signals to prevent accumulation
        self._disconnect_signals()

        self._controller = controller

        # Create the canvas
        self._canvas = PixelCanvas(controller)

        # Clear previous items from container
        while self._canvas_layout.count():
            item = self._canvas_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._canvas_layout.addWidget(self._canvas)

        # Connect canvas signals to controller
        self._canvas.pixelPressed.connect(controller.handle_pixel_press)
        self._canvas.pixelMoved.connect(controller.handle_pixel_move)
        self._canvas.pixelReleased.connect(controller.handle_pixel_release)

        # Connect icon toolbar signals
        self._icon_toolbar.toolChanged.connect(controller.set_tool)
        self._icon_toolbar.zoomInClicked.connect(self._on_zoom_in)
        self._icon_toolbar.zoomOutClicked.connect(self._on_zoom_out)
        self._icon_toolbar.gridToggled.connect(self._canvas.set_grid_visible)
        # Note: tileGridToggled connection depends on canvas support (may add later)

        # Connect palette preview toggle (canvas is guaranteed to exist here)
        canvas = self._canvas
        assert canvas is not None, "Canvas must exist in set_controller"
        self._icon_toolbar.palettePreviewToggled.connect(lambda visible: canvas.set_greyscale_mode(not visible))

        # Initialize canvas greyscale mode based on toolbar's default state
        canvas.set_greyscale_mode(not self._icon_toolbar.is_palette_preview_enabled())

        # Connect palette panel signals
        self._palette_panel.colorSelected.connect(controller.set_selected_color)

        # Connect controller→panel signals (bidirectional sync)
        controller.toolChanged.connect(self._icon_toolbar.set_tool)
        controller.colorChanged.connect(self._palette_panel.set_selected_color)
        controller.paletteChanged.connect(self._update_palette)

        # Connect preview panel to controller
        self._preview_panel.controller = controller
        controller.imageChanged.connect(self._preview_panel.update_preview)
        controller.paletteChanged.connect(self._preview_panel.update_preview)

        # Bidirectional zoom sync: canvas → toolbar (if needed for display)
        self._canvas.zoomRequested.connect(self._on_zoom_changed_from_canvas)

        # Connect canvas hover events to status bar
        self._canvas.hoverPositionChanged.connect(self._on_hover_position_changed)

    def update_from_controller(self) -> None:
        """Update UI state from controller."""
        if not self._controller:
            return

        # Update tool selection
        current_tool = self._controller.get_current_tool_name()
        self._icon_toolbar.set_tool(current_tool)

        # Update selected color
        selected_color = self._controller.get_selected_color()
        self._palette_panel.set_selected_color(selected_color)

        # Update palette colors
        colors = self._controller.get_current_colors()
        self._palette_panel.set_palette(colors)

    def set_palette(self, colors: list[tuple[int, int, int]], name: str = "") -> None:
        """Update the displayed palette."""
        self._palette_panel.set_palette(colors, name)

    def set_image_loaded(self, loaded: bool) -> None:
        """Enable/disable editing controls based on image state."""
        self._icon_toolbar.setEnabled(loaded)
        self._inject_btn.setEnabled(loaded)
        self._save_export_panel.set_save_enabled(loaded)
        self._save_export_panel.set_export_enabled(loaded)

    def _update_palette(self) -> None:
        """Update palette panel when controller palette changes."""
        if not self._controller:
            return

        colors = self._controller.get_current_colors()
        palette_name = self._controller.palette_model.name
        self._palette_panel.set_palette(colors, palette_name)

    def _on_zoom_in(self) -> None:
        """Handle zoom in button click."""
        if not self._canvas:
            return
        current_zoom = self._canvas.zoom
        new_zoom = min(current_zoom + 1, 64)  # Max zoom 64x
        self._canvas.set_zoom(new_zoom)

    def _on_zoom_out(self) -> None:
        """Handle zoom out button click."""
        if not self._canvas:
            return
        current_zoom = self._canvas.zoom
        new_zoom = max(current_zoom - 1, 1)  # Min zoom 1x
        self._canvas.set_zoom(new_zoom)

    def _on_zoom_changed_from_canvas(self, zoom: int) -> None:
        """Handle zoom change from canvas (e.g., mouse wheel)."""
        # Update status bar or other UI elements if needed
        pass

    def _on_hover_position_changed(self, x: int, y: int) -> None:
        """Update status bar from canvas hover position."""
        if x == -1 and y == -1:
            # Mouse left canvas
            self._status_bar.clear_cursor()
            return

        # Update cursor position
        self._status_bar.update_cursor(x, y)

        if not self._controller:
            return

        # Calculate tile ID (8x8 tiles for SNES sprites)
        width, _height = self._controller.get_image_size()
        if width > 0:
            tiles_per_row = max(1, width // 8)
            tile_id = (y // 8) * tiles_per_row + (x // 8)
            self._status_bar.update_tile(tile_id)

        # Get pixel color and update color preview
        color_index = self._controller.image_model.get_pixel(x, y)
        colors = self._controller.get_current_colors()
        if 0 <= color_index < len(colors):
            self._status_bar.update_color(colors[color_index])
