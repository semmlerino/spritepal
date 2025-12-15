"""
Consolidated UI Coordinator Manager for SpritePal.

This manager combines menu bar, toolbar, and status bar management
into a single cohesive unit for better UI coordination.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, override

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QProgressBar,
    QStatusBar,
    QToolBar,
)

from .base_manager import BaseManager

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

class MenuBarActionsProtocol(Protocol):
    """Protocol defining menu bar action handlers."""

    def new_extraction(self) -> None: ...
    def show_settings(self) -> None: ...
    def show_cache_manager(self) -> None: ...
    def clear_all_caches(self) -> None: ...

class ToolBarActionsProtocol(Protocol):
    """Protocol defining toolbar action handlers."""

    def quick_extract(self) -> None: ...
    def quick_inject(self) -> None: ...
    def toggle_preview(self) -> None: ...
    def refresh_view(self) -> None: ...

class UICoordinatorManager(BaseManager):
    """
    Consolidated manager for all UI coordination:
    - Menu bar management
    - Toolbar management
    - Status bar management
    - Unified action handling

    This manager provides centralized UI component management with
    consistent theming, state synchronization, and action coordination.
    """

    # UI update signals
    menu_action_triggered = Signal(str)  # Action name
    toolbar_action_triggered = Signal(str)  # Action name
    status_message = Signal(str, int)  # Message, timeout
    progress_update = Signal(int, int, str)  # Current, total, message

    def __init__(self, main_window: QMainWindow | None = None,
                 parent: QObject | None = None) -> None:
        """
        Initialize UI coordinator manager.

        Args:
            main_window: Main application window
            parent: Qt parent object
        """
        # Store main window reference
        self._main_window = main_window

        # UI components
        self._menu_bar: QMenuBar | None = None
        self._tool_bar: QToolBar | None = None
        self._status_bar: QStatusBar | None = None

        # Status bar widgets
        self._status_label: QLabel | None = None
        self._progress_bar: QProgressBar | None = None
        self._permanent_widgets: dict[str, QWidget] = {}

        # Action handlers
        self._menu_actions: dict[str, Callable[[], None]] = {}
        self._toolbar_actions: dict[str, Callable[[], None]] = {}

        # UI state
        self._toolbar_visible = True
        self._status_bar_visible = True
        self._menu_state: dict[str, bool] = {}  # Action name -> enabled state

        # Create adapters
        self._menu_adapter: MenuBarAdapter | None = None
        self._toolbar_adapter: ToolBarAdapter | None = None
        self._status_adapter: StatusBarAdapter | None = None

        super().__init__("UICoordinatorManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize UI components."""
        try:
            if self._main_window:
                self._setup_ui_components()

            # Create adapters
            self._menu_adapter = MenuBarAdapter(self)
            self._toolbar_adapter = ToolBarAdapter(self)
            self._status_adapter = StatusBarAdapter(self)

            self._is_initialized = True
            self._logger.info("UICoordinatorManager initialized successfully")

        except Exception as e:
            self._handle_error(e, "initialization")
            raise

    @override
    def cleanup(self) -> None:
        """Cleanup UI resources."""
        # Clear action handlers
        self._menu_actions.clear()
        self._toolbar_actions.clear()

        # Clear widget references
        self._permanent_widgets.clear()

        self._logger.info("UICoordinatorManager cleaned up")

    def set_main_window(self, main_window: QMainWindow) -> None:
        """
        Set or update the main window.

        Args:
            main_window: Main application window
        """
        self._main_window = main_window
        if self._is_initialized:
            self._setup_ui_components()

    def _setup_ui_components(self) -> None:
        """Setup UI components from main window."""
        if not self._main_window:
            return

        # Get or create menu bar
        self._menu_bar = self._main_window.menuBar()

        # Get or create toolbar
        existing_toolbars = self._main_window.findChildren(QToolBar)
        if existing_toolbars:
            self._tool_bar = existing_toolbars[0]
        else:
            self._tool_bar = QToolBar("Main Toolbar")
            self._main_window.addToolBar(self._tool_bar)

        # Get or create status bar
        self._status_bar = self._main_window.statusBar()
        self._setup_status_bar()

    def _setup_status_bar(self) -> None:
        """Setup status bar components."""
        if not self._status_bar:
            return

        # Create status label
        self._status_label = QLabel("Ready")
        self._status_bar.addWidget(self._status_label)

        # Create progress bar (hidden by default)
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._status_bar.addWidget(self._progress_bar)

    # ========== Menu Bar Management ==========

    def create_menu(self, menu_name: str) -> QMenu | None:
        """
        Create a new menu in the menu bar.

        Args:
            menu_name: Name of the menu

        Returns:
            Created menu or None if no menu bar
        """
        if not self._menu_bar:
            return None

        menu = self._menu_bar.addMenu(menu_name)
        return menu

    def add_menu_action(self, menu_name: str, action_name: str,
                       handler: Callable[[], None],
                       shortcut: str | None = None,
                       checkable: bool = False) -> QAction | None:
        """
        Add an action to a menu.

        Args:
            menu_name: Name of the menu
            action_name: Name of the action
            handler: Action handler function
            shortcut: Optional keyboard shortcut
            checkable: Whether action is checkable

        Returns:
            Created action or None
        """
        if not self._menu_bar or not self._main_window:
            return None

        # Find or create menu
        menu = None
        for action in self._menu_bar.actions():
            if action.menu() and action.text() == menu_name:
                menu = action.menu()
                break

        if not menu:
            menu = self.create_menu(menu_name)

        if not menu:
            return None

        # Create action
        action = QAction(action_name, self._main_window)

        if shortcut:
            action.setShortcut(shortcut)

        action.setCheckable(checkable)

        # Connect handler
        action_id = f"{menu_name}.{action_name}"
        self._menu_actions[action_id] = handler
        action.triggered.connect(lambda: self._handle_menu_action(action_id))

        menu.addAction(action)  # type: ignore[attr-defined]  # Qt menu method not in QObject stub
        return action

    def add_menu_separator(self, menu_name: str) -> None:
        """Add separator to menu."""
        if not self._menu_bar:
            return

        for action in self._menu_bar.actions():
            if action.menu() and action.text() == menu_name:
                action.menu().addSeparator()  # type: ignore[attr-defined]  # Qt menu method not in QObject stub
                break

    def _handle_menu_action(self, action_id: str) -> None:
        """Handle menu action trigger."""
        if action_id in self._menu_actions:
            self.menu_action_triggered.emit(action_id)
            self._menu_actions[action_id]()

    def set_menu_action_enabled(self, menu_name: str, action_name: str,
                               enabled: bool) -> None:
        """Enable or disable a menu action."""
        if not self._menu_bar:
            return

        for menu_action in self._menu_bar.actions():
            if menu_action.menu() and menu_action.text() == menu_name:
                menu = menu_action.menu()
                for action in menu.actions():  # type: ignore[attr-defined]  # Qt menu method not in QObject stub
                    if action.text() == action_name:
                        action.setEnabled(enabled)
                        self._menu_state[f"{menu_name}.{action_name}"] = enabled
                        break
                break

    # ========== Toolbar Management ==========

    def add_toolbar_action(self, action_name: str, icon_name: str | None,
                          handler: Callable[[], None],
                          tooltip: str | None = None,
                          checkable: bool = False) -> QAction | None:
        """
        Add an action to the toolbar.

        Args:
            action_name: Name of the action
            icon_name: Optional icon resource name
            handler: Action handler function
            tooltip: Optional tooltip text
            checkable: Whether action is checkable

        Returns:
            Created action or None
        """
        if not self._tool_bar or not self._main_window:
            return None

        # Create action
        action = QAction(action_name, self._main_window)

        if tooltip:
            action.setToolTip(tooltip)

        action.setCheckable(checkable)

        # TODO: Add icon support
        # if icon_name:
        #     action.setIcon(QIcon(icon_name))

        # Connect handler
        self._toolbar_actions[action_name] = handler
        action.triggered.connect(lambda: self._handle_toolbar_action(action_name))

        self._tool_bar.addAction(action)
        return action

    def add_toolbar_separator(self) -> None:
        """Add separator to toolbar."""
        if self._tool_bar:
            self._tool_bar.addSeparator()

    def add_toolbar_widget(self, widget: QWidget) -> None:
        """Add custom widget to toolbar."""
        if self._tool_bar:
            self._tool_bar.addWidget(widget)

    def _handle_toolbar_action(self, action_name: str) -> None:
        """Handle toolbar action trigger."""
        if action_name in self._toolbar_actions:
            self.toolbar_action_triggered.emit(action_name)
            self._toolbar_actions[action_name]()

    def set_toolbar_visible(self, visible: bool) -> None:
        """Show or hide toolbar."""
        if self._tool_bar:
            self._tool_bar.setVisible(visible)
            self._toolbar_visible = visible

    def set_toolbar_action_enabled(self, action_name: str, enabled: bool) -> None:
        """Enable or disable toolbar action."""
        if not self._tool_bar:
            return

        for action in self._tool_bar.actions():
            if action.text() == action_name:
                action.setEnabled(enabled)
                break

    # ========== Status Bar Management ==========

    def show_status_message(self, message: str, timeout: int = 5000) -> None:
        """
        Show a temporary status message.

        Args:
            message: Message to display
            timeout: Timeout in milliseconds (0 for permanent)
        """
        if self._status_bar:
            self._status_bar.showMessage(message, timeout)
            self.status_message.emit(message, timeout)

    def set_status_text(self, text: str) -> None:
        """Set permanent status text."""
        if self._status_label:
            self._status_label.setText(text)

    def show_progress(self, current: int, total: int,
                     message: str = "") -> None:
        """
        Show progress in status bar.

        Args:
            current: Current progress value
            total: Total progress value
            message: Optional progress message
        """
        if not self._progress_bar:
            return

        if total > 0:
            self._progress_bar.setVisible(True)
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(current)

            if message:
                self.set_status_text(message)

            self.progress_update.emit(current, total, message)
        else:
            self.hide_progress()

    def hide_progress(self) -> None:
        """Hide progress bar."""
        if self._progress_bar:
            self._progress_bar.setVisible(False)
            self.set_status_text("Ready")

    def add_permanent_widget(self, widget_id: str, widget: QWidget) -> None:
        """
        Add a permanent widget to status bar.

        Args:
            widget_id: Unique identifier for the widget
            widget: Widget to add
        """
        if self._status_bar:
            self._status_bar.addPermanentWidget(widget)
            self._permanent_widgets[widget_id] = widget

    def remove_permanent_widget(self, widget_id: str) -> None:
        """Remove permanent widget from status bar."""
        if widget_id in self._permanent_widgets and self._status_bar:
            widget = self._permanent_widgets.pop(widget_id)
            self._status_bar.removeWidget(widget)

    def set_status_bar_visible(self, visible: bool) -> None:
        """Show or hide status bar."""
        if self._status_bar:
            self._status_bar.setVisible(visible)
            self._status_bar_visible = visible

    # ========== Unified Action Management ==========

    def register_action_handler(self, action_path: str,
                               handler: Callable[[], None]) -> None:
        """
        Register a handler for an action path.

        Args:
            action_path: Action path (e.g., "File.New", "toolbar.Extract")
            handler: Handler function
        """
        if action_path.startswith("toolbar."):
            action_name = action_path[8:]  # Remove "toolbar." prefix
            self._toolbar_actions[action_name] = handler
        else:
            self._menu_actions[action_path] = handler

    def trigger_action(self, action_path: str) -> None:
        """
        Programmatically trigger an action.

        Args:
            action_path: Action path to trigger
        """
        if action_path in self._menu_actions:
            self._menu_actions[action_path]()
        elif action_path.startswith("toolbar."):
            action_name = action_path[8:]
            if action_name in self._toolbar_actions:
                self._toolbar_actions[action_name]()

    def update_ui_state(self, state: dict[str, Any]) -> None:
        """
        Update UI state based on application state.

        Args:
            state: State dictionary with UI settings
        """
        # Update menu states
        for action_path, enabled in state.get("menu_states", {}).items():
            parts = action_path.split(".")
            if len(parts) == 2:
                self.set_menu_action_enabled(parts[0], parts[1], enabled)

        # Update toolbar states
        for action_name, enabled in state.get("toolbar_states", {}).items():
            self.set_toolbar_action_enabled(action_name, enabled)

        # Update visibility
        if "toolbar_visible" in state:
            self.set_toolbar_visible(state["toolbar_visible"])

        if "status_bar_visible" in state:
            self.set_status_bar_visible(state["status_bar_visible"])

    # ========== Backward Compatibility Adapters ==========

    def get_menu_bar_adapter(self) -> MenuBarAdapter:
        """Get menu bar manager adapter."""
        if not self._menu_adapter:
            self._menu_adapter = MenuBarAdapter(self)
        return self._menu_adapter

    def get_toolbar_adapter(self) -> ToolBarAdapter:
        """Get toolbar manager adapter."""
        if not self._toolbar_adapter:
            self._toolbar_adapter = ToolBarAdapter(self)
        return self._toolbar_adapter

    def get_status_bar_adapter(self) -> StatusBarAdapter:
        """Get status bar manager adapter."""
        if not self._status_adapter:
            self._status_adapter = StatusBarAdapter(self)
        return self._status_adapter

