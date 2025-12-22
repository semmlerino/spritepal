"""
Menu bar management for MainWindow
"""
from __future__ import annotations

from typing import Protocol

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenuBar, QMessageBox


class MenuBarActionsProtocol(Protocol):
    """Protocol defining the interface for menu bar actions"""

    def new_extraction(self) -> None:
        """Start a new extraction"""
        ...

    def show_settings(self) -> None:
        """Show settings dialog"""
        ...

    def show_presets(self) -> None:
        """Show sprite presets dialog"""
        ...

    def show_cache_manager(self) -> None:
        """Show cache manager dialog"""
        ...

    def clear_all_caches(self) -> None:
        """Clear all caches with confirmation"""
        ...

class MenuBarManager:
    """Manages menu bar creation and actions for MainWindow"""

    def __init__(self, window: QMainWindow, actions_handler: MenuBarActionsProtocol) -> None:
        """Initialize menu bar manager

        Args:
            window: The main window to create menus for
            actions_handler: Handler for menu actions
        """
        self.window = window
        self.actions_handler = actions_handler

    def create_menus(self) -> None:
        """Create application menus"""
        menubar = self.window.menuBar()
        if not menubar:
            return

        self._create_file_menu(menubar)
        self._create_tools_menu(menubar)
        self._create_help_menu(menubar)

    def _create_file_menu(self, menubar: QMenuBar) -> None:
        """Create File menu"""
        file_menu = menubar.addMenu("File")

        # New extraction
        new_action = QAction("New Extraction", self.window)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.actions_handler.new_extraction)
        if file_menu:
            file_menu.addAction(new_action)
            file_menu.addSeparator()

        # Exit
        exit_action = QAction("Exit", self.window)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.window.close)
        if file_menu:
            file_menu.addAction(exit_action)

    def _create_tools_menu(self, menubar: QMenuBar) -> None:
        """Create Tools menu"""
        tools_menu = menubar.addMenu("Tools")

        # Settings
        settings_action = QAction("Settings...", self.window)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.actions_handler.show_settings)
        if tools_menu:
            tools_menu.addAction(settings_action)

        # Manage Presets
        presets_action = QAction("Manage Presets...", self.window)
        presets_action.setShortcut("Ctrl+P")
        presets_action.triggered.connect(self.actions_handler.show_presets)
        if tools_menu:
            tools_menu.addAction(presets_action)
            tools_menu.addSeparator()

        # Cache Manager
        cache_manager_action = QAction("Cache Manager...", self.window)
        cache_manager_action.triggered.connect(self.actions_handler.show_cache_manager)
        if tools_menu:
            tools_menu.addAction(cache_manager_action)
            tools_menu.addSeparator()

        # Clear All Caches
        clear_cache_action = QAction("Clear All Caches", self.window)
        clear_cache_action.triggered.connect(self.actions_handler.clear_all_caches)
        if tools_menu:
            tools_menu.addAction(clear_cache_action)

    def _create_help_menu(self, menubar: QMenuBar) -> None:
        """Create Help menu"""
        help_menu = menubar.addMenu("Help")

        # Keyboard shortcuts
        shortcuts_action = QAction("Keyboard Shortcuts", self.window)
        shortcuts_action.setShortcut("F1")
        shortcuts_action.triggered.connect(self._show_keyboard_shortcuts)
        if help_menu:
            help_menu.addAction(shortcuts_action)
            help_menu.addSeparator()

        # About
        about_action = QAction("About SpritePal", self.window)
        about_action.triggered.connect(self._show_about)
        if help_menu:
            help_menu.addAction(about_action)

    def _show_about(self) -> None:
        """Show about dialog"""
        QMessageBox.about(
            self.window,
            "About SpritePal",
            "<h2>SpritePal</h2>"
            "<p>Version 1.0.0</p>"
            "<p>A modern sprite extraction tool for SNES games.</p>"
            "<p>Simplifies sprite extraction with automatic palette association.</p>"
            "<br>"
            "<p>Part of the Kirby Super Star sprite editing toolkit.</p>"
        )

    def _show_keyboard_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog"""
        shortcuts_text = """
        <h3>Main Actions</h3>
        <table>
        <tr><td><b>Ctrl+E / F5</b></td><td>Extract sprites</td></tr>
        <tr><td><b>Ctrl+O</b></td><td>Open in editor</td></tr>
        <tr><td><b>Ctrl+R</b></td><td>Arrange rows</td></tr>
        <tr><td><b>Ctrl+G</b></td><td>Grid arrange</td></tr>
        <tr><td><b>Ctrl+I</b></td><td>Inject sprites</td></tr>
        <tr><td><b>Ctrl+N</b></td><td>New extraction</td></tr>
        <tr><td><b>Ctrl+Q</b></td><td>Exit application</td></tr>
        </table>

        <h3>Navigation</h3>
        <table>
        <tr><td><b>Ctrl+Tab</b></td><td>Next tab</td></tr>
        <tr><td><b>Ctrl+Shift+Tab</b></td><td>Previous tab</td></tr>
        <tr><td><b>Alt+N</b></td><td>Focus output name field</td></tr>
        <tr><td><b>F1</b></td><td>Show this help</td></tr>
        </table>

        <h3>ROM Manual Offset Mode</h3>
        <table>
        <tr><td><b>Ctrl+M</b></td><td>Open Manual Offset Control window</td></tr>
        <tr><td><b>Alt+Left</b></td><td>Find previous sprite (in dialog)</td></tr>
        <tr><td><b>Alt+Right</b></td><td>Find next sprite (in dialog)</td></tr>
        <tr><td><b>Page Up</b></td><td>Jump backward 64KB (in dialog)</td></tr>
        <tr><td><b>Page Down</b></td><td>Jump forward 64KB (in dialog)</td></tr>
        </table>

        <h3>Preview Window</h3>
        <table>
        <tr><td><b>G</b></td><td>Toggle grid</td></tr>
        <tr><td><b>F</b></td><td>Zoom to fit</td></tr>
        <tr><td><b>Ctrl+0</b></td><td>Reset zoom to 4x</td></tr>
        <tr><td><b>C</b></td><td>Toggle palette</td></tr>
        <tr><td><b>Mouse Wheel</b></td><td>Zoom in/out</td></tr>
        </table>
        """

        QMessageBox.information(
            self.window,
            "Keyboard Shortcuts",
            shortcuts_text
        )
