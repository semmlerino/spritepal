"""
Reusable search filter controls for sprite searching.

Consolidates filter controls that were duplicated across search tabs.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.common.collapsible_group_box import CollapsibleGroupBox
from utils.constants import MAX_SPRITE_SIZE, MIN_SPRITE_SIZE


@dataclass
class SearchFilter:
    """Container for search filter settings."""

    min_size: int
    max_size: int
    min_tiles: int
    max_tiles: int
    alignment: int
    include_compressed: bool
    include_uncompressed: bool
    confidence_threshold: float = 0.5  # For visual similarity searches

    @classmethod
    def default(cls) -> SearchFilter:
        """Create default filter settings."""
        return cls(
            min_size=MIN_SPRITE_SIZE,
            max_size=MAX_SPRITE_SIZE,
            min_tiles=1,
            max_tiles=1024,
            alignment=1,  # Any alignment
            include_compressed=True,
            include_uncompressed=False,
            confidence_threshold=0.5,
        )


# Alignment values mapping
ALIGNMENT_VALUES = {
    "Any": 1,
    "0x10": 0x10,
    "0x100": 0x100,
    "0x1000": 0x1000,
    "0x8000": 0x8000,
}


class SearchFiltersWidget(QWidget):
    """
    Reusable search filter controls for sprite searching.

    Consolidates:
    - Size range (min/max bytes)
    - Tile count range
    - Compression type (compressed/uncompressed)
    - Alignment requirements

    Args:
        parent: Parent widget
        collapsible: If True, wrap in CollapsibleGroupBox
        expanded: Initial expanded state (only used if collapsible=True)
        title: Group box title

    Signals:
        filters_changed: Emitted when any filter value changes
    """

    filters_changed = Signal(SearchFilter)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        collapsible: bool = False,
        expanded: bool = True,
        title: str = "Filters",
    ):
        super().__init__(parent)
        self._collapsible = collapsible
        self._expanded = expanded
        self._title = title

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the filter controls UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create the filter controls
        filter_content = self._create_filter_controls()

        if self._collapsible:
            # Wrap in collapsible group box
            group = CollapsibleGroupBox(self._title, collapsed=not self._expanded)
            group_layout = QVBoxLayout()
            group_layout.addWidget(filter_content)
            group.setContentLayout(group_layout)
            main_layout.addWidget(group)
        else:
            # Use regular group box
            group = QGroupBox(self._title)
            group_layout = QVBoxLayout(group)
            group_layout.addWidget(filter_content)
            main_layout.addWidget(group)

    def _create_filter_controls(self) -> QWidget:
        """Create the actual filter control widgets."""
        container = QWidget()
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Size filter
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(0, MAX_SPRITE_SIZE)
        self.min_size_spin.setValue(MIN_SPRITE_SIZE)
        self.min_size_spin.setSingleStep(0x100)
        self.min_size_spin.setToolTip("Minimum sprite data size in bytes")

        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(0, MAX_SPRITE_SIZE)
        self.max_size_spin.setValue(MAX_SPRITE_SIZE)
        self.max_size_spin.setSingleStep(0x100)
        self.max_size_spin.setToolTip("Maximum sprite data size in bytes")

        size_label = QLabel("Size Range:")
        size_label.setToolTip(
            "Filter by sprite data size. 16x16 sprites are typically 128-512 bytes."
        )
        layout.addWidget(size_label, 0, 0)
        layout.addWidget(self.min_size_spin, 0, 1)
        layout.addWidget(QLabel("-"), 0, 2)
        layout.addWidget(self.max_size_spin, 0, 3)

        # Tile count filter
        self.min_tiles_spin = QSpinBox()
        self.min_tiles_spin.setRange(1, 1024)
        self.min_tiles_spin.setValue(1)
        self.min_tiles_spin.setToolTip("Minimum number of 8x8 tiles")

        self.max_tiles_spin = QSpinBox()
        self.max_tiles_spin.setRange(1, 1024)
        self.max_tiles_spin.setValue(1024)
        self.max_tiles_spin.setToolTip("Maximum number of 8x8 tiles")

        tile_label = QLabel("Tile Count:")
        tile_label.setToolTip(
            "SNES sprites are made of 8x8 tiles. A 16x16 sprite uses 4 tiles."
        )
        layout.addWidget(tile_label, 1, 0)
        layout.addWidget(self.min_tiles_spin, 1, 1)
        layout.addWidget(QLabel("-"), 1, 2)
        layout.addWidget(self.max_tiles_spin, 1, 3)

        # Compression filter
        self.compressed_check = QCheckBox("Include Compressed")
        self.compressed_check.setChecked(True)
        self.compressed_check.setToolTip("Include HAL-compressed sprite data")

        self.uncompressed_check = QCheckBox("Include Uncompressed")
        self.uncompressed_check.setChecked(False)
        self.uncompressed_check.setToolTip("Include raw uncompressed sprite data")

        layout.addWidget(self.compressed_check, 2, 0, 1, 2)
        layout.addWidget(self.uncompressed_check, 2, 2, 1, 2)

        # Alignment filter
        self.alignment_combo = QComboBox()
        self.alignment_combo.addItems(list(ALIGNMENT_VALUES.keys()))
        self.alignment_combo.setToolTip(
            "Required offset alignment. 0x100 means offset ends in 00."
        )

        alignment_label = QLabel("Alignment:")
        alignment_label.setToolTip(
            "Some ROMs store sprites at aligned addresses for faster access."
        )
        layout.addWidget(alignment_label, 3, 0)
        layout.addWidget(self.alignment_combo, 3, 1, 1, 3)

        return container

    def _connect_signals(self) -> None:
        """Connect control signals to emit filters_changed."""
        self.min_size_spin.valueChanged.connect(self._on_filter_changed)
        self.max_size_spin.valueChanged.connect(self._on_filter_changed)
        self.min_tiles_spin.valueChanged.connect(self._on_filter_changed)
        self.max_tiles_spin.valueChanged.connect(self._on_filter_changed)
        self.compressed_check.stateChanged.connect(self._on_filter_changed)
        self.uncompressed_check.stateChanged.connect(self._on_filter_changed)
        self.alignment_combo.currentIndexChanged.connect(self._on_filter_changed)

    def _on_filter_changed(self) -> None:
        """Handle any filter value change."""
        self.filters_changed.emit(self.get_filters())

    def get_filters(self) -> SearchFilter:
        """Get current filter settings as a SearchFilter dataclass."""
        alignment_text = self.alignment_combo.currentText()
        alignment_value = ALIGNMENT_VALUES.get(alignment_text, 1)

        return SearchFilter(
            min_size=self.min_size_spin.value(),
            max_size=self.max_size_spin.value(),
            min_tiles=self.min_tiles_spin.value(),
            max_tiles=self.max_tiles_spin.value(),
            alignment=alignment_value,
            include_compressed=self.compressed_check.isChecked(),
            include_uncompressed=self.uncompressed_check.isChecked(),
        )

    def set_filters(self, filters: SearchFilter) -> None:
        """Set filter values from a SearchFilter dataclass."""
        # Block signals during update to avoid multiple emissions
        self.blockSignals(True)
        try:
            self.min_size_spin.setValue(filters.min_size)
            self.max_size_spin.setValue(filters.max_size)
            self.min_tiles_spin.setValue(filters.min_tiles)
            self.max_tiles_spin.setValue(filters.max_tiles)
            self.compressed_check.setChecked(filters.include_compressed)
            self.uncompressed_check.setChecked(filters.include_uncompressed)

            # Find alignment in combo box
            for text, value in ALIGNMENT_VALUES.items():
                if value == filters.alignment:
                    self.alignment_combo.setCurrentText(text)
                    break
        finally:
            self.blockSignals(False)

        # Emit once after all updates
        self.filters_changed.emit(filters)

    def reset_to_defaults(self) -> None:
        """Reset all filters to default values."""
        self.set_filters(SearchFilter.default())
