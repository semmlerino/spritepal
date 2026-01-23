"""Interactive Workbench Canvas for sprite alignment.

This module provides a QGraphicsView-based canvas for aligning AI frames
to game frames with interactive manipulation:

- Mouse drag to translate
- Corner handles for uniform scaling
- Keyboard nudge (arrow keys, Shift for 8px steps)
- Ctrl+MouseWheel for view zoom
- Middle mouse drag for view pan
- Tile overlay showing OAM tile boundaries
- Auto-alignment based on bounding boxes

Scene Structure:
    QGraphicsScene
    ├── GameFrameItem (background, non-interactive)
    ├── TileOverlayItem (shows OAM tile boundaries)
    │   └── TouchedTileHighlight[] (dynamic, updated on transform)
    ├── AIFrameItem (movable, scalable)
    │   └── ScaleHandles[4] (corner handles)
    └── GridOverlayItem (optional 8x8 reference grid)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, override

from PIL import Image
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.frame_mapping_project import AIFrame, GameFrame
from core.services.sprite_compositor import SpriteCompositor, TransformParams
from core.services.tile_sampling_service import TileSamplingService
from ui.frame_mapping.views.workbench_items import (
    AIFrameItem,
    GameFrameItem,
    GridOverlayItem,
    PreviewItem,
    TileOverlayItem,
)
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette
    from core.mesen_integration.click_extractor import CaptureResult

logger = get_logger(__name__)

# Display scale for the canvas (2x)
DISPLAY_SCALE = 2
# Canvas size
CANVAS_SIZE = 300
# Debounce delay for tile touch calculation (ms)
TILE_CALC_DEBOUNCE_MS = 100
# Debounce delay for preview generation (ms)
PREVIEW_DEBOUNCE_MS = 150
# Debounce delay for pixel hover updates (ms)
PIXEL_HOVER_DEBOUNCE_MS = 50
PIXEL_HIGHLIGHT_DEBOUNCE_MS = 100  # Debounce for mask generation when hovering palette


class WorkbenchGraphicsView(QGraphicsView):
    """Custom QGraphicsView with checkerboard background, zoom, and pan support.

    Interactions:
    - Ctrl+MouseWheel: Zoom view (0.25x to 4x)
    - Middle mouse drag: Pan view

    Signals:
        scene_mouse_moved: Emitted when mouse moves over the scene (scene_x, scene_y)
        scene_mouse_left: Emitted when mouse leaves the viewport
    """

    scene_mouse_moved = Signal(float, float)  # scene_x, scene_y
    scene_mouse_left = Signal()
    scene_clicked = Signal(float, float)  # scene_x, scene_y

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor(26, 26, 26)))
        self.setMinimumSize(CANVAS_SIZE, CANVAS_SIZE)
        self.setStyleSheet("border: 1px solid #444;")

        # Enable mouse tracking for hover detection
        self.setMouseTracking(True)

        # Pan state for middle mouse button
        self._is_panning = False
        self._pan_start: QPointF | None = None

    @override
    def drawBackground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        """Draw checkerboard background."""
        super().drawBackground(painter, rect)

        cell_size = 16
        colors = [QColor(60, 60, 60), QColor(80, 80, 80)]

        # Get visible rect in scene coordinates
        visible = self.mapToScene(self.viewport().rect()).boundingRect()

        start_x = int(visible.left() // cell_size) * cell_size
        start_y = int(visible.top() // cell_size) * cell_size

        y = start_y
        while y < visible.bottom():
            x = start_x
            while x < visible.right():
                color_index = (int(x // cell_size) + int(y // cell_size)) % 2
                painter.fillRect(
                    QRectF(x, y, cell_size, cell_size),
                    colors[color_index],
                )
                x += cell_size
            y += cell_size

    @override
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for view zoom (Ctrl) or pass through."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            current_scale = self.transform().m11()

            # Clamp zoom: 0.25x to 4x
            if (zoom_factor > 1 and current_scale < 4.0) or (zoom_factor < 1 and current_scale > 0.25):
                self.scale(zoom_factor, zoom_factor)
            event.accept()
        else:
            super().wheelEvent(event)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for middle button pan and left-click."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            # Emit click position for eyedropper mode
            scene_pos = self.mapToScene(event.position().toPoint())
            self.scene_clicked.emit(scene_pos.x(), scene_pos.y())
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for panning and emit scene position."""
        if self._is_panning and self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()

            # Translate the view
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
        else:
            # Emit scene position for pixel inspection
            scene_pos = self.mapToScene(event.position().toPoint())
            self.scene_mouse_moved.emit(scene_pos.x(), scene_pos.y())
            super().mouseMoveEvent(event)

    @override
    def leaveEvent(self, event: object) -> None:
        """Handle mouse leaving the viewport."""
        self.scene_mouse_left.emit()
        super().leaveEvent(event)  # type: ignore[arg-type]

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to end panning."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self._pan_start = None
            self.unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class WorkbenchCanvas(QWidget):
    """Interactive canvas for sprite alignment.

    Provides a QGraphicsView-based canvas with controls for:
    - Aligning AI frames to game frames
    - Scaling the AI frame overlay
    - Viewing OAM tile boundaries
    - Auto-alignment based on bounding boxes

    Signals:
        alignment_changed: Emitted when alignment values change.
            Args: (offset_x: int, offset_y: int, flip_h: bool, flip_v: bool, scale: float)
        compression_type_changed: Emitted when compression type selection changes.
            Args: (compression_type: str) - "raw" or "hal"
    """

    alignment_changed = Signal(int, int, bool, bool, float)  # offset_x, offset_y, flip_h, flip_v, scale
    compression_type_changed = Signal(str)  # "raw" or "hal"
    apply_scale_to_all_requested = Signal(float)  # scale factor to apply to all other mappings
    # Pixel inspection signals
    pixel_hovered = Signal(int, int, object, int)  # x, y, rgb (tuple or None), palette_index
    pixel_left = Signal()  # mouse left the canvas
    eyedropper_picked = Signal(object, int)  # rgb (tuple), palette_index

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_ai_frame: AIFrame | None = None
        self._current_game_frame: GameFrame | None = None
        self._capture_result: CaptureResult | None = None
        self._game_pixmap: QPixmap | None = None
        self._ai_pixmap: QPixmap | None = None
        self._ai_image: Image.Image | None = None  # PIL image for auto-alignment
        self._has_mapping = False
        self._updating_from_external = False

        # Tile calculation debounce timer with snapshot
        self._tile_calc_timer = QTimer(self)
        self._tile_calc_timer.setSingleShot(True)
        self._tile_calc_timer.timeout.connect(self._update_tile_touch_status)
        # Snapshot: (offset_x, offset_y, scale) captured when scheduling
        self._tile_calc_snapshot: tuple[int, int, float] | None = None

        # Preview generation debounce timer with snapshot
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._generate_preview)
        self._preview_enabled = False
        # Snapshot: (offset_x, offset_y, flip_h, flip_v, scale) captured when scheduling
        self._preview_snapshot: tuple[int, int, bool, bool, float] | None = None

        self._tile_sampling_service = TileSamplingService()
        self._multi_palette_warning_label: QLabel | None = None
        self._stale_entries_warning_label: QLabel | None = None

        # Pixel hover tracking
        self._pixel_hover_timer = QTimer(self)
        self._pixel_hover_timer.setSingleShot(True)
        self._pixel_hover_timer.timeout.connect(self._emit_pixel_hovered)
        self._pending_hover_pos: tuple[float, float] | None = None
        self._sheet_palette: SheetPalette | None = None

        # Eyedropper mode
        self._eyedropper_mode = False

        # Pixel highlight for bidirectional palette-to-canvas highlighting
        self._pixel_highlight_timer = QTimer(self)
        self._pixel_highlight_timer.setSingleShot(True)
        self._pixel_highlight_timer.timeout.connect(self._generate_pixel_highlight_mask)
        self._pending_highlight_index: int | None = None
        self._pixel_highlight_item: QGraphicsPixmapItem | None = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title row
        title_layout = QHBoxLayout()
        title = QLabel("Workbench Canvas")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        title_layout.addWidget(title)

        title_layout.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; font-size: 10px;")
        title_layout.addWidget(self._status_label)

        layout.addLayout(title_layout)

        # Pixel inspector row
        pixel_inspector = QHBoxLayout()
        pixel_inspector.setContentsMargins(0, 0, 0, 0)
        pixel_inspector.setSpacing(8)

        pixel_label = QLabel("Pixel:")
        pixel_label.setStyleSheet("font-size: 10px; color: #888;")
        pixel_inspector.addWidget(pixel_label)

        self._pixel_info_label = QLabel("--")
        self._pixel_info_label.setStyleSheet("font-size: 10px; font-family: monospace;")
        self._pixel_info_label.setMinimumWidth(200)
        pixel_inspector.addWidget(self._pixel_info_label)

        pixel_inspector.addStretch()

        self._eyedropper_btn = QPushButton("🎯 Pick")
        self._eyedropper_btn.setToolTip("Pick color from canvas (E)")
        self._eyedropper_btn.setCheckable(True)
        self._eyedropper_btn.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        self._eyedropper_btn.setFixedHeight(22)
        self._eyedropper_btn.toggled.connect(self._on_eyedropper_toggled)
        pixel_inspector.addWidget(self._eyedropper_btn)

        layout.addLayout(pixel_inspector)

        # Multi-palette warning banner
        self._multi_palette_warning_label = QLabel("⚠ Multi-palette capture detected. Preview may not match injection.")
        self._multi_palette_warning_label.setStyleSheet(
            "background-color: #FFF3CD; color: #856404; padding: 6px 8px; border-radius: 4px; font-size: 11px;"
        )
        self._multi_palette_warning_label.setVisible(False)
        layout.addWidget(self._multi_palette_warning_label)

        # Stale entries warning banner (entry IDs in capture don't match game frame selection)
        self._stale_entries_warning_label = QLabel(
            "⚠ Entry IDs mismatch. Injection may use different tiles than preview."
        )
        self._stale_entries_warning_label.setStyleSheet(
            "background-color: #F8D7DA; color: #721C24; padding: 6px 8px; border-radius: 4px; font-size: 11px;"
        )
        self._stale_entries_warning_label.setVisible(False)
        layout.addWidget(self._stale_entries_warning_label)

        # Graphics scene and view
        self._scene = QGraphicsScene(self)
        self._view = WorkbenchGraphicsView(self._scene, self)
        layout.addWidget(self._view, 1)

        # Create scene items
        self._game_frame_item = GameFrameItem()
        self._preview_item = PreviewItem()
        self._tile_overlay_item = TileOverlayItem()
        self._ai_frame_item = AIFrameItem()
        self._grid_overlay_item = GridOverlayItem()

        self._scene.addItem(self._game_frame_item)
        self._scene.addItem(self._preview_item)
        self._scene.addItem(self._tile_overlay_item)
        self._scene.addItem(self._ai_frame_item)
        self._scene.addItem(self._grid_overlay_item)

        # Pixel highlight overlay (created on demand, added to scene here)
        self._pixel_highlight_item = QGraphicsPixmapItem()
        self._pixel_highlight_item.setZValue(100)  # Above AI frame, below grid
        self._pixel_highlight_item.setVisible(False)
        self._scene.addItem(self._pixel_highlight_item)

        # Controls row 1: Opacity and Scale
        controls1 = QHBoxLayout()
        controls1.setContentsMargins(0, 0, 0, 0)
        controls1.setSpacing(8)

        # Opacity control
        opacity_label = QLabel("Opacity:")
        opacity_label.setStyleSheet("font-size: 11px;")
        controls1.addWidget(opacity_label)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(70)
        self._opacity_slider.setMaximumWidth(80)
        controls1.addWidget(self._opacity_slider)

        self._opacity_value = QLabel("70%")
        self._opacity_value.setStyleSheet("font-size: 11px;")
        self._opacity_value.setMinimumWidth(35)
        controls1.addWidget(self._opacity_value)

        controls1.addWidget(self._create_separator())

        # Scale control
        scale_label = QLabel("Scale:")
        scale_label.setStyleSheet("font-size: 11px;")
        controls1.addWidget(scale_label)

        self._scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._scale_slider.setRange(10, 100)  # 0.1 to 1.0
        self._scale_slider.setValue(100)
        self._scale_slider.setMaximumWidth(80)
        controls1.addWidget(self._scale_slider)

        self._scale_value = QLabel("1.0x")
        self._scale_value.setStyleSheet("font-size: 11px;")
        self._scale_value.setMinimumWidth(35)
        controls1.addWidget(self._scale_value)

        controls1.addStretch()

        # Offset display
        self._offset_label = QLabel("Offset: (0, 0)")
        self._offset_label.setStyleSheet("font-size: 11px;")
        controls1.addWidget(self._offset_label)

        layout.addLayout(controls1)

        # Controls row 2: Flip, Grid, Auto-align, Apply
        controls2 = QHBoxLayout()
        controls2.setContentsMargins(0, 0, 0, 0)
        controls2.setSpacing(8)

        # Flip controls
        self._flip_h_checkbox = QCheckBox("H-Flip")
        self._flip_h_checkbox.setStyleSheet("font-size: 11px;")
        controls2.addWidget(self._flip_h_checkbox)

        self._flip_v_checkbox = QCheckBox("V-Flip")
        self._flip_v_checkbox.setStyleSheet("font-size: 11px;")
        controls2.addWidget(self._flip_v_checkbox)

        controls2.addWidget(self._create_separator())

        # Tile overlay toggle
        self._tile_overlay_checkbox = QCheckBox("Tile Overlay")
        self._tile_overlay_checkbox.setStyleSheet("font-size: 11px;")
        self._tile_overlay_checkbox.setChecked(True)
        controls2.addWidget(self._tile_overlay_checkbox)

        # Grid toggle
        self._grid_checkbox = QCheckBox("Grid (8x8)")
        self._grid_checkbox.setStyleSheet("font-size: 11px;")
        controls2.addWidget(self._grid_checkbox)

        # Preview toggle
        self._preview_checkbox = QCheckBox("Preview")
        self._preview_checkbox.setStyleSheet("font-size: 11px;")
        self._preview_checkbox.setToolTip("Show in-game preview (quantized, clipped to silhouette)")
        controls2.addWidget(self._preview_checkbox)

        controls2.addWidget(self._create_separator())

        # Compression type selector
        compression_label = QLabel("Compression:")
        compression_label.setStyleSheet("font-size: 11px;")
        controls2.addWidget(compression_label)

        self._compression_combo = QComboBox()
        self._compression_combo.addItem("RAW", "raw")
        self._compression_combo.addItem("HAL", "hal")
        self._compression_combo.setStyleSheet("font-size: 11px;")
        self._compression_combo.setToolTip("Compression type for ROM injection (RAW=uncompressed, HAL=compressed)")
        self._compression_combo.setMaximumWidth(60)
        controls2.addWidget(self._compression_combo)

        controls2.addStretch()

        # Auto-align button
        self._auto_align_btn = QPushButton("Auto-Align")
        self._auto_align_btn.setStyleSheet("font-size: 11px;")
        self._auto_align_btn.setMaximumWidth(80)
        self._auto_align_btn.setToolTip("Center AI frame over game frame based on bounding boxes")
        controls2.addWidget(self._auto_align_btn)

        # Match Scale checkbox (next to Auto-Align)
        self._match_scale_checkbox = QCheckBox("Match Scale")
        self._match_scale_checkbox.setStyleSheet("font-size: 11px;")
        self._match_scale_checkbox.setToolTip("Auto-Align also scales AI frame to fit game sprite bounds")
        controls2.addWidget(self._match_scale_checkbox)

        layout.addLayout(controls2)

        # Controls row 3: Preserve sprite and Apply Scale to All
        controls3 = QHBoxLayout()
        controls3.setContentsMargins(0, 0, 0, 0)
        controls3.setSpacing(8)

        # Preserve sprite checkbox
        self._preserve_sprite_checkbox = QCheckBox("Preserve sprite")
        self._preserve_sprite_checkbox.setStyleSheet("font-size: 11px;")
        self._preserve_sprite_checkbox.setToolTip(
            "When checked, original game sprite remains visible where AI frame "
            "doesn't cover it. When unchecked (default), original sprite is "
            "completely removed - only AI frame content remains."
        )
        self._preserve_sprite_checkbox.setChecked(False)  # Default: remove original
        controls3.addWidget(self._preserve_sprite_checkbox)

        controls3.addStretch()

        # Apply Scale to All button
        self._apply_scale_all_btn = QPushButton("Apply Scale to All")
        self._apply_scale_all_btn.setStyleSheet("font-size: 11px;")
        self._apply_scale_all_btn.setMaximumWidth(120)
        self._apply_scale_all_btn.setToolTip("Apply current scale to all other mapped frames")
        controls3.addWidget(self._apply_scale_all_btn)

        layout.addLayout(controls3)

        # Hotkey hints
        hints_label = QLabel("Arrow: nudge 1px (Shift: 8px) | +/-: scale 1% (Shift: 5%)")
        hints_label.setStyleSheet("font-size: 10px; color: #888; font-style: italic;")
        layout.addWidget(hints_label)

        # Set initial enabled state
        self._set_controls_enabled(False)

    def _create_separator(self) -> QFrame:
        """Create a vertical separator."""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        return separator

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self._scale_slider.valueChanged.connect(self._on_scale_slider_changed)
        self._flip_h_checkbox.toggled.connect(self._on_flip_changed)
        self._flip_v_checkbox.toggled.connect(self._on_flip_changed)
        self._tile_overlay_checkbox.toggled.connect(self._on_tile_overlay_toggled)
        self._grid_checkbox.toggled.connect(self._on_grid_toggled)
        self._preview_checkbox.toggled.connect(self._on_preview_toggled)
        self._compression_combo.currentIndexChanged.connect(self._on_compression_changed)
        self._auto_align_btn.clicked.connect(self._on_auto_align)
        self._preserve_sprite_checkbox.toggled.connect(self._on_preserve_sprite_toggled)
        self._apply_scale_all_btn.clicked.connect(self._on_apply_scale_to_all)

        # AI frame item signals
        self._ai_frame_item.transform_changed.connect(self._on_ai_frame_transform_changed)

        # View mouse signals for pixel inspection
        self._view.scene_mouse_moved.connect(self._on_scene_mouse_moved)
        self._view.scene_mouse_left.connect(self._on_scene_mouse_left)
        self._view.scene_clicked.connect(self._on_scene_clicked)

        # Internal pixel info label updates
        self.pixel_hovered.connect(self._update_pixel_info_label)
        self.pixel_left.connect(self._clear_pixel_info_label)

    def set_game_frame(
        self,
        frame: GameFrame | None,
        preview_pixmap: QPixmap | None = None,
        capture_result: CaptureResult | None = None,
        used_fallback: bool = False,
    ) -> None:
        """Set the game frame (background).

        Args:
            frame: GameFrame to display, or None to clear.
            preview_pixmap: Optional pre-rendered preview pixmap.
            capture_result: Optional CaptureResult for tile overlay.
            used_fallback: Whether fallback entry IDs were used (stale selection).
        """
        self._current_game_frame = frame
        self._capture_result = capture_result

        # Show stale entries warning if fallback was used
        if self._stale_entries_warning_label:
            self._stale_entries_warning_label.setVisible(used_fallback)

        if frame is None:
            self._game_pixmap = None
            self._game_frame_item.setPixmap(QPixmap())
            self._tile_overlay_item.set_tile_rects([])
            self._update_auto_align_button_state()
            return

        if preview_pixmap is not None:
            self._game_pixmap = preview_pixmap
        elif frame.capture_path:
            preview_path = frame.capture_path.with_suffix(".png")
            if preview_path.exists():
                self._game_pixmap = QPixmap(str(preview_path))
            else:
                self._game_pixmap = None
        else:
            self._game_pixmap = None

        if self._game_pixmap is not None:
            # Scale for display
            scaled = self._game_pixmap.scaled(
                self._game_pixmap.width() * DISPLAY_SCALE,
                self._game_pixmap.height() * DISPLAY_SCALE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self._game_frame_item.setPixmap(scaled)

            # Update grid bounds
            self._grid_overlay_item.set_bounds(QRectF(0, 0, scaled.width(), scaled.height()))

            # Center the view on the game frame
            self._view.setSceneRect(
                QRectF(
                    -50,
                    -50,
                    scaled.width() + 100,
                    scaled.height() + 100,
                )
            )
            self._view.centerOn(scaled.width() / 2, scaled.height() / 2)

        # Update tile overlay from capture result
        self._update_tile_overlay()
        self._update_status()
        # Update auto-align button state based on new game frame
        self._update_auto_align_button_state()
        # Update preview if enabled
        self._schedule_preview_update()

        # Show warning if multi-palette capture detected
        if self._multi_palette_warning_label:
            has_multiple = self._has_multiple_palettes()
            self._multi_palette_warning_label.setVisible(has_multiple)

        # Update compression type combo from game frame
        # Use first ROM offset's type, or default to "raw"
        compression_type = "raw"
        if frame.rom_offsets and frame.compression_types:
            first_offset = frame.rom_offsets[0]
            compression_type = frame.compression_types.get(first_offset, "raw")
        # Block signals to prevent triggering change handler during UI update
        self._compression_combo.blockSignals(True)
        index = self._compression_combo.findData(compression_type)
        if index >= 0:
            self._compression_combo.setCurrentIndex(index)
        self._compression_combo.blockSignals(False)

    def _has_multiple_palettes(self) -> bool:
        """Check if capture has multiple distinct palettes.

        Returns:
            True if capture entries use different palette indices
        """
        if self._capture_result is None or not self._capture_result.entries:
            return False

        palettes = set()
        for entry in self._capture_result.entries:
            palettes.add(entry.palette)

        return len(palettes) > 1

    def set_ai_frame(self, frame: AIFrame | None) -> None:
        """Set the AI frame (overlay).

        Args:
            frame: AIFrame to display, or None to clear.
        """
        self._current_ai_frame = frame

        if frame is None:
            self._ai_pixmap = None
            self._ai_image = None
            self._ai_frame_item.set_pixmap(None)
            self._update_auto_align_button_state()
            return

        if frame.path.exists():
            self._ai_pixmap = QPixmap(str(frame.path))
            # Also load as PIL image for auto-alignment
            try:
                self._ai_image = Image.open(frame.path).convert("RGBA")
            except Exception as e:
                logger.warning(
                    "Failed to load PIL image for %s: %s - auto-align will be disabled",
                    frame.path,
                    e,
                )
                self._ai_image = None
        else:
            self._ai_pixmap = None
            self._ai_image = None

        if self._ai_pixmap is not None:
            # Scale for display
            scaled = self._ai_pixmap.scaled(
                self._ai_pixmap.width() * DISPLAY_SCALE,
                self._ai_pixmap.height() * DISPLAY_SCALE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self._ai_frame_item.set_pixmap(scaled)

        self._update_status()
        # Update auto-align button state based on new AI frame
        self._update_auto_align_button_state()
        # Update preview if enabled
        self._schedule_preview_update()

    def set_alignment(
        self,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
        *,
        has_mapping: bool = True,
    ) -> None:
        """Set the alignment values.

        Args:
            offset_x: X offset for the AI frame.
            offset_y: Y offset for the AI frame.
            flip_h: Horizontal flip state.
            flip_v: Vertical flip state.
            scale: Scale factor (0.1 - 10.0).
            has_mapping: Whether this represents a valid mapping (affects control state).
        """
        self._has_mapping = has_mapping
        self._set_controls_enabled(has_mapping)
        self._updating_from_external = True

        try:
            # Update AI frame item position (scaled for display)
            self._ai_frame_item.setPos(offset_x * DISPLAY_SCALE, offset_y * DISPLAY_SCALE)
            self._ai_frame_item.set_scale_factor(scale)
            self._ai_frame_item.set_flip(flip_h, flip_v)

            # Update controls
            self._flip_h_checkbox.blockSignals(True)
            self._flip_v_checkbox.blockSignals(True)
            self._scale_slider.blockSignals(True)

            self._flip_h_checkbox.setChecked(flip_h)
            self._flip_v_checkbox.setChecked(flip_v)
            self._scale_slider.setValue(int(scale * 100))
            self._scale_value.setText(f"{scale:.1f}x")
            self._offset_label.setText(f"Offset: ({offset_x}, {offset_y})")

            self._flip_h_checkbox.blockSignals(False)
            self._flip_v_checkbox.blockSignals(False)
            self._scale_slider.blockSignals(False)

            # Schedule tile touch status update
            self._schedule_tile_touch_update()
            # Update preview if enabled
            self._schedule_preview_update()
        finally:
            self._updating_from_external = False

        self._update_status()

    def clear_alignment(self) -> None:
        """Clear alignment values (reset to defaults)."""
        self.set_alignment(0, 0, False, False, 1.0, has_mapping=False)

    def clear(self) -> None:
        """Clear all content."""
        self._current_ai_frame = None
        self._current_game_frame = None
        self._capture_result = None
        self._game_pixmap = None
        self._ai_pixmap = None
        self._ai_image = None
        self._has_mapping = False

        self._game_frame_item.setPixmap(QPixmap())
        self._ai_frame_item.set_pixmap(None)
        self._tile_overlay_item.set_tile_rects([])

        self.clear_alignment()
        self._update_status()

    def get_alignment(self) -> tuple[int, int, bool, bool, float]:
        """Get current alignment values.

        Returns:
            Tuple of (offset_x, offset_y, flip_h, flip_v, scale).
        """
        pos = self._ai_frame_item.pos()
        # Convert from display scale to actual coordinates
        offset_x = int(pos.x() / DISPLAY_SCALE)
        offset_y = int(pos.y() / DISPLAY_SCALE)
        return (
            offset_x,
            offset_y,
            self._flip_h_checkbox.isChecked(),
            self._flip_v_checkbox.isChecked(),
            self._ai_frame_item.scale_factor(),
        )

    def get_preserve_sprite(self) -> bool:
        """Get current preserve sprite setting.

        Returns:
            True if original sprite should remain visible where AI doesn't cover,
            False if original sprite should be completely removed (default).
        """
        return self._preserve_sprite_checkbox.isChecked()

    def get_current_ai_frame_id(self) -> str | None:
        """Get the current AI frame ID.

        Returns:
            AI frame ID or None if no frame is selected.
        """
        return self._current_ai_frame.id if self._current_ai_frame else None

    def focus_canvas(self) -> None:
        """Set focus to the canvas for keyboard input."""
        self._view.setFocus()
        self._ai_frame_item.setSelected(True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable alignment controls.

        Note: Auto-align button is managed separately by _update_auto_align_button_state()
        because it has additional requirements (AI image and capture result).
        """
        self._opacity_slider.setEnabled(enabled)
        self._scale_slider.setEnabled(enabled)
        self._flip_h_checkbox.setEnabled(enabled)
        self._flip_v_checkbox.setEnabled(enabled)
        self._tile_overlay_checkbox.setEnabled(enabled)
        self._grid_checkbox.setEnabled(enabled)
        self._compression_combo.setEnabled(enabled)
        self._match_scale_checkbox.setEnabled(enabled)
        self._preserve_sprite_checkbox.setEnabled(enabled)
        self._apply_scale_all_btn.setEnabled(enabled)
        # Auto-align button managed separately by _update_auto_align_button_state()
        self._update_auto_align_button_state()

    def _can_auto_align(self) -> bool:
        """Check if auto-align is possible.

        Auto-align requires:
        - A valid PIL image (for content detection)
        - A capture result (for bounding box)
        - An active mapping
        """
        return self._ai_image is not None and self._capture_result is not None and self._has_mapping

    def _update_auto_align_button_state(self) -> None:
        """Update auto-align button enabled state based on current conditions."""
        can_align = self._can_auto_align()
        self._auto_align_btn.setEnabled(can_align)
        if not can_align:
            # Provide tooltip explaining why auto-align is disabled
            if self._ai_image is None:
                self._auto_align_btn.setToolTip("Auto-align requires AI image to be loaded")
            elif self._capture_result is None:
                self._auto_align_btn.setToolTip("Auto-align requires game frame capture")
            elif not self._has_mapping:
                self._auto_align_btn.setToolTip("Auto-align requires a frame mapping")
        else:
            self._auto_align_btn.setToolTip("Automatically align AI frame to game sprite bounds")

    def _update_status(self) -> None:
        """Update the status label."""
        if self._current_ai_frame is None:
            self._status_label.setText("No AI frame selected")
        elif not self._has_mapping:
            self._status_label.setText("Frame not mapped")
        else:
            self._status_label.setText("Drag to adjust, handles to scale")

    def set_stale_entries_warning_visible(self, visible: bool) -> None:
        """Set the visibility of the stale entries warning label.

        Called when the controller detects stale entry IDs during injection
        to proactively warn the user.

        Args:
            visible: Whether to show the warning label.
        """
        if self._stale_entries_warning_label:
            self._stale_entries_warning_label.setVisible(visible)

    def _update_tile_overlay(self) -> None:
        """Update tile overlay from capture result."""
        if self._capture_result is None:
            self._tile_overlay_item.set_tile_rects([])
            return

        # Build tile rectangles from OAM entries
        tile_rects: list[QRectF] = []
        bbox = self._capture_result.bounding_box

        for entry in self._capture_result.entries:
            # Calculate relative position within the sprite bounds
            rel_x = (entry.x - bbox.x) * DISPLAY_SCALE
            rel_y = (entry.y - bbox.y) * DISPLAY_SCALE
            width = entry.width * DISPLAY_SCALE
            height = entry.height * DISPLAY_SCALE

            # For larger sprites (16x16 or 32x32), break into 8x8 tiles
            tile_size = 8 * DISPLAY_SCALE
            for ty in range(0, height, tile_size):
                for tx in range(0, width, tile_size):
                    tile_rects.append(
                        QRectF(
                            rel_x + tx,
                            rel_y + ty,
                            tile_size,
                            tile_size,
                        )
                    )

        self._tile_overlay_item.set_tile_rects(tile_rects)

    def _schedule_tile_touch_update(self) -> None:
        """Schedule a debounced tile touch status update.

        Captures current alignment snapshot to ensure the calculation uses
        the values at schedule time, not fire time.
        """
        # Capture snapshot at schedule time (not fire time)
        pos = self._ai_frame_item.pos()
        offset_x = int(pos.x() / DISPLAY_SCALE)
        offset_y = int(pos.y() / DISPLAY_SCALE)
        scale = self._ai_frame_item.scale_factor()
        self._tile_calc_snapshot = (offset_x, offset_y, scale)
        self._tile_calc_timer.start(TILE_CALC_DEBOUNCE_MS)

    def _update_tile_touch_status(self) -> None:
        """Update which tiles are touched by the AI frame overlay.

        Uses the alignment snapshot captured at schedule time if available,
        otherwise falls back to current values.
        """
        if self._ai_image is None or self._capture_result is None:
            self._tile_overlay_item.set_touched_indices(set())
            return

        # Use snapshot if available, otherwise use current values
        if self._tile_calc_snapshot is not None:
            offset_x, offset_y, scale = self._tile_calc_snapshot
        else:
            # Fallback to current values (for direct calls in tests)
            pos = self._ai_frame_item.pos()
            offset_x = int(pos.x() / DISPLAY_SCALE)
            offset_y = int(pos.y() / DISPLAY_SCALE)
            scale = self._ai_frame_item.scale_factor()

        # Build tile rects in actual coordinates
        tile_rects: list[QRectF] = []
        bbox = self._capture_result.bounding_box

        for entry in self._capture_result.entries:
            rel_x = entry.x - bbox.x
            rel_y = entry.y - bbox.y

            for ty in range(0, entry.height, 8):
                for tx in range(0, entry.width, 8):
                    tile_rects.append(
                        QRectF(
                            rel_x + tx,
                            rel_y + ty,
                            8,
                            8,
                        )
                    )

        # Convert QRectF to QRect for the service
        qt_rects = [QRect(int(r.x()), int(r.y()), int(r.width()), int(r.height())) for r in tile_rects]

        # Calculate touched/untouched (untouched is not used but returned)
        touched, _untouched = self._tile_sampling_service.get_touched_tiles(
            qt_rects,
            self._ai_image.width,
            self._ai_image.height,
            offset_x,
            offset_y,
            scale,
        )

        self._tile_overlay_item.set_touched_indices(touched)

    def _on_opacity_changed(self, value: int) -> None:
        """Handle opacity slider change."""
        self._opacity_value.setText(f"{value}%")
        self._ai_frame_item.set_overlay_opacity(value / 100.0)

    def _on_scale_slider_changed(self, value: int) -> None:
        """Handle scale slider change, preserving center position."""
        if self._updating_from_external:
            return

        new_scale = value / 100.0
        old_scale = self._ai_frame_item.scale_factor()
        if abs(new_scale - old_scale) < 0.001:
            return

        # Capture center before scaling
        center_before = self._ai_frame_item.sceneBoundingRect().center()

        # Apply scale
        self._scale_value.setText(f"{new_scale:.1f}x")
        self._ai_frame_item.set_scale_factor(new_scale)

        # Reposition to preserve center
        center_after = self._ai_frame_item.sceneBoundingRect().center()
        delta = center_before - center_after
        self._ai_frame_item.setPos(self._ai_frame_item.pos() + delta)

    def _on_flip_changed(self) -> None:
        """Handle flip checkbox change."""
        if self._updating_from_external:
            return
        flip_h = self._flip_h_checkbox.isChecked()
        flip_v = self._flip_v_checkbox.isChecked()
        self._ai_frame_item.set_flip(flip_h, flip_v)
        self._schedule_preview_update()
        self._emit_alignment_changed()

    def _on_tile_overlay_toggled(self, checked: bool) -> None:
        """Handle tile overlay toggle."""
        self._tile_overlay_item.set_overlay_visible(checked)

    def _on_grid_toggled(self, checked: bool) -> None:
        """Handle grid toggle."""
        self._grid_overlay_item.set_grid_visible(checked)

    def _on_preview_toggled(self, checked: bool) -> None:
        """Handle preview toggle.

        When enabled, shows a preview of how the final sprite will look
        after injection (quantized to palette).
        The AI frame switches to ghost mode (outline only) so it can
        still be repositioned while viewing the preview.
        """
        self._preview_enabled = checked
        if checked:
            # Ghost mode: visible outline, still draggable
            self._ai_frame_item.set_ghost_mode(True)
            self._schedule_preview_update()
        else:
            # Show AI frame again for alignment work
            self._ai_frame_item.set_ghost_mode(False)
            self._preview_item.setVisible(False)
        # Update game frame visibility based on preview + preserve sprite state
        self._update_game_frame_visibility()

    def _on_compression_changed(self, index: int) -> None:
        """Handle compression type combo change."""
        compression_type = self._compression_combo.currentData()
        if compression_type and self._current_game_frame is not None:
            self.compression_type_changed.emit(compression_type)

    def _on_preserve_sprite_toggled(self, checked: bool) -> None:
        """Handle preserve sprite checkbox toggle.

        Updates the preview to reflect the new compositing behavior.
        """
        # Schedule preview update to reflect the change
        self._schedule_preview_update()
        # Update game frame visibility based on preview + preserve sprite state
        self._update_game_frame_visibility()

    def _update_game_frame_visibility(self) -> None:
        """Update game frame item visibility based on preview and preserve sprite state.

        When preview is enabled:
        - If "Preserve sprite" is ON: game frame visible (shows through transparent areas)
        - If "Preserve sprite" is OFF: game frame hidden (being completely replaced)

        When preview is disabled: game frame always visible for alignment work.
        """
        if self._preview_enabled and not self._preserve_sprite_checkbox.isChecked():
            # Preview ON + Preserve sprite OFF = hide game frame (complete replacement)
            self._game_frame_item.setVisible(False)
        else:
            # Show game frame for alignment or when preserving original
            self._game_frame_item.setVisible(True)

    def _on_apply_scale_to_all(self) -> None:
        """Handle Apply Scale to All button click.

        Emits signal with current scale for the workspace to handle
        (showing confirmation dialog and calling controller).
        """
        if not self._has_mapping:
            return
        current_scale = self._ai_frame_item.scale_factor()
        self.apply_scale_to_all_requested.emit(current_scale)

    def _schedule_preview_update(self) -> None:
        """Schedule a debounced preview generation.

        Captures current alignment snapshot to ensure the preview uses
        the values at schedule time, not fire time.
        """
        if not self._preview_enabled:
            return
        # Capture snapshot at schedule time (not fire time)
        pos = self._ai_frame_item.pos()
        offset_x = int(pos.x() / DISPLAY_SCALE)
        offset_y = int(pos.y() / DISPLAY_SCALE)
        flip_h = self._flip_h_checkbox.isChecked()
        flip_v = self._flip_v_checkbox.isChecked()
        scale = self._ai_frame_item.scale_factor()
        self._preview_snapshot = (offset_x, offset_y, flip_h, flip_v, scale)
        self._preview_timer.start(PREVIEW_DEBOUNCE_MS)

    def _generate_preview(self) -> None:
        """Generate the in-game preview image.

        Uses SpriteCompositor with "original" policy so uncovered areas
        show original sprite pixels (WYSIWYG preview).

        Transform order: flip -> scale (SNES-correct, matching injection)

        Uses the alignment snapshot captured at schedule time if available,
        otherwise falls back to current values.
        """
        logger.debug("_generate_preview called, enabled=%s", self._preview_enabled)
        if not self._preview_enabled:
            self._preview_item.setVisible(False)
            return

        logger.debug(
            "_generate_preview: ai_image=%s, capture_result=%s, game_pixmap=%s",
            self._ai_image is not None,
            self._capture_result is not None,
            self._game_pixmap is not None,
        )
        if self._ai_image is None or self._capture_result is None or self._game_pixmap is None:
            self._preview_item.setVisible(False)
            return

        # Use snapshot if available, otherwise use current values
        if self._preview_snapshot is not None:
            offset_x, offset_y, flip_h, flip_v, scale = self._preview_snapshot
        else:
            # Fallback to current values (for direct calls in tests)
            pos = self._ai_frame_item.pos()
            offset_x = int(pos.x() / DISPLAY_SCALE)
            offset_y = int(pos.y() / DISPLAY_SCALE)
            flip_h = self._flip_h_checkbox.isChecked()
            flip_v = self._flip_v_checkbox.isChecked()
            scale = self._ai_frame_item.scale_factor()

        try:
            # Use SpriteCompositor with policy based on "Preserve sprite" checkbox
            # - Checked: "original" - original sprite visible where AI doesn't cover
            # - Unchecked: "transparent" - original sprite completely removed
            uncovered_policy: Literal["transparent", "original"] = (
                "original" if self._preserve_sprite_checkbox.isChecked() else "transparent"
            )
            compositor = SpriteCompositor(uncovered_policy=uncovered_policy)
            transform = TransformParams(
                offset_x=offset_x,
                offset_y=offset_y,
                flip_h=flip_h,
                flip_v=flip_v,
                scale=scale,
            )

            result = compositor.composite_frame(
                ai_image=self._ai_image,
                capture_result=self._capture_result,
                transform=transform,
                quantize=True,
                sheet_palette=self._sheet_palette,
            )

            preview_img = result.composited_image

            # Convert PIL image to QPixmap
            from PySide6.QtGui import QImage

            data = preview_img.tobytes("raw", "RGBA")
            qimage = QImage(
                data,
                preview_img.width,
                preview_img.height,
                preview_img.width * 4,
                QImage.Format.Format_RGBA8888,
            )

            # Scale for display
            scaled_pixmap = QPixmap.fromImage(qimage).scaled(
                preview_img.width * DISPLAY_SCALE,
                preview_img.height * DISPLAY_SCALE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )

            logger.debug(
                "_generate_preview: setting pixmap size=%dx%d",
                scaled_pixmap.width(),
                scaled_pixmap.height(),
            )
            self._preview_item.setPixmap(scaled_pixmap)
            self._preview_item.setVisible(True)

        except Exception:
            logger.exception("Failed to generate preview")
            self._preview_item.setVisible(False)

    def _on_auto_align(self) -> None:
        """Handle auto-align button click.

        Calculates alignment offset that centers the AI frame content over the game
        frame, accounting for current flip and scale transforms.

        If Match Scale is checked, also calculates scale to fit AI content within
        game sprite bounds (using smaller dimension to fit within bounds).
        """
        if self._ai_image is None:
            logger.warning("Auto-align skipped: AI image not loaded (PIL load may have failed)")
            self._status_label.setText("Auto-align requires AI image")
            return

        if self._capture_result is None:
            logger.warning("Auto-align skipped: No capture result available")
            self._status_label.setText("Auto-align requires game frame capture")
            return

        # Get AI content bounding box (non-transparent pixels)
        ai_bbox = self._ai_image.getbbox()
        if ai_bbox is None:
            # No non-transparent pixels - use full image
            ai_bbox = (0, 0, self._ai_image.width, self._ai_image.height)

        ai_x, ai_y, ai_x2, ai_y2 = ai_bbox
        ai_content_width = ai_x2 - ai_x
        ai_content_height = ai_y2 - ai_y

        # Apply flip corrections (flip changes where content visually appears)
        flip_h = self._flip_h_checkbox.isChecked()
        flip_v = self._flip_v_checkbox.isChecked()

        # Game frame bounding box
        bbox = self._capture_result.bounding_box

        # Calculate scale if Match Scale is checked
        if self._match_scale_checkbox.isChecked() and ai_content_width > 0 and ai_content_height > 0:
            # Calculate scale to fit AI content within game bounds
            scale_x = bbox.width / ai_content_width
            scale_y = bbox.height / ai_content_height
            # Use smaller dimension to fit within bounds (preserves aspect ratio)
            scale = min(scale_x, scale_y)
            # Clamp to valid range
            scale = max(0.1, min(1.0, scale))
            logger.debug(
                "Auto-align: Match Scale calculated scale=%.2f (scale_x=%.2f, scale_y=%.2f)",
                scale,
                scale_x,
                scale_y,
            )
        else:
            scale = self._ai_frame_item.scale_factor()

        # Calculate AI content center in original image coordinates
        ai_center_x = ai_x + ai_content_width / 2
        ai_center_y = ai_y + ai_content_height / 2

        if flip_h:
            ai_center_x = self._ai_image.width - ai_center_x
        if flip_v:
            ai_center_y = self._ai_image.height - ai_center_y

        # Apply scale to get visual content center
        scaled_ai_center_x = ai_center_x * scale
        scaled_ai_center_y = ai_center_y * scale

        # Game frame center (displayed at origin 0,0)
        game_center_x = bbox.width / 2
        game_center_y = bbox.height / 2

        # Calculate offset to align centers
        offset_x = int(game_center_x - scaled_ai_center_x)
        offset_y = int(game_center_y - scaled_ai_center_y)

        # Apply the alignment (with potentially updated scale)
        self.set_alignment(
            offset_x,
            offset_y,
            flip_h,
            flip_v,
            scale,
        )
        self._emit_alignment_changed()
        # Update scene rect and center view on aligned frames
        self._update_scene_for_alignment()

    def _on_ai_frame_transform_changed(self, offset_x: int, offset_y: int, scale: float) -> None:
        """Handle transform change from AI frame item."""
        if self._updating_from_external:
            return

        # Convert from display scale to actual coordinates
        # Use int() for truncation toward zero (not floor division)
        # This ensures consistent behavior for negative offsets
        actual_x = int(offset_x / DISPLAY_SCALE)
        actual_y = int(offset_y / DISPLAY_SCALE)

        # Update UI
        self._offset_label.setText(f"Offset: ({actual_x}, {actual_y})")
        self._scale_slider.blockSignals(True)
        self._scale_slider.setValue(int(scale * 100))
        self._scale_value.setText(f"{scale:.1f}x")
        self._scale_slider.blockSignals(False)

        # Schedule tile touch update
        self._schedule_tile_touch_update()

        # Schedule preview update if enabled
        self._schedule_preview_update()

        # Emit signal
        self._emit_alignment_changed()

    def _emit_alignment_changed(self) -> None:
        """Emit alignment_changed signal with current values."""
        offset_x, offset_y, flip_h, flip_v, scale = self.get_alignment()
        self.alignment_changed.emit(offset_x, offset_y, flip_h, flip_v, scale)

    def _update_scene_for_alignment(self) -> None:
        """Update scene rect and fit view to show both frames after alignment.

        After auto-align repositions the AI frame (potentially to large negative
        coordinates), the view must be adjusted to show both frames. When the
        offset is very large, the combined rect can span thousands of pixels,
        causing excessive zoom-out that makes frames appear as tiny dots.

        Fix: Clamp the viewport to a reasonable size based on the game frame
        dimensions. If the combined rect is unreasonably large (more than 5x
        the game frame), only fit the game frame and let the user pan to the
        AI frame if needed.
        """
        # Get the combined bounding rect of both frames
        game_rect = self._game_frame_item.sceneBoundingRect()
        ai_rect = self._ai_frame_item.sceneBoundingRect()

        # Skip if either rect is invalid (empty or null)
        if game_rect.isEmpty() and ai_rect.isEmpty():
            return

        # Union of both rects plus padding
        combined = game_rect.united(ai_rect)

        # CLAMP: If combined rect is unreasonably large due to extreme offset,
        # only fit the game frame to prevent excessive zoom-out.
        # Use 5x the game frame size as threshold for "reasonable".
        max_reasonable_size = max(game_rect.width(), game_rect.height()) * 5

        if combined.width() > max_reasonable_size or combined.height() > max_reasonable_size:
            # Large offset detected - center on game frame with modest padding
            target_rect = game_rect.adjusted(-50, -50, 50, 50)
        else:
            # Normal case - show both frames with padding
            target_rect = combined.adjusted(-50, -50, 50, 50)

        # Update scene rect to include both frames (even if not all visible)
        # This ensures the AI frame is still accessible via pan/zoom
        self._view.setSceneRect(combined.adjusted(-50, -50, 50, 50))

        # Use fitInView on the target rect (clamped if necessary)
        self._view.fitInView(target_rect, Qt.AspectRatioMode.KeepAspectRatio)

    # -------------------------------------------------------------------------
    # Pixel Inspection
    # -------------------------------------------------------------------------

    def set_sheet_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette for color-to-index lookups.

        Args:
            palette: SheetPalette to use for pixel inspection, or None to clear.
        """
        self._sheet_palette = palette

    def _on_scene_mouse_moved(self, scene_x: float, scene_y: float) -> None:
        """Handle mouse move over the scene - schedule pixel lookup.

        Uses debouncing to avoid excessive updates on rapid mouse movement.
        """
        self._pending_hover_pos = (scene_x, scene_y)
        self._pixel_hover_timer.start(PIXEL_HOVER_DEBOUNCE_MS)

    def _on_scene_mouse_left(self) -> None:
        """Handle mouse leaving the canvas."""
        self._pending_hover_pos = None
        self._pixel_hover_timer.stop()
        self.pixel_left.emit()

    def _emit_pixel_hovered(self) -> None:
        """Emit pixel_hovered signal with color and palette index.

        Called after debounce timer fires with the pending hover position.
        """
        if self._pending_hover_pos is None:
            return

        scene_x, scene_y = self._pending_hover_pos

        # Get pixel info at the scene position
        result = self._get_pixel_at_scene_pos(scene_x, scene_y)
        if result is None:
            # Outside AI frame bounds
            self.pixel_hovered.emit(-1, -1, None, -1)
            return

        img_x, img_y, rgb, palette_index = result
        self.pixel_hovered.emit(img_x, img_y, rgb, palette_index)

    def _get_pixel_at_scene_pos(
        self, scene_x: float, scene_y: float
    ) -> tuple[int, int, tuple[int, int, int], int] | None:
        """Get pixel information at a scene position.

        Args:
            scene_x: X coordinate in scene space
            scene_y: Y coordinate in scene space

        Returns:
            Tuple of (img_x, img_y, rgb, palette_index) or None if outside bounds.
        """
        if self._ai_image is None:
            return None

        # Convert scene coords to AI image coords
        # Scene is scaled by DISPLAY_SCALE, so divide to get original coords
        img_x = int(scene_x / DISPLAY_SCALE)
        img_y = int(scene_y / DISPLAY_SCALE)

        # Check bounds
        if img_x < 0 or img_x >= self._ai_image.width:
            return None
        if img_y < 0 or img_y >= self._ai_image.height:
            return None

        # Get pixel color from AI image
        try:
            pixel_raw = self._ai_image.getpixel((img_x, img_y))
            # Cast to tuple for type safety (PIL returns various types)
            if isinstance(pixel_raw, (int, float)):
                return None  # Grayscale single value - not supported
            if not isinstance(pixel_raw, tuple):
                return None
            # Handle RGBA or RGB
            if len(pixel_raw) == 4:
                r, g, b, a = int(pixel_raw[0]), int(pixel_raw[1]), int(pixel_raw[2]), int(pixel_raw[3])
                if a == 0:
                    # Transparent pixel - index 0
                    return (img_x, img_y, (r, g, b), 0)
                rgb = (r, g, b)
            elif len(pixel_raw) >= 3:
                rgb = (int(pixel_raw[0]), int(pixel_raw[1]), int(pixel_raw[2]))
            else:
                return None

            # Lookup palette index
            palette_index = self._lookup_palette_index(rgb)
            return (img_x, img_y, rgb, palette_index)

        except Exception as e:
            logger.debug("Failed to get pixel at (%d, %d): %s", img_x, img_y, e)
            return None

    def _lookup_palette_index(self, rgb: tuple[int, int, int]) -> int:
        """Lookup the palette index for an RGB color.

        Uses explicit color_mappings if available, otherwise finds nearest color.

        Args:
            rgb: RGB color tuple

        Returns:
            Palette index (0-15) or -1 if no palette is set.
        """
        if self._sheet_palette is None:
            return -1

        # Check explicit mappings first
        if rgb in self._sheet_palette.color_mappings:
            return self._sheet_palette.color_mappings[rgb]

        # Fallback to nearest color in palette
        return self._find_nearest_palette_index(rgb)

    def _find_nearest_palette_index(self, color: tuple[int, int, int]) -> int:
        """Find the palette index with the nearest color.

        Args:
            color: RGB color tuple

        Returns:
            Index of nearest palette color (1-15, skipping index 0/transparency).
        """
        if self._sheet_palette is None or not self._sheet_palette.colors:
            return -1

        min_dist = float("inf")
        best_idx = 1  # Default to index 1, skip 0 (transparency)

        for idx, pal_color in enumerate(self._sheet_palette.colors):
            if idx == 0:
                continue  # Skip transparency index
            dist = (
                (color[0] - pal_color[0]) ** 2
                + (color[1] - pal_color[1]) ** 2
                + (color[2] - pal_color[2]) ** 2
            )
            if dist < min_dist:
                min_dist = dist
                best_idx = idx

        return best_idx

    # -------------------------------------------------------------------------
    # Eyedropper Mode
    # -------------------------------------------------------------------------

    def set_eyedropper_mode(self, enabled: bool) -> None:
        """Enable or disable eyedropper mode.

        When enabled, clicking on the canvas will pick the pixel color
        and emit eyedropper_picked signal.

        Args:
            enabled: True to enable eyedropper mode.
        """
        self._eyedropper_mode = enabled
        if enabled:
            self._view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._view.unsetCursor()

    def is_eyedropper_mode(self) -> bool:
        """Check if eyedropper mode is active."""
        return self._eyedropper_mode

    def _on_eyedropper_toggled(self, checked: bool) -> None:
        """Handle eyedropper button toggle."""
        self.set_eyedropper_mode(checked)

    def _update_pixel_info_label(self, x: int, y: int, rgb: object, palette_index: int) -> None:
        """Update the pixel info label with hover information.

        Args:
            x: Image X coordinate
            y: Image Y coordinate
            rgb: RGB tuple or None if outside bounds
            palette_index: Palette index (0-15) or -1 if no palette
        """
        if x < 0 or rgb is None:
            self._pixel_info_label.setText("--")
            return

        # Cast rgb properly
        r, g, b = rgb  # type: ignore[misc]

        if palette_index >= 0:
            text = f"({x:3}, {y:3})  RGB({r:3},{g:3},{b:3})  Idx:{palette_index:X}"
        else:
            text = f"({x:3}, {y:3})  RGB({r:3},{g:3},{b:3})"

        self._pixel_info_label.setText(text)

    def _clear_pixel_info_label(self) -> None:
        """Clear the pixel info label when mouse leaves."""
        self._pixel_info_label.setText("--")

    def highlight_pixels_by_index(self, index: int | None) -> None:
        """Highlight all pixels that use the given palette index.

        This is called when the user hovers over a palette swatch to show
        which pixels in the AI frame use that color.

        Args:
            index: Palette index to highlight, or None to hide highlight
        """
        if index is None:
            # Hide highlight immediately
            self._pixel_highlight_timer.stop()
            self._pending_highlight_index = None
            if self._pixel_highlight_item is not None:
                self._pixel_highlight_item.setVisible(False)
            return

        # Debounce the mask generation
        self._pending_highlight_index = index
        self._pixel_highlight_timer.start(PIXEL_HIGHLIGHT_DEBOUNCE_MS)

    def _generate_pixel_highlight_mask(self) -> None:
        """Generate and display the pixel highlight mask for the pending index."""
        index = self._pending_highlight_index
        if index is None:
            return

        if self._ai_image is None:
            return

        if self._pixel_highlight_item is None:
            return

        # Generate mask showing pixels using this palette index
        try:
            # Create a mask image with same size as AI frame
            width, height = self._ai_image.size
            # Create RGBA image for the mask (yellow with transparency)
            mask = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            pixels = mask.load()
            ai_pixels = self._ai_image.load()

            if pixels is None or ai_pixels is None:
                return

            # Find all pixels that map to this palette index
            for y in range(height):
                for x in range(width):
                    pixel_raw = ai_pixels[x, y]
                    if isinstance(pixel_raw, (int, float)):
                        continue  # Grayscale, skip

                    # At this point pixel_raw is a tuple - check length
                    if len(pixel_raw) < 3:
                        continue

                    # Check if pixel has alpha and is transparent
                    if len(pixel_raw) >= 4 and int(pixel_raw[3]) == 0:
                        continue  # Skip transparent pixels

                    rgb = (int(pixel_raw[0]), int(pixel_raw[1]), int(pixel_raw[2]))
                    pixel_index = self._lookup_palette_index(rgb)

                    if pixel_index == index:
                        # Highlight this pixel with yellow tint at 50% opacity
                        pixels[x, y] = (255, 255, 0, 128)

            # Convert to QPixmap and display
            # Scale to display size
            scaled_width = width * DISPLAY_SCALE
            scaled_height = height * DISPLAY_SCALE
            scaled_mask = mask.resize(
                (scaled_width, scaled_height), Image.Resampling.NEAREST
            )

            # Convert PIL image to QPixmap
            data = scaled_mask.tobytes("raw", "RGBA")
            from PySide6.QtGui import QImage

            qimage = QImage(
                data,
                scaled_width,
                scaled_height,
                scaled_width * 4,
                QImage.Format.Format_RGBA8888,
            )
            pixmap = QPixmap.fromImage(qimage)

            # Position the highlight overlay to match the AI frame
            self._pixel_highlight_item.setPixmap(pixmap)
            self._pixel_highlight_item.setPos(self._ai_frame_item.pos())
            self._pixel_highlight_item.setVisible(True)

        except Exception as e:
            logger.warning("Failed to generate pixel highlight mask: %s", e)
            self._pixel_highlight_item.setVisible(False)

    def _on_scene_clicked(self, scene_x: float, scene_y: float) -> None:
        """Handle click on the scene - pick color if eyedropper mode is active.

        Args:
            scene_x: Scene X coordinate
            scene_y: Scene Y coordinate
        """
        if not self._eyedropper_mode:
            return

        # Get pixel info at clicked position
        result = self._get_pixel_at_scene_pos(scene_x, scene_y)
        if result is None:
            return

        _img_x, _img_y, rgb, palette_index = result

        # Emit the picked color and disable eyedropper mode (single-shot)
        self.eyedropper_picked.emit(rgb, palette_index)

        # Auto-disable eyedropper mode
        self._eyedropper_btn.setChecked(False)
        self.set_eyedropper_mode(False)
