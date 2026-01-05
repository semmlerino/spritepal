#!/usr/bin/env python3
"""
Multi-palette tab for the sprite editor.
Handles multi-palette preview functionality.
"""

from typing import Any

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class MultiPaletteViewer(QWidget):
    """Widget for viewing sprites with multiple palettes applied."""

    palette_selected = Signal(int)  # Emits selected palette number

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._palette_labels: list[QLabel] = []
        self._current_palettes: list[list[tuple[int, int, int]]] = []

    def _setup_ui(self) -> None:
        """Setup the viewer UI."""
        layout = QVBoxLayout(self)

        # Scroll area for palette previews
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Container for palette previews
        self._container = QWidget()
        self._grid_layout = QGridLayout(self._container)
        self._grid_layout.setSpacing(10)

        scroll.setWidget(self._container)
        layout.addWidget(scroll)

        # Statistics label
        self.stats_label = QLabel("No OAM data loaded")
        layout.addWidget(self.stats_label)

    def set_single_image_all_palettes(
        self,
        base_img: Image.Image,
        palettes: list[list[tuple[int, int, int]]],
    ) -> None:
        """Display a single image with all 16 palettes applied.

        Args:
            base_img: PIL indexed image (mode 'P')
            palettes: List of 16 palettes, each with 16 RGB tuples
        """
        # Clear existing previews
        self._clear_previews()
        self._current_palettes = palettes

        # Create preview for each palette
        for i, palette in enumerate(palettes[:16]):
            # Create copy of image and apply palette
            img_copy = base_img.copy()

            # Convert palette to flat list for PIL
            flat_palette: list[int] = []
            for color in palette[:16]:
                flat_palette.extend(color)
            # Pad to 256 colors (768 values)
            while len(flat_palette) < 768:
                flat_palette.extend([0, 0, 0])

            img_copy.putpalette(flat_palette)

            # Convert to QPixmap
            pixmap = self._pil_to_pixmap(img_copy)

            # Create label for this palette
            label = QLabel()
            label.setPixmap(pixmap.scaled(
                128, 128,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            ))
            label.setToolTip(f"Palette {i}")
            label.setStyleSheet(
                "QLabel { border: 2px solid #444; padding: 4px; }"
                "QLabel:hover { border: 2px solid #888; }"
            )
            label.mousePressEvent = lambda e, idx=i: self._on_palette_clicked(idx)

            # Add palette number label
            palette_label = QLabel(f"Palette {i}")
            palette_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Add to grid (4 columns)
            row = i // 4
            col = i % 4

            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.addWidget(label)
            container_layout.addWidget(palette_label)

            self._grid_layout.addWidget(container, row, col)
            self._palette_labels.append(label)

    def _clear_previews(self) -> None:
        """Clear all palette previews."""
        for i in reversed(range(self._grid_layout.count())):
            item = self._grid_layout.itemAt(i)
            if item and (widget := item.widget()):
                widget.deleteLater()
        self._palette_labels.clear()

    def _on_palette_clicked(self, palette_idx: int) -> None:
        """Handle palette preview click."""
        self.palette_selected.emit(palette_idx)

    def _pil_to_pixmap(self, img: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap."""
        # Convert to RGB if indexed
        if img.mode == "P" or img.mode != "RGBA":
            img = img.convert("RGBA")

        data = img.tobytes("raw", "RGBA")
        qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)

    def set_oam_statistics(self, stats: dict[str, Any]) -> None:
        """Set OAM statistics display."""
        if stats:
            text = f"OAM: {stats.get('sprite_count', 0)} sprites"
            if "palette_usage" in stats:
                usage = stats["palette_usage"]
                text += f" | Palettes used: {', '.join(str(p) for p in sorted(usage.keys()))}"
            self.stats_label.setText(text)
        else:
            self.stats_label.setText("No OAM data loaded")


class MultiPaletteTab(QWidget):
    """Tab widget for multi-palette preview functionality."""

    # Signals
    browse_oam_requested = Signal()
    generate_preview_requested = Signal()
    palette_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the multi-palette tab UI."""
        layout = QVBoxLayout(self)

        # Controls
        controls_group = QGroupBox("Multi-Palette Controls")
        controls_layout = QHBoxLayout()

        # OAM file selection
        self.oam_file_edit = QLineEdit()
        self.oam_file_edit.setReadOnly(True)
        self.oam_browse_btn = QPushButton("Load OAM")
        self.oam_browse_btn.clicked.connect(self.browse_oam_requested.emit)

        controls_layout.addWidget(QLabel("OAM:"))
        controls_layout.addWidget(self.oam_file_edit)
        controls_layout.addWidget(self.oam_browse_btn)

        # Preview size control
        controls_layout.addWidget(QLabel("Preview Size:"))
        self.preview_size_spin = QSpinBox()
        self.preview_size_spin.setRange(16, 512)
        self.preview_size_spin.setValue(64)  # Default to 64 tiles (2KB)
        self.preview_size_spin.setSuffix(" tiles")
        controls_layout.addWidget(self.preview_size_spin)

        # Generate preview button
        self.generate_multi_btn = QPushButton("Generate Multi-Palette Preview")
        self.generate_multi_btn.clicked.connect(self.generate_preview_requested.emit)
        controls_layout.addWidget(self.generate_multi_btn)

        controls_layout.addStretch()
        controls_group.setLayout(controls_layout)
        layout.addWidget(controls_group)

        # Create multi-palette viewer
        self.multi_palette_viewer = MultiPaletteViewer()
        self.multi_palette_viewer.palette_selected.connect(self._on_palette_selected)
        layout.addWidget(self.multi_palette_viewer)

    def _on_palette_selected(self, palette_num: int) -> None:
        """Handle palette selection."""
        self.palette_selected.emit(palette_num)

    def set_oam_file(self, file_path: str) -> None:
        """Set the OAM file path."""
        self.oam_file_edit.setText(file_path)

    def get_preview_size(self) -> int:
        """Get the preview size in tiles."""
        return self.preview_size_spin.value()

    def set_single_image_all_palettes(
        self,
        base_img: Image.Image,
        palettes: list[list[tuple[int, int, int]]],
    ) -> None:
        """Set single image with all palettes."""
        self.multi_palette_viewer.set_single_image_all_palettes(base_img, palettes)

    def set_oam_statistics(self, stats: dict[str, Any]) -> None:
        """Set OAM statistics."""
        self.multi_palette_viewer.set_oam_statistics(stats)

    def get_multi_palette_viewer(self) -> MultiPaletteViewer:
        """Get the multi-palette viewer widget."""
        return self.multi_palette_viewer
