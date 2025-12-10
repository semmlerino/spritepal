"""
DialogContext class for managing shared state across dialog components.

This module provides the DialogContext dataclass that serves as a centralized
state container for all dialog components in the composition-based refactoring.
It enables component communication and provides access to shared dialog elements.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


@dataclass
class DialogContext:
    """
    Shared state container for dialog components.

    This class holds references to the main dialog elements and provides
    a registry for components to communicate with each other. It is passed
    to all component initialize() methods to enable shared state access.

    Attributes:
        dialog: The parent QDialog instance
        main_layout: The main QVBoxLayout of the dialog
        content_widget: The main content area widget
        button_box: Optional dialog button box (OK/Cancel/etc.)
        status_bar: Optional status bar for messages
        tab_widget: Optional tab widget for tabbed interfaces
        main_splitter: Optional splitter for resizable panes
        config: Configuration dictionary passed during initialization
        components: Registry mapping component names to QObject instances
    """

    # Required fields
    dialog: QDialog
    main_layout: QVBoxLayout
    content_widget: QWidget

    # Optional UI elements (default to None)
    button_box: QDialogButtonBox | None = None
    status_bar: QStatusBar | None = None
    tab_widget: QTabWidget | None = None
    main_splitter: QSplitter | None = None

    # Configuration and component registry
    config: dict[str, Any] = field(default_factory=dict)
    components: dict[str, QObject] = field(default_factory=dict)

    def register_component(self, name: str, component: QObject) -> None:
        """
        Register a component in the component registry.

        This allows components to be accessed by other components using
        the get_component() method, enabling inter-component communication.

        Args:
            name: Unique name for the component
            component: The QObject-based component to register

        Raises:
            ValueError: If a component with the same name is already registered
        """
        if name in self.components:
            raise ValueError(f"Component '{name}' is already registered")

        self.components[name] = component

    def get_component(self, name: str) -> QObject | None:
        """
        Get a registered component by name.

        Args:
            name: The name of the component to retrieve

        Returns:
            The registered component or None if not found
        """
        return self.components.get(name)

    def has_component(self, name: str) -> bool:
        """
        Check if a component is registered.

        Args:
            name: The name of the component to check

        Returns:
            True if the component is registered, False otherwise
        """
        return name in self.components

    def unregister_component(self, name: str) -> None:
        """
        Remove a component from the registry.

        This can be useful for cleanup or when components are dynamically
        replaced during the dialog lifecycle.

        Args:
            name: The name of the component to remove

        Raises:
            KeyError: If the component is not registered
        """
        if name not in self.components:
            raise KeyError(f"Component '{name}' is not registered")
        del self.components[name]