class MenuBarAdapter:
    """Adapter providing MenuBarManager interface."""

    def __init__(self, coordinator: UICoordinatorManager):
        self.window = coordinator._main_window
        self.coordinator = coordinator
        self.actions_handler = None

    def create_menus(self) -> None:
        """Create standard application menus."""
        # File menu
        self.coordinator.create_menu("File")
        self.coordinator.add_menu_action("File", "New Extraction",
                                        self._new_extraction, "Ctrl+N")
        self.coordinator.add_menu_separator("File")
        self.coordinator.add_menu_action("File", "Exit",
                                        self._exit, "Ctrl+Q")

        # Tools menu
        self.coordinator.create_menu("Tools")
        self.coordinator.add_menu_action("Tools", "Settings...",
                                        self._show_settings, "Ctrl+,")
        self.coordinator.add_menu_action("Tools", "Cache Manager...",
                                        self._show_cache_manager)

        # Help menu
        self.coordinator.create_menu("Help")
        self.coordinator.add_menu_action("Help", "About",
                                        self._show_about)

    def _new_extraction(self) -> None:
        if self.actions_handler:
            self.actions_handler.new_extraction()

    def _show_settings(self) -> None:
        if self.actions_handler:
            self.actions_handler.show_settings()

    def _show_cache_manager(self) -> None:
        if self.actions_handler:
            self.actions_handler.show_cache_manager()

    def _show_about(self) -> None:
        pass  # Implement about dialog

    def _exit(self) -> None:
        if self.window:
            self.window.close()

