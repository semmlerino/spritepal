"""Comparison Panel for side-by-side frame viewing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, GameFrame

logger = logging.getLogger(__name__)

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


class ComparisonPanel(QWidget):
    """Panel for side-by-side comparison of game and AI frames.

    Shows:
    - Left: Game frame (from capture)
    - Right: AI frame (generated)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Game frame preview (left)
        self._game_preview = FramePreview("Game Frame")
        layout.addWidget(self._game_preview, 1)

        # AI frame preview (right)
        self._ai_preview = FramePreview("AI Frame")
        layout.addWidget(self._ai_preview, 1)

    def set_game_frame(self, frame: GameFrame | None, preview_pixmap: QPixmap | None = None) -> None:
        """Set the game frame to display.

        Args:
            frame: GameFrame to display, or None to clear
            preview_pixmap: Optional pre-rendered preview pixmap
        """
        if frame is None:
            self._game_preview.clear()
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
        elif frame.capture_path:
            # Try to load preview from capture path
            preview_path = frame.capture_path.with_suffix(".png")
            self._game_preview.set_image(preview_path, metadata)
        else:
            self._game_preview.clear()
            self._game_preview._metadata_label.setText(metadata)

    def set_ai_frame(self, frame: AIFrame | None) -> None:
        """Set the AI frame to display.

        Args:
            frame: AIFrame to display, or None to clear
        """
        if frame is None:
            self._ai_preview.clear()
            return

        # Build metadata string
        metadata_parts = [frame.path.name]
        if frame.width and frame.height:
            metadata_parts.append(f"{frame.width}x{frame.height}")

        metadata = "\n".join(metadata_parts)
        self._ai_preview.set_image(frame.path, metadata)

    def clear(self) -> None:
        """Clear both previews."""
        self._game_preview.clear()
        self._ai_preview.clear()
