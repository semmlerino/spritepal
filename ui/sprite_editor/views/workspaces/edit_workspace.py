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
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.common.signal_utils import safe_disconnect
from ui.common.spacing_constants import PANEL_PADDING, SPACING_MEDIUM, SPACING_SMALL

from ..panels import OptionsPanel, PalettePanel, PreviewPanel, ToolPanel
from ..widgets import PixelCanvas

if TYPE_CHECKING:
    from ...controllers.editing_controller import EditingController


class EditWorkspace(QWidget):
    """Reusable workspace with tool panels and pixel canvas.

    This workspace provides the core editing UI:
    - Left panel: Tool, Palette, Options, Preview panels in a scroll area
    - Right panel: Pixel canvas in a scroll area

    The workspace connects to an EditingController for signal wiring.
    Multiple EditWorkspace instances can share the same controller,
    enabling mode switching without reparenting widgets.
    """

    # Signals
    detach_requested = Signal()
    image_modified = Signal()
    ready_for_inject = Signal()

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
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(PANEL_PADDING, PANEL_PADDING, PANEL_PADDING, PANEL_PADDING)
        main_layout.setSpacing(SPACING_MEDIUM)

        # Create splitter for resizable layout
        self._splitter = QSplitter()
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Left side: Tool panels in scroll area
        left_panel = QWidget()
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SPACING_SMALL)

        # Tool panel
        self._tool_panel = ToolPanel()
        left_layout.addWidget(self._tool_panel)

        # Palette panel
        self._palette_panel = PalettePanel()
        left_layout.addWidget(self._palette_panel)

        # Options panel
        self._options_panel = OptionsPanel()
        left_layout.addWidget(self._options_panel)

        # Preview panel
        self._preview_panel = PreviewPanel()
        left_layout.addWidget(self._preview_panel)

        # Action buttons
        actions_layout = QHBoxLayout()

        self._detach_btn = QPushButton("Pop Out Editor")
        self._detach_btn.setToolTip("Open editor in a separate window")
        self._detach_btn.clicked.connect(self.detach_requested.emit)
        actions_layout.addWidget(self._detach_btn)

        self._inject_btn = QPushButton("Ready for Inject")
        self._inject_btn.setToolTip("Save changes and switch to Inject tab")
        self._inject_btn.clicked.connect(self.ready_for_inject.emit)
        actions_layout.addWidget(self._inject_btn)

        left_layout.addLayout(actions_layout)
        left_layout.addStretch()

        # Wrap in scroll area for small screens
        self._left_scroll = QScrollArea()
        self._left_scroll.setWidgetResizable(True)
        self._left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._left_scroll.setWidget(left_panel)
        # Allow user to resize, set reasonable min width
        self._left_scroll.setMinimumWidth(200)
        self._left_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._splitter.addWidget(self._left_scroll)

        # Right side: Canvas in scroll area
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

        # Set splitter sizes (left panel: 300px, canvas: rest)
        self._splitter.setSizes([300, 600])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._splitter, 1)

    # Public panel accessors (for external signal connections)
    @property
    def tool_panel(self) -> ToolPanel:
        """Access the tool panel."""
        return self._tool_panel

    @property
    def palette_panel(self) -> PalettePanel:
        """Access the palette panel."""
        return self._palette_panel

    @property
    def options_panel(self) -> OptionsPanel:
        """Access the options panel."""
        return self._options_panel

    @property
    def preview_panel(self) -> PreviewPanel:
        """Access the preview panel."""
        return self._preview_panel

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

        # Disconnect tool panel signals
        safe_disconnect(self._tool_panel.toolChanged)
        safe_disconnect(self._tool_panel.brushSizeChanged)

        # Disconnect palette panel signals
        safe_disconnect(self._palette_panel.colorSelected)

        # Disconnect options panel signals
        safe_disconnect(self._options_panel.gridToggled)
        safe_disconnect(self._options_panel.paletteToggled)
        safe_disconnect(self._options_panel.zoomChanged)
        safe_disconnect(self._options_panel.zoomToFit)

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

        # Connect tool panel signals
        self._tool_panel.toolChanged.connect(controller.set_tool)
        self._tool_panel.brushSizeChanged.connect(controller.set_brush_size)

        # Connect palette panel signals
        self._palette_panel.colorSelected.connect(controller.set_selected_color)

        # Connect controller→panel signals (bidirectional sync)
        controller.toolChanged.connect(self._tool_panel.set_tool)
        controller.colorChanged.connect(self._palette_panel.set_selected_color)
        controller.paletteChanged.connect(self._update_palette)

        # Connect preview panel to controller
        self._preview_panel.controller = controller
        controller.imageChanged.connect(self._preview_panel.update_preview)
        controller.paletteChanged.connect(self._preview_panel.update_preview)
        controller.colorChanged.connect(self._preview_panel.update_color_preview)

        # Connect palette selection to color preview
        self._palette_panel.colorSelected.connect(self._preview_panel.update_color_preview)

        # Connect options panel signals to canvas
        canvas = self._canvas
        self._options_panel.gridToggled.connect(canvas.set_grid_visible)
        self._options_panel.paletteToggled.connect(lambda visible: canvas.set_greyscale_mode(not visible))
        self._options_panel.zoomChanged.connect(canvas.set_zoom)

        # Bidirectional zoom sync: canvas → slider
        canvas.zoomRequested.connect(self._options_panel.set_zoom)

        # Fit button handler
        self._options_panel.zoomToFit.connect(self._on_zoom_to_fit)

    def update_from_controller(self) -> None:
        """Update UI state from controller."""
        if not self._controller:
            return

        # Update tool selection
        current_tool = self._controller.get_current_tool_name()
        self._tool_panel.set_tool(current_tool)

        # Update brush size
        brush_size = self._controller.tool_manager.get_brush_size()
        self._tool_panel.set_brush_size(brush_size)

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
        self._tool_panel.setEnabled(loaded)
        self._options_panel.setEnabled(loaded)
        self._inject_btn.setEnabled(loaded)

    def _update_palette(self) -> None:
        """Update palette panel when controller palette changes."""
        if not self._controller:
            return

        colors = self._controller.get_current_colors()
        palette_name = self._controller.palette_model.name
        self._palette_panel.set_palette(colors, palette_name)

    def _on_zoom_to_fit(self) -> None:
        """Calculate and apply zoom to fit image in viewport."""
        if not self._canvas or not self._controller:
            return

        # Get viewport visible area
        viewport_size = self._scroll_area.viewport().size()

        # Get image dimensions
        img_width, img_height = self._controller.get_image_size()
        if img_width == 0 or img_height == 0:
            return

        # Calculate zoom that fits entire image
        zoom_x = max(1, viewport_size.width() // img_width)
        zoom_y = max(1, viewport_size.height() // img_height)
        fit_zoom = min(zoom_x, zoom_y, 64)  # Clamp to valid range

        # Apply zoom to both canvas and slider
        self._canvas.set_zoom(fit_zoom)
        self._options_panel.set_zoom(fit_zoom)
