"""
DialogBase migration adapter for backward compatibility.

This adapter provides a drop-in replacement for the existing DialogBase class,
using the new composition-based architecture while maintaining full backward
compatibility with the existing API. This allows gradual migration of dialogs
without breaking existing code.

Usage:
    Replace:
        from ui.components.base.dialog_base import DialogBase
    With:
        from ui.components.base.composed.migration_adapter import DialogBaseMigrationAdapter as DialogBase
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from typing_extensions import override

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QWidget,
)

from utils.logging_config import get_logger

from .composed_dialog import ComposedDialog

logger = get_logger(__name__)

class InitializationOrderError(Exception):
    """Raised when initialization order requirements are violated."""

class DialogBaseMigrationAdapter(ComposedDialog):
    """
    Migration adapter providing DialogBase-compatible API using composition.

    This class provides full backward compatibility with the existing DialogBase
    while using the new composition-based architecture internally. It maps all
    DialogBase methods and properties to the appropriate component calls.

    The initialization order checking is simplified but still present for
    compatibility, though the composition architecture makes it less critical.
    """

    # Class-level registry of known widget attributes to check (for compatibility)
    _WIDGET_ATTRIBUTES: ClassVar[list[str]] = [
        "rom_map", "offset_widget", "scan_controls", "import_export",
        "status_panel", "preview_widget", "mode_selector", "status_label",
        "dumps_dir_edit", "cache_enabled_check", "source_list", "arranged_list",
        "available_list"
    ]

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str | None = None,
        modal: bool = True,
        min_size: tuple[int | None, int | None] | None = None,
        size: tuple[int, int | None] | None = None,
        with_status_bar: bool = False,
        with_button_box: bool = True,
        default_tab: int | None = None,
        orientation: Any | None = None,  # For splitter dialogs
        splitter_handle_width: int = 8,  # For splitter dialogs
        **kwargs: Any  # Accept any additional keyword arguments
    ) -> None:
        """
        Initialize the dialog with DialogBase-compatible parameters.

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
            **kwargs: Additional keyword arguments (ignored, for compatibility)
        """
        # Store configuration for later use
        self._default_tab = default_tab
        self._orientation = orientation
        self._splitter_handle_width = splitter_handle_width
        self._tab_widget: QTabWidget | None = None

        # Initialize tracking (simplified but kept for compatibility)
        self._initialization_phase = "during_init"
        self._declared_variables: set[str] = set()
        self._setup_called = False

        # Record existing instance variables (for compatibility)
        try:
            for attr_name in dir(self):
                if not attr_name.startswith("_") and hasattr(self, attr_name):
                    self._declared_variables.add(attr_name)
        except RuntimeError:
            pass

        # Build configuration for ComposedDialog
        config = {
            "with_status_bar": with_status_bar,
            "with_button_box": with_button_box,
        }

        # Store whether to call _setup_ui later
        self._should_call_setup_ui = hasattr(self, "_setup_ui")

        # Initialize parent with composition configuration
        logger.debug("DEBUGGING: About to call super().__init__ for ComposedDialog")
        try:
            super().__init__(parent, **config)
            logger.debug("DEBUGGING: ComposedDialog.__init__ completed successfully")
        except Exception as e:
            logger.error(f"DEBUGGING: ComposedDialog.__init__ failed: {e}")
            import traceback
            logger.error(f"DEBUGGING: Full traceback: {traceback.format_exc()}")
            raise

        # Apply dialog properties
        logger.debug("DEBUGGING: Applying dialog properties")
        if modal:
            self.setWindowModality(Qt.WindowModality.ApplicationModal)
        # Delay WA_DeleteOnClose until after initialization is complete
        logger.debug("DEBUGGING: Dialog properties applied (WA_DeleteOnClose deferred)")

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
            if height is not None:
                self.resize(width, height)

        # Note: _setup_ui is called by setup_ui() which is invoked by ComposedDialog
        # After that, we do additional setup

        # Create compatibility properties (after setup_ui has been called)
        self._setup_compatibility_properties()

        # Create splitter if requested (and not already created by subclass)
        if orientation is not None and not hasattr(self, 'main_splitter'):
            # Remove the empty content_widget that was added by ComposedDialog
            self.main_layout.removeWidget(self.content_widget)
            self.content_widget.deleteLater()

            # Create and add the splitter
            self.main_splitter = QSplitter(orientation)
            self.main_splitter.setHandleWidth(splitter_handle_width)

            # Insert splitter before button box if it exists
            button_manager = self.get_component("button_box")
            if button_manager and hasattr(button_manager, "button_box"):
                insert_index = self.main_layout.indexOf(button_manager.button_box)  # type: ignore[attr-defined]
                self.main_layout.insertWidget(insert_index, self.main_splitter)
            else:
                self.main_layout.addWidget(self.main_splitter)

            # For splitter dialogs, the splitter IS the content widget
            self.content_widget = self.main_splitter
            self.context.content_widget = self.main_splitter
            self.context.main_splitter = self.main_splitter
        elif not hasattr(self, 'main_splitter'):
            self.main_splitter = None

        # Verify initialization (simplified check for compatibility)
        self._verify_initialization()
        self._initialization_phase = "complete"

        # DEFER WA_DeleteOnClose until dialog is actually being closed
        # Setting it during initialization causes Qt signal lifecycle issues
        self._should_delete_on_close = True
        logger.debug("DEBUGGING: WA_DeleteOnClose deferred until close event")

    def _setup_compatibility_properties(self) -> None:
        """Set up properties for DialogBase compatibility."""
        # Map status_bar property
        status_manager = self.get_component("status_bar")
        if status_manager and hasattr(status_manager, "status_bar"):
            self.status_bar = status_manager.status_bar  # type: ignore[attr-defined]
            # Mock setStatusBar for dialogs (DialogBase compatibility)
            self.setStatusBar = lambda: self.status_bar
        else:
            self.status_bar = None

        # Map button_box property
        button_manager = self.get_component("button_box")
        if button_manager and hasattr(button_manager, "button_box"):
            self.button_box = button_manager.button_box  # type: ignore[attr-defined]
        else:
            self.button_box = None

        # These are already set by ComposedDialog but ensure they exist
        # for DialogBase compatibility
        if not hasattr(self, 'main_layout'):
            self.main_layout = self.context.main_layout
        if not hasattr(self, 'content_widget'):
            self.content_widget = self.context.content_widget

    @override
    def __setattr__(self, name: str, value: Any) -> None:
        """
        Override setattr for initialization order checking (compatibility).

        The composition architecture makes this less critical, but we keep it
        for backward compatibility with DialogBase expectations.
        """
        # Allow private attributes and initialization tracking
        if name.startswith("_"):
            super().__setattr__(name, value)
            return

        # During initialization phase, track what's happening (simplified)
        if hasattr(self, "_initialization_phase"):
            phase = self._initialization_phase

            # Check for suspicious patterns (for compatibility)
            if (phase == "setup" and
                value is None and
                name in self._WIDGET_ATTRIBUTES):
                logger.warning(
                    f"{self.__class__.__name__}: Assigning None to '{name}' "
                    f"during setup phase - possible initialization order bug!"
                )

            # After setup, check for late assignments (for compatibility)
            elif (phase == "complete" and
                  value is None and
                  name not in self._declared_variables and
                  name in self._WIDGET_ATTRIBUTES):
                # Less strict than original - just warn instead of raising
                logger.warning(
                    f"{self.__class__.__name__}: Late assignment of None to '{name}' "
                    f"after setup - consider declaring before super().__init__()"
                )

        super().__setattr__(name, value)

    def _verify_initialization(self) -> None:
        """Verify initialization (simplified for compatibility)."""
        # Check for common widget attributes that should not be None
        for attr_name in self._WIDGET_ATTRIBUTES:
            if hasattr(self, attr_name):
                value = getattr(self, attr_name)
                if value is None and attr_name not in self._declared_variables:
                    logger.warning(
                        f"{self.__class__.__name__}: Widget attribute '{attr_name}' "
                        f"is None after initialization - was it properly created?"
                    )

    def _setup_ui(self) -> None:
        """
        Set up the dialog UI (DialogBase compatibility).

        Subclasses MAY implement this method to create their UI.
        This is called automatically by __init__ after instance variables
        are declared but before the dialog is shown.
        """
        # Optional method - subclasses can implement if needed
        pass

    # Override setup_ui to call _setup_ui for compatibility
    @override
    def setup_ui(self) -> None:
        """ComposedDialog setup_ui - delegates to _setup_ui for compatibility."""
        # First ensure compatibility properties are set up
        if not hasattr(self, 'status_bar'):
            self._setup_compatibility_properties()

        # Then call _setup_ui if it exists and hasn't been called
        if hasattr(self, '_setup_ui') and not self._setup_called:
            self._initialization_phase = "setup"
            self._setup_ui()
            self._setup_called = True

    def set_content_layout(self, layout: Any) -> None:
        """
        Set the content layout for the dialog.

        Args:
            layout: The layout to set as the dialog's content
        """
        if hasattr(layout, "setContentsMargins"):
            layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addLayout(layout)

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
            # Update context
            self.context.tab_widget = self._tab_widget

        self._tab_widget.addTab(widget, label)

        # Set default tab if specified
        if hasattr(self, "_default_tab") and self._default_tab is not None:
            self._tab_widget.setCurrentIndex(self._default_tab)

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

    def add_horizontal_splitter(self, handle_width: int | None = None) -> Any:
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
            self.context.main_splitter = splitter

        return splitter

    def add_panel(self, widget: QWidget, stretch_factor: int = 1) -> None:
        """
        Add a panel to the dialog.

        Args:
            widget: The widget to add
            stretch_factor: Stretch factor for the widget
        """
        # Create main_splitter if it doesn't exist yet (early initialization)
        if not hasattr(self, 'main_splitter') or self.main_splitter is None:
            # Create default horizontal splitter
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QSplitter
            self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
            self.main_splitter.setHandleWidth(12)  # Default handle width
            self.main_layout.addWidget(self.main_splitter)
            if hasattr(self, 'context'):
                self.context.main_splitter = self.main_splitter

        # Add to splitter
        self.main_splitter.addWidget(widget)
        # Set stretch factor
        self.main_splitter.setStretchFactor(
            self.main_splitter.count() - 1, stretch_factor
        )

    def add_button(self, text: str, callback: Any | None = None) -> Any:
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

        # If we have a button box manager, add to it
        button_manager = self.get_component("button_box")
        if button_manager and hasattr(button_manager, "add_button"):
            button_manager.add_button(  # type: ignore[attr-defined]
                button, QDialogButtonBox.ButtonRole.ActionRole
            )

        return button

    def update_status(self, message: str) -> None:
        """
        Update the status bar message (for dialogs with status bars).

        Args:
            message: Status message to display
        """
        status_manager = self.get_component("status_bar")
        if status_manager and hasattr(status_manager, "update_status"):
            status_manager.update_status(message)  # type: ignore[attr-defined]
        elif hasattr(self, "status_bar") and self.status_bar:
            # Fallback to direct status bar access
            self.status_bar.showMessage(message)

    def show_error(self, title: str, message: str) -> None:
        """
        Show an error message dialog.

        Args:
            title: Error dialog title
            message: Error message to display
        """
        message_manager = self.get_component("message_dialog")
        if message_manager and hasattr(message_manager, "show_error"):
            message_manager.show_error(title, message)  # type: ignore[attr-defined]
        else:
            # Fallback to direct QMessageBox
            QMessageBox.critical(self, title, message)

    def show_info(self, title: str, message: str) -> None:
        """
        Show an information message dialog.

        Args:
            title: Info dialog title
            message: Info message to display
        """
        message_manager = self.get_component("message_dialog")
        if message_manager and hasattr(message_manager, "show_info"):
            message_manager.show_info(title, message)  # type: ignore[attr-defined]
        else:
            # Fallback to direct QMessageBox
            QMessageBox.information(self, title, message)

    def show_warning(self, title: str, message: str) -> None:
        """
        Show a warning message dialog.

        Args:
            title: Warning dialog title
            message: Warning message to display
        """
        message_manager = self.get_component("message_dialog")
        if message_manager and hasattr(message_manager, "show_warning"):
            message_manager.show_warning(title, message)  # type: ignore[attr-defined]
        else:
            # Fallback to direct QMessageBox
            QMessageBox.warning(self, title, message)

    def confirm_action(self, title: str, message: str) -> bool:
        """
        Show a confirmation dialog.

        Args:
            title: Confirmation dialog title
            message: Confirmation message

        Returns:
            True if user confirmed, False otherwise
        """
        message_manager = self.get_component("message_dialog")
        if message_manager and hasattr(message_manager, "confirm_action"):
            return message_manager.confirm_action(title, message)  # type: ignore[attr-defined]
        # Fallback to direct QMessageBox
        reply = QMessageBox.question(self, title, message)
        return reply == QMessageBox.StandardButton.Yes

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle close event and set WA_DeleteOnClose at the right time."""
        logger.debug("DEBUGGING: closeEvent called, now setting WA_DeleteOnClose")
        if getattr(self, '_should_delete_on_close', False):
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            logger.debug("DEBUGGING: WA_DeleteOnClose set during close event")

        super().closeEvent(event)
