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
    from ui.sprite_editor.controllers import (
        EditingController,
        ExtractionController,
        InjectionController,
    )
    from ui.sprite_editor.controllers.rom_workflow_controller import (
        ROMWorkflowController,
    )


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
        # Initialize controller references before super().__init__()
        self._extraction_controller: ExtractionController | None = None
        self._editing_controller: EditingController | None = None
        self._injection_controller: InjectionController | None = None
        self._rom_workflow_controller: ROMWorkflowController | None = None

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

    def _connect_canvas_signals(self, canvas) -> None:  # type: ignore[reportExplicitAny]
        """Connect canvas signals to status bar updates.

        Args:
            canvas: The PixelCanvas instance to connect
        """
        canvas.hoverPositionChanged.connect(self._on_canvas_hover)

    def _on_canvas_hover(self, x: int, y: int) -> None:
        """Handle canvas hover position changes.

        Args:
            x: X coordinate (-1 if no position)
            y: Y coordinate (-1 if no position)
        """
        if x >= 0 and y >= 0:
            self.set_coords(x, y)
        else:
            self.clear_coords()

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

    def wire_controllers(
        self,
        extraction_controller: ExtractionController,
        editing_controller: EditingController,
        injection_controller: InjectionController,
        rom_workflow_controller: ROMWorkflowController | None = None,
    ) -> None:
        """Wire menu actions to controller methods.

        Called by SpriteEditorApplication after creating controllers.

        Args:
            extraction_controller: Controller for sprite extraction
            editing_controller: Controller for sprite editing
            injection_controller: Controller for sprite injection
            rom_workflow_controller: Controller for ROM workflow (optional)
        """
        # Store references for later use
        self._extraction_controller = extraction_controller
        self._editing_controller = editing_controller
        self._injection_controller = injection_controller
        self._rom_workflow_controller = rom_workflow_controller

        # File menu
        self.action_open_vram.triggered.connect(extraction_controller.browse_vram_file)
        self.action_open_cgram.triggered.connect(extraction_controller.browse_cgram_file)
        self.action_open_png.triggered.connect(injection_controller.browse_png_file)
        self.action_save.triggered.connect(editing_controller.save_image)
        self.action_save_as.triggered.connect(editing_controller.save_image_as)

        # Edit menu
        self.action_undo.triggered.connect(editing_controller.undo)
        self.action_redo.triggered.connect(editing_controller.redo)

        # Tools menu
        self.action_pencil.triggered.connect(lambda: editing_controller.set_tool("pencil"))
        self.action_fill.triggered.connect(lambda: editing_controller.set_tool("fill"))
        self.action_picker.triggered.connect(lambda: editing_controller.set_tool("picker"))

        # Tool state sync
        editing_controller.toolChanged.connect(self._update_tool_menu)

    def _update_tool_menu(self, tool: str) -> None:
        """Update tool menu checkmarks based on current tool.

        Args:
            tool: The current tool name ("pencil", "fill", or "picker")
        """
        self.action_pencil.setChecked(tool == "pencil")
        self.action_fill.setChecked(tool == "fill")
        self.action_picker.setChecked(tool == "picker")
