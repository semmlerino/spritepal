#!/usr/bin/env python3
"""
Multi-palette tab for the sprite editor.
Handles multi-palette preview functionality.
"""

from typing import Any

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.common.signal_utils import safe_disconnect


class ClickableLabel(QLabel):
    """QLabel subclass that emits clicked signal with palette index."""

    clicked = Signal(int)

    def __init__(self, palette_idx: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette_idx = palette_idx

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        """Override to emit clicked signal with palette index."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._palette_idx)
        super().mousePressEvent(event)


class MultiPaletteViewer(QWidget):
    """Widget for viewing sprites with multiple palettes applied."""

    palette_selected = Signal(int)  # Emits selected palette number

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._palette_labels: list[ClickableLabel] = []
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

            # Create clickable label for this palette
            label = ClickableLabel(i)
            label.setPixmap(
                pixmap.scaled(
                    384,
                    384,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )
            label.setToolTip(f"Palette {i}")
            label.setStyleSheet(
                "QLabel { border: 2px solid #444; padding: 4px; }QLabel:hover { border: 2px solid #888; }"
            )
            # Connect signal instead of monkey-patching mousePressEvent
            label.clicked.connect(self._on_palette_clicked)

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

    def set_palette_images(self, palette_images: dict[str, Image.Image]) -> None:
        """Display pre-rendered palette images directly.

        Args:
            palette_images: Dict mapping 'palette_0'..'palette_15' to PIL images
        """
        self._clear_previews()

        # Sort palette numbers
        palette_nums = []
        for key in palette_images:
            if key.startswith("palette_"):
                try:
                    num = int(key.split("_")[1])
                    if 0 <= num < 16:
                        palette_nums.append(num)
                except (ValueError, IndexError):
                    continue
        palette_nums.sort()

        # Display each palette image in grid (4 columns)
        for i in palette_nums:
            img = palette_images.get(f"palette_{i}")
            if not img:
                continue

            pixmap = self._pil_to_pixmap(img)
            label = ClickableLabel(i)
            label.setPixmap(
                pixmap.scaled(
                    384,
                    384,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )
            label.setToolTip(f"Palette {i}")
            label.setStyleSheet(
                "QLabel { border: 2px solid #444; padding: 4px; }QLabel:hover { border: 2px solid #888; }"
            )
            label.clicked.connect(self._on_palette_clicked)

            palette_label = QLabel(f"Palette {i}")
            palette_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.addWidget(label)
            container_layout.addWidget(palette_label)

            row, col = i // 4, i % 4
            self._grid_layout.addWidget(container, row, col)
            self._palette_labels.append(label)

    def _clear_previews(self) -> None:
        """Clear all palette previews."""
        # Disconnect signals to prevent memory leaks
        for label in self._palette_labels:
            safe_disconnect(label.clicked)

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

    def set_oam_statistics(self, stats: dict[str, Any]) -> None:  # type: ignore[reportExplicitAny]
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
        # Store controller reference before calling super
        from ...controllers.extraction_controller import ExtractionController

        self.extraction_controller: ExtractionController | None = None
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the multi-palette tab UI."""
        layout = QVBoxLayout(self)

        # Controls
        controls_group = QGroupBox("Multi-Palette Controls")
        controls_layout = QHBoxLayout()

        # OAM file selection (optional - enables palette filtering)
        self.oam_file_edit = QLineEdit()
        self.oam_file_edit.setReadOnly(True)
        self.oam_file_edit.setPlaceholderText("Optional: OAM enables palette filtering")
        self.oam_browse_btn = QPushButton("Load OAM (Optional)")
        self.oam_browse_btn.setToolTip(
            "OAM file enables palette filtering.\nWithout it, all 16 palettes will be shown."
        )
        self.oam_browse_btn.clicked.connect(self.browse_oam_requested.emit)

        controls_layout.addWidget(QLabel("OAM:"))
        controls_layout.addWidget(self.oam_file_edit)
        controls_layout.addWidget(self.oam_browse_btn)

        # Preview size control
        controls_layout.addWidget(QLabel("Preview Size:"))
        self.preview_size_spin = QSpinBox()
        self.preview_size_spin.setRange(16, 512)
        self.preview_size_spin.setValue(192)  # Default to 192 tiles (6KB)
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

        # Output area for status messages
        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setMaximumHeight(100)
        output_layout.addWidget(self.output_area)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Track if we've already shown the OAM info message
        self._oam_info_shown = False

        # Initialize with validation check
        self._validate_prerequisites()

    def _on_palette_selected(self, palette_num: int) -> None:
        """Handle palette selection."""
        # Update border styles for all palette previews
        for label in self.multi_palette_viewer._palette_labels:
            if label._palette_idx == palette_num:
                # Selected: green border
                label.setStyleSheet("border: 3px solid #00FF00;")
            else:
                # Others: gray border
                label.setStyleSheet("border: 1px solid #999;")

        self.palette_selected.emit(palette_num)

    def set_oam_file(self, file_path: str) -> None:
        """Set the OAM file path and validate prerequisites."""
        self.oam_file_edit.setText(file_path)
        # Reset the info flag so we can show new info if OAM is loaded
        self._oam_info_shown = False
        self._validate_prerequisites()

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

    def set_palette_images(self, palette_images: dict[str, Image.Image]) -> None:
        """Set palette images directly."""
        self.multi_palette_viewer.set_palette_images(palette_images)

    def set_oam_statistics(self, stats: dict[str, Any]) -> None:  # type: ignore[reportExplicitAny]
        """Set OAM statistics."""
        self.multi_palette_viewer.set_oam_statistics(stats)

    def get_multi_palette_viewer(self) -> MultiPaletteViewer:
        """Get the multi-palette viewer widget."""
        return self.multi_palette_viewer

    def append_output(self, text: str) -> None:
        """Append text to output area."""
        self.output_area.append(text)

    def clear_output(self) -> None:
        """Clear output area."""
        self.output_area.clear()

    def set_extraction_controller(self, controller: Any) -> None:  # type: ignore[reportExplicitAny]
        """Set the extraction controller reference for prerequisite validation.

        Args:
            controller: ExtractionController instance (typed as Any to avoid circular import)
        """
        self.extraction_controller = controller
        # Re-validate prerequisites with controller now available
        self._validate_prerequisites()

    def _validate_prerequisites(self) -> None:
        """Validate that prerequisites are met for multi-palette generation.

        OAM file is optional - if not provided, all 16 palettes will be shown.
        """
        # Check for OAM file (optional)
        has_oam = bool(self.oam_file_edit.text())

        # Check for VRAM and CGRAM files via controller (required)
        has_vram = False
        has_cgram = False
        if self.extraction_controller is not None:
            has_vram = bool(self.extraction_controller.vram_file)
            has_cgram = bool(self.extraction_controller.cgram_file)

        # Enable generate button if VRAM and CGRAM are present (OAM is optional)
        required_present = has_vram and has_cgram
        self.generate_multi_btn.setEnabled(required_present)

        # Show info about OAM being optional (only once)
        if not has_oam and not self._oam_info_shown and required_present:
            self.append_output("Info: OAM file not loaded. All 16 palettes will be shown.")
            self._oam_info_shown = True

        # Show warning for missing required files
        if not required_present:
            missing = []
            if not has_vram:
                missing.append("VRAM file")
            if not has_cgram:
                missing.append("CGRAM file")

            if missing:
                warning = f"Required files missing: {', '.join(missing)}."
                self.append_output(warning)
