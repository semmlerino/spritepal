"""
Region Jump Widget

Provides quick navigation to sprite-dense regions of the ROM.
Features:
- Dropdown list of detected regions
- Shows region statistics (sprite count, quality)
- Direct offset jumping
- Smart mode integration
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import SPACING_COMPACT_SMALL, SPACING_TINY
from ui.styles.theme import COLORS
from utils.logging_config import get_logger
from utils.sprite_regions import SpriteRegion

logger = get_logger(__name__)


class RegionJumpWidget(QWidget):
    """
    Widget for quick navigation between sprite regions.

    Features:
    - Region selection dropdown
    - Direct offset input
    - Region statistics display
    - Smart navigation mode
    """

    # Signals
    region_selected = Signal(int)  # Emitted when region is selected
    offset_requested = Signal(int)  # Emitted for direct offset jump

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        # State
        self.regions: list[SpriteRegion] = []
        self.current_region_index = -1
        self.smart_mode = False

        # UI Components
        self.region_combo: QComboBox | None = None
        self.go_button: QPushButton | None = None
        self.offset_spinbox: QSpinBox | None = None
        self.stats_label: QLabel | None = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Create the UI layout"""
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_COMPACT_SMALL)
        layout.setContentsMargins(0, 0, 0, 0)

        # Main container frame
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background: {COLORS["panel_background"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(SPACING_COMPACT_SMALL)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # Title row
        title_row = QHBoxLayout()
        title_label = QLabel("Quick Jump")
        title_font = QFont()
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_row.addWidget(title_label)

        title_row.addStretch()

        self.stats_label = QLabel("No regions")
        self.stats_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
        title_row.addWidget(self.stats_label)

        container_layout.addLayout(title_row)

        # Region selector row
        region_row = QHBoxLayout()
        region_row.setSpacing(SPACING_TINY)

        region_label = QLabel("Region:")
        region_label.setMinimumWidth(50)
        region_row.addWidget(region_label)

        self.region_combo = QComboBox()
        self.region_combo.setMinimumWidth(200)
        self.region_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        if self.region_combo:
            self.region_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                padding: 4px;
                border-radius: 3px;
            }}
            QComboBox:hover {{
                border-color: {COLORS["highlight"]};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {COLORS["text_muted"]};
                margin-right: 4px;
            }}
        """)
        region_row.addWidget(self.region_combo)

        self.go_button = QPushButton("Go")
        self.go_button.setMinimumWidth(40)
        if self.go_button:
            self.go_button.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS["highlight"]};
                color: {COLORS["text_primary"]};
                border: none;
                padding: 4px 8px;
                border-radius: 3px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {COLORS["highlight_hover"]};
            }}
            QPushButton:pressed {{
                background: {COLORS["browse_pressed"]};
            }}
            QPushButton:disabled {{
                background: {COLORS["border"]};
                color: {COLORS["text_muted"]};
            }}
        """)
        region_row.addWidget(self.go_button)

        container_layout.addLayout(region_row)

        # Direct offset row
        offset_row = QHBoxLayout()
        offset_row.setSpacing(SPACING_TINY)

        offset_label = QLabel("Offset:")
        offset_label.setMinimumWidth(50)
        offset_row.addWidget(offset_label)

        self.offset_spinbox = QSpinBox()
        self.offset_spinbox.setMinimum(0)
        self.offset_spinbox.setMaximum(0x400000)  # Default 4MB
        self.offset_spinbox.setSingleStep(0x1000)
        self.offset_spinbox.setDisplayIntegerBase(16)
        self.offset_spinbox.setPrefix("0x")
        if self.offset_spinbox:
            self.offset_spinbox.setStyleSheet(f"""
            QSpinBox {{
                background: {COLORS["input_background"]};
                border: 1px solid {COLORS["border"]};
                padding: 4px;
                border-radius: 3px;
                font-family: monospace;
            }}
            QSpinBox:hover {{
                border-color: {COLORS["highlight"]};
            }}
        """)
        offset_row.addWidget(self.offset_spinbox)

        go_offset_button = QPushButton("Jump")
        go_offset_button.setMinimumWidth(50)
        go_offset_button.clicked.connect(self._on_offset_jump)
        offset_row.addWidget(go_offset_button)

        container_layout.addLayout(offset_row)

        layout.addWidget(container)

    def _connect_signals(self):
        """Connect internal signals"""
        if self.region_combo is not None:
            self.region_combo.currentIndexChanged.connect(self._on_region_changed)
        if self.go_button is not None:
            self.go_button.clicked.connect(self._on_go_clicked)

    def _on_region_changed(self, index: int):
        """Handle region selection change"""
        if 0 <= index < len(self.regions):
            self.current_region_index = index
            self._update_stats_display()

            # Update offset spinbox to show region start
            region = self.regions[index]
            if self.offset_spinbox is not None:
                self.offset_spinbox.setValue(region.center_offset)

    def _on_go_clicked(self):
        """Handle go button click"""
        if 0 <= self.current_region_index < len(self.regions):
            self.region_selected.emit(self.current_region_index)

    def _on_offset_jump(self):
        """Handle direct offset jump"""
        if self.offset_spinbox is not None:
            offset = self.offset_spinbox
            self.offset_requested.emit(offset)

    def _update_stats_display(self):
        """Update region statistics display"""
        if self.stats_label is None:
            return

        if not self.regions:
            if self.stats_label:
                self.stats_label.setText("No regions")
            return

        if 0 <= self.current_region_index < len(self.regions):
            region = self.regions[self.current_region_index]
            quality_text = self._get_quality_text(region.average_quality)
            if self.stats_label:
                self.stats_label.setText(f"{region.sprite_count} sprites, {quality_text} quality")
        else:
            total_sprites = sum(r.sprite_count for r in self.regions)
            if self.stats_label:
                self.stats_label.setText(f"{len(self.regions)} regions, {total_sprites} sprites total")

    def _get_quality_text(self, quality: float) -> str:
        """Convert quality value to text description"""
        if quality > 0.8:
            return "high"
        if quality > 0.5:
            return "medium"
        return "low"

    def _format_region_name(self, region: SpriteRegion, index: int) -> str:
        """Format region name for display"""
        if region.custom_name:
            return region.custom_name

        # Build descriptive name
        name_parts = []

        # Region number
        name_parts.append(f"Region {index + 1}")

        # Add type if classified
        if hasattr(region, "region_type") and region.region_type != "unknown":
            name_parts.append(f"({region.region_type})")

        # Add sprite count
        name_parts.append(f"- {region.sprite_count} sprites")

        # Add quality indicator
        if region.average_quality > 0.8:
            name_parts.append("★★★")
        elif region.average_quality > 0.5:
            name_parts.append("★★")
        else:
            name_parts.append("★")

        return " ".join(name_parts)

    # Public API

    def set_regions(self, regions: list[SpriteRegion]):
        """Set available regions"""
        self.regions = regions
        self.current_region_index = -1

        # Update combo box
        if self.region_combo is not None:
            self.region_combo.clear()

            if not regions:
                if self.region_combo:
                    self.region_combo.addItem("No regions detected")
                if self.region_combo:
                    self.region_combo.setEnabled(False)
                if self.go_button is not None:
                    self.go_button.setEnabled(False)
            else:
                for i, region in enumerate(regions):
                    if self.region_combo:
                        self.region_combo.addItem(self._format_region_name(region, i))

                if self.region_combo:
                    self.region_combo.setEnabled(True)
                if self.go_button is not None:
                    self.go_button.setEnabled(True)

                # Select first region by default
                if regions and self.region_combo:
                    self.region_combo.setCurrentIndex(0)

        self._update_stats_display()

    def set_smart_mode(self, enabled: bool):
        """Enable/disable smart mode features"""
        self.smart_mode = enabled

        # In smart mode, emphasize region navigation
        if self.region_combo is not None:
            if enabled:
                if self.region_combo:
                    self.region_combo.setStyleSheet(f"""
                    QComboBox {{
                        background: {COLORS["cache_resuming_bg"]};
                        border: 2px solid {COLORS["success"]};
                        padding: 4px;
                        border-radius: 3px;
                    }}
                    QComboBox:hover {{
                        border-color: {COLORS["cache_resuming_text"]};
                    }}
                    QComboBox::drop-down {{
                        border: none;
                    }}
                    QComboBox::down-arrow {{
                        image: none;
                        border-left: 4px solid transparent;
                        border-right: 4px solid transparent;
                        border-top: 6px solid {COLORS["success"]};
                        margin-right: 4px;
                    }}
                """)
            # Reset to normal style
            elif self.region_combo:
                self.region_combo.setStyleSheet(f"""
                    QComboBox {{
                        background: {COLORS["input_background"]};
                        border: 1px solid {COLORS["border"]};
                        padding: 4px;
                        border-radius: 3px;
                    }}
                    QComboBox:hover {{
                        border-color: {COLORS["highlight"]};
                    }}
                    QComboBox::drop-down {{
                        border: none;
                    }}
                    QComboBox::down-arrow {{
                        image: none;
                        border-left: 4px solid transparent;
                        border-right: 4px solid transparent;
                        border-top: 6px solid {COLORS["text_muted"]};
                        margin-right: 4px;
                    }}
                """)

    def get_current_region_index(self) -> int:
        """Get currently selected region index"""
        return self.current_region_index

    def set_current_region(self, index: int):
        """Set current region programmatically"""
        if self.region_combo and 0 <= index < len(self.regions):
            self.region_combo.setCurrentIndex(index)

    def set_rom_size(self, size: int):
        """Update ROM size for offset limits"""
        if self.offset_spinbox is not None:
            self.offset_spinbox.setMaximum(size)

    def highlight_region_for_offset(self, offset: int):
        """Highlight the region containing the given offset"""
        for i, region in enumerate(self.regions):
            if region.start_offset <= offset <= region.end_offset:
                if self.region_combo is not None:
                    self.region_combo.setCurrentIndex(i)
                break
