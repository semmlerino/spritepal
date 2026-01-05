#!/usr/bin/env python3
"""
Main window for the unified sprite editor.
Combines extract, edit, inject, and multi-palette tabs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .tabs import EditTab, ExtractTab, InjectTab, MultiPaletteTab

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager


class SpriteEditorMainWindow(QMainWindow):
    """Main window for the unified sprite editor application."""

    # Signals
    tab_changed = Signal(int)
    file_open_requested = Signal()
    file_save_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_manager: ApplicationStateManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("SpritePal Unified Editor")
        self.setMinimumSize(1000, 700)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the main UI layout."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Create tabs
        self.extract_tab = ExtractTab(settings_manager=self.settings_manager)
        self.edit_tab = EditTab()
        self.inject_tab = InjectTab(settings_manager=self.settings_manager)
        self.multi_palette_tab = MultiPaletteTab()

        # Add tabs to tab widget
        self.tab_widget.addTab(self.extract_tab, "Extract")
        self.tab_widget.addTab(self.edit_tab, "Edit")
        self.tab_widget.addTab(self.inject_tab, "Inject")
        self.tab_widget.addTab(self.multi_palette_tab, "Multi-Palette")

        # Add tab widget to layout
        layout.addWidget(self.tab_widget)

        # Setup menus, toolbar, and status bar
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()


    def _setup_menus(self) -> None:
        """Setup the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self.action_open_vram = QAction("Open &VRAM...", self)
        self.action_open_vram.setShortcut(QKeySequence.StandardKey.Open)
        file_menu.addAction(self.action_open_vram)

        self.action_open_cgram = QAction("Open &CGRAM...", self)
        self.action_open_cgram.setShortcut("Ctrl+G")
        file_menu.addAction(self.action_open_cgram)

        self.action_open_png = QAction("Open &PNG...", self)
        self.action_open_png.setShortcut("Ctrl+P")
        file_menu.addAction(self.action_open_png)

        file_menu.addSeparator()

        self.action_save = QAction("&Save...", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        file_menu.addAction(self.action_save)

        self.action_save_as = QAction("Save &As...", self)
        self.action_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        file_menu.addAction(self.action_save_as)

        file_menu.addSeparator()

        self.action_exit = QAction("E&xit", self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_exit.triggered.connect(self.close)
        file_menu.addAction(self.action_exit)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self.action_undo = QAction("&Undo", self)
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(self.action_undo)

        self.action_redo = QAction("&Redo", self)
        self.action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(self.action_redo)

        # View menu
        view_menu = menubar.addMenu("&View")

        self.action_extract_tab = QAction("&Extract Tab", self)
        self.action_extract_tab.setShortcut("Ctrl+1")
        self.action_extract_tab.triggered.connect(lambda: self.switch_to_tab(0))
        view_menu.addAction(self.action_extract_tab)

        self.action_edit_tab = QAction("E&dit Tab", self)
        self.action_edit_tab.setShortcut("Ctrl+2")
        self.action_edit_tab.triggered.connect(lambda: self.switch_to_tab(1))
        view_menu.addAction(self.action_edit_tab)

        self.action_inject_tab = QAction("&Inject Tab", self)
        self.action_inject_tab.setShortcut("Ctrl+3")
        self.action_inject_tab.triggered.connect(lambda: self.switch_to_tab(2))
        view_menu.addAction(self.action_inject_tab)

        self.action_multi_palette_tab = QAction("&Multi-Palette Tab", self)
        self.action_multi_palette_tab.setShortcut("Ctrl+4")
        self.action_multi_palette_tab.triggered.connect(lambda: self.switch_to_tab(3))
        view_menu.addAction(self.action_multi_palette_tab)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        self.action_pencil = QAction("&Pencil", self)
        self.action_pencil.setShortcut("P")
        self.action_pencil.setCheckable(True)
        self.action_pencil.setChecked(True)  # Default tool
        tools_menu.addAction(self.action_pencil)

        self.action_fill = QAction("&Fill", self)
        self.action_fill.setShortcut("F")
        self.action_fill.setCheckable(True)
        tools_menu.addAction(self.action_fill)

        self.action_picker = QAction("Color &Picker", self)
        self.action_picker.setShortcut("I")
        self.action_picker.setCheckable(True)
        tools_menu.addAction(self.action_picker)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        self.action_about = QAction("&About", self)
        help_menu.addAction(self.action_about)

    def _setup_toolbar(self) -> None:
        """Setup the toolbar."""
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        toolbar.addAction(self.action_open_vram)
        toolbar.addAction(self.action_open_cgram)
        toolbar.addSeparator()
        toolbar.addAction(self.action_undo)
        toolbar.addAction(self.action_redo)
        toolbar.addSeparator()
        toolbar.addAction(self.action_pencil)
        toolbar.addAction(self.action_fill)
        toolbar.addAction(self.action_picker)

    def _setup_statusbar(self) -> None:
        """Setup the status bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        # Add permanent widgets
        self.status_label = QLabel("Ready")
        self.statusbar.addWidget(self.status_label, 1)

        self.coords_label = QLabel("")
        self.statusbar.addPermanentWidget(self.coords_label)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change."""
        self.tab_changed.emit(index)

    def switch_to_tab(self, index: int) -> None:
        """Switch to a specific tab."""
        if 0 <= index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(index)

    def show_extract_tab(self) -> None:
        """Show the extract tab."""
        self.switch_to_tab(0)

    def show_edit_tab(self) -> None:
        """Show the edit tab."""
        self.switch_to_tab(1)

    def show_inject_tab(self) -> None:
        """Show the inject tab."""
        self.switch_to_tab(2)

    def show_multi_palette_tab(self) -> None:
        """Show the multi-palette tab."""
        self.switch_to_tab(3)

    def set_status(self, message: str) -> None:
        """Set the status bar message."""
        self.status_label.setText(message)

    def set_coords(self, x: int, y: int) -> None:
        """Set the coordinates display."""
        self.coords_label.setText(f"({x}, {y})")

    def clear_coords(self) -> None:
        """Clear the coordinates display."""
        self.coords_label.setText("")
