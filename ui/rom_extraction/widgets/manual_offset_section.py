"""Manual offset section widget for ROM extraction panel.

Provides a collapsible section with:
- Toggle button that expands to show manual offset controls
- Offset display label showing current manual offset
- Browse button to open manual offset dialog
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from ui.common.spacing_constants import BUTTON_HEIGHT
from ui.styles.components import get_manual_offset_button_style
from ui.styles.theme import COLORS


class ManualOffsetSection(QWidget):
    """Collapsible section for manual offset browsing.

    Contains a toggle button that expands to show the "Browse Sprites" button.
    Displays the current manual offset when set.
    """

    # Signals
    browse_clicked = Signal()  # Emitted when Browse button clicked
    toggled = Signal(bool)  # Emitted when section expanded/collapsed

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the UI components."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toggle button row
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)

        # Toggle button
        self._toggle_button = QToolButton()
        self._toggle_button.setText("Manual Offset Browser")
        self._toggle_button.setCheckable(True)
        self._toggle_button.setChecked(False)
        self._toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle_button.setToolTip(
            "Manually browse sprites at any ROM offset\ninstead of using the preset sprite list above"
        )
        self._toggle_button.setStyleSheet(
            "QToolButton { border: none; padding: 4px; font-weight: bold; }"
            "QToolButton:hover { background-color: rgba(255, 255, 255, 0.1); }"
            "QToolButton::right-arrow { subcontrol-position: center left; }"
            "QToolButton::down-arrow { subcontrol-position: center left; }"
        )
        self._toggle_button.toggled.connect(self._on_toggled)
        toggle_row.addWidget(self._toggle_button)

        # Offset display label
        self._offset_display = QLabel("")
        self._offset_display.setStyleSheet(f"color: {COLORS['highlight']}; font-weight: bold;")
        self._offset_display.setVisible(False)
        toggle_row.addWidget(self._offset_display)

        toggle_row.addStretch()

        main_layout.addLayout(toggle_row)

        # Browse button (hidden by default)
        self._browse_button = QPushButton("Browse Sprites (Ctrl+M)")
        self._browse_button.setMinimumHeight(BUTTON_HEIGHT)
        self._browse_button.setVisible(False)
        self._browse_button.setToolTip(
            "Open advanced sprite browser to explore ROM offsets manually\nKeyboard shortcut: Ctrl+M"
        )
        self._browse_button.setStyleSheet(get_manual_offset_button_style())
        self._browse_button.clicked.connect(self._on_browse_clicked)
        main_layout.addWidget(self._browse_button)

    def _on_toggled(self, expanded: bool) -> None:
        """Handle toggle button state change.

        Args:
            expanded: Whether section is expanded
        """
        # Update arrow direction
        arrow = Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        self._toggle_button.setArrowType(arrow)

        # Show/hide browse button
        self._browse_button.setVisible(expanded)

        # Emit signal
        self.toggled.emit(expanded)

    def _on_browse_clicked(self) -> None:
        """Handle browse button click."""
        self.browse_clicked.emit()

    def set_offset_display(self, text: str) -> None:
        """Set the offset display text (e.g., '0x200000').

        Args:
            text: The offset text to display
        """
        self._offset_display.setText(text)
        self._offset_display.setVisible(bool(text))

    def set_expanded(self, expanded: bool) -> None:
        """Programmatically expand/collapse the section.

        Args:
            expanded: Whether to expand the section
        """
        self._toggle_button.setChecked(expanded)

    def is_expanded(self) -> bool:
        """Check if section is currently expanded.

        Returns:
            True if section is expanded
        """
        return self._toggle_button.isChecked()

    def set_browse_enabled(self, enabled: bool) -> None:
        """Enable/disable the browse button.

        Args:
            enabled: Whether to enable the button
        """
        self._browse_button.setEnabled(enabled)

    def is_browse_visible(self) -> bool:
        """Check if browse button is currently visible.

        Returns:
            True if browse button is visible
        """
        return self._browse_button.isVisible()

    def is_browse_enabled(self) -> bool:
        """Check if browse button is currently enabled.

        Returns:
            True if browse button is enabled
        """
        return self._browse_button.isEnabled()

    def is_offset_display_visible(self) -> bool:
        """Check if offset display label is currently visible.

        Returns:
            True if offset display is visible
        """
        return self._offset_display.isVisible()

    def get_offset_display_text(self) -> str:
        """Get the current offset display text.

        Returns:
            Current offset text
        """
        return self._offset_display.text()

    def get_toggle_arrow_type(self) -> Qt.ArrowType:
        """Get the current arrow type of the toggle button.

        Returns:
            Current arrow type
        """
        return self._toggle_button.arrowType()
