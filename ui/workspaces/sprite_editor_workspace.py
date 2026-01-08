#!/usr/bin/env python3
"""
Sprite Editor Workspace - top-level container for sprite editing.

This workspace provides the complete sprite editing experience with:
- Header: Mode switch (VRAM/ROM) + undo/redo buttons
- Mode stack: VRAMEditorPage or ROMWorkflowPage based on mode selection

Unlike the old SpriteEditTab which used tab hiding and reparenting,
this workspace uses a QStackedWidget for clean mode switching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.sprite_editor.controllers.main_controller import MainController
from ui.sprite_editor.views.workspaces import ROMWorkflowPage, VRAMEditorPage

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager

logger = logging.getLogger(__name__)


class SpriteEditorWorkspace(QWidget):
    """Top-level workspace for sprite editing.

    This workspace provides:
    - Header with mode switch (VRAM/ROM) and undo/redo buttons
    - QStackedWidget for mode switching (no reparenting needed)
    - Coordinates controllers across both mode pages

    Signals:
        status_message: Emitted for status updates (routed to main status bar)
        mode_changed: Emitted when mode switches ('vram' or 'rom')
    """

    # Signals
    status_message = Signal(str)
    mode_changed = Signal(str)  # 'vram' or 'rom'
    undo_state_changed = Signal(bool, bool)  # can_undo, can_redo
    offset_changed = Signal(int)

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

        # Wire controllers to pages
        self._wire_controllers()

        logger.debug("SpriteEditorWorkspace initialized")

    def _setup_ui(self) -> None:
        """Create the workspace UI."""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header with mode switch (undo/redo moved to main toolbar)
        header = self._create_header()
        layout.addWidget(header)

        # Mode stack (replaces tab widget with hide/show logic)
        self._mode_stack = QStackedWidget()
        self._mode_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Create mode pages
        self._vram_page = VRAMEditorPage(settings_manager=self._settings_manager)
        self._rom_page = ROMWorkflowPage()

        # Hide "Pop Out Editor" button in embedded mode
        if hasattr(self._vram_page.edit_tab, "detach_btn"):
            self._vram_page.edit_tab.detach_btn.hide()

        # Add pages to stack
        self._mode_stack.addWidget(self._vram_page)  # Index 0: VRAM mode
        self._mode_stack.addWidget(self._rom_page)  # Index 1: ROM mode

        layout.addWidget(self._mode_stack, 1)

    def _create_header(self) -> QWidget:
        """Create header with mode switch."""
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

        return header

    def _wire_controllers(self) -> None:
        """Wire controllers to mode pages."""
        # Get editing controller (shared between both pages)
        editing_ctrl = self._controller.editing_controller

        # Wire VRAM page
        self._controller.extraction_controller.set_view(self._vram_page.extract_tab)
        editing_ctrl.set_view(self._vram_page.edit_tab)
        self._controller.injection_controller.set_view(self._vram_page.inject_tab)
        self._controller.extraction_controller.set_multi_palette_view(self._vram_page.multi_palette_tab)

        # Wire ROM page's workspace to the same editing controller
        # This is the key: both pages share the same EditingController
        self._rom_page.workspace.set_controller(editing_ctrl)

        # Wire ROM workflow controller to ROM page
        self._controller.rom_workflow_controller.set_view(self._rom_page)

        # Connect undo/redo state updates (forwarded to signal)
        editing_ctrl.undoStateChanged.connect(self.undo_state_changed.emit)

        # Connect offset changed
        self._rom_page.offset_changed.connect(self.offset_changed.emit)

        # Connect ready_for_inject from VRAM page
        self._vram_page.ready_for_inject.connect(self._on_ready_for_inject)

        # Connect mode change
        self.mode_changed.connect(self._controller.set_mode)
        self.mode_changed.connect(self._on_mode_switched)

        logger.debug("Controllers wired to workspace pages")

    def undo(self) -> None:
        """Trigger undo action."""
        self._controller.editing_controller.undo()

    def redo(self) -> None:
        """Trigger redo action."""
        self._controller.editing_controller.redo()

    def _on_mode_changed(self, index: int) -> None:
        """Handle mode combo box change."""
        mode = self._mode_combo.currentData()
        logger.info("Mode combo changed to index %s, mode=%s", index, mode)
        self.mode_changed.emit(mode)

    def _on_mode_switched(self, mode: str) -> None:
        """Handle UI switching between VRAM and ROM workflows.

        This is now simple: just switch the stacked widget page.
        No reparenting, no tab hiding, no forced visibility cascades.
        """
        if mode == "rom":
            self._mode_stack.setCurrentWidget(self._rom_page)
            logger.info("Switched to ROM workflow page")
        else:
            self._mode_stack.setCurrentWidget(self._vram_page)
            logger.info("Switched to VRAM workflow page")

    def _on_ready_for_inject(self) -> None:
        """Handle 'ready for inject' from edit tab."""
        # Switch to inject tab in VRAM page
        self._vram_page.switch_to_inject_tab()
        logger.debug("Switched to inject tab")

    # Public API for external access
    @property
    def controller(self) -> MainController:
        """Access the main controller."""
        return self._controller

    @property
    def vram_page(self) -> VRAMEditorPage:
        """Access the VRAM workflow page."""
        return self._vram_page

    @property
    def rom_page(self) -> ROMWorkflowPage:
        """Access the ROM workflow page."""
        return self._rom_page

    @property
    def mode_combo(self) -> QComboBox:
        """Access the mode combo box."""
        return self._mode_combo

    def set_mode(self, mode: str) -> None:
        """Programmatically set the mode."""
        index = 0 if mode == "vram" else 1
        self._mode_combo.setCurrentIndex(index)

    def jump_to_offset(self, offset: int, *, auto_open: bool = True) -> None:
        """Jump to a specific ROM offset.

        Switches to ROM mode and navigates to the offset.

        Args:
            offset: ROM offset to navigate to.
            auto_open: If True, automatically open in editor when preview completes.
                       Defaults to True for better UX (user expects double-click to edit).
        """
        # Switch to ROM mode
        self._mode_combo.setCurrentIndex(1)

        # Set offset in ROM workflow controller (auto_open triggers editor after preview)
        self._controller.rom_workflow_controller.set_offset(offset, auto_open=auto_open)

    def load_rom(self, path: str) -> None:
        """Load a ROM into the sprite editor.

        Delegates to the ROM workflow controller.
        """
        self._controller.rom_workflow_controller.load_rom(path)

    # Backward compatibility: expose tabs that old code might access
    @property
    def _extract_tab(self):
        """Backward compatibility accessor."""
        return self._vram_page.extract_tab

    @property
    def _edit_tab(self):
        """Backward compatibility accessor."""
        return self._vram_page.edit_tab

    @property
    def _inject_tab(self):
        """Backward compatibility accessor."""
        return self._vram_page.inject_tab

    @property
    def _multi_palette_tab(self):
        """Backward compatibility accessor."""
        return self._vram_page.multi_palette_tab
