"""
Embedded sprite editor tab for SpritePal main UI.

Wraps the sprite editor components for integration with the main application.
Unlike the standalone SpriteEditorMainWindow, this embeds just the tab content
without menus/toolbar/statusbar (those are handled by the main SpritePal window).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.sprite_editor.controllers.main_controller import MainController
from ui.sprite_editor.views.tabs import EditTab, ExtractTab, InjectTab, MultiPaletteTab

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager

logger = logging.getLogger(__name__)


class SpriteEditTab(QWidget):
    """
    Wrapper panel embedding sprite editor within main SpritePal UI.

    This creates the 4 sprite editor tabs (Extract, Edit, Inject, Multi-Palette)
    and coordinates them via MainController, but without the menus/toolbar/statusbar
    that the standalone editor has.

    Signals:
        status_message: Emitted for status updates (routed to main status bar)
    """

    # Signals
    status_message = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_manager: ApplicationStateManager | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager

        # Create controller first (it creates sub-controllers)
        self._controller = MainController(self)
        self._controller.status_message.connect(self.status_message.emit)

        # Setup UI
        self._setup_ui()

        # Wire controllers to tabs (manually, since we don't have SpriteEditorMainWindow)
        self._wire_controllers()

        logger.debug("SpriteEditTab initialized")

    def _setup_ui(self) -> None:
        """Setup the embedded editor UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with action buttons (replaces toolbar)
        header = self._create_header()
        layout.addWidget(header)

        # Internal tab widget with 4 tabs
        self._tab_widget = QTabWidget()
        self._tab_widget.currentChanged.connect(self._on_internal_tab_changed)

        # Create tabs
        self._extract_tab = ExtractTab(settings_manager=self._settings_manager)
        self._edit_tab = EditTab()
        self._inject_tab = InjectTab(settings_manager=self._settings_manager)
        self._multi_palette_tab = MultiPaletteTab()

        # Add tabs
        self._tab_widget.addTab(self._extract_tab, "Extract")
        self._tab_widget.addTab(self._edit_tab, "Edit")
        self._tab_widget.addTab(self._inject_tab, "Inject")
        self._tab_widget.addTab(self._multi_palette_tab, "Multi-Palette")

        layout.addWidget(self._tab_widget)

    def _create_header(self) -> QWidget:
        """Create header with action buttons."""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(8)

        # Label
        label = QLabel("Sprite Editor")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        layout.addStretch()

        # Undo/Redo buttons
        self._undo_btn = QPushButton("Undo")
        self._undo_btn.setEnabled(False)
        self._undo_btn.clicked.connect(self._controller.editing_controller.undo)
        layout.addWidget(self._undo_btn)

        self._redo_btn = QPushButton("Redo")
        self._redo_btn.setEnabled(False)
        self._redo_btn.clicked.connect(self._controller.editing_controller.redo)
        layout.addWidget(self._redo_btn)

        # Tool buttons
        self._pencil_btn = QPushButton("Pencil")
        self._pencil_btn.setCheckable(True)
        self._pencil_btn.setChecked(True)
        self._pencil_btn.clicked.connect(
            lambda: self._controller.editing_controller.set_tool("pencil")
        )
        layout.addWidget(self._pencil_btn)

        self._fill_btn = QPushButton("Fill")
        self._fill_btn.setCheckable(True)
        self._fill_btn.clicked.connect(
            lambda: self._controller.editing_controller.set_tool("fill")
        )
        layout.addWidget(self._fill_btn)

        self._picker_btn = QPushButton("Picker")
        self._picker_btn.setCheckable(True)
        self._picker_btn.clicked.connect(
            lambda: self._controller.editing_controller.set_tool("picker")
        )
        layout.addWidget(self._picker_btn)

        return header

    def _wire_controllers(self) -> None:
        """Wire controllers to tabs without SpriteEditorMainWindow."""
        # Connect tabs to their controllers
        self._controller.extraction_controller.set_view(self._extract_tab)
        self._controller.editing_controller.set_view(self._edit_tab)
        self._controller.injection_controller.set_view(self._inject_tab)
        self._controller.extraction_controller.set_multi_palette_view(
            self._multi_palette_tab
        )

        # Connect undo/redo state updates
        self._controller.editing_controller.undoStateChanged.connect(
            self._update_undo_state
        )

        # Connect tool state updates
        self._controller.editing_controller.toolChanged.connect(self._update_tool_state)

        # Connect edit tab workflow signals
        self._edit_tab.ready_for_inject.connect(self._on_ready_for_inject)

        logger.debug("Controllers wired to embedded tabs")

    def _update_undo_state(self, can_undo: bool, can_redo: bool) -> None:
        """Sync undo/redo button state from editing controller."""
        self._undo_btn.setEnabled(can_undo)
        self._redo_btn.setEnabled(can_redo)

    def _update_tool_state(self, tool_name: str) -> None:
        """Sync tool button checkmarks from editing controller."""
        self._pencil_btn.setChecked(tool_name == "pencil")
        self._fill_btn.setChecked(tool_name == "fill")
        self._picker_btn.setChecked(tool_name == "picker")

    def _on_internal_tab_changed(self, index: int) -> None:
        """Handle internal tab change."""
        states = ["extract", "edit", "inject", "multi_palette"]
        if 0 <= index < len(states):
            self._controller.workflow_state_changed.emit(states[index])

    def _on_ready_for_inject(self) -> None:
        """Handle 'ready for inject' from edit tab."""
        # Delegate to controller
        self._controller._on_ready_for_inject()
        # Switch to inject tab
        self._tab_widget.setCurrentIndex(2)

    # Public API

    def jump_to_offset(self, offset: int) -> None:
        """
        Jump to a ROM offset for extraction.

        Called from RecentCapturesWidget when user activates a captured offset.

        Args:
            offset: ROM offset to load
        """
        logger.info("SpriteEditTab.jump_to_offset: 0x%06X", offset)

        # Switch to extract tab
        self._tab_widget.setCurrentIndex(0)

        # Set the offset in the extract tab
        # The ExtractTab has an offset input field we can populate
        offset_hex = f"0x{offset:06X}"
        offset_input = getattr(self._extract_tab, "_offset_input", None)
        if offset_input is not None:
            offset_input.setText(offset_hex)
            self.status_message.emit(f"Offset set to {offset_hex}")
        else:
            logger.warning("ExtractTab doesn't have _offset_input attribute")

    def switch_to_extract(self) -> None:
        """Switch to Extract tab."""
        self._tab_widget.setCurrentIndex(0)

    def switch_to_edit(self) -> None:
        """Switch to Edit tab."""
        self._tab_widget.setCurrentIndex(1)

    def switch_to_inject(self) -> None:
        """Switch to Inject tab."""
        self._tab_widget.setCurrentIndex(2)

    def cleanup(self) -> None:
        """Clean up resources before destruction."""
        logger.debug("Cleaning up SpriteEditTab")
        self._controller.cleanup()
