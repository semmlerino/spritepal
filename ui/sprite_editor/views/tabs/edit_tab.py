#!/usr/bin/env python3
"""
Edit tab for the unified sprite editor.
Combines the pixel editor canvas with tool and palette panels.
Supports both embedded and detached editing modes.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.common.signal_utils import safe_disconnect

from ..panels import OptionsPanel, PalettePanel, PreviewPanel, ToolPanel
from ..widgets import PixelCanvas

if TYPE_CHECKING:
    from ...controllers.editing_controller import EditingController


class EditTab(QWidget):
    """Tab widget for pixel editing functionality.

    Embeds the pixel canvas and editing panels. Can be detached
    to a separate window for dedicated editing.
    """

    # Signals
    detach_requested = Signal()
    image_modified = Signal()
    ready_for_inject = Signal()

    def __init__(
        self,
        controller: "EditingController | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._canvas: PixelCanvas | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the edit tab UI."""
        main_layout = QHBoxLayout(self)

        # Create splitter for resizable layout
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        # Left side: Tool panels
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Tool panel
        self.tool_panel = ToolPanel()
        left_layout.addWidget(self.tool_panel)

        # Palette panel
        self.palette_panel = PalettePanel()
        left_layout.addWidget(self.palette_panel)

        # Options panel
        self.options_panel = OptionsPanel()
        left_layout.addWidget(self.options_panel)

        # Preview panel
        self.preview_panel = PreviewPanel()
        left_layout.addWidget(self.preview_panel)

        # Detach/Actions buttons
        actions_layout = QHBoxLayout()

        self.detach_btn = QPushButton("Pop Out Editor")
        self.detach_btn.setToolTip("Open editor in a separate window")
        self.detach_btn.clicked.connect(self.detach_requested.emit)
        actions_layout.addWidget(self.detach_btn)

        self.inject_btn = QPushButton("Ready for Inject")
        self.inject_btn.setToolTip("Save changes and switch to Inject tab")
        self.inject_btn.clicked.connect(self.ready_for_inject.emit)
        actions_layout.addWidget(self.inject_btn)

        left_layout.addLayout(actions_layout)

        splitter.addWidget(left_panel)

        # Right side: Canvas in scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #303030; border: none; }")

        # Container for canvas to allow centering/resizing
        self.canvas_container = QWidget()
        self.canvas_layout = QVBoxLayout(self.canvas_container)
        self.canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_layout.setContentsMargins(0, 0, 0, 0)

        # Canvas placeholder (will be set by controller)
        self._canvas_placeholder = QWidget()
        self._canvas_placeholder.setMinimumSize(400, 400)
        self.canvas_layout.addWidget(self._canvas_placeholder)

        self.scroll_area.setWidget(self.canvas_container)

        splitter.addWidget(self.scroll_area)

        # Set splitter sizes (left panel: 250px, canvas: rest)
        splitter.setSizes([250, 600])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        # Connect panel signals
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect panel signals to controller."""
        # These will be connected when controller is set
        pass

    def set_canvas(self, canvas: PixelCanvas) -> None:
        """Set the pixel canvas widget."""
        self._canvas = canvas
        # Clear previous items
        while self.canvas_layout.count():
            item = self.canvas_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.canvas_layout.addWidget(canvas)

    def get_canvas(self) -> PixelCanvas | None:
        """Get the pixel canvas widget."""
        return self._canvas

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

        # Disconnect tool panel signals (panels created in _setup_ui, always exist)
        safe_disconnect(self.tool_panel.toolChanged)
        safe_disconnect(self.tool_panel.brushSizeChanged)

        # Disconnect palette panel signals
        safe_disconnect(self.palette_panel.colorSelected)

        # Disconnect options panel signals
        safe_disconnect(self.options_panel.gridToggled)
        safe_disconnect(self.options_panel.paletteToggled)
        safe_disconnect(self.options_panel.zoomChanged)
        safe_disconnect(self.options_panel.zoomToFit)

        # Disconnect controller signals (bidirectional sync)
        if self.controller is not None:
            safe_disconnect(self.controller.toolChanged)
            safe_disconnect(self.controller.colorChanged)
            safe_disconnect(self.controller.paletteChanged)
            safe_disconnect(self.controller.imageChanged)

    def set_controller(self, controller: "EditingController") -> None:
        """Set the editing controller, create canvas, and connect signals."""
        # Disconnect any existing signals to prevent accumulation
        self._disconnect_signals()

        self.controller = controller

        # Create the canvas (moved from MainController)
        self._canvas = PixelCanvas(controller)

        # Clear previous items from container
        while self.canvas_layout.count():
            item = self.canvas_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.canvas_layout.addWidget(self._canvas)

        # Connect canvas signals to controller
        self._canvas.pixelPressed.connect(controller.handle_pixel_press)
        self._canvas.pixelMoved.connect(controller.handle_pixel_move)
        self._canvas.pixelReleased.connect(controller.handle_pixel_release)

        # Connect tool panel signals
        self.tool_panel.toolChanged.connect(controller.set_tool)
        self.tool_panel.brushSizeChanged.connect(controller.set_brush_size)

        # Connect palette panel signals
        self.palette_panel.colorSelected.connect(controller.set_selected_color)

        # Connect controller→panel signals (bidirectional sync)
        controller.toolChanged.connect(self.tool_panel.set_tool)
        controller.colorChanged.connect(self.palette_panel.set_selected_color)
        controller.paletteChanged.connect(self._update_palette)

        # Connect preview panel to controller
        self.preview_panel.controller = controller
        controller.imageChanged.connect(self.preview_panel.update_preview)
        controller.paletteChanged.connect(self.preview_panel.update_preview)
        controller.colorChanged.connect(self.preview_panel.update_color_preview)

        # Connect palette selection to color preview
        self.palette_panel.colorSelected.connect(self.preview_panel.update_color_preview)

        # Connect options panel signals to canvas
        # Capture canvas in local var to avoid None type issues in lambda
        canvas = self._canvas
        self.options_panel.gridToggled.connect(canvas.set_grid_visible)
        self.options_panel.paletteToggled.connect(lambda visible: canvas.set_greyscale_mode(not visible))
        self.options_panel.zoomChanged.connect(canvas.set_zoom)

        # Bidirectional zoom sync: canvas → slider
        canvas.zoomRequested.connect(self.options_panel.set_zoom)

        # Fit button handler
        self.options_panel.zoomToFit.connect(self._on_zoom_to_fit)

    def update_from_controller(self) -> None:
        """Update UI state from controller."""
        if not self.controller:
            return

        # Update tool selection
        current_tool = self.controller.get_current_tool_name()
        self.tool_panel.set_tool(current_tool)

        # Update brush size
        brush_size = self.controller.tool_manager.get_brush_size()
        self.tool_panel.set_brush_size(brush_size)

        # Update selected color
        selected_color = self.controller.get_selected_color()
        self.palette_panel.set_selected_color(selected_color)

        # Update palette colors
        colors = self.controller.get_current_colors()
        self.palette_panel.set_palette(colors)

    def set_palette(self, colors: list[tuple[int, int, int]], name: str = "") -> None:
        """Update the displayed palette."""
        self.palette_panel.set_palette(colors, name)

    def set_image_loaded(self, loaded: bool) -> None:
        """Enable/disable editing controls based on image state."""
        self.tool_panel.setEnabled(loaded)
        self.options_panel.setEnabled(loaded)
        self.inject_btn.setEnabled(loaded)

    def _update_palette(self) -> None:
        """Update palette panel when controller palette changes.

        Called when controller.paletteChanged signal emits.
        """
        if not self.controller:
            return

        colors = self.controller.get_current_colors()
        palette_name = self.controller.palette_model.name
        self.palette_panel.set_palette(colors, palette_name)

    def _on_zoom_to_fit(self) -> None:
        """Calculate and apply zoom to fit image in viewport."""
        if not self._canvas or not self.controller:
            return

        # Get viewport visible area
        viewport_size = self.scroll_area.viewport().size()

        # Get image dimensions
        img_width, img_height = self.controller.get_image_size()
        if img_width == 0 or img_height == 0:
            return

        # Calculate zoom that fits entire image
        zoom_x = max(1, viewport_size.width() // img_width)
        zoom_y = max(1, viewport_size.height() // img_height)
        fit_zoom = min(zoom_x, zoom_y, 64)  # Clamp to valid range

        # Apply zoom to both canvas and slider
        self._canvas.set_zoom(fit_zoom)
        self.options_panel.set_zoom(fit_zoom)
