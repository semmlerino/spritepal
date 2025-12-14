"""
Smart tab widget for manual offset dialog.

Provides region-based navigation and smart mode controls for efficient
sprite exploration.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import (
    COMPACT_BUTTON_HEIGHT,
    GROUP_PADDING,
    SPACING_SMALL,
    SPACING_TINY,
)
from ui.styles.theme import COLORS
from utils.sprite_regions import SpriteRegion


class SimpleSmartTab(QWidget):
    """
    Smart tab with region-based navigation for efficient sprite exploration.

    Signals:
        smart_mode_changed: Emitted when smart mode is toggled
        region_changed: Emitted when selected region changes
        offset_requested: Request to navigate to specific offset
    """

    smart_mode_changed = Signal(bool)
    region_changed = Signal(int)
    offset_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        Initialize the smart tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # State
        self._sprite_regions: list[tuple[int, float]] = []
        self._current_region_index: int = 0

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up space-efficient smart tab UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING_TINY)
        layout.setContentsMargins(GROUP_PADDING, GROUP_PADDING, GROUP_PADDING, GROUP_PADDING)

        # Unified smart controls frame
        smart_frame = QFrame()
        smart_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        smart_layout = QVBoxLayout(smart_frame)
        smart_layout.setSpacing(SPACING_TINY)
        smart_layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)

        # Single title for the entire smart tab
        title = self._create_section_title("Smart Navigation")
        smart_layout.addWidget(title)

        # Smart mode checkbox
        self.smart_checkbox = QCheckBox("Enable Smart Mode")
        self.smart_checkbox.setToolTip("Navigate through detected sprite regions")
        self.smart_checkbox.toggled.connect(self.smart_mode_changed.emit)
        smart_layout.addWidget(self.smart_checkbox)

        # Compact region selection row
        region_row = QHBoxLayout()
        region_row.setSpacing(6)

        region_row.addWidget(QLabel("Region:"))

        self.region_combo = QComboBox()
        self.region_combo.currentIndexChanged.connect(self._on_region_changed)
        region_row.addWidget(self.region_combo)

        # Compact go button
        go_region_button = QPushButton("Go")
        go_region_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        go_region_button.setFixedHeight(COMPACT_BUTTON_HEIGHT)
        go_region_button.clicked.connect(self._go_to_current_region)
        region_row.addWidget(go_region_button)

        smart_layout.addLayout(region_row)
        layout.addWidget(smart_frame)
        layout.addStretch()  # Push content to top

    def _on_region_changed(self, index: int) -> None:
        """
        Handle region selection change.

        Args:
            index: Selected region index
        """
        self._current_region_index = index
        self.region_changed.emit(index)

    def _go_to_current_region(self) -> None:
        """Go to the currently selected region."""
        if 0 <= self._current_region_index < len(self._sprite_regions):
            region = self._sprite_regions[self._current_region_index]
            if hasattr(region, "offset"):
                self.offset_requested.emit(region.offset)  # type: ignore[attr-defined]
            elif len(region) >= 2:
                self.offset_requested.emit(region[0])  # Assume (offset, quality) tuple

    def set_sprite_regions(self, sprites: list[tuple[int, float]]) -> None:
        """
        Set sprite regions from sprite data.

        Args:
            sprites: List of (offset, quality) tuples
        """
        self._sprite_regions = sprites

        # Update combo box
        if self.region_combo:
            self.region_combo.clear()
        for i, (offset, quality) in enumerate(sprites):
            if self.region_combo:
                self.region_combo.addItem(f"Region {i+1}: 0x{offset:06X} (Q: {quality:.2f})")

    def get_sprite_regions(self) -> list[SpriteRegion]:
        """
        Get sprite regions in expected format.

        Returns:
            List of SpriteRegion objects
        """
        regions = []
        for i, (offset, quality) in enumerate(self._sprite_regions):
            # Create a SpriteRegion with proper constructor parameters
            region = SpriteRegion(
                region_id=i,
                start_offset=offset,
                end_offset=offset + 0x1000,  # Assume 4KB regions
                sprite_offsets=[offset],
                sprite_qualities=[quality],
                average_quality=quality,
                sprite_count=1,
                size_bytes=0x1000,
                density=quality,
                custom_name=f"Region {i+1}"
            )
            regions.append(region)
        return regions

    def is_smart_mode_enabled(self) -> bool:
        """
        Check if smart mode is enabled.

        Returns:
            True if smart mode is enabled
        """
        return self.smart_checkbox.isChecked()

    def _create_section_title(self, text: str) -> QLabel:
        """
        Create a styled section title label.

        Args:
            text: Title text

        Returns:
            Styled label widget
        """
        title = QLabel(text)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {COLORS['highlight']}; padding: 2px 4px; border-radius: 3px;")
        return title

    def get_current_region_index(self) -> int:
        """
        Get current region index.

        Returns:
            Currently selected region index
        """
        return self._current_region_index
