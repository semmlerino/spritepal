"""
Toolbar and action button management for MainWindow
"""
from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget

from ui.styles import get_button_style


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
        self.arrange_rows_button: QPushButton
        self.arrange_grid_button: QPushButton
        self.inject_button: QPushButton

    def create_action_buttons(self, layout: QGridLayout) -> None:
        """Create action buttons and add them to the provided layout

        Args:
            layout: Grid layout to add buttons to
        """
        self._create_extract_button(layout)
        self._create_open_editor_button(layout)
        self._create_arrange_buttons(layout)
        self._create_inject_button(layout)
        self._connect_button_signals()

    def _create_extract_button(self, layout: QGridLayout) -> None:
        """Create extract button"""
        self.extract_button = QPushButton("Extract for Editing")
        self.extract_button.setMinimumHeight(35)
        self.extract_button.setShortcut(QKeySequence("Ctrl+E"))
        self.extract_button.setToolTip("Extract sprites for editing (Ctrl+E)")
        if self.extract_button:
            self.extract_button.setStyleSheet(get_button_style("extract"))
        layout.addWidget(self.extract_button, 0, 0)

    def _create_open_editor_button(self, layout: QGridLayout) -> None:
        """Create open editor button"""
        self.open_editor_button = QPushButton("Open in Editor")
        self.open_editor_button.setMinimumHeight(35)
        if self.open_editor_button:
            self.open_editor_button.setEnabled(False)
        self.open_editor_button.setShortcut(QKeySequence("Ctrl+O"))
        self.open_editor_button.setToolTip("Open extracted sprites in pixel editor (Ctrl+O)")
        if self.open_editor_button:
            self.open_editor_button.setStyleSheet(get_button_style("editor"))
        layout.addWidget(self.open_editor_button, 0, 1)

    def _create_arrange_buttons(self, layout: QGridLayout) -> None:
        """Create arrange buttons"""
        self.arrange_rows_button = QPushButton("Arrange Rows")
        self.arrange_rows_button.setMinimumHeight(35)
        if self.arrange_rows_button:
            self.arrange_rows_button.setEnabled(False)
        self.arrange_rows_button.setShortcut(QKeySequence("Ctrl+R"))
        self.arrange_rows_button.setToolTip("Arrange sprite rows for easier editing (Ctrl+R)")
        if self.arrange_rows_button:
            self.arrange_rows_button.setStyleSheet(get_button_style("primary"))
        layout.addWidget(self.arrange_rows_button, 1, 0)

        self.arrange_grid_button = QPushButton("Grid Arrange")
        self.arrange_grid_button.setMinimumHeight(35)
        if self.arrange_grid_button:
            self.arrange_grid_button.setEnabled(False)
        self.arrange_grid_button.setShortcut(QKeySequence("Ctrl+G"))
        self.arrange_grid_button.setToolTip(
            "Arrange sprites using flexible grid (rows/columns/tiles) (Ctrl+G)"
        )
        if self.arrange_grid_button:
            self.arrange_grid_button.setStyleSheet(get_button_style("secondary"))
        layout.addWidget(self.arrange_grid_button, 1, 1)

    def _create_inject_button(self, layout: QGridLayout) -> None:
        """Create inject button"""
        self.inject_button = QPushButton("Inject")
        self.inject_button.setMinimumHeight(35)
        if self.inject_button:
            self.inject_button.setEnabled(False)
        self.inject_button.setShortcut(QKeySequence("Ctrl+I"))
        self.inject_button.setToolTip("Inject edited sprite back into VRAM or ROM (Ctrl+I)")
        if self.inject_button:
            self.inject_button.setStyleSheet(get_button_style("accent"))
        layout.addWidget(self.inject_button, 2, 0, 1, 2)  # Span both columns

    def _connect_button_signals(self) -> None:
        """Connect button signals to action handlers"""
        self.extract_button.clicked.connect(self.actions_handler.on_extract_clicked)
        self.open_editor_button.clicked.connect(self.actions_handler.on_open_editor_clicked)
        self.arrange_rows_button.clicked.connect(self.actions_handler.on_arrange_rows_clicked)
        self.arrange_grid_button.clicked.connect(self.actions_handler.on_arrange_grid_clicked)
        self.inject_button.clicked.connect(self.actions_handler.on_inject_clicked)

    def set_extract_enabled(self, enabled: bool) -> None:
        """Set extract button enabled state"""
        if hasattr(self, "extract_button") and self.extract_button:
            self.extract_button.setEnabled(enabled)

    def set_post_extraction_buttons_enabled(self, enabled: bool) -> None:
        """Set post-extraction buttons enabled state"""
        if hasattr(self, "open_editor_button") and self.open_editor_button:
            self.open_editor_button.setEnabled(enabled)
        if hasattr(self, "arrange_rows_button") and self.arrange_rows_button:
            self.arrange_rows_button.setEnabled(enabled)
        if hasattr(self, "arrange_grid_button") and self.arrange_grid_button:
            self.arrange_grid_button.setEnabled(enabled)
        if hasattr(self, "inject_button") and self.inject_button:
            self.inject_button.setEnabled(enabled)

    def reset_buttons(self) -> None:
        """Reset all buttons to initial state"""
        if hasattr(self, "extract_button") and self.extract_button:
            self.extract_button.setEnabled(False)
        self.set_post_extraction_buttons_enabled(False)
