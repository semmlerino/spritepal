#!/usr/bin/env python3
"""
Reusable editing workspace containing tool panels and pixel canvas.

This component can be embedded in both VRAM mode (via EditTab wrapper)
and ROM mode (directly in ROMWorkflowPage), eliminating the need for
widget reparenting when switching modes.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
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

from ..panels import OverlayPanel, PalettePanel, PreviewPanel
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

    Args:
        embed_mode: Layout mode for the workspace.
            - 'standalone': Creates internal splitter for canvas/panels (default, VRAM mode)
            - 'embedded': Creates widgets without splitter - parent manages layout (ROM flat mode)
        parent: Parent widget.
    """

    # Signals
    detach_requested = Signal()
    image_modified = Signal()
    ready_for_inject = Signal()
    saveToRomRequested = Signal()
    exportPngRequested = Signal()
    saveProjectRequested = Signal()
    loadProjectRequested = Signal()
    importImageRequested = Signal()
    arrangeClicked = Signal()

    def __init__(self, embed_mode: str = "standalone", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._embed_mode = embed_mode
        self._controller: EditingController | None = None
        self._canvas: PixelCanvas | None = None
        self._splitter: QSplitter | None = None
        self._last_validation_state = True
        self._image_loaded = False
        self._setup_ui()
        self._setup_shortcuts()
        # Ensure workspace expands to fill parent container
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _setup_ui(self) -> None:
        """Create the workspace UI with tool panels and canvas."""
        # Create all widgets regardless of mode
        self._icon_toolbar = IconToolbar()
        self._scroll_area = self._create_canvas_scroll_area()
        self._right_scroll = self._create_right_panel_scroll()
        self._status_bar = EditorStatusBar()

        # Connect SaveExportPanel signals
        self._save_export_panel.saveToRomClicked.connect(self.saveToRomRequested.emit)
        self._save_export_panel.exportPngClicked.connect(self.exportPngRequested.emit)
        self._save_export_panel.saveProjectClicked.connect(self.saveProjectRequested.emit)
        self._save_export_panel.loadProjectClicked.connect(self.loadProjectRequested.emit)

        # Connect IconToolbar action signals
        self._icon_toolbar.importClicked.connect(self.importImageRequested.emit)

        if self._embed_mode == "standalone":
            # Standalone mode: Create full layout with internal splitter
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(PANEL_PADDING, PANEL_PADDING, PANEL_PADDING, PANEL_PADDING)
            main_layout.setSpacing(SPACING_MEDIUM)

            # Top: Icon toolbar
            main_layout.addWidget(self._icon_toolbar)

            # Center: Splitter for canvas/panels
            self._splitter = QSplitter(Qt.Orientation.Horizontal)
            self._splitter.setChildrenCollapsible(False)
            self._splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            self._splitter.addWidget(self._scroll_area)
            self._splitter.addWidget(self._right_scroll)

            # Set splitter sizes (canvas: majority, right panel: 250px)
            self._splitter.setSizes([700, 250])
            self._splitter.setStretchFactor(0, 1)  # Canvas stretches
            self._splitter.setStretchFactor(1, 0)  # Right panel fixed

            main_layout.addWidget(self._splitter, 1)

            # Bottom: Status bar
            main_layout.addWidget(self._status_bar)
        else:
            # Embedded mode: Create minimal layout (just for signals/controller)
            # Parent is responsible for layouting toolbar, canvas, panels, statusbar
            # We set a minimal layout to avoid Qt warnings about missing layout
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)
            # Don't add any widgets - parent will take them

    def _create_canvas_scroll_area(self) -> QScrollArea:
        """Create the canvas scroll area with placeholder."""
        from ui.styles.theme import COLORS

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll_area.setStyleSheet(f"QScrollArea {{ background-color: {COLORS['darker_gray']}; border: none; }}")

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

        scroll_area.setWidget(self._canvas_container)
        return scroll_area

    def _create_right_panel_scroll(self) -> QScrollArea:
        """Create the right panel with palette, preview, and action buttons."""
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

        # Overlay panel (for image import alignment)
        self._overlay_panel = OverlayPanel()
        right_layout.addWidget(self._overlay_panel)

        # Arrange Tiles button (for ROM workflow with scattered tiles)
        self._arrange_tiles_btn = QPushButton("Arrange Tiles...")
        self._arrange_tiles_btn.setToolTip("Rearrange scattered tiles into contiguous layout for editing")
        self._arrange_tiles_btn.setEnabled(False)
        self._arrange_tiles_btn.clicked.connect(self.arrangeClicked.emit)
        right_layout.addWidget(self._arrange_tiles_btn)

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
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setWidget(right_panel)
        # Allow user to resize, set reasonable min width
        right_scroll.setMinimumWidth(200)
        right_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        return right_scroll

    def _setup_shortcuts(self) -> None:
        """Setup keyboard shortcuts for tools and actions."""
        # Tool shortcuts are handled by the main window actions to avoid ambiguity
        # when embedded. If standalone usage is needed, these should be re-enabled
        # or managed via a shared action manager.
        # QShortcut(QKeySequence("P"), self, lambda: self._icon_toolbar.tool_buttons["pencil"].click())
        # QShortcut(QKeySequence("B"), self, lambda: self._icon_toolbar.tool_buttons["fill"].click())
        # QShortcut(QKeySequence("K"), self, lambda: self._icon_toolbar.tool_buttons["picker"].click())
        # QShortcut(QKeySequence("E"), self, lambda: self._icon_toolbar.tool_buttons["eraser"].click())

        # Toggle shortcuts
        if self._icon_toolbar.grid_btn:
            QShortcut(QKeySequence("G"), self, self._icon_toolbar.grid_btn.click)
        if self._icon_toolbar.tile_grid_btn:
            QShortcut(QKeySequence("T"), self, self._icon_toolbar.tile_grid_btn.click)
        if self._icon_toolbar.palette_preview_btn:
            QShortcut(QKeySequence("C"), self, self._icon_toolbar.palette_preview_btn.click)

        # Zoom shortcuts
        if self._icon_toolbar.zoom_in_btn:
            QShortcut(QKeySequence("+"), self, self._icon_toolbar.zoom_in_btn.click)
            QShortcut(QKeySequence("="), self, self._icon_toolbar.zoom_in_btn.click)  # Handle unshifted +
        if self._icon_toolbar.zoom_out_btn:
            QShortcut(QKeySequence("-"), self, self._icon_toolbar.zoom_out_btn.click)

        # Reset zoom
        QShortcut(QKeySequence("Ctrl+0"), self, self._on_zoom_reset)

        # Fit to window
        QShortcut(QKeySequence("F"), self, self._on_zoom_fit)

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
    def overlay_panel(self) -> OverlayPanel:
        """Access the overlay panel."""
        return self._overlay_panel

    @property
    def status_bar(self) -> EditorStatusBar:
        """Access the status bar."""
        return self._status_bar

    @property
    def scroll_area(self) -> QScrollArea:
        """Access the canvas scroll area."""
        return self._scroll_area

    @property
    def right_panel_scroll(self) -> QScrollArea:
        """Access the right panel scroll area (palette, preview, save/export).

        Used by parent when embed_mode='embedded' to add to its own splitter.
        """
        return self._right_scroll

    @property
    def canvas_layout(self) -> QVBoxLayout:
        """Access the canvas layout."""
        return self._canvas_layout

    @property
    def is_inject_button_visible(self) -> bool:
        """Return whether inject button is currently visible."""
        return self._inject_btn.isVisible()

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
        safe_disconnect(self._icon_toolbar.backgroundChanged)

        # Disconnect palette panel signals
        safe_disconnect(self._palette_panel.colorSelected)
        safe_disconnect(self._palette_panel.sourceChanged)
        safe_disconnect(self._palette_panel.loadPaletteClicked)
        safe_disconnect(self._palette_panel.savePaletteClicked)
        safe_disconnect(self._palette_panel.editColorClicked)

        # Disconnect controller signals (bidirectional sync)
        if self._controller is not None:
            safe_disconnect(self._controller.toolChanged)
            safe_disconnect(self._controller.colorChanged)
            safe_disconnect(self._controller.paletteChanged)
            safe_disconnect(self._controller.paletteSourceAdded)
            safe_disconnect(self._controller.paletteSourceSelected)
            safe_disconnect(self._controller.paletteSourcesCleared)
            safe_disconnect(self._controller.imageChanged)
            safe_disconnect(self._controller.validationChanged)

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
        self._icon_toolbar.tileGridToggled.connect(self._canvas.set_tile_grid_visible)
        self._icon_toolbar.backgroundChanged.connect(self._canvas.set_background)

        # Connect palette preview toggle
        self._icon_toolbar.palettePreviewToggled.connect(self._on_palette_preview_toggled)

        # Initialize greyscale mode based on toolbar's default state
        self._on_palette_preview_toggled(self._icon_toolbar.is_palette_preview_enabled())

        # Connect palette panel signals
        self._palette_panel.colorSelected.connect(controller.set_selected_color)
        self._palette_panel.sourceChanged.connect(controller.handle_palette_source_changed)
        self._palette_panel.loadPaletteClicked.connect(controller.handle_load_palette)
        self._palette_panel.savePaletteClicked.connect(controller.handle_save_palette)
        self._palette_panel.editColorClicked.connect(controller.handle_edit_color)

        # Connect controller→panel signals (bidirectional sync)
        controller.toolChanged.connect(self._icon_toolbar.set_tool)
        controller.colorChanged.connect(self._palette_panel.set_selected_color)
        controller.paletteChanged.connect(self._update_palette)
        controller.paletteSourceAdded.connect(self._palette_panel.add_palette_source)
        controller.paletteSourceSelected.connect(self._on_palette_source_selected)
        controller.paletteSourcesCleared.connect(self._palette_panel.clear_palette_sources)
        controller.validationChanged.connect(self._on_validation_changed)

        # Populate existing palette sources from controller
        existing_sources = controller.get_palette_sources()
        # Sort by type and index for consistent display
        # We want ROM sources, then Mesen sources (arbitrary but consistent)
        for key, value in sorted(existing_sources.items()):
            source_type, index = key
            _colors, name = value
            self._palette_panel.add_palette_source(name, source_type, index)

        # Connect preview panel to controller
        self._preview_panel.controller = controller
        controller.imageChanged.connect(self._preview_panel.update_preview)
        controller.imageChanged.connect(self._on_image_changed)
        controller.paletteChanged.connect(self._preview_panel.update_preview)

        # Bidirectional zoom sync: canvas → toolbar (if needed for display)
        self._canvas.zoomRequested.connect(self._on_zoom_changed_from_canvas)

        # Connect canvas hover events to status bar
        self._canvas.hoverPositionChanged.connect(self._on_hover_position_changed)

        # Initialize image loaded state
        if controller.has_image():
            self.set_image_loaded(True)

    def _on_image_changed(self) -> None:
        """Handle image change from controller."""
        self.set_image_loaded(True)

    def _on_palette_source_selected(self, source_type: str, palette_index: int) -> None:
        """Handle programmatic palette source selection from controller."""
        selector = self._palette_panel.palette_source_selector
        selector.set_selected_source(source_type, palette_index)

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
        self._image_loaded = loaded
        self._icon_toolbar.setEnabled(loaded)
        self._save_export_panel.set_export_enabled(loaded)
        self._update_button_states()

    def _on_validation_changed(self, is_valid: bool, _errors: list[str]) -> None:
        """Handle validation state change from controller."""
        self._last_validation_state = is_valid
        self._update_button_states()

    def _update_button_states(self) -> None:
        """Update button enabled states based on image loaded and validation."""
        # Only enable save/inject if image is loaded AND valid
        can_save = self._image_loaded and self._last_validation_state

        self._inject_btn.setEnabled(can_save)
        self._save_export_panel.set_save_enabled(can_save)

    def set_workflow_mode(self, mode: str) -> None:
        """Configure workspace for specific workflow mode.

        Args:
            mode: 'vram' or 'rom'
        """
        if mode == "vram":
            # VRAM Mode:
            # - Ready for Inject: Visible (switch to inject tab)
            # - Save to ROM: Hidden (not applicable)
            # - Export PNG: Visible
            self._inject_btn.setVisible(True)
            self._save_export_panel.set_save_visible(False)
            self._save_export_panel.set_export_visible(True)
        elif mode == "rom":
            # ROM Mode:
            # - Ready for Inject: Hidden (stay in same view)
            # - Save to ROM: Visible (direct injection)
            # - Export PNG: Visible
            self._inject_btn.setVisible(False)
            self._save_export_panel.set_save_visible(True)
            self._save_export_panel.set_export_visible(True)

    def _update_palette(self) -> None:
        """Update palette panel when controller palette changes."""
        if not self._controller:
            return

        colors = self._controller.get_current_colors()
        palette_name = self._controller.palette_model.name
        self._palette_panel.set_palette(colors, palette_name)

    def _on_palette_preview_toggled(self, visible: bool) -> None:
        """Handle palette preview toggle.

        visible=True means "Show Palette Colors" -> Greyscale OFF
        visible=False means "Show Indices/Greyscale" -> Greyscale ON
        """
        greyscale_mode = not visible

        if self._canvas:
            self._canvas.set_greyscale_mode(greyscale_mode)

        self._preview_panel.set_greyscale_mode(greyscale_mode)

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

    def _on_zoom_reset(self) -> None:
        """Handle zoom reset shortcut."""
        if not self._canvas:
            return
        self._canvas.set_zoom(4)  # Reset to default 4x

    def _on_zoom_fit(self) -> None:
        """Handle zoom fit shortcut."""
        if not self._canvas or not self._controller:
            return

        image_size = self._controller.get_image_size()
        if not image_size or image_size[0] == 0 or image_size[1] == 0:
            return

        width, height = image_size

        # Get viewport size minus padding
        viewport = self._scroll_area.viewport()
        vp_width = viewport.width() - 40  # 20px padding on each side
        vp_height = viewport.height() - 40

        if vp_width <= 0 or vp_height <= 0:
            return

        # Calculate max zoom that fits
        zoom_x = vp_width // width
        zoom_y = vp_height // height

        fit_zoom = min(zoom_x, zoom_y)

        # Clamp between 1 and 64
        fit_zoom = max(1, min(64, fit_zoom))

        self._canvas.set_zoom(fit_zoom)

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

    # Validation facade methods

    def set_save_enabled(self, enabled: bool) -> None:
        """Enable or disable the save to ROM button based on validation state.

        Args:
            enabled: Whether the save button should be enabled
        """
        self._last_validation_state = enabled
        self._update_button_states()

    def set_save_project_enabled(self, enabled: bool) -> None:
        """Enable or disable the save project button.

        Args:
            enabled: Whether the save project button should be enabled
        """
        self._save_export_panel.set_save_project_enabled(enabled)

    def set_arrange_enabled(self, enabled: bool) -> None:
        """Enable or disable the Arrange Tiles button.

        Args:
            enabled: Whether the arrange tiles button should be enabled
        """
        self._arrange_tiles_btn.setEnabled(enabled)
