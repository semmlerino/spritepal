"""
ComposedDialog base class for composition-based dialog architecture.

This module provides the ComposedDialog class that serves as a base class for dialogs
using the composition pattern. It automatically initializes and manages dialog
components based on configuration, providing a flexible alternative to monolithic
inheritance hierarchies.
"""
from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import QObject
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from .button_box_manager import ButtonBoxManager
from .dialog_context import DialogContext
from .message_dialog_manager import MessageDialogManager
from .status_bar_manager import StatusBarManager


class ComposedDialog(QDialog):
    """
    Base class for dialogs using composition pattern.

    This class provides a dialog base that uses composition to add functionality
    instead of relying on inheritance. Components are initialized based on
    configuration parameters and managed through their lifecycle.

    Configuration options:
        - with_button_box: Include button box (default: True)
        - with_status_bar: Include status bar (default: False)

    Components are automatically registered in the dialog context and can be
    accessed using get_component(name).

    Example:
        class MyDialog(ComposedDialog):
            def setup_ui(self):
                # Add custom UI elements to self.content_widget
                pass
    """

    def __init__(self, parent: QWidget | None = None, **config: Any) -> None:
        """
        Initialize the composed dialog.

        Args:
            parent: Parent widget for the dialog
            **config: Configuration options for component initialization
        """
        super().__init__(parent)

        # Store configuration
        self.config = config

        # Create main layout and content widget
        self.main_layout = QVBoxLayout(self)
        self.content_widget = QWidget()
        self.main_layout.addWidget(self.content_widget)

        # Create dialog context for component communication
        self.context = DialogContext(
            dialog=self,
            main_layout=self.main_layout,
            content_widget=self.content_widget,
            config=config
        )

        # List to track components for lifecycle management
        self.components: list[QObject] = []

        # Initialize components based on configuration
        self._initialize_components()

        # Allow subclasses to set up custom UI
        if hasattr(self, 'setup_ui') and callable(self.setup_ui):
            self.setup_ui()

    def _initialize_components(self) -> None:
        """
        Initialize dialog components based on configuration.

        This method creates and initializes components according to the
        configuration passed to the constructor. Components are automatically
        registered in the dialog context.
        """
        # Always initialize message dialog manager
        message_manager = MessageDialogManager()
        message_manager.initialize(self.context)
        self._register_component("message_dialog", message_manager)

        # Initialize button box manager if requested (default: True)
        if self.config.get("with_button_box", True) is not False:
            button_manager = ButtonBoxManager()
            button_manager.initialize(self.context)
            self._register_component("button_box", button_manager)

        # Always initialize dialog signal manager for custom signals
        from .dialog_signal_manager import DialogSignalManager
        signal_manager = DialogSignalManager()
        signal_manager.initialize(self.context)
        self._register_component("dialog_signals", signal_manager)

        # Always initialize Qt dialog signal manager for standard Qt signals
        from .qt_dialog_signal_manager import QtDialogSignalManager
        qt_signal_manager = QtDialogSignalManager()
        qt_signal_manager.initialize(self.context)
        self._register_component("qt_dialog_signals", qt_signal_manager)

        # Initialize status bar manager if requested (default: False)
        if self.config.get("with_status_bar", False) is True:
            status_manager = StatusBarManager()
            status_manager.initialize(self.context)
            self._register_component("status_bar", status_manager)

    def _register_component(self, name: str, component: QObject) -> None:
        """
        Register a component in the context and component list.

        Args:
            name: Unique name for the component
            component: The component to register
        """
        self.context.register_component(name, component)
        self.components.append(component)

    def get_component(self, name: str) -> QObject | None:
        """
        Get a registered component by name.

        Args:
            name: The name of the component to retrieve

        Returns:
            The registered component or None if not found
        """
        return self.context.get_component(name)

    def setup_ui(self) -> None:
        """
        Set up the dialog UI.

        This method should be overridden by subclasses to add custom UI elements.
        The content_widget is available for adding custom widgets, and components
        can be accessed using get_component().

        Note:
            This method is called automatically after component initialization
            if it exists in the subclass.
        """
        pass

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handle dialog close event.

        This method ensures proper cleanup of all components when the dialog
        is closed. Components that implement a cleanup() method will have it
        called automatically.

        Args:
            event: The close event
        """
        # Call cleanup on all components that support it
        for component in self.components:
            if hasattr(component, 'cleanup') and callable(getattr(component, 'cleanup', None)):
                component.cleanup()  # type: ignore[attr-defined]

        # Call parent close event
        super().closeEvent(event)
