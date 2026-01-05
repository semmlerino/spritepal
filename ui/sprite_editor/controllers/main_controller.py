#!/usr/bin/env python3
"""
Main controller for coordinating all sub-controllers.
Acts as the central coordinator for the unified sprite editor.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal

from .editing_controller import EditingController
from .extraction_controller import ExtractionController
from .injection_controller import InjectionController

if TYPE_CHECKING:
    from ..views.main_window import SpriteEditorMainWindow


class MainController(QObject):
    """Main controller coordinating all application controllers."""

    # Signals
    status_message = Signal(str)
    workflow_state_changed = Signal(str)  # 'extract', 'edit', 'inject'

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        # Create sub-controllers
        self.extraction_controller = ExtractionController(self)
        self.editing_controller = EditingController(self)
        self.injection_controller = InjectionController(self)

        # Main window reference
        self._main_window: SpriteEditorMainWindow | None = None

        # Current workflow state
        self._workflow_state = "extract"

        # Track temp files for cleanup
        self._temp_files: list[str] = []

        # Connect cross-controller signals
        self._connect_cross_controller_signals()

    def set_main_window(self, window: "SpriteEditorMainWindow") -> None:
        """Set the main window and connect views to controllers."""
        self._main_window = window

        # Connect tabs to controllers
        # Note: EditTab.set_controller() creates the canvas and connects signals
        self.extraction_controller.set_view(window.extract_tab)
        self.editing_controller.set_view(window.edit_tab)
        self.injection_controller.set_view(window.inject_tab)

        # Connect main window signals
        self._connect_main_window_signals()

    def _connect_main_window_signals(self) -> None:
        """Connect main window signals."""
        if not self._main_window:
            return

        # Tab changed
        if hasattr(self._main_window, "tab_changed"):
            self._main_window.tab_changed.connect(self._on_tab_changed)

        # Edit tab workflow signals
        self._main_window.edit_tab.ready_for_inject.connect(self._on_ready_for_inject)

    def _connect_cross_controller_signals(self) -> None:
        """Connect signals between controllers for workflow coordination."""
        # When extraction completes, load into editor
        self.extraction_controller.extraction_completed.connect(self._on_extraction_completed)

        # When injection completes, show success
        self.injection_controller.injection_completed.connect(self._on_injection_completed)

    def _on_tab_changed(self, tab_index: int) -> None:
        """Handle tab change."""
        states = ["extract", "edit", "inject", "multi_palette"]
        if 0 <= tab_index < len(states):
            self._workflow_state = states[tab_index]
            self.workflow_state_changed.emit(self._workflow_state)

    def _on_extraction_completed(self, image: Image.Image, tile_count: int) -> None:
        """Handle extraction completion - load into editor."""
        # Convert PIL image to numpy array for editor
        image_array = np.array(image, dtype=np.uint8)

        # Get palette from image
        palette_data = image.getpalette()
        palette: list[tuple[int, int, int]] = []
        if palette_data:
            for i in range(0, min(48, len(palette_data)), 3):
                palette.append((palette_data[i], palette_data[i + 1], palette_data[i + 2]))

        # Pad to 16 colors
        while len(palette) < 16:
            palette.append((0, 0, 0))

        # Load into editor
        self.editing_controller.load_image(image_array, palette)

        # Switch to edit tab
        if self._main_window:
            self._main_window.switch_to_tab(1)  # Edit tab

        self.status_message.emit(f"Extracted {tile_count} tiles - ready for editing")

    def _on_ready_for_inject(self) -> None:
        """Handle 'ready for inject' from edit tab."""
        # Export edited image to temp file
        import tempfile

        data = self.editing_controller.get_image_data()
        if data is None:
            self.status_message.emit("No image to inject")
            return

        # Create unique temp PNG file to avoid collision with other instances
        with tempfile.NamedTemporaryFile(
            suffix=".png",
            prefix="spritepal_",
            delete=False,
        ) as f:
            temp_path = f.name

        # Create PIL image
        img = Image.fromarray(data, mode="P")
        img.putpalette(self.editing_controller.get_flat_palette())
        img.save(temp_path, "PNG")

        # Track temp file for cleanup
        self._temp_files.append(temp_path)

        # Set as source for injection
        self.injection_controller.set_source_image(temp_path)

        # Switch to inject tab
        if self._main_window:
            self._main_window.switch_to_tab(2)  # Inject tab

        self.status_message.emit("Image exported - ready for injection")

    def _on_injection_completed(self, output_path: str) -> None:
        """Handle injection completion."""
        self._cleanup_temp_files()
        self.status_message.emit(f"Injection complete: {output_path}")

    def _cleanup_temp_files(self) -> None:
        """Remove temp files created during workflow."""
        for path in self._temp_files:
            try:
                temp_path = Path(path)
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass  # Best effort cleanup
        self._temp_files.clear()

    def cleanup(self) -> None:
        """Clean up all sub-controllers and resources."""
        self._cleanup_temp_files()
        self.extraction_controller.cleanup()
        self.injection_controller.cleanup()
        # EditingController doesn't have cleanup method yet
        # if hasattr(self.editing_controller, "cleanup"):
        #     self.editing_controller.cleanup()

    # Public workflow methods

    def quick_extract(self) -> None:
        """Perform quick extraction with current settings."""
        if self._main_window:
            self._main_window.switch_to_tab(0)  # Extract tab
        self.extraction_controller.browse_vram_file()

    def quick_inject(self) -> None:
        """Open inject tab and prompt for PNG."""
        if self._main_window:
            self._main_window.switch_to_tab(2)  # Inject tab
        self.injection_controller.browse_png_file()

    def save_current_state(self) -> None:
        """Save current application state."""
        # TODO: Implement settings persistence
        pass

    def load_saved_state(self) -> None:
        """Load saved application state."""
        # TODO: Implement settings loading
        pass
