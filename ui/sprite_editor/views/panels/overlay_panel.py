"""Panel for overlay import and positioning controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class OverlayPanel(QGroupBox):
    """Panel for overlay import and positioning controls.

    Provides controls for:
    - Importing an overlay image
    - Adjusting opacity of base sprite and overlay independently
    - Displaying and editing overlay position
    - Applying or canceling the overlay
    """

    importRequested = Signal()
    applyRequested = Signal()
    cancelRequested = Signal()
    baseOpacityChanged = Signal(int)
    overlayOpacityChanged = Signal(int)
    overlayScaleChanged = Signal(float)
    positionChanged = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("OVERLAY", parent)
        self._setup_ui()
        # Start with controls disabled until overlay is imported
        self._set_controls_enabled(False)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Import button - always enabled
        self._import_btn = QPushButton("Import Overlay...")
        self._import_btn.setToolTip("Import an image to overlay on the sprite")
        self._import_btn.clicked.connect(self.importRequested.emit)
        layout.addWidget(self._import_btn)

        # Base sprite opacity
        base_layout = QHBoxLayout()
        base_layout.addWidget(QLabel("Sprite:"))
        self._base_slider = QSlider(Qt.Orientation.Horizontal)
        self._base_slider.setRange(0, 100)
        self._base_slider.setValue(100)
        self._base_slider.setToolTip("Base sprite opacity")
        self._base_slider.valueChanged.connect(self._on_base_opacity_changed)
        base_layout.addWidget(self._base_slider)
        self._base_label = QLabel("100%")
        self._base_label.setFixedWidth(40)
        base_layout.addWidget(self._base_label)
        layout.addLayout(base_layout)

        # Overlay opacity
        overlay_layout = QHBoxLayout()
        overlay_layout.addWidget(QLabel("Overlay:"))
        self._overlay_slider = QSlider(Qt.Orientation.Horizontal)
        self._overlay_slider.setRange(0, 100)
        self._overlay_slider.setValue(80)
        self._overlay_slider.setToolTip("Overlay image opacity")
        self._overlay_slider.valueChanged.connect(self._on_overlay_opacity_changed)
        overlay_layout.addWidget(self._overlay_slider)
        self._overlay_label = QLabel("80%")
        self._overlay_label.setFixedWidth(40)
        overlay_layout.addWidget(self._overlay_label)
        layout.addLayout(overlay_layout)

        # Overlay scale
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        self._scale_slider = QSlider(Qt.Orientation.Horizontal)
        self._scale_slider.setRange(1, 300)  # 1% to 300%
        self._scale_slider.setValue(100)
        self._scale_slider.setToolTip("Overlay image scale")
        self._scale_slider.valueChanged.connect(self._on_overlay_scale_changed)
        scale_layout.addWidget(self._scale_slider)
        self._scale_label = QLabel("100%")
        self._scale_label.setFixedWidth(40)
        scale_layout.addWidget(self._scale_label)
        layout.addLayout(scale_layout)

        # Position display
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("Position:"))
        self._pos_x = QSpinBox()
        self._pos_x.setRange(-9999, 9999)
        self._pos_x.setPrefix("X: ")
        self._pos_x.setToolTip("Overlay X position in pixels")
        self._pos_x.valueChanged.connect(self._on_position_changed)
        pos_layout.addWidget(self._pos_x)
        self._pos_y = QSpinBox()
        self._pos_y.setRange(-9999, 9999)
        self._pos_y.setPrefix("Y: ")
        self._pos_y.setToolTip("Overlay Y position in pixels")
        self._pos_y.valueChanged.connect(self._on_position_changed)
        pos_layout.addWidget(self._pos_y)
        layout.addLayout(pos_layout)

        # Help text
        help_label = QLabel("Drag overlay or use arrow keys to position.\nShift+arrows for 8px nudge.")
        help_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(help_label)

        # Apply/Cancel buttons
        btn_layout = QHBoxLayout()
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setToolTip("Merge overlay onto sprite")
        self._apply_btn.clicked.connect(self.applyRequested.emit)
        btn_layout.addWidget(self._apply_btn)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setToolTip("Discard overlay")
        self._cancel_btn.clicked.connect(self.cancelRequested.emit)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def _on_base_opacity_changed(self, value: int) -> None:
        self._base_label.setText(f"{value}%")
        self.baseOpacityChanged.emit(value)

    def _on_overlay_opacity_changed(self, value: int) -> None:
        self._overlay_label.setText(f"{value}%")
        self.overlayOpacityChanged.emit(value)

    def _on_overlay_scale_changed(self, value: int) -> None:
        scale = value / 100.0
        self._scale_label.setText(f"{value}%")
        self.overlayScaleChanged.emit(scale)

    def _on_position_changed(self) -> None:
        self.positionChanged.emit(self._pos_x.value(), self._pos_y.value())

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable controls that require an overlay."""
        self._base_slider.setEnabled(enabled)
        self._overlay_slider.setEnabled(enabled)
        self._scale_slider.setEnabled(enabled)
        self._pos_x.setEnabled(enabled)
        self._pos_y.setEnabled(enabled)
        self._apply_btn.setEnabled(enabled)
        self._cancel_btn.setEnabled(enabled)

    def set_overlay_active(self, active: bool) -> None:
        """Enable/disable controls when overlay is loaded."""
        self._set_controls_enabled(active)

    def update_position(self, x: int, y: int) -> None:
        """Update position display from canvas."""
        self._pos_x.blockSignals(True)
        self._pos_y.blockSignals(True)
        self._pos_x.setValue(x)
        self._pos_y.setValue(y)
        self._pos_x.blockSignals(False)
        self._pos_y.blockSignals(False)

    def reset(self) -> None:
        """Reset panel to initial state."""
        self._base_slider.setValue(100)
        self._overlay_slider.setValue(80)
        self._scale_slider.setValue(100)
        self._pos_x.setValue(0)
        self._pos_y.setValue(0)
        self._set_controls_enabled(False)
