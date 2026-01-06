#!/usr/bin/env python3
"""
ROM Workflow Controller for the Sprite Editor.
Coordinates ROM loading, previewing, editing, and injection.
"""

import logging
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal

from core.app_context import get_app_context
from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

if TYPE_CHECKING:
    from ..views.workspaces.rom_workflow_page import ROMWorkflowPage
    from .main_controller import MainController

logger = logging.getLogger(__name__)


class ROMWorkflowController(QObject):
    """
    Controller for the unified ROM workflow.
    States:
    - PREVIEW: Browsing ROM offsets.
    - EDIT: Sprite loaded in editor.
    - SAVE: Confirming injection back to ROM.
    """

    # Signals
    status_message = Signal(str)
    rom_info_updated = Signal(str)
    preview_ready = Signal(object, int)  # QPixmap or Image, compressed_size
    workflow_state_changed = Signal(str)  # 'preview', 'edit', 'save'

    def __init__(self, main_controller: "MainController") -> None:
        super().__init__(main_controller)
        self.main_controller = main_controller
        self._view: "ROMWorkflowPage | None" = None

        # Core components - use shared instances from AppContext
        context = get_app_context()
        self.rom_cache = context.rom_cache
        self.rom_extractor = context.rom_extractor
        self.log_watcher = context.log_watcher

        # Preview coordinator
        self.preview_coordinator = SmartPreviewCoordinator(self)
        self.preview_coordinator.preview_ready.connect(self._on_preview_ready)
        self.preview_coordinator.preview_error.connect(self._on_preview_error)
        self.preview_coordinator.set_rom_data_provider(self._get_rom_data_for_preview)

        # State
        self.rom_path: str = ""
        self.rom_size: int = 0
        self.current_offset: int = 0
        self.state: str = "preview"  # 'preview', 'edit', 'save'

        # Current sprite data
        self.current_tile_data: bytes | None = None
        self.current_width: int = 0
        self.current_height: int = 0
        self.current_sprite_name: str = ""
        self.original_compressed_size: int = 0
        self.available_slack: int = 0

        # Connect LogWatcher
        self._connect_log_watcher()

    def _connect_log_watcher(self) -> None:
        """Connect LogWatcher signals to handle discovered offsets."""
        self.log_watcher.offset_discovered.connect(self._on_offset_discovered)
        # Start watching if not already
        self.log_watcher.start_watching()

    def _on_offset_discovered(self, capture: object) -> None:
        """Handle new offset discovered from Mesen2 log."""
        if self._view:
            from core.mesen_integration.log_watcher import CapturedOffset

            if isinstance(capture, CapturedOffset):
                self._view.recent_captures_widget.add_capture(capture)

    def set_view(self, view: "ROMWorkflowPage") -> None:
        """Set the view and connect signals."""
        self._view = view
        self._connect_view_signals()

        # Load existing persistent clicks
        persistent_clicks = self.log_watcher.load_persistent_clicks()
        if persistent_clicks:
            view.recent_captures_widget.load_persistent(persistent_clicks)

    def _connect_view_signals(self) -> None:
        """Connect view signals."""
        if not self._view:
            return

        self._view.source_bar.offset_changed.connect(self.set_offset)
        self._view.source_bar.action_clicked.connect(self.handle_primary_action)
        self._view.source_bar.browse_rom_requested.connect(self.browse_rom)

        # Recent captures signals
        self._view.recent_captures_widget.offset_selected.connect(self.set_offset)
        self._view.recent_captures_widget.offset_activated.connect(self.set_offset)

        # Navigation buttons
        self._view.prev_btn.clicked.connect(self.navigate_prev)
        self._view.next_btn.clicked.connect(self.navigate_next)

        # Connect preview coordinator to view's slider if it exists
        if hasattr(self._view, "offset_slider"):
            self.preview_coordinator.connect_slider(self._view.offset_slider)
            # Also connect slider value changed to update offset
            self._view.offset_slider.valueChanged.connect(self.set_offset)

    def navigate_prev(self) -> None:
        """Move backward by step size."""
        if self._view:
            step = self._view.step_spin.value()
            self.set_offset(max(0, self.current_offset - step))

    def navigate_next(self) -> None:
        """Move forward by step size."""
        if self._view:
            step = self._view.step_spin.value()
            self.set_offset(min(self.rom_size - 1, self.current_offset + step))

    def browse_rom(self) -> None:
        """Open file dialog to select ROM file."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self._view,
            "Open ROM File",
            "",
            "SNES ROMs (*.sfc *.smc);;All Files (*)",
        )
        if file_path:
            self.load_rom(file_path)

    def load_rom(self, path: str) -> None:
        """Load and validate ROM file."""
        from pathlib import Path

        rom_path = Path(path)
        if not rom_path.exists():
            self.status_message.emit(f"Error: ROM file not found: {path}")
            return

        self.rom_path = path
        self.rom_size = rom_path.stat().st_size

        # Update view
        if self._view:
            self._view.source_bar.set_rom_path(path)
            self._view.set_rom_size(self.rom_size)

        # Get ROM info (checksum/title)
        try:
            # Simple title extraction for now
            with open(path, "rb") as f:
                f.seek(0x7FC0 if self.rom_size % 0x8000 == 0 else 0x81C0)
                title = f.read(21).decode("ascii", errors="ignore").strip()
                self.rom_info_updated.emit(f"{title}")
                if self._view:
                    self._view.source_bar.set_info(title)
        except Exception:
            self.rom_info_updated.emit("Unknown ROM")

        self.status_message.emit(f"Loaded ROM: {rom_path.name}")

        # Trigger initial preview
        self.set_offset(self.current_offset)

    def set_offset(self, offset: int) -> None:
        """Set current ROM offset and request preview."""
        if offset < 0 or (self.rom_size > 0 and offset >= self.rom_size):
            return

        # Check for unsaved changes if in edit mode
        if self.state == "edit" and self.main_controller.editing_controller.undo_manager.can_undo():
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self._view,
                "Unsaved Changes",
                "You have unsaved changes in the editor. Changing the offset will discard them. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                # Reset slider/text to current offset
                if self._view:
                    self._view.source_bar.set_offset(self.current_offset)
                    self._view.offset_slider.setValue(self.current_offset)
                return

            # User chose to continue, reset state to preview
            self.state = "preview"
            if self._view:
                self._view.source_bar.set_action_text("Open in Editor")
                self._view.set_workflow_state("preview")

        self.current_offset = offset
        if self._view:
            self._view.source_bar.set_offset(offset)
            # Update slider if not already matched
            if self._view.offset_slider.value() != offset:
                self._view.offset_slider.blockSignals(True)
                self._view.offset_slider.setValue(offset)
                self._view.offset_slider.blockSignals(False)

        if self.rom_path:
            self.preview_coordinator.request_manual_preview(offset)

    def handle_primary_action(self) -> None:
        """Handle the state-dependent primary action button."""
        if self.state == "preview":
            self.open_in_editor()
        elif self.state == "edit":
            self.prepare_injection()
        elif self.state == "save":
            self.save_to_rom()

    def open_in_editor(self) -> None:
        """Load the current preview into the pixel editor."""
        if not self.current_tile_data:
            self.status_message.emit("No sprite data to edit")
            return

        # Use SpriteRenderer to create PIL image from 4bpp
        from ..services import SpriteRenderer

        renderer = SpriteRenderer()

        # For ROM mode, we might need a default palette if none selected
        # Use palette from extraction controller if available
        if (
            hasattr(self.main_controller.extraction_controller, "_view")
            and self.main_controller.extraction_controller._view
        ):
            params = self.main_controller.extraction_controller._view.get_extraction_params()
            int(params.get("palette_num", 0))  # type: ignore

        image = renderer.render_4bpp(self.current_tile_data, self.current_width, self.current_height)

        # Convert to numpy and load into editor
        image_array = np.array(image, dtype=np.uint8)
        palette_data = image.getpalette()
        palette: list[tuple[int, int, int]] = []
        if palette_data:
            for i in range(0, min(48, len(palette_data)), 3):
                palette.append((palette_data[i], palette_data[i + 1], palette_data[i + 2]))
        while len(palette) < 16:
            palette.append((0, 0, 0))

        self.main_controller.editing_controller.load_image(image_array, palette)

        # Change state
        self.state = "edit"
        if self._view:
            self._view.source_bar.set_action_text("Save to ROM")
            self._view.set_workflow_state("edit")
        self.workflow_state_changed.emit("edit")
        self.status_message.emit("Sprite loaded in editor")

    def prepare_injection(self) -> None:
        """Transition from editing to save confirmation with size comparison."""
        data = self.main_controller.editing_controller.get_image_data()
        if data is None:
            self.status_message.emit("No image to inject")
            return

        # Calculate new compressed size
        try:
            from core.hal_compression import HALCompressor

            from ..services import ImageConverter

            converter = ImageConverter()

            # Convert to 4bpp tiles
            img = Image.fromarray(data, mode="P")
            img.putpalette(self.main_controller.editing_controller.get_flat_palette())

            # Simple conversion for size estimation
            tiles = converter.image_to_tiles(img)

            import tempfile
            from pathlib import Path

            compressor = HALCompressor()
            with tempfile.NamedTemporaryFile(suffix=".hal", delete=False) as tmp:
                compressed_path = tmp.name

            try:
                new_size = compressor.compress_to_file(tiles, compressed_path)
            finally:
                Path(compressed_path).unlink(missing_ok=True)

            # Show confirmation dialog
            from PySide6.QtWidgets import QMessageBox

            msg = "Ready to inject edited sprite into ROM.\n\n"
            msg += f"Target Offset: 0x{self.current_offset:06X}\n"
            msg += f"Original Size: {self.original_compressed_size} bytes\n"
            
            # Use max 32 bytes slack by default for safety
            safe_slack = min(self.available_slack, 32)
            if self.available_slack > 0:
                msg += f"Available Space: {self.original_compressed_size + safe_slack} bytes "
                msg += f"({self.original_compressed_size} + {safe_slack} slack)\n"
            
            msg += f"New Size: {new_size} bytes\n\n"

            if new_size > (self.original_compressed_size + safe_slack):
                msg += "⚠️ WARNING: New sprite is LARGER than available space. "
                msg += "This WILL overwrite adjacent data and likely crash the game!\n\n"
            elif new_size > self.original_compressed_size:
                msg += "NOTE: New sprite is slightly larger than original, "
                msg += f"but fits within detected slack space ({new_size - self.original_compressed_size} bytes used).\n\n"

            msg += "A backup of the ROM will be created automatically.\n"
            msg += "Proceed with injection?"

            reply = QMessageBox.question(
                self._view, "Confirm ROM Injection", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.save_to_rom()

        except Exception as e:
            logger.exception("Error during injection preparation")
            self.status_message.emit(f"Error: {e}")

    def save_to_rom(self) -> None:
        """Inject edited sprite back to ROM."""
        data = self.main_controller.editing_controller.get_image_data()
        if data is None:
            self.status_message.emit("No image to save")
            return

        try:
            self.status_message.emit(f"Saving to ROM at 0x{self.current_offset:06X}...")

            # Create PIL image for conversion
            img = Image.fromarray(data, mode="P")
            img.putpalette(self.main_controller.editing_controller.get_flat_palette())

            # Save to temp PNG for injector
            import tempfile
            from pathlib import Path

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                img.save(f.name, "PNG")
                temp_png = f.name

            # Perform injection with backup
            rom_injector = self.rom_extractor.rom_injector
            
            # First attempt (standard validation)
            success, message = rom_injector.inject_sprite_to_rom(
                sprite_path=temp_png,
                rom_path=self.rom_path,
                output_path=self.rom_path,
                sprite_offset=self.current_offset,
                create_backup=True,
            )
            
            # Handle failure due to checksum mismatch
            if not success and "ROM checksum mismatch" in message:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.question(
                    self._view,
                    "ROM Checksum Mismatch",
                    f"Validation failed: {message}\n\n"
                    "This usually happens with modified/patched ROMs.\n"
                    "Do you want to ignore this warning and proceed anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    self.status_message.emit("Retrying with lenient checksum validation...")
                    success, message = rom_injector.inject_sprite_to_rom(
                        sprite_path=temp_png,
                        rom_path=self.rom_path,
                        output_path=self.rom_path,
                        sprite_offset=self.current_offset,
                        create_backup=True,
                        ignore_checksum=True,
                    )

            # Handle failure due to compressed size too large
            if not success and "Compressed sprite too large" in message:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.warning(
                    self._view,
                    "Sprite Too Large",
                    f"{message}\n\n"
                    "⚠️ FORCE INJECTION WARNING ⚠️\n\n"
                    "Force injecting will overwrite adjacent ROM data, which may:\n"
                    "• Corrupt other sprites or game data\n"
                    "• Cause the game to crash or glitch\n\n"
                    "A backup of your ROM will be created first.\n\n"
                    "Do you want to force inject anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,  # Default to No
                )

                if reply == QMessageBox.StandardButton.Yes:
                    self.status_message.emit("Force injecting (backup created)...")
                    success, message = rom_injector.inject_sprite_to_rom(
                        sprite_path=temp_png,
                        rom_path=self.rom_path,
                        output_path=self.rom_path,
                        sprite_offset=self.current_offset,
                        create_backup=True,
                        force=True,
                    )

            # Cleanup temp file
            try:
                Path(temp_png).unlink()
            except OSError:
                pass

            if success:
                self.status_message.emit(f"Successfully saved: {message}")
                # Show success in view
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self._view,
                    "Save Successful",
                    f"Sprite injected successfully at 0x{self.current_offset:06X}.\n\n{message}",
                )

                # Back to edit state
                self.state = "edit"
                if self._view:
                    self._view.source_bar.set_action_text("Save to ROM")
                    self._view.set_workflow_state("edit")
                    # Trigger a re-preview to verify
                    self.set_offset(self.current_offset)
            else:
                self.status_message.emit(f"Injection failed: {message}")
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self._view, "Injection Failed", f"Failed to inject sprite: {message}")

        except Exception as e:
            logger.exception("Error during ROM injection")
            self.status_message.emit(f"Error saving to ROM: {e}")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self._view, "Error", f"An error occurred during injection: {e}")

    def _get_rom_data_for_preview(self) -> tuple[str, object] | None:
        """Provide ROM data for smart preview coordinator."""
        if not self.rom_path:
            return None
        return (self.rom_path, self.rom_extractor)

    def _on_preview_ready(
        self, tile_data: bytes, width: int, height: int, sprite_name: str, compressed_size: int, slack_size: int = 0
    ) -> None:
        """Handle preview ready from coordinator."""
        self.current_tile_data = tile_data
        self.current_width = width
        self.current_height = height
        self.current_sprite_name = sprite_name
        self.original_compressed_size = compressed_size
        self.available_slack = slack_size

        # Render for view
        from ..services import SpriteRenderer

        renderer = SpriteRenderer()
        image = renderer.render_4bpp(tile_data, width, height)

        # Convert PIL to QPixmap or emit as is
        self.preview_ready.emit(image, compressed_size)

        if self._view:
            self._view.update_preview(image)
            slack_info = f" (+{slack_size} slack)" if slack_size > 0 else ""
            self.status_message.emit(f"Sprite found! Original size: {compressed_size} bytes{slack_info}")

    def _on_preview_error(self, error_msg: str) -> None:
        """Handle preview error."""
        self.current_tile_data = None
        self.status_message.emit(f"Preview error: {error_msg}")

    def cleanup(self) -> None:
        """Clean up resources."""
        self.preview_coordinator.cleanup()
