"""Comparison Panel for side-by-side and overlay frame viewing."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.frame_mapping.services.canvas_config_service import CanvasConfig
from ui.frame_mapping.views.base_overlay_canvas import BaseOverlayCanvas
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, GameFrame

logger = get_logger(__name__)

# Preview display size
PREVIEW_SIZE = 256


class FramePreview(QFrame):
    """A single frame preview with image and metadata."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Title
        self._title_label = QLabel(self._title)
        self._title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_label)

        # Image container
        self._image_container = QWidget()
        self._image_container.setMinimumSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self._image_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        container_layout = QVBoxLayout(self._image_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background-color: #2a2a2a;")
        self._image_label.setMinimumSize(PREVIEW_SIZE, PREVIEW_SIZE)
        container_layout.addWidget(self._image_label)

        layout.addWidget(self._image_container, 1)

        # Metadata
        self._metadata_label = QLabel()
        self._metadata_label.setStyleSheet("color: #888; font-size: 11px;")
        self._metadata_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._metadata_label.setWordWrap(True)
        layout.addWidget(self._metadata_label)

    def set_image(self, path: Path | None, metadata: str = "") -> None:
        """Set the preview image from a file path.

        Args:
            path: Path to image file, or None to clear
            metadata: Metadata text to display below image
        """
        if path is None or not path.exists():
            self._image_label.clear()
            self._image_label.setText("No image")
            self._metadata_label.setText("")
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._image_label.clear()
            self._image_label.setText("Failed to load")
            self._metadata_label.setText("")
            return

        # Scale to fit while maintaining aspect ratio
        scaled = pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        self._metadata_label.setText(metadata)

    def set_pixmap(self, pixmap: QPixmap | None, metadata: str = "") -> None:
        """Set the preview image directly from a QPixmap.

        Args:
            pixmap: QPixmap to display, or None to clear
            metadata: Metadata text to display below image
        """
        if pixmap is None or pixmap.isNull():
            self._image_label.clear()
            self._image_label.setText("No image")
            self._metadata_label.setText("")
            return

        scaled = pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        self._metadata_label.setText(metadata)

    def clear(self) -> None:
        """Clear the preview."""
        self._image_label.clear()
        self._image_label.setText("No image")
        self._metadata_label.setText("")


class InlineOverlayCanvas(BaseOverlayCanvas):
    """Display-only overlay canvas for comparison view.

    Shows game frame with AI frame overlaid. Read-only - doesn't support dragging.
    Double-clicking emits alignment_edit_requested when both frames are loaded.

    Signals:
        alignment_edit_requested: Emitted when user double-clicks to edit alignment
    """

    alignment_edit_requested = Signal()

    @override
    def mouseDoubleClickEvent(self, event: object) -> None:
        """Handle double-click to request alignment edit."""
        # Only emit if we have both frames loaded
        if self._game_pixmap is not None and self._ai_pixmap is not None:
            self.alignment_edit_requested.emit()


class ComparisonPanel(QWidget):
    """Panel for comparing game and AI frames.

    Supports two modes:
    - Side-by-side: Shows frames next to each other
    - Overlay: Shows AI frame overlaid on game frame with opacity control

    When a mapping is selected with alignment data, the overlay shows the
    adjusted position and flip state.

    Signals:
        alignment_edit_requested: Emitted when user double-clicks overlay to edit alignment
    """

    alignment_edit_requested = Signal()

    def __init__(self, parent: QWidget | None = None, config: CanvasConfig | None = None) -> None:
        super().__init__(parent)

        # Configuration (with defaults if not provided)
        if config is None:
            config = CanvasConfig(size=350, display_scale=4)
        self._config = config

        self._current_game_frame: GameFrame | None = None
        self._current_ai_frame: AIFrame | None = None
        self._game_pixmap: QPixmap | None = None
        self._ai_pixmap: QPixmap | None = None
        self._alignment_offset_x = 0
        self._alignment_offset_y = 0
        self._alignment_flip_h = False
        self._alignment_flip_v = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Mode toggle
        mode_layout = QHBoxLayout()
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(8)

        mode_label = QLabel("View:")
        mode_label.setStyleSheet("font-size: 11px;")
        mode_layout.addWidget(mode_label)

        self._mode_group = QButtonGroup(self)
        self._side_by_side_radio = QRadioButton("Side-by-Side")
        self._overlay_radio = QRadioButton("Overlay")
        self._overlay_radio.setChecked(True)  # Default to overlay per UX spec
        self._mode_group.addButton(self._side_by_side_radio, 0)
        self._mode_group.addButton(self._overlay_radio, 1)
        mode_layout.addWidget(self._side_by_side_radio)
        mode_layout.addWidget(self._overlay_radio)

        mode_layout.addStretch()

        # Alignment info (shown when overlay mode and alignment data available)
        self._alignment_label = QLabel()
        self._alignment_label.setStyleSheet("color: #888; font-size: 11px;")
        mode_layout.addWidget(self._alignment_label)

        layout.addLayout(mode_layout)

        # Stacked widget for mode switching
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        # Side-by-side view
        side_by_side_widget = QWidget()
        sbs_layout = QHBoxLayout(side_by_side_widget)
        sbs_layout.setContentsMargins(0, 0, 0, 0)
        sbs_layout.setSpacing(8)

        self._game_preview = FramePreview("Game Frame")
        sbs_layout.addWidget(self._game_preview, 1)

        self._ai_preview = FramePreview("AI Frame")
        sbs_layout.addWidget(self._ai_preview, 1)

        self._stack.addWidget(side_by_side_widget)

        # Overlay view
        overlay_widget = QWidget()
        overlay_layout = QVBoxLayout(overlay_widget)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(4)

        # Overlay canvas (centered, double-click to edit alignment)
        canvas_container = QHBoxLayout()
        canvas_container.addStretch()
        self._overlay_canvas = InlineOverlayCanvas(self._config.size, self._config.display_scale)
        self._overlay_canvas.alignment_edit_requested.connect(self.alignment_edit_requested.emit)
        canvas_container.addWidget(self._overlay_canvas)
        canvas_container.addStretch()
        overlay_layout.addLayout(canvas_container, 1)

        # Opacity slider and alignment button
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addStretch()

        opacity_label = QLabel("AI Opacity:")
        opacity_label.setStyleSheet("font-size: 11px;")
        controls_layout.addWidget(opacity_label)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(50)
        self._opacity_slider.setMaximumWidth(150)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        controls_layout.addWidget(self._opacity_slider)

        self._opacity_value_label = QLabel("50%")
        self._opacity_value_label.setStyleSheet("font-size: 11px;")
        self._opacity_value_label.setMinimumWidth(35)
        controls_layout.addWidget(self._opacity_value_label)

        # Adjust Alignment button
        self._adjust_alignment_button = QPushButton("Adjust Alignment")
        self._adjust_alignment_button.setToolTip("Click to adjust AI frame position (or double-click canvas)")
        self._adjust_alignment_button.setStyleSheet("font-size: 11px;")
        self._adjust_alignment_button.clicked.connect(self.alignment_edit_requested.emit)
        controls_layout.addWidget(self._adjust_alignment_button)

        controls_layout.addStretch()

        overlay_layout.addLayout(controls_layout)

        self._stack.addWidget(overlay_widget)

        # Set initial view to overlay (index 1)
        self._stack.setCurrentIndex(1)

        # Connect mode toggle
        self._mode_group.idToggled.connect(self._on_mode_changed)

    def _on_mode_changed(self, id: int, checked: bool) -> None:
        """Handle mode toggle."""
        if checked:
            self._stack.setCurrentIndex(id)
            self._update_alignment_label()

    def _on_opacity_changed(self, value: int) -> None:
        """Handle opacity slider change."""
        self._opacity_value_label.setText(f"{value}%")
        self._overlay_canvas.set_opacity(value / 100.0)

    def _update_alignment_label(self) -> None:
        """Update the alignment info label."""
        if self._stack.currentIndex() == 1:  # Overlay mode
            if (
                self._alignment_offset_x != 0
                or self._alignment_offset_y != 0
                or self._alignment_flip_h
                or self._alignment_flip_v
            ):
                parts = []
                if self._alignment_offset_x != 0 or self._alignment_offset_y != 0:
                    parts.append(f"Offset: ({self._alignment_offset_x}, {self._alignment_offset_y})")
                if self._alignment_flip_h:
                    parts.append("H-Flip")
                if self._alignment_flip_v:
                    parts.append("V-Flip")
                self._alignment_label.setText(" | ".join(parts))
            else:
                self._alignment_label.setText("")
        else:
            self._alignment_label.setText("")

    def _sync_overlay_canvas(self) -> None:
        """Synchronize overlay canvas with current state."""
        self._overlay_canvas.set_game_frame(self._game_pixmap)
        self._overlay_canvas.set_ai_frame(self._ai_pixmap)
        self._overlay_canvas.set_offset(self._alignment_offset_x, self._alignment_offset_y)
        self._overlay_canvas.set_flip(self._alignment_flip_h, self._alignment_flip_v)

    def set_game_frame(self, frame: GameFrame | None, preview_pixmap: QPixmap | None = None) -> None:
        """Set the game frame to display.

        Args:
            frame: GameFrame to display, or None to clear
            preview_pixmap: Optional pre-rendered preview pixmap
        """
        self._current_game_frame = frame

        if frame is None:
            self._game_preview.clear()
            self._game_pixmap = None
            self._sync_overlay_canvas()
            return

        # Build metadata string
        metadata_parts = [frame.id]
        if frame.rom_offsets:
            offset_str = ", ".join(f"0x{o:06X}" for o in frame.rom_offsets[:3])
            if len(frame.rom_offsets) > 3:
                offset_str += f" +{len(frame.rom_offsets) - 3} more"
            metadata_parts.append(offset_str)
        if frame.width and frame.height:
            metadata_parts.append(f"{frame.width}x{frame.height}")

        metadata = "\n".join(metadata_parts)

        if preview_pixmap is not None:
            self._game_preview.set_pixmap(preview_pixmap, metadata)
            self._game_pixmap = preview_pixmap
        elif frame.capture_path:
            preview_path = frame.capture_path.with_suffix(".png")
            self._game_preview.set_image(preview_path, metadata)
            if preview_path.exists():
                self._game_pixmap = QPixmap(str(preview_path))
            else:
                self._game_pixmap = None
        else:
            self._game_preview.clear()
            self._game_preview._metadata_label.setText(metadata)
            self._game_pixmap = None

        self._sync_overlay_canvas()

    def set_ai_frame(self, frame: AIFrame | None) -> None:
        """Set the AI frame to display.

        Args:
            frame: AIFrame to display, or None to clear
        """
        self._current_ai_frame = frame

        if frame is None:
            self._ai_preview.clear()
            self._ai_pixmap = None
            self._sync_overlay_canvas()
            return

        # Build metadata string
        metadata_parts = [frame.path.name]
        if frame.width and frame.height:
            metadata_parts.append(f"{frame.width}x{frame.height}")

        metadata = "\n".join(metadata_parts)
        self._ai_preview.set_image(frame.path, metadata)

        if frame.path.exists():
            self._ai_pixmap = QPixmap(str(frame.path))
        else:
            self._ai_pixmap = None

        self._sync_overlay_canvas()

    def set_alignment(
        self,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
    ) -> None:
        """Set the alignment values for overlay display.

        Args:
            offset_x: X offset for the AI frame
            offset_y: Y offset for the AI frame
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
        """
        self._alignment_offset_x = offset_x
        self._alignment_offset_y = offset_y
        self._alignment_flip_h = flip_h
        self._alignment_flip_v = flip_v
        self._overlay_canvas.set_offset(offset_x, offset_y)
        self._overlay_canvas.set_flip(flip_h, flip_v)
        self._update_alignment_label()

    def switch_to_overlay_mode(self) -> None:
        """Switch the comparison panel to overlay view mode programmatically."""
        self._overlay_radio.setChecked(True)

    def clear_alignment(self) -> None:
        """Clear alignment values (reset to defaults)."""
        self.set_alignment(0, 0, False, False)

    def clear_game_frame(self) -> None:
        """Clear just the game frame preview (for unmapped AI frame selection)."""
        self._game_preview.clear()
        self._current_game_frame = None
        self._game_pixmap = None
        self.clear_alignment()
        self._sync_overlay_canvas()

    def clear(self) -> None:
        """Clear both previews and alignment."""
        self._game_preview.clear()
        self._ai_preview.clear()
        self._current_game_frame = None
        self._current_ai_frame = None
        self._game_pixmap = None
        self._ai_pixmap = None
        self.clear_alignment()
        self._sync_overlay_canvas()
