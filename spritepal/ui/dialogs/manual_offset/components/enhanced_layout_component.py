"""
Enhanced Layout Component for Composed Implementation

Provides superior visual design with modern spacing, proportions, and responsive behavior.
This component demonstrates the visual improvements possible with the new architecture.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ui.dialogs.manual_offset.core.manual_offset_dialog_core import (
        ManualOffsetDialogCore,
    )

from ui.styles.theme import COLORS
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Enhanced modern layout constants
class ModernLayoutConstants:
    """Modern spacing and sizing constants for superior visual design."""

    # Spacing - more generous and visually pleasing
    PRIMARY_SPACING = 12        # Main element spacing
    SECONDARY_SPACING = 8       # Related element spacing
    COMPACT_SPACING = 6         # Tight spacing for grouped items
    MINIMAL_SPACING = 4         # Very tight spacing

    # Margins - breathing room for content
    DIALOG_MARGINS = 16         # Outer dialog margins
    PANEL_MARGINS = 12          # Panel content margins
    GROUP_MARGINS = 8           # Group box margins
    COMPACT_MARGINS = 6         # Tight margins

    # Sizes - optimized for modern displays
    BUTTON_HEIGHT = 36          # More touch-friendly
    INPUT_HEIGHT = 32           # Comfortable input height
    SPLITTER_HANDLE_WIDTH = 12  # More prominent splitter
    HEADER_HEIGHT = 40          # Section headers

    # Panel proportions - more balanced than 1:3
    LEFT_PANEL_RATIO = 0.35     # 35% for controls
    RIGHT_PANEL_RATIO = 0.65    # 65% for preview

    # Minimum sizes - responsive design
    MIN_LEFT_PANEL_WIDTH = 380   # Accommodate modern form layouts
    MAX_LEFT_PANEL_WIDTH = 600   # Prevent overly wide forms
    MIN_RIGHT_PANEL_WIDTH = 450  # Ensure preview visibility
    MIN_DIALOG_WIDTH = 900       # Increased for better proportions
    MIN_DIALOG_HEIGHT = 600      # More comfortable height

    # Tab-specific ratios - refined for better balance
    TAB_RATIOS = {
        0: 0.32,  # Browse tab - streamlined
        1: 0.35,  # Smart tab - normal
        2: 0.30,  # History tab - list focused
        3: 0.38,  # Gallery tab - needs more control space
    }

class EnhancedLayoutComponent:
    """
    Enhanced layout manager with modern visual design principles.

    Provides superior spacing, proportions, and visual hierarchy
    compared to the legacy implementation.
    """

    def __init__(self, dialog: ManualOffsetDialogCore) -> None:
        """Initialize enhanced layout manager."""
        self.dialog = dialog
        self.constants = ModernLayoutConstants()
        self._resize_timer: QTimer | None = None
        self._setup_resize_timer()

    def _setup_resize_timer(self) -> None:
        """Set up debounced resize handling."""
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._apply_responsive_layout)

    def create_enhanced_layout(self) -> None:
        """Apply enhanced layout to the entire dialog."""
        logger.debug("Applying enhanced modern layout")

        # Update dialog sizing
        self._apply_enhanced_sizing()

        # Configure splitter with better proportions (if available)
        if hasattr(self.dialog, 'main_splitter'):
            if self.dialog.main_splitter:
                self._configure_enhanced_splitter(self.dialog.main_splitter)
            else:
                logger.debug("Main splitter not yet available, layout will be applied later")

    def _apply_enhanced_sizing(self) -> None:
        """Apply enhanced sizing constraints to dialog."""
        # Better default size for modern displays
        self.dialog.resize(1100, 700)  # Improved from 1000x650

        # Enhanced minimum size
        self.dialog.setMinimumSize(
            self.constants.MIN_DIALOG_WIDTH,
            self.constants.MIN_DIALOG_HEIGHT
        )

    def _configure_enhanced_splitter(self, splitter: QSplitter) -> None:
        """Configure splitter with modern visual design."""
        # Enhanced handle width for better usability
        splitter.setHandleWidth(self.constants.SPLITTER_HANDLE_WIDTH)

        # Better default proportions (35:65 instead of 25:75)
        total_width = self.dialog.width()
        left_width = int(total_width * self.constants.LEFT_PANEL_RATIO)
        right_width = total_width - left_width

        splitter.setSizes([left_width, right_width])

        # Set size constraints for panels
        if splitter.count() >= 2:
            # Left panel constraints
            left_widget = splitter.widget(0)
            if left_widget:
                left_widget.setMinimumWidth(self.constants.MIN_LEFT_PANEL_WIDTH)
                left_widget.setMaximumWidth(self.constants.MAX_LEFT_PANEL_WIDTH)

            # Right panel constraints
            right_widget = splitter.widget(1)
            if right_widget:
                right_widget.setMinimumWidth(self.constants.MIN_RIGHT_PANEL_WIDTH)

    def enhance_panel_layout(self, panel: QWidget, panel_type: str = "generic") -> None:
        """Apply enhanced layout to a panel."""
        layout = panel.layout()
        if not layout:
            logger.debug(f"No layout found for panel type: {panel_type}")
            return

        # Apply enhanced spacing and margins
        if panel_type == "left":
            # Left panel - form-focused layout
            layout.setSpacing(self.constants.SECONDARY_SPACING)
            layout.setContentsMargins(
                self.constants.PANEL_MARGINS,
                self.constants.PANEL_MARGINS,
                self.constants.PANEL_MARGINS,
                self.constants.PANEL_MARGINS
            )
        elif panel_type == "right":
            # Right panel - preview-focused layout
            layout.setSpacing(self.constants.PRIMARY_SPACING)
            layout.setContentsMargins(
                self.constants.PANEL_MARGINS,
                self.constants.PANEL_MARGINS,
                self.constants.PANEL_MARGINS,
                self.constants.PANEL_MARGINS
            )
        else:
            # Generic enhanced spacing
            layout.setSpacing(self.constants.SECONDARY_SPACING)
            layout.setContentsMargins(
                self.constants.PANEL_MARGINS // 2,
                self.constants.PANEL_MARGINS // 2,
                self.constants.PANEL_MARGINS // 2,
                self.constants.PANEL_MARGINS // 2
            )

    def create_section_header(self, title: str, subtitle: str = "") -> QWidget:
        """Create a visually enhanced section header."""
        header_widget = QFrame()
        header_widget.setFrameStyle(QFrame.Shape.NoFrame)
        header_widget.setMaximumHeight(self.constants.HEADER_HEIGHT)

        layout = QVBoxLayout(header_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Main title
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setWeight(QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {COLORS['highlight']}; margin-bottom: 2px;")
        layout.addWidget(title_label)

        # Subtitle if provided
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_font = QFont()
            subtitle_font.setPointSize(9)
            subtitle_label.setFont(subtitle_font)
            subtitle_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-style: italic;")
            layout.addWidget(subtitle_label)

        # Add bottom spacing
        layout.addItem(QSpacerItem(
            0, self.constants.MINIMAL_SPACING,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed
        ))

        return header_widget

    def add_visual_separator(self, layout: QVBoxLayout) -> None:
        """Add a subtle visual separator between sections."""
        separator = QFrame()
        separator.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)
        separator.setMaximumHeight(1)
        separator.setStyleSheet(f"""
            QFrame {{
                color: {COLORS["border"]};
                background-color: {COLORS["border"]};
                border: none;
            }}
        """)
        layout.addWidget(separator)

        # Add spacing after separator
        layout.addItem(QSpacerItem(
            0, self.constants.SECONDARY_SPACING,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed
        ))

    def update_for_tab(self, tab_index: int) -> None:
        """Update layout for specific tab with enhanced proportions."""
        if not hasattr(self.dialog, 'main_splitter') or not self.dialog.main_splitter:
            return

        # Use enhanced tab ratios
        ratio = self.constants.TAB_RATIOS.get(tab_index, self.constants.LEFT_PANEL_RATIO)

        # Apply with smooth animation-like effect
        if self._resize_timer:
            self._resize_timer.start(150)  # Debounced resize

        # Calculate new sizes
        total_width = self.dialog.width()
        left_width = int(total_width * ratio)
        right_width = total_width - left_width

        # Apply new proportions
        self.dialog.main_splitter.setSizes([left_width, right_width])

    def _apply_responsive_layout(self) -> None:
        """Apply responsive layout adjustments."""
        if not hasattr(self.dialog, 'main_splitter'):
            return

        dialog_width = self.dialog.width()

        # Adjust layout based on dialog width
        if dialog_width < 1000:
            # Compact layout for smaller windows
            self._apply_compact_layout()
        elif dialog_width > 1400:
            # Spacious layout for larger windows
            self._apply_spacious_layout()
        else:
            # Standard layout
            self._apply_standard_layout()

    def _apply_compact_layout(self) -> None:
        """Apply compact layout for smaller windows."""
        if self.dialog.main_splitter:
            # More space for preview in compact mode
            total_width = self.dialog.width()
            left_width = max(self.constants.MIN_LEFT_PANEL_WIDTH, int(total_width * 0.30))
            right_width = total_width - left_width
            self.dialog.main_splitter.setSizes([left_width, right_width])

    def _apply_spacious_layout(self) -> None:
        """Apply spacious layout for larger windows."""
        if self.dialog.main_splitter:
            # Can afford more space for controls
            total_width = self.dialog.width()
            left_width = min(self.constants.MAX_LEFT_PANEL_WIDTH, int(total_width * 0.40))
            right_width = total_width - left_width
            self.dialog.main_splitter.setSizes([left_width, right_width])

    def _apply_standard_layout(self) -> None:
        """Apply standard layout proportions."""
        if self.dialog.main_splitter:
            self._configure_enhanced_splitter(self.dialog.main_splitter)

    def handle_dialog_resize(self, width: int, height: int) -> None:
        """Handle dialog resize with debouncing."""
        if self._resize_timer:
            self._resize_timer.start(100)  # Debounce resize events

    def cleanup(self) -> None:
        """Clean up layout manager resources."""
        if self._resize_timer:
            self._resize_timer.stop()
            self._resize_timer.deleteLater()
            self._resize_timer = None
        logger.debug("Enhanced layout component cleaned up")
