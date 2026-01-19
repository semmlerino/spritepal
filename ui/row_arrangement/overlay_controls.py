"""
Overlay controls widget for sprite rearrangement.

Provides UI controls for the overlay layer: import, position, opacity, visibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ui.row_arrangement.overlay_layer import OverlayLayer


class OverlayControls(QGroupBox):
    """Widget providing controls for the overlay layer.

    Signals:
        import_requested: Emitted when user clicks Import button.
        clear_requested: Emitted when user clicks Clear button.
        preview_mapping_requested: Emitted when user clicks Preview Mapping button.
    """

    import_requested = Signal()
    clear_requested = Signal()
    preview_mapping_requested = Signal()
    extract_palette_requested = Signal()
    snap_to_grid_requested = Signal()

    def __init__(self, overlay: OverlayLayer, parent: QWidget | None = None) -> None:
        super().__init__("Overlay Image", parent)
        self._overlay = overlay
        self._setup_ui()
        self._connect_signals()

        # Sync with current overlay state
        self._update_position_spinboxes(int(self._overlay.x), int(self._overlay.y))
        self._update_opacity_slider(self._overlay.opacity)
        self._update_scale_controls(self._overlay.scale)
        self._update_visibility_checkbox(self._overlay.visible)
        self._update_resample_combo(self._overlay.resampling_mode.value)
        self._update_enabled_state()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # Import/Clear row
        import_row = QHBoxLayout()
        self.import_btn = QPushButton("Import...")
        self.import_btn.setToolTip("Import an overlay image for reference")
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Remove the overlay image")
        import_row.addWidget(self.import_btn)
        import_row.addWidget(self.clear_btn)
        layout.addLayout(import_row)

        # Preview Mapping button (shows live palette mapping preview)
        self.preview_mapping_btn = QPushButton("Preview Mapping...")
        self.preview_mapping_btn.setToolTip(
            "Preview how overlay colors will map to the palette.\nAdjust mappings before applying."
        )
        layout.addWidget(self.preview_mapping_btn)

        # Extract Palette button (creates palette from overlay colors)
        self.extract_palette_btn = QPushButton("Extract Palette")
        self.extract_palette_btn.setToolTip(
            "Create a 16-color palette from overlay colors.\n"
            "Use this when you want the sprite to match the overlay exactly."
        )
        layout.addWidget(self.extract_palette_btn)

        # Snap to Grid button (aligns overlay dimensions to tile boundaries)
        self.snap_to_grid_btn = QPushButton("Snap to Grid")
        self.snap_to_grid_btn.setToolTip(
            "Adjust scale so overlay dimensions are multiples of 8 pixels.\n"
            "This ensures pixel-perfect alignment with tile boundaries."
        )
        layout.addWidget(self.snap_to_grid_btn)

        # Position controls
        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("X:"))
        self.x_spin = QSpinBox()
        self.x_spin.setRange(-9999, 9999)
        self.x_spin.setToolTip("Horizontal position (pixels)")
        pos_row.addWidget(self.x_spin)

        pos_row.addWidget(QLabel("Y:"))
        self.y_spin = QSpinBox()
        self.y_spin.setRange(-9999, 9999)
        self.y_spin.setToolTip("Vertical position (pixels)")
        pos_row.addWidget(self.y_spin)
        layout.addLayout(pos_row)

        # Scale slider
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Scale:"))
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(1, 500)  # 0.1% to 50%
        self.scale_slider.setValue(50)  # Default 5.0%
        self.scale_slider.setToolTip("Overlay scale (0.1-50%)")
        scale_row.addWidget(self.scale_slider)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 50.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(5.0)
        self.scale_spin.setSuffix("%")
        self.scale_spin.setDecimals(1)
        scale_row.addWidget(self.scale_spin)
        layout.addLayout(scale_row)

        # Opacity slider
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(50)
        self.opacity_slider.setToolTip("Overlay transparency (0-100%)")
        opacity_row.addWidget(self.opacity_slider)
        self.opacity_label = QLabel("50%")
        self.opacity_label.setMinimumWidth(35)
        opacity_row.addWidget(self.opacity_label)
        layout.addLayout(opacity_row)

        # Visibility checkbox
        self.visible_check = QCheckBox("Show overlay")
        self.visible_check.setChecked(True)
        self.visible_check.setToolTip("Toggle overlay visibility")
        layout.addWidget(self.visible_check)

        # Resampling mode combo
        resample_row = QHBoxLayout()
        resample_row.addWidget(QLabel("Quality:"))
        self.resample_combo = QComboBox()
        self.resample_combo.addItem("Pixel Perfect", Image.Resampling.NEAREST)
        self.resample_combo.addItem("Smoothed", Image.Resampling.BOX)
        self.resample_combo.addItem("High Quality", Image.Resampling.LANCZOS)
        self.resample_combo.setToolTip(
            "Pixel Perfect: Sharp edges for pixel art (default)\n"
            "Smoothed: Averaged pixels for softer result\n"
            "High Quality: Best for photos/gradients"
        )
        self.resample_combo.setCurrentIndex(0)  # Default to Pixel Perfect
        resample_row.addWidget(self.resample_combo)
        layout.addLayout(resample_row)

        # Nudge hint
        hint = QLabel("Arrow keys: ±1px (±10px with Shift)")
        hint.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(hint)

    def _connect_signals(self) -> None:
        """Connect signals between controls and overlay."""
        # UI -> Overlay
        self.import_btn.clicked.connect(self._on_import_clicked)
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        self.preview_mapping_btn.clicked.connect(self.preview_mapping_requested.emit)
        self.extract_palette_btn.clicked.connect(self.extract_palette_requested.emit)
        self.snap_to_grid_btn.clicked.connect(self._on_snap_to_grid_clicked)
        self.x_spin.valueChanged.connect(self._on_position_changed)
        self.y_spin.valueChanged.connect(self._on_position_changed)
        self.scale_slider.valueChanged.connect(self._on_scale_slider_changed)
        self.scale_spin.valueChanged.connect(self._on_scale_spin_changed)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.visible_check.toggled.connect(self._on_visibility_changed)
        self.resample_combo.currentIndexChanged.connect(self._on_resample_changed)

        # Overlay -> UI
        self._overlay.position_changed.connect(self._update_position_spinboxes)
        self._overlay.opacity_changed.connect(self._update_opacity_slider)
        self._overlay.scale_changed.connect(self._update_scale_controls)
        self._overlay.visibility_changed.connect(self._update_visibility_checkbox)
        self._overlay.resampling_mode_changed.connect(self._update_resample_combo)
        self._overlay.image_changed.connect(self._update_enabled_state)

    def _on_import_clicked(self) -> None:
        """Handle import button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Overlay Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)",
        )
        if file_path:
            # Try to get target dimensions from parent dialog for auto-scaling
            target_w, target_h = None, None
            # Look for GridArrangementDialog in the parent chain without circular import
            parent = self.parentWidget()
            while parent:
                if parent.__class__.__name__ == "GridArrangementDialog":
                    # Accessing attributes via duck typing to avoid import
                    grid = getattr(parent, "arrangement_grid", None)
                    processor = getattr(parent, "processor", None)
                    if grid and processor:
                        target_w = grid.grid_cols * processor.tile_width
                        target_h = grid.grid_rows * processor.tile_height
                    break
                parent = parent.parentWidget()

            self._overlay.import_image(file_path, target_w, target_h)

    def _on_clear_clicked(self) -> None:
        """Handle clear button click."""
        self._overlay.clear_image()

    def _on_snap_to_grid_clicked(self) -> None:
        """Handle snap to grid button click."""
        if self._overlay.snap_to_tile_grid(tile_size=8):
            # Scale was adjusted - emit signal so dialog can update
            self.snap_to_grid_requested.emit()

    def _on_position_changed(self) -> None:
        """Handle position spinbox changes."""
        x = self.x_spin.value()
        y = self.y_spin.value()
        # No need to block overlay signals; _update_position_spinboxes handles re-entrancy
        self._overlay.set_position(x, y)

    def _on_scale_slider_changed(self, value: int) -> None:
        """Handle scale slider changes (1-500 = 0.1%-50%)."""
        scale_percent = value / 10.0
        self.scale_spin.blockSignals(True)
        self.scale_spin.setValue(scale_percent)
        self.scale_spin.blockSignals(False)
        self._overlay.set_scale(scale_percent / 100.0)

    def _on_scale_spin_changed(self, value: float) -> None:
        """Handle scale spinbox changes (0.1-50.0)."""
        slider_value = int(value * 10)
        self.scale_slider.blockSignals(True)
        self.scale_slider.setValue(slider_value)
        self.scale_slider.blockSignals(False)
        self._overlay.set_scale(value / 100.0)

    def _on_opacity_changed(self, value: int) -> None:
        """Handle opacity slider changes."""
        opacity = value / 100.0
        self.opacity_label.setText(f"{value}%")
        self._overlay.set_opacity(opacity)

    def _on_visibility_changed(self, visible: bool) -> None:
        """Handle visibility checkbox changes."""
        self._overlay.set_visible(visible)

    def _on_resample_changed(self, index: int) -> None:
        """Handle resampling mode combo box changes."""
        mode = self.resample_combo.itemData(index)
        if mode is not None:
            self._overlay.set_resampling_mode(mode)

    def _update_position_spinboxes(self, x: int, y: int) -> None:
        """Update spinboxes from overlay state."""
        self.x_spin.blockSignals(True)
        self.y_spin.blockSignals(True)
        self.x_spin.setValue(x)
        self.y_spin.setValue(y)
        self.x_spin.blockSignals(False)
        self.y_spin.blockSignals(False)

    def _update_opacity_slider(self, opacity: float) -> None:
        """Update opacity slider from overlay state."""
        value = int(opacity * 100)
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(value)
        self.opacity_slider.blockSignals(False)
        self.opacity_label.setText(f"{value}%")

    def _update_scale_controls(self, scale: float) -> None:
        """Update scale controls from overlay state."""
        percent = scale * 100.0
        slider_value = int(percent * 10)

        self.scale_slider.blockSignals(True)
        self.scale_slider.setValue(slider_value)
        self.scale_slider.blockSignals(False)

        self.scale_spin.blockSignals(True)
        self.scale_spin.setValue(percent)
        self.scale_spin.blockSignals(False)

    def _update_visibility_checkbox(self, visible: bool) -> None:
        """Update checkbox from overlay state."""
        self.visible_check.blockSignals(True)
        self.visible_check.setChecked(visible)
        self.visible_check.blockSignals(False)

    def _update_resample_combo(self, mode_value: int) -> None:
        """Update combo box from overlay state."""
        self.resample_combo.blockSignals(True)
        # Find the index for this mode value
        for i in range(self.resample_combo.count()):
            item_data = self.resample_combo.itemData(i)
            if item_data is not None and item_data.value == mode_value:
                self.resample_combo.setCurrentIndex(i)
                break
        self.resample_combo.blockSignals(False)

    def _update_enabled_state(self) -> None:
        """Update enabled state based on whether overlay has image."""
        has_image = self._overlay.has_image()
        self.clear_btn.setEnabled(has_image)
        self.preview_mapping_btn.setEnabled(has_image)
        self.extract_palette_btn.setEnabled(has_image)
        self.snap_to_grid_btn.setEnabled(has_image)
        self.x_spin.setEnabled(has_image)
        self.y_spin.setEnabled(has_image)
        self.scale_slider.setEnabled(has_image)
        self.scale_spin.setEnabled(has_image)
        self.opacity_slider.setEnabled(has_image)
        self.visible_check.setEnabled(has_image)
        self.resample_combo.setEnabled(has_image)
