"""Mode selector widget for ROM extraction"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

# UI Spacing Constants (imported from centralized module)
from ui.common.spacing_constants import (
    EXTRACTION_COMBO_MIN_WIDTH as COMBO_MIN_WIDTH,
    SPACING_COMPACT_MEDIUM as SPACING_MEDIUM,
)

from .base_widget import BaseExtractionWidget


class ModeSelectorWidget(BaseExtractionWidget):
    """Widget for selecting extraction mode (preset vs manual)"""

    # Signals
    mode_changed = Signal(int)  # Emitted when mode changes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Initialize the user interface"""
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(SPACING_MEDIUM)
        mode_layout.setContentsMargins(0, 0, 0, 0)  # Group box CSS provides padding

        mode_label = self._create_control_label("Mode:")
        mode_layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.setMinimumWidth(COMBO_MIN_WIDTH)
        self.mode_combo.addItems(["Preset Sprites", "Manual Offset Exploration"])
        if self.mode_combo:
            self.mode_combo.setCurrentIndex(1)  # Default to manual offset mode
        self.mode_combo.currentIndexChanged.connect(self.mode_changed.emit)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()

        self._setup_widget_with_group("Extraction Mode", mode_layout)

    def get_current_mode(self) -> int:
        """Get the current mode index (0=preset, 1=manual)"""
        return self.mode_combo.currentIndex()

    def is_manual_mode(self) -> bool:
        """Check if manual mode is selected"""
        return self.mode_combo.currentIndex() == 1
