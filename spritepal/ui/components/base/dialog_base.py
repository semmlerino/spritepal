"""
Base dialog class for SpritePal.

This class provides a standardized base for all dialogs with common features
like button boxes, status bars, tabs, and splitters.

IMPORTANT: Subclasses MUST declare instance variables BEFORE calling super().__init__()
to avoid overwriting widgets created in _setup_ui(). See CLAUDE.md for details.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLayout,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class DialogBase(QDialog):
    """
    Base class for all SpritePal dialogs.

    Subclasses MUST follow this pattern:

    ```python
    class MyDialog(DialogBase):
        def __init__(self, parent: QWidget | None = None):
            # Step 1: Declare instance variables BEFORE super()
            self.my_widget: QWidget | None = None
            self.my_data: list[str] = []

            # Step 2: Call parent init (this calls _setup_ui)
            super().__init__(parent)

        def _setup_ui(self):
            # Step 3: Create widgets (safe - variables already declared)
            self.my_widget = QWidget()
    ```
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str | None = None,
        modal: bool = True,
        min_size: tuple[int | None, int | None] | None = None,
        size: tuple[int, int] | None = None,
        with_status_bar: bool = False,
        with_button_box: bool = True,
        default_tab: int | None = None,
        orientation: Qt.Orientation | None = None,  # For splitter dialogs
        splitter_handle_width: int = 8,  # For splitter dialogs
    ) -> None:
        """
        Initialize the dialog base.

        Args:
            parent: Parent widget (optional)
            title: Window title (optional)
            modal: Whether dialog should be modal (default: True)
            min_size: Minimum size as (width, height) tuple, None for no limit
            size: Fixed size as (width, height) tuple (optional)
            with_status_bar: Whether to add a status bar
            with_button_box: Whether to add a standard button box (default: True)
            default_tab: Default tab index for tabbed dialogs (optional)
            orientation: Splitter orientation for splitter dialogs (optional)
            splitter_handle_width: Handle width for splitter dialogs (default: 8)
        """
        # Call Qt's init FIRST - required for PySide6
        super().__init__(parent)

        # Store configuration for subclasses
        self._default_tab = default_tab
        self._orientation = orientation
        self._splitter_handle_width = splitter_handle_width

        # Set standard dialog properties
        if modal:
            self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        # Apply optional settings
        if title:
            self.setWindowTitle(title)

        if min_size:
            width, height = min_size
            if width is not None:
                self.setMinimumWidth(width)
            if height is not None:
                self.setMinimumHeight(height)

        if size:
            width, height = size
            self.resize(width, height)

        if with_status_bar:
            self.status_bar = QStatusBar(self)
        else:
            self.status_bar = None

        # Create main layout for dialogs that need it
        self.main_layout = QVBoxLayout(self)
        self.setLayout(self.main_layout)

        # For splitter dialogs
        self.main_splitter = None  # Will be set by add_horizontal_splitter

        # If orientation is specified, create a splitter automatically
        if orientation is not None:
            self.main_splitter = QSplitter(orientation)
            self.main_splitter.setHandleWidth(self._splitter_handle_width)
            self.main_layout.addWidget(self.main_splitter)
            # For splitter dialogs, the splitter IS the content widget
            self.content_widget = self.main_splitter
        else:
            # Create content widget only for non-splitter dialogs
            self.content_widget = QWidget()
            self.main_layout.addWidget(self.content_widget)

        # Create button box if requested
        if with_button_box:
            self.button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            self.button_box.accepted.connect(self.accept)
            self.button_box.rejected.connect(self.reject)
            self.main_layout.addWidget(self.button_box)
        else:
            self.button_box = None

        # For tabbed dialogs, create tab widget
        self._tab_widget: QTabWidget | None = None
        self.tab_widget = self._tab_widget  # Public alias for tests

        # Call setup method if it exists
        if hasattr(self, "_setup_ui"):
            self._setup_ui()

    def _setup_ui(self) -> None:
        """
        Set up the dialog UI.

        Subclasses MAY implement this method to create their UI.
        This is called automatically by __init__ after instance variables
        are declared but before the dialog is shown.

        If not implemented, subclasses should set up their UI in __init__.
        """
        # Optional method - subclasses can implement if needed

    def set_content_layout(self, layout: QLayout) -> None:
        """
        Set the content layout for the dialog.

        Args:
            layout: The layout to set as the dialog's content
        """
        layout.setContentsMargins(0, 0, 0, 0)
        self.content_widget.setLayout(layout)

    def add_tab(self, widget: QWidget, label: str) -> None:
        """
        Add a tab to the dialog (for tabbed dialogs).

        Args:
            widget: The widget to add as a tab
            label: The tab label
        """
        if self._tab_widget is None:
            self._tab_widget = QTabWidget()
            self.tab_widget = self._tab_widget  # Update public alias
            self.main_layout.addWidget(self._tab_widget)

        self._tab_widget.addTab(widget, label)

        # Set default tab if specified
        if self._default_tab is not None and self._tab_widget:
            self._tab_widget.setCurrentIndex(self._default_tab)

    def add_horizontal_splitter(self, handle_width: int | None = None) -> QSplitter:
        """
        Add a horizontal splitter to the dialog (for splitter dialogs).

        Args:
            handle_width: Width of the splitter handle (uses default if not specified)

        Returns:
            The created splitter widget
        """

        if handle_width is None:
            handle_width = self._splitter_handle_width

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(handle_width)

        # If main_splitter already exists, add to it instead of main_layout
        if self.main_splitter is not None:
            self.main_splitter.addWidget(splitter)
        else:
            self.main_layout.addWidget(splitter)
            self.main_splitter = splitter

        return splitter

    def add_panel(self, widget: QWidget, stretch_factor: int = 1) -> None:
        """
        Add a panel to the dialog.

        Args:
            widget: The widget to add
            stretch_factor: Stretch factor for the widget
        """
        if self.main_splitter is not None:
            # Add to splitter if it exists
            self.main_splitter.addWidget(widget)
            # Set stretch factor
            self.main_splitter.setStretchFactor(self.main_splitter.count() - 1, stretch_factor)
        else:
            # Otherwise add to main layout
            self.main_layout.addWidget(widget, stretch_factor)

    def add_button(self, text: str, callback: object | None = None) -> QPushButton:
        """
        Add a button to the dialog.

        Args:
            text: Button text
            callback: Optional callback function

        Returns:
            The created button
        """

        button = QPushButton(text)
        if callback:
            button.clicked.connect(callback)
        return button

    def update_status(self, message: str) -> None:
        """
        Update the status bar message (for dialogs with status bars).

        Args:
            message: Status message to display
        """
        if hasattr(self, "status_bar") and self.status_bar:
            self.status_bar.showMessage(message)

    def set_current_tab(self, index: int) -> None:
        """
        Set the current tab for tabbed dialogs.

        Args:
            index: Tab index to switch to
        """
        if self._tab_widget is not None:
            self._tab_widget.setCurrentIndex(index)

    def get_current_tab_index(self) -> int:
        """
        Get the current tab index for tabbed dialogs.

        Returns:
            Current tab index, or -1 if no tabs exist
        """
        if self._tab_widget is not None:
            return self._tab_widget.currentIndex()
        return -1
