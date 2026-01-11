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
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
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

from ui.sprite_editor.controllers import (
    EditingController,
    ExtractionController,
    InjectionController,
)
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
from ui.sprite_editor.views.workspaces import ROMWorkflowPage, VRAMEditorPage

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.mesen_integration.log_watcher import LogWatcher
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache
    from core.sprite_library import SpriteLibrary
    from ui.managers.status_bar_manager import StatusBarManager

logger = logging.getLogger(__name__)


class SpriteEditorWorkspace(QWidget):
    """Top-level workspace for sprite editing.

    This workspace provides:
    - Header with mode switch (VRAM/ROM) and undo/redo buttons
    - QStackedWidget for mode switching (no reparenting needed)
    - Coordinates controllers across both mode pages

    Signals:
        mode_changed: Emitted when mode switches ('vram' or 'rom')

    Signal Flow:
        _mode_combo.currentIndexChanged → _on_mode_changed → mode_changed.emit
        mode_changed → _on_mode_changed_internal (propagates to sub-controllers)
        mode_changed → _on_mode_switched (switches _mode_stack page)
    """

    # Signal: mode_changed
    # Emitted by: _on_mode_changed when combo selection changes
    # Consumed by:
    #   - self._on_mode_changed_internal: propagates to extraction/injection controllers
    #   - self._on_mode_switched: switches _mode_stack between VRAM and ROM pages
    mode_changed = Signal(str)  # 'vram' or 'rom'

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings_manager: ApplicationStateManager | None = None,
        message_service: StatusBarManager | None = None,
        rom_cache: ROMCache | None = None,
        rom_extractor: ROMExtractor | None = None,
        log_watcher: LogWatcher | None = None,
        sprite_library: SpriteLibrary | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager

        # Create sub-controllers directly (no MainController wrapper)
        self._extraction_controller = ExtractionController(
            self,
            rom_cache=rom_cache,
            rom_extractor=rom_extractor,
        )
        self._editing_controller = EditingController(self)
        self._injection_controller = InjectionController(self)
        self._rom_workflow_controller = ROMWorkflowController(
            self,
            self._editing_controller,
            message_service=message_service,
            rom_cache=rom_cache,
            rom_extractor=rom_extractor,
            log_watcher=log_watcher,
            sprite_library=sprite_library,
        )

        # Track temporary files for cleanup during injection workflow
        self._temp_files: list[str] = []

        # Setup UI
        self._setup_ui()

        # Wire controllers to pages
        self._wire_controllers()

        logger.debug("SpriteEditorWorkspace initialized")

    def set_message_service(self, service: StatusBarManager | None) -> None:
        """Inject message service after construction (for deferred initialization)."""
        # Only ROM workflow controller needs message service currently
        self._rom_workflow_controller.set_message_service(service)

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
        self._mode_combo.setCurrentIndex(1)  # Default to ROM mode (Mesen2 workflow)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self._mode_combo)

        layout.addStretch()

        return header

    def _wire_controllers(self) -> None:
        """Wire controllers to mode pages."""
        # Wire VRAM page
        self._extraction_controller.set_view(self._vram_page.extract_tab)
        self._editing_controller.set_view(self._vram_page.edit_tab)
        # Wire Export PNG for VRAM mode
        self._vram_page.edit_tab.workspace.exportPngRequested.connect(self._editing_controller.save_image_as)
        self._injection_controller.set_view(self._vram_page.inject_tab)
        self._extraction_controller.set_multi_palette_view(self._vram_page.multi_palette_tab)

        # Wire ROM page's workspace to the same editing controller
        # This is the key: both pages share the same EditingController
        self._rom_page.workspace.set_controller(self._editing_controller)

        # Wire ROM workflow controller to ROM page
        self._rom_workflow_controller.set_view(self._rom_page)

        # Connect ready_for_inject from VRAM page
        self._vram_page.ready_for_inject.connect(self._on_ready_for_inject)

        # Connect injection completion for temp file cleanup
        self._injection_controller.injection_completed.connect(self._on_injection_completed)

        # Connect mode changes to propagate to extraction and injection controllers
        self.mode_changed.connect(self._on_mode_changed_internal)
        self.mode_changed.connect(self._on_mode_switched)

        # Sync stack AND controllers to match initial combo state
        # (combo was set to ROM mode before signals were wired)
        initial_mode = self._mode_combo.currentData()
        self._on_mode_switched(initial_mode)
        self._on_mode_changed_internal(initial_mode)  # Also sync controllers

        logger.debug("Controllers wired to workspace pages")

    def _on_mode_changed_internal(self, mode: str) -> None:
        """Propagate mode changes to extraction and injection controllers."""
        self._extraction_controller.set_mode(mode)
        self._injection_controller.set_mode(mode)

    def undo(self) -> None:
        """Trigger undo action."""
        self._editing_controller.undo()

    def redo(self) -> None:
        """Trigger redo action."""
        self._editing_controller.redo()

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
        """Handle 'ready for inject' from edit tab.

        Prepares the edited image as a temporary PNG file for injection.
        """
        # Get the edited image data
        image_data = self._editing_controller.get_image_data()
        if image_data is None:
            logger.warning("No image data to prepare for injection")
            return

        # Get palette
        palette = self._editing_controller.get_flat_palette()

        # Create indexed image with palette
        img = Image.fromarray(image_data, mode="P")
        img.putpalette(palette)

        # Save to temp file
        temp_dir = Path(tempfile.gettempdir())
        temp_path = str(temp_dir / f"spritepal_inject_{id(self)}.png")
        img.save(temp_path)

        # Track for cleanup
        self._temp_files.append(temp_path)

        # Pass to injection controller
        self._injection_controller.set_source_image(temp_path)

        # Check if we have a loaded ROM context to pre-fill
        if self._rom_workflow_controller.rom_path:
            logger.info("Auto-configuring Inject Tab with loaded ROM: %s", self._rom_workflow_controller.rom_path)
            # Switch Inject Tab to ROM mode
            self._injection_controller.set_mode("rom")
            # Set the ROM file
            self._injection_controller.set_rom_file(self._rom_workflow_controller.rom_path)

        # Switch to inject tab in VRAM page
        self._vram_page.switch_to_inject_tab()
        logger.debug("Prepared image for injection and switched to inject tab")

    def _on_injection_completed(self, output_path: str) -> None:
        """Handle injection completion - cleanup temp files.

        Args:
            output_path: Path to the generated VRAM/ROM file
        """
        self._cleanup_temp_files()
        logger.debug(f"Injection completed, temp files cleaned up: {output_path}")

    def _cleanup_temp_files(self) -> None:
        """Clean up temporary files created during injection workflow."""
        for path in self._temp_files:
            try:
                temp_path = Path(path)
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass  # Best effort cleanup
        self._temp_files.clear()

    # Public API for external access
    @property
    def extraction_controller(self) -> ExtractionController:
        """Access the extraction controller."""
        return self._extraction_controller

    @property
    def editing_controller(self) -> EditingController:
        """Access the editing controller."""
        return self._editing_controller

    @property
    def injection_controller(self) -> InjectionController:
        """Access the injection controller."""
        return self._injection_controller

    @property
    def rom_workflow_controller(self) -> ROMWorkflowController:
        """Access the ROM workflow controller."""
        return self._rom_workflow_controller

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

    @property
    def current_mode(self) -> str:
        """Get the current workflow mode ('vram' or 'rom')."""
        return self._mode_combo.currentData()

    def set_mode(self, mode: str) -> None:
        """Programmatically set the mode."""
        index = 0 if mode == "vram" else 1
        self._mode_combo.setCurrentIndex(index)

    def jump_to_offset(self, offset: int, *, auto_open: bool = True, capture_name: str | None = None) -> None:
        """Jump to a specific ROM offset.

        Switches to ROM mode and navigates to the offset.

        Args:
            offset: ROM offset to navigate to.
            auto_open: If True, automatically open in editor when preview completes.
                       Defaults to True for better UX (user expects double-click to edit).
            capture_name: Optional display name for the capture (e.g., "0x3C6EF1 (f1500)").
                          If provided, ensures the capture appears in asset browser.
        """
        # DEBUG PRINT - bypasses logging to verify code path
        print(f"[DEBUG PRINT] jump_to_offset: offset=0x{offset:06X}, capture_name={capture_name}", flush=True)
        # Switch to ROM mode
        self._mode_combo.setCurrentIndex(1)

        # Ensure capture is in asset browser and selected (for cross-component sync)
        self._rom_workflow_controller.ensure_and_select_capture(offset, capture_name)

        # Set offset in ROM workflow controller (auto_open triggers editor after preview)
        self._rom_workflow_controller.set_offset(offset, auto_open=auto_open)

    def load_rom(self, path: str) -> None:
        """Load a ROM into the sprite editor.

        Delegates to the ROM workflow controller.
        """
        # Switch to ROM mode first so the user sees the loaded ROM
        self.set_mode("rom")

        self._rom_workflow_controller.load_rom(path)

    def cleanup(self) -> None:
        """Clean up resources on shutdown."""
        # Clean up temp files
        self._cleanup_temp_files()

        # Clean up sub-controllers
        self._extraction_controller.cleanup()
        self._injection_controller.cleanup()

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
