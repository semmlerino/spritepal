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
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.sprite_editor.controllers.main_controller import MainController
from ui.sprite_editor.views.tabs import EditTab, ExtractTab, InjectTab, MultiPaletteTab
from ui.sprite_editor.views.tabs.rom_workflow_tab import ROMWorkflowTab

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
    mode_changed = Signal(str)  # 'vram' or 'rom'

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

        # Internal tab widget
        self._tab_widget = QTabWidget()
        self._tab_widget.currentChanged.connect(self._on_internal_tab_changed)

        # Create tabs
        self._extract_tab = ExtractTab(settings_manager=self._settings_manager)
        self._edit_tab = EditTab()
        self._inject_tab = InjectTab(settings_manager=self._settings_manager)
        self._multi_palette_tab = MultiPaletteTab()
        self._rom_workflow_tab = ROMWorkflowTab(edit_tab=self._edit_tab)

        # Add tabs
        self._tab_widget.addTab(self._extract_tab, "Extract")
        self._tab_widget.addTab(self._edit_tab, "Edit")
        self._tab_widget.addTab(self._inject_tab, "Inject")
        self._tab_widget.addTab(self._multi_palette_tab, "Multi-Palette")
        self._tab_widget.addTab(self._rom_workflow_tab, "ROM Workflow")

        # Hide ROM Workflow tab by default (index 4)
        self._tab_widget.setTabVisible(4, False)

        # Hide "Pop Out Editor" button in embedded mode (workflow clarity)
        if hasattr(self._edit_tab, "detach_btn"):
            self._edit_tab.detach_btn.hide()

        # Add tab widget with stretch factor to fill available space
        layout.addWidget(self._tab_widget, 1)

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

        # Mode Switcher
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("VRAM Mode", "vram")
        self._mode_combo.addItem("ROM Mode", "rom")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self._mode_combo)

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

        return header

    def _wire_controllers(self) -> None:
        """Wire controllers to tabs without SpriteEditorMainWindow."""
        # Connect tabs to their controllers
        self._controller.extraction_controller.set_view(self._extract_tab)
        self._controller.editing_controller.set_view(self._edit_tab)
        self._controller.injection_controller.set_view(self._inject_tab)
        self._controller.extraction_controller.set_multi_palette_view(self._multi_palette_tab)
        self._controller.rom_workflow_controller.set_view(self._rom_workflow_tab)

        # Connect undo/redo state updates
        self._controller.editing_controller.undoStateChanged.connect(self._update_undo_state)

        # Connect edit tab workflow signals
        self._edit_tab.ready_for_inject.connect(self._on_ready_for_inject)

        # Connect mode change
        self.mode_changed.connect(self._controller.set_mode)
        self.mode_changed.connect(self._on_mode_switched)

        logger.debug("Controllers wired to embedded tabs")

    def _on_mode_switched(self, mode: str) -> None:
        """Handle UI switching between VRAM and ROM workflows."""
        is_rom = mode == "rom"
        logger.info("Mode switched to: %s", mode)

        if is_rom:
            # Move EditTab to ROM workflow container
            self._rom_workflow_tab.edit_tab_layout.addWidget(self._edit_tab)

            # Hide VRAM tabs, show ROM Workflow
            for i in range(4):
                self._tab_widget.setTabVisible(i, False)
            self._tab_widget.setTabVisible(4, True)
            self._tab_widget.setCurrentIndex(4)

            # Force visibility on all ROM workflow components
            self._rom_workflow_tab.show()
            self._rom_workflow_tab.main_splitter.show()
            self._rom_workflow_tab.left_panel.show()
            self._rom_workflow_tab.edit_tab_container.show()
            self._edit_tab.show()

            # Force layout update
            self._tab_widget.update()
            self._rom_workflow_tab.update()

            logger.info(
                "ROM Workflow: tab visible=%s, current=%s, rom_tab size=%s",
                self._tab_widget.isTabVisible(4),
                self._tab_widget.currentIndex(),
                self._rom_workflow_tab.size(),
            )
        else:
            # Move EditTab back to TabWidget at index 1
            self._tab_widget.insertTab(1, self._edit_tab, "Edit")

            # Show VRAM tabs, hide ROM Workflow
            for i in range(4):
                self._tab_widget.setTabVisible(i, True)
            self._tab_widget.setTabVisible(4, False)
            self._tab_widget.setCurrentIndex(0)

    def _update_undo_state(self, can_undo: bool, can_redo: bool) -> None:
        """Sync undo/redo button state from editing controller."""
        self._undo_btn.setEnabled(can_undo)
        self._redo_btn.setEnabled(can_redo)

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

    def _on_mode_changed(self, index: int) -> None:
        """Handle mode change."""
        mode = self._mode_combo.itemData(index)
        self.mode_changed.emit(mode)

    def set_mode(self, mode: str) -> None:
        """Set the editor mode ('vram' or 'rom')."""
        index = self._mode_combo.findData(mode)
        if index >= 0:
            if self._mode_combo.currentIndex() == index:
                # Already at this index, manually trigger the mode switch
                self._on_mode_switched(mode)
            else:
                self._mode_combo.setCurrentIndex(index)

    # Public API

    def load_rom(self, path: str) -> None:
        """Load a ROM into the sprite editor."""
        self._controller.rom_workflow_controller.load_rom(path)

    def jump_to_offset(self, offset: int) -> None:
        """
        Jump to a ROM offset for extraction.

        Called from RecentCapturesWidget when user activates a captured offset.

        Args:
            offset: ROM offset to load
        """
        logger.info("SpriteEditTab.jump_to_offset: 0x%06X", offset)

        # Switch to ROM mode
        self.set_mode("rom")

        # Use ROM workflow controller
        self._controller.rom_workflow_controller.set_offset(offset)
        self.status_message.emit(f"Offset set to 0x{offset:06X}")

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
