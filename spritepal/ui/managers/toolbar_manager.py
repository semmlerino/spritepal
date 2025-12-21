"""
Toolbar and action button management for MainWindow
"""
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QMenu, QPushButton, QWidget

from ui.common.spacing_constants import BUTTON_HEIGHT, SPACING_MEDIUM
from ui.styles import (
    get_button_style,
    get_danger_action_button_style,
    get_extraction_checklist_style,
    get_ready_status_style,
)

# Primary action button is taller for visual hierarchy
PRIMARY_BUTTON_HEIGHT = BUTTON_HEIGHT + 8  # 36px for Extract button


class ToolbarActionsProtocol(Protocol):
    """Protocol defining the interface for toolbar actions"""

    def on_extract_clicked(self) -> None:
        """Handle extract button click"""
        ...

    def on_open_editor_clicked(self) -> None:
        """Handle open editor button click"""
        ...

    def on_arrange_rows_clicked(self) -> None:
        """Handle arrange rows button click"""
        ...

    def on_arrange_grid_clicked(self) -> None:
        """Handle arrange grid button click"""
        ...

    def on_inject_clicked(self) -> None:
        """Handle inject button click"""
        ...

class ToolbarManager(QObject):
    """Manages action buttons and toolbar for MainWindow"""

    # Signals - forward button clicks to main window
    extract_clicked = Signal()
    open_editor_clicked = Signal()
    arrange_rows_clicked = Signal()
    arrange_grid_clicked = Signal()
    inject_clicked = Signal()

    def __init__(self, parent: QWidget, actions_handler: ToolbarActionsProtocol) -> None:
        """Initialize toolbar manager

        Args:
            parent: Parent widget to contain the buttons
            actions_handler: Handler for button actions
        """
        super().__init__(parent)
        self.parent_widget = parent
        self.actions_handler = actions_handler

        # Button references
        self.extract_button: QPushButton
        self.open_editor_button: QPushButton
        self.arrange_button: QPushButton  # Consolidated arrange button with menu
        self.arrange_menu: QMenu  # Menu for arrange options
        self.inject_button: QPushButton

        # Status label for extraction readiness feedback
        self.extraction_status_label: QLabel

    def create_action_buttons(self, layout: QGridLayout) -> None:
        """Create action buttons and add them to the provided layout

        Layout structure (with visual hierarchy):
        - Row 0: Status label (span 2)
        - Row 1: Extract button (span 2, prominent)
        - Row 2: Separator line
        - Row 3: Open Editor + Arrange side-by-side
        - Row 4: Inject button (span 2)

        Args:
            layout: Grid layout to add buttons to
        """
        # Add horizontal margins to align with form content above
        layout.setContentsMargins(SPACING_MEDIUM, 0, SPACING_MEDIUM, 0)

        self._create_extraction_status_label(layout)
        self._create_extract_button(layout)
        self._create_separator(layout)
        self._create_open_editor_button(layout)
        self._create_arrange_button(layout)
        self._create_inject_button(layout)
        self._connect_button_signals()

    def _create_separator(self, layout: QGridLayout) -> None:
        """Create visual separator between primary and secondary actions"""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator, 2, 0, 1, 2)  # Row 2, span both columns

    def _create_extraction_status_label(self, layout: QGridLayout) -> None:
        """Create inline status label showing extraction readiness"""
        self.extraction_status_label = QLabel("")
        self.extraction_status_label.setStyleSheet(get_extraction_checklist_style())
        self.extraction_status_label.setWordWrap(True)
        self.extraction_status_label.hide()  # Hidden when extraction is ready
        # Add to row -1 (before extract button), spanning both columns
        layout.addWidget(self.extraction_status_label, 0, 0, 1, 2)

    def _create_extract_button(self, layout: QGridLayout) -> None:
        """Create extract button - primary action with visual emphasis"""
        self.extract_button = QPushButton("Extract")
        self.extract_button.setMinimumHeight(PRIMARY_BUTTON_HEIGHT)  # Taller for emphasis
        self.extract_button.setShortcut(QKeySequence("Ctrl+E"))
        self.extract_button.setToolTip("Extract sprites for editing (Ctrl+E)")
        if self.extract_button:
            self.extract_button.setStyleSheet(get_button_style("extract"))
        layout.addWidget(self.extract_button, 1, 0, 1, 2)  # Row 1, span both columns

    def _create_open_editor_button(self, layout: QGridLayout) -> None:
        """Create open editor button - secondary action with outline style"""
        self.open_editor_button = QPushButton("Open Editor")
        self.open_editor_button.setMinimumHeight(BUTTON_HEIGHT)
        if self.open_editor_button:
            self.open_editor_button.setEnabled(False)
        self.open_editor_button.setShortcut(QKeySequence("Ctrl+O"))
        self.open_editor_button.setToolTip("Open extracted sprites in pixel editor (Ctrl+O)")
        if self.open_editor_button:
            self.open_editor_button.setStyleSheet(get_button_style("secondary_outline"))
        layout.addWidget(self.open_editor_button, 3, 0)  # Row 3, first column

    def _create_arrange_button(self, layout: QGridLayout) -> None:
        """Create consolidated arrange button with dropdown menu - secondary action"""
        self.arrange_button = QPushButton("Arrange...")
        self.arrange_button.setMinimumHeight(BUTTON_HEIGHT)
        if self.arrange_button:
            self.arrange_button.setEnabled(False)
        self.arrange_button.setToolTip("Arrange sprites (Ctrl+R for rows, Ctrl+G for grid)")
        if self.arrange_button:
            self.arrange_button.setStyleSheet(get_button_style("secondary_outline"))

        # Create dropdown menu for arrange options
        self.arrange_menu = QMenu(self.parent_widget)
        self.arrange_rows_action = self.arrange_menu.addAction("By Rows (Ctrl+R)")
        self.arrange_rows_action.setShortcut(QKeySequence("Ctrl+R"))
        self.arrange_rows_action.setToolTip("Arrange sprite rows for easier editing")

        self.arrange_grid_action = self.arrange_menu.addAction("By Grid (Ctrl+G)")
        self.arrange_grid_action.setShortcut(QKeySequence("Ctrl+G"))
        self.arrange_grid_action.setToolTip("Arrange sprites in flexible grid layout")

        self.arrange_button.setMenu(self.arrange_menu)

        layout.addWidget(self.arrange_button, 3, 1)  # Row 3, second column

    def _create_inject_button(self, layout: QGridLayout) -> None:
        """Create inject button - writes to ROM, uses prominent warning color"""
        self.inject_button = QPushButton("Inject")
        # Match Extract button height for visual balance
        self.inject_button.setMinimumHeight(PRIMARY_BUTTON_HEIGHT)
        if self.inject_button:
            self.inject_button.setEnabled(False)
        self.inject_button.setShortcut(QKeySequence("Ctrl+I"))
        self.inject_button.setToolTip("Inject edited sprite back into VRAM or ROM (Ctrl+I)")
        if self.inject_button:
            # Use gradient danger style for visual prominence
            self.inject_button.setStyleSheet(get_danger_action_button_style())
        layout.addWidget(self.inject_button, 4, 0, 1, 2)  # Row 4, span both columns

    def _connect_button_signals(self) -> None:
        """Connect button signals to action handlers"""
        self.extract_button.clicked.connect(self.actions_handler.on_extract_clicked)
        self.open_editor_button.clicked.connect(self.actions_handler.on_open_editor_clicked)
        self.arrange_rows_action.triggered.connect(self.actions_handler.on_arrange_rows_clicked)
        self.arrange_grid_action.triggered.connect(self.actions_handler.on_arrange_grid_clicked)
        self.inject_button.clicked.connect(self.actions_handler.on_inject_clicked)

    def set_extract_enabled(self, enabled: bool, reason: str = "") -> None:
        """Set extract button enabled state with validation feedback.

        Args:
            enabled: Whether button should be enabled
            reason: If disabled, explanation of why (e.g., "Load a ROM file")
        """
        if not hasattr(self, "extract_button") or not self.extract_button:
            return

        self.extract_button.setEnabled(enabled)

        # Update inline status label visibility and text
        if hasattr(self, "extraction_status_label") and self.extraction_status_label:
            if enabled:
                # Show positive ready status with green accent
                self.extraction_status_label.setText("✓ Ready to extract")
                self.extraction_status_label.setStyleSheet(get_ready_status_style())
                self.extraction_status_label.show()
            elif reason:
                self.extraction_status_label.setText(f"⚠ {reason}")
                self.extraction_status_label.setStyleSheet(get_extraction_checklist_style())
                self.extraction_status_label.show()
            else:
                self.extraction_status_label.setText("⚠ Requirements not met")
                self.extraction_status_label.setStyleSheet(get_extraction_checklist_style())
                self.extraction_status_label.show()

        # Also keep tooltip for accessibility
        if enabled:
            self.extract_button.setToolTip("Extract sprites for editing (Ctrl+E)")
        elif reason:
            self.extract_button.setToolTip(f"Cannot extract: {reason}")
        else:
            self.extract_button.setToolTip("Cannot extract - requirements not met")

    def set_post_extraction_buttons_enabled(self, enabled: bool) -> None:
        """Set post-extraction buttons enabled state"""
        if hasattr(self, "open_editor_button") and self.open_editor_button:
            self.open_editor_button.setEnabled(enabled)
        if hasattr(self, "arrange_button") and self.arrange_button:
            self.arrange_button.setEnabled(enabled)
        if hasattr(self, "inject_button") and self.inject_button:
            self.inject_button.setEnabled(enabled)

    def reset_buttons(self) -> None:
        """Reset all buttons to initial state"""
        if hasattr(self, "extract_button") and self.extract_button:
            self.extract_button.setEnabled(False)
        self.set_post_extraction_buttons_enabled(False)
