#!/usr/bin/env python3
"""
Edit tab for the unified sprite editor.
Combines the pixel editor canvas with tool and palette panels.
Supports both embedded and detached editing modes.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
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
        left_layout.addStretch()

        splitter.addWidget(left_panel)

        # Right side: Canvas in scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #303030; border: none; }")

        # Canvas placeholder (will be set by controller)
        self._canvas_placeholder = QWidget()
        self._canvas_placeholder.setMinimumSize(400, 400)
        self.scroll_area.setWidget(self._canvas_placeholder)

        splitter.addWidget(self.scroll_area)

        # Set splitter sizes (left panel: 250px, canvas: rest)
        splitter.setSizes([250, 600])

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
        self.scroll_area.setWidget(canvas)

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

    def set_controller(self, controller: "EditingController") -> None:
        """Set the editing controller, create canvas, and connect signals."""
        # Disconnect any existing signals to prevent accumulation
        self._disconnect_signals()

        self.controller = controller

        # Create the canvas (moved from MainController)
        self._canvas = PixelCanvas(controller)
        self.scroll_area.setWidget(self._canvas)

        # Connect canvas signals to controller
        self._canvas.pixelPressed.connect(controller.handle_pixel_press)
        self._canvas.pixelMoved.connect(controller.handle_pixel_move)
        self._canvas.pixelReleased.connect(controller.handle_pixel_release)

        # Connect tool panel signals
        self.tool_panel.toolChanged.connect(controller.set_tool)
        self.tool_panel.brushSizeChanged.connect(controller.set_brush_size)

        # Connect palette panel signals
        self.palette_panel.colorSelected.connect(controller.set_selected_color)

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