class ToolBarAdapter:
    """Adapter providing ToolBarManager interface."""

    def __init__(self, coordinator: UICoordinatorManager):
        self.coordinator = coordinator
        self.window = coordinator._main_window

    def create_toolbar(self) -> None:
        """Create standard toolbar actions."""
        self.coordinator.add_toolbar_action("Extract", None,
                                           lambda: None, "Quick Extract")
        self.coordinator.add_toolbar_action("Inject", None,
                                           lambda: None, "Quick Inject")
        self.coordinator.add_toolbar_separator()
        self.coordinator.add_toolbar_action("Preview", None,
                                           lambda: None, "Toggle Preview", True)
        self.coordinator.add_toolbar_action("Refresh", None,
                                           lambda: None, "Refresh View")

    def set_visible(self, visible: bool) -> None:
        self.coordinator.set_toolbar_visible(visible)

    def set_action_enabled(self, action: str, enabled: bool) -> None:
        self.coordinator.set_toolbar_action_enabled(action, enabled)

class StatusBarAdapter:
    """Adapter providing StatusBarManager interface."""

    def __init__(self, coordinator: UICoordinatorManager):
        self.coordinator = coordinator
        self.window = coordinator._main_window

    def show_message(self, message: str, timeout: int = 5000) -> None:
        self.coordinator.show_status_message(message, timeout)

    def set_text(self, text: str) -> None:
        self.coordinator.set_status_text(text)

    def show_progress(self, value: int, maximum: int) -> None:
        self.coordinator.show_progress(value, maximum)

    def hide_progress(self) -> None:
        self.coordinator.hide_progress()

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        import uuid
        widget_id = str(uuid.uuid4())
        self.coordinator.add_permanent_widget(widget_id, widget)
