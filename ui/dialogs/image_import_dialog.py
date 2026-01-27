"""Dialog for importing external images with color quantization."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.color_quantization import QuantizationResult
from ui.components.base.dialog_base import DialogBase
from ui.workers.quantization_worker import AsyncQuantizationService

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray
    from PIL import Image


class ImageImportDialog(DialogBase):
    """Dialog for importing external images with color quantization.

    Allows users to:
    - Browse and select an image file
    - Preview original vs quantized result
    - Configure dithering and transparency options
    - View generated 16-color palette

    Signals:
        import_requested: Emitted when user clicks Import with valid result
    """

    import_requested = Signal(object)  # QuantizationResult

    def __init__(
        self,
        parent: QWidget | None = None,
        target_size: tuple[int, int] | None = None,
    ) -> None:
        """Initialize the import dialog.

        Args:
            parent: Parent widget
            target_size: Target (width, height) for scaling imported images
        """
        # Store configuration before super().__init__ (DialogBase pattern)
        self._target_size = target_size
        self._source_path: str = ""
        self._source_image: Image.Image | None = None
        self._result: QuantizationResult | None = None

        # Async quantization service
        self._quantization_service: AsyncQuantizationService | None = None

        super().__init__(
            parent,
            title="Import Image",
            min_size=(700, 550),
            with_button_box=True,
        )

        # Set up async quantization service after UI is created
        self._quantization_service = AsyncQuantizationService(self)
        self._quantization_service.result_ready.connect(self._on_quantization_ready)
        self._quantization_service.quantization_failed.connect(self._on_quantization_failed)
        self._quantization_service.quantization_started.connect(self._on_quantization_started)

        # Customize button box
        if self.button_box:
            ok_button = self.button_box.button(self.button_box.StandardButton.Ok)
            if ok_button:
                ok_button.setText("Import")
                ok_button.setEnabled(False)

    @override
    def _setup_ui(self) -> None:
        """Build dialog UI components."""
        layout = QVBoxLayout()
        self.content_widget.setLayout(layout)

        # Preview section
        preview_layout = QHBoxLayout()

        # Original preview
        original_group = QGroupBox("Original")
        original_layout = QVBoxLayout(original_group)
        self._original_preview = QLabel()
        self._original_preview.setMinimumSize(256, 256)
        self._original_preview.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        self._original_preview.setAlignment(self._original_preview.alignment())
        self._original_preview.setScaledContents(False)
        original_layout.addWidget(self._original_preview)
        self._original_info = QLabel("No image loaded")
        original_layout.addWidget(self._original_info)
        preview_layout.addWidget(original_group)

        # Quantized preview
        quantized_group = QGroupBox("Quantized (16 colors)")
        quantized_layout = QVBoxLayout(quantized_group)
        self._quantized_preview = QLabel()
        self._quantized_preview.setMinimumSize(256, 256)
        self._quantized_preview.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        self._quantized_preview.setScaledContents(False)
        quantized_layout.addWidget(self._quantized_preview)

        # Loading indicator (hidden by default)
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)  # Indeterminate mode
        self._loading_bar.setVisible(False)
        self._loading_bar.setMaximumHeight(16)
        quantized_layout.addWidget(self._loading_bar)

        self._quantized_info = QLabel("--")
        quantized_layout.addWidget(self._quantized_info)
        preview_layout.addWidget(quantized_group)

        layout.addLayout(preview_layout)

        # Source file section
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Source:"))
        self._source_input = QLineEdit()
        self._source_input.setReadOnly(True)
        self._source_input.setPlaceholderText("Select an image file...")
        source_layout.addWidget(self._source_input, 1)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_clicked)
        source_layout.addWidget(browse_button)
        layout.addLayout(source_layout)

        # Options section
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self._dither_checkbox = QCheckBox("Enable dithering")
        self._dither_checkbox.setChecked(True)
        self._dither_checkbox.setToolTip("Apply Floyd-Steinberg dithering for smoother color transitions")
        self._dither_checkbox.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self._dither_checkbox)

        self._transparency_checkbox = QCheckBox("Preserve transparency (alpha → index 0)")
        self._transparency_checkbox.setChecked(True)
        self._transparency_checkbox.setToolTip("Map transparent pixels to color index 0")
        self._transparency_checkbox.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self._transparency_checkbox)

        # Background type selector for preview
        bg_layout = QHBoxLayout()
        bg_layout.addWidget(QLabel("Preview background:"))
        self._bg_combo = QComboBox()
        self._bg_combo.addItems(["Checkerboard", "Black", "White"])
        self._bg_combo.setToolTip("Background color for transparent pixels in preview")
        self._bg_combo.currentIndexChanged.connect(self._on_option_changed)
        bg_layout.addWidget(self._bg_combo)
        bg_layout.addStretch()
        options_layout.addLayout(bg_layout)

        # Target size info
        if self._target_size:
            target_label = QLabel(f"Target size: {self._target_size[0]} x {self._target_size[1]} pixels")
            target_label.setToolTip("Image will be scaled to match sprite dimensions")
            options_layout.addWidget(target_label)

        layout.addWidget(options_group)

        # Palette preview section
        palette_group = QGroupBox("Generated Palette")
        palette_layout = QVBoxLayout(palette_group)
        self._palette_grid = QWidget()
        self._palette_grid_layout = QGridLayout(self._palette_grid)
        self._palette_grid_layout.setSpacing(2)

        # Create 16 color swatches
        self._color_swatches: list[QLabel] = []
        for i in range(16):
            swatch = QLabel()
            swatch.setFixedSize(24, 24)
            swatch.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
            swatch.setStyleSheet("background-color: #000000;")
            swatch.setToolTip(f"Index {i}")
            self._palette_grid_layout.addWidget(swatch, 0, i)
            self._color_swatches.append(swatch)

        # Index labels
        for i in range(16):
            label = QLabel(str(i))
            label.setAlignment(label.alignment())
            self._palette_grid_layout.addWidget(label, 1, i)

        palette_layout.addWidget(self._palette_grid)
        layout.addWidget(palette_group)

    def _on_browse_clicked(self) -> None:
        """Handle Browse button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)",
        )

        if file_path:
            self._source_path = file_path
            self._source_input.setText(file_path)
            self._load_and_preview()

    def _load_and_preview(self) -> None:
        """Load source image and generate quantized preview."""
        from PIL import Image

        try:
            self._source_image = Image.open(self._source_path)

            # Update original preview
            self._update_original_preview()

            # Generate quantized preview
            self._update_quantized_preview()

        except Exception as e:
            self._original_info.setText(f"Error: {e}")
            self._source_image = None
            self._result = None
            self._set_import_enabled(False)

    def _update_original_preview(self) -> None:
        """Update the original image preview."""
        if self._source_image is None:
            return

        # Convert to QPixmap for display
        pixmap = self._pil_to_qpixmap(self._source_image)
        if pixmap:
            scaled = pixmap.scaled(
                256,
                256,
                aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                mode=Qt.TransformationMode.SmoothTransformation,
            )
            self._original_preview.setPixmap(scaled)

        # Update info label
        mode = self._source_image.mode
        w, h = self._source_image.size
        self._original_info.setText(f"{w} x {h} pixels, {mode}")

    def _update_quantized_preview(self) -> None:
        """Request async quantization and preview generation."""
        if self._source_image is None or self._quantization_service is None:
            return

        # Disable import button while quantizing
        self._set_import_enabled(False)

        # Request async quantization
        self._quantization_service.request_quantization(
            source_image=self._source_image,
            target_size=self._target_size,
            dither=self._dither_checkbox.isChecked(),
            transparency_threshold=127 if self._transparency_checkbox.isChecked() else 0,
        )

    def _on_quantization_started(self) -> None:
        """Handle quantization start - show loading indicator."""
        self._loading_bar.setVisible(True)
        self._quantized_info.setText("Quantizing...")

    def _on_quantization_ready(self, result: QuantizationResult) -> None:
        """Handle async quantization completion.

        Args:
            result: The quantization result from the worker.
        """
        self._loading_bar.setVisible(False)
        self._result = result

        # Update preview image
        preview_image = self._indexed_to_pil(
            result.indexed_data,
            result.palette,
        )
        pixmap = self._pil_to_qpixmap(preview_image)
        if pixmap:
            # Scale for display (may be smaller than 256x256)
            scaled = pixmap.scaled(
                256,
                256,
                aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                mode=Qt.TransformationMode.FastTransformation,  # Nearest neighbor for pixel art
            )
            self._quantized_preview.setPixmap(scaled)

        # Update info
        h, w = result.indexed_data.shape
        self._quantized_info.setText(f"{w} x {h} pixels, 16 colors")

        # Update palette display
        self._update_palette_display()

        # Enable import button
        self._set_import_enabled(True)

    def _on_quantization_failed(self, error_message: str) -> None:
        """Handle quantization failure.

        Args:
            error_message: Description of the failure.
        """
        self._loading_bar.setVisible(False)
        self._quantized_info.setText(f"Error: {error_message}")
        self._result = None
        self._set_import_enabled(False)

    def _update_palette_display(self) -> None:
        """Update the palette color swatches."""
        if self._result is None:
            return

        for i, color in enumerate(self._result.palette):
            if i < len(self._color_swatches):
                r, g, b = color
                self._color_swatches[i].setStyleSheet(f"background-color: rgb({r}, {g}, {b});")
                self._color_swatches[i].setToolTip(f"Index {i}: RGB({r}, {g}, {b})")

    def _on_option_changed(self) -> None:
        """Handle option checkbox changes."""
        if self._source_image is not None:
            self._update_quantized_preview()

    def _set_import_enabled(self, enabled: bool) -> None:
        """Enable or disable the Import button."""
        if self.button_box:
            ok_button = self.button_box.button(self.button_box.StandardButton.Ok)
            if ok_button:
                ok_button.setEnabled(enabled)

    def _pil_to_qpixmap(self, image: Image.Image) -> QPixmap | None:
        """Convert PIL Image to QPixmap."""

        # Convert to RGBA for Qt
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        data = image.tobytes("raw", "RGBA")
        qimage = QImage(
            data,
            image.width,
            image.height,
            QImage.Format.Format_RGBA8888,
        )

        # QImage doesn't keep the data, so we need to copy
        return QPixmap.fromImage(qimage.copy())

    def _create_checkerboard(self, w: int, h: int, cell_size: int = 8) -> NDArray[np.uint8]:
        """Create checkerboard pattern for transparency display using vectorized ops.

        Args:
            w: Width in pixels
            h: Height in pixels
            cell_size: Size of each checker cell (default 8)

        Returns:
            RGBA numpy array with checkerboard pattern
        """
        # Create coordinate grids
        y_coords = np.arange(h)
        x_coords = np.arange(w)
        y_grid, x_grid = np.meshgrid(y_coords, x_coords, indexing="ij")

        # Calculate which tile each pixel belongs to
        tile_x = x_grid // cell_size
        tile_y = y_grid // cell_size

        # Create checkerboard mask (True for light, False for dark)
        is_light = ((tile_x + tile_y) % 2) == 0

        # Create RGBA array
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        light = (220, 220, 220, 255)  # Match PixelCanvas colors
        dark = (180, 180, 180, 255)

        rgba[is_light] = light
        rgba[~is_light] = dark

        return rgba

    def _indexed_to_pil(
        self,
        indexed: NDArray[np.uint8],
        palette: list[tuple[int, int, int]],
    ) -> Image.Image:
        """Convert indexed array to PIL Image with transparency background.

        Uses the selected background type for transparent pixels (index 0).
        """
        import numpy as np
        from PIL import Image

        h, w = indexed.shape
        bg_type = self._bg_combo.currentText().lower()

        # Create background based on selection
        if bg_type == "checkerboard":
            rgba = self._create_checkerboard(w, h)
        elif bg_type == "white":
            rgba = np.full((h, w, 4), 255, dtype=np.uint8)
        else:  # black
            rgba = np.zeros((h, w, 4), dtype=np.uint8)
            rgba[:, :, 3] = 255  # Opaque black

        # Apply palette colors for non-transparent pixels
        for i, color in enumerate(palette):
            if i == 0:  # Index 0 = transparent, keep background
                continue
            mask = indexed == i
            rgba[mask, 0] = color[0]
            rgba[mask, 1] = color[1]
            rgba[mask, 2] = color[2]
            rgba[mask, 3] = 255

        return Image.fromarray(rgba, mode="RGBA")

    @override
    def accept(self) -> None:
        """Handle dialog accept (Import button)."""
        if self._result:
            self.import_requested.emit(self._result)
        super().accept()

    def get_result(self) -> QuantizationResult | None:
        """Get quantization result after dialog closes.

        Returns:
            QuantizationResult if import was successful, None otherwise
        """
        return self._result
