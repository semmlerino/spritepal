#!/usr/bin/env python3
"""
Options panel for the pixel editor.
Contains grid, color mode, and zoom controls.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import GROUP_PADDING, SPACING_MEDIUM, SPACING_SMALL


class OptionsPanel(QWidget):
    """Panel for editor options and zoom controls."""

    # Signals
    gridToggled = Signal(bool)
    paletteToggled = Signal(bool)
    zoomChanged = Signal(int)
    zoomToFit = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the options panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(GROUP_PADDING, GROUP_PADDING, GROUP_PADDING, GROUP_PADDING)
        layout.setSpacing(SPACING_MEDIUM)

        # Options group box
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()
        options_layout.setSpacing(SPACING_SMALL)

        # Grid checkbox
        self.grid_checkbox = QCheckBox("Show Grid")
        self.grid_checkbox.setChecked(False)
        self.grid_checkbox.toggled.connect(self.gridToggled.emit)

        # Apply palette checkbox
        self.apply_palette_checkbox = QCheckBox("Apply Palette")
        self.apply_palette_checkbox.setChecked(True)
        self.apply_palette_checkbox.setToolTip(
            "When checked, shows actual palette colors. "
            "When unchecked, shows palette indices (0-15) as grayscale values."
        )
        self.apply_palette_checkbox.toggled.connect(self.paletteToggled.emit)

        # Zoom controls group
        zoom_group = QGroupBox("Zoom Controls")
        zoom_group_layout = QVBoxLayout()
        zoom_group_layout.setSpacing(SPACING_SMALL)

        # Zoom slider with label
        zoom_slider_layout = QHBoxLayout()
        zoom_slider_layout.setSpacing(SPACING_SMALL)
        zoom_slider_layout.addWidget(QLabel("Zoom:"))

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 64)
        self.zoom_slider.setValue(4)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)

        self.zoom_label = QLabel("4x")
        zoom_slider_layout.addWidget(self.zoom_slider)
        zoom_slider_layout.addWidget(self.zoom_label)

        # Quick zoom buttons
        zoom_buttons_layout = QHBoxLayout()
        zoom_buttons_layout.setSpacing(2)  # Tight spacing for button row
        self.zoom_buttons: list[tuple[QPushButton, int]] = []

        zoom_presets = [("1x", 1), ("2x", 2), ("4x", 4), ("8x", 8), ("16x", 16)]
        for label, value in zoom_presets:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, v=value: self.set_zoom(v))
            # Removed fixed width to prevent clipping
            zoom_buttons_layout.addWidget(btn)
            self.zoom_buttons.append((btn, value))

        # Fit to window button
        self.fit_btn = QPushButton("Fit")
        self.fit_btn.clicked.connect(self.zoomToFit.emit)
        self.fit_btn.setToolTip("Fit image to visible area")
        zoom_buttons_layout.addWidget(self.fit_btn)

        zoom_group_layout.addLayout(zoom_slider_layout)
        zoom_group_layout.addLayout(zoom_buttons_layout)
        zoom_group.setLayout(zoom_group_layout)

        # Add all to options layout
        options_layout.addWidget(self.grid_checkbox)
        options_layout.addWidget(self.apply_palette_checkbox)
        options_layout.addWidget(zoom_group)
        options_group.setLayout(options_layout)

        # Add to main layout
        layout.addWidget(options_group)

    def _on_zoom_changed(self, value: int) -> None:
        """Handle zoom slider change."""
        self.zoom_label.setText(f"{value}x")
        self.zoomChanged.emit(value)

    def set_zoom(self, value: int) -> None:
        """Set zoom level programmatically."""
        self.zoom_slider.setValue(value)

    def get_zoom(self) -> int:
        """Get current zoom level."""
        return self.zoom_slider.value()

    def is_grid_visible(self) -> bool:
        """Check if grid is enabled."""
        return self.grid_checkbox.isChecked()

    def is_palette_applied(self) -> bool:
        """Check if palette colors should be shown."""
        return self.apply_palette_checkbox.isChecked()
