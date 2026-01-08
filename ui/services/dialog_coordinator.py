"""Dialog coordination service for extraction workflows.

Extracted from ExtractionController to provide dialog management without
coupling to the main extraction workflow.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget

from core.console_error_handler import ConsoleErrorHandler
from utils.constants import DEFAULT_TILES_PER_ROW, TILE_WIDTH
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

logger = get_logger(__name__)


class DialogCoordinator(QObject):
    """Coordinates arrangement and editor dialogs.

    This service handles dialog-related operations that were previously
    in ExtractionController, providing a cleaner separation of concerns.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the dialog coordinator.

        Args:
            parent: Parent widget for dialogs (typically MainWindow)
        """
        super().__init__(parent)
        self._parent = parent
        self._error_handler = ConsoleErrorHandler()

    def open_in_editor(
        self,
        sprite_file: str,
        status_callback: Callable[[str], None] | None = None,
    ) -> bool:
        """Open the extracted sprites in the pixel editor.

        Args:
            sprite_file: Path to the sprite file to open
            status_callback: Optional callback for status messages

        Returns:
            True if editor was launched successfully, False otherwise
        """
        # Get the directory where this spritepal package is located
        spritepal_dir = Path(__file__).parent.parent.parent
        exhal_dir = spritepal_dir.parent

        # Look for pixel editor launcher using absolute paths
        launcher_paths = [
            spritepal_dir / "launch_pixel_editor.py",
            spritepal_dir / "pixel_editor" / "launch_pixel_editor.py",
            exhal_dir / "launch_pixel_editor.py",
            exhal_dir / "pixel_editor" / "launch_pixel_editor.py",
        ]

        launcher_path = None
        for path in launcher_paths:
            if path.exists():
                launcher_path = path
                break

        if not launcher_path:
            if status_callback:
                status_callback("Pixel editor not found")
            return False

        # Validate sprite file before launching
        image_result = FileValidator.validate_image_file(sprite_file)
        if not image_result.is_valid:
            if status_callback:
                status_callback(f"Invalid sprite file: {image_result.error_message}")
            return False

        # Ensure launcher path is absolute and exists
        launcher_path = launcher_path.resolve()
        if not launcher_path.exists():
            if status_callback:
                status_callback("Pixel editor launcher not found")
            return False

        # Launch pixel editor with the sprite file
        try:
            sprite_file_abs = Path(sprite_file).resolve()
            _ = subprocess.Popen([sys.executable, str(launcher_path), str(sprite_file_abs)])
            if status_callback:
                status_callback(f"Opened {sprite_file_abs.name} in pixel editor")
            return True
        except (OSError, subprocess.SubprocessError) as e:
            self._error_handler.handle_warning("Pixel Editor", f"Failed to open: {e}")
            if status_callback:
                status_callback(f"Failed to open pixel editor: {e}")
            return False
        except Exception as e:
            self._error_handler.handle_exception(e, "Launching pixel editor")
            if status_callback:
                status_callback(f"Failed to open pixel editor: {e}")
            return False

    def open_row_arrangement(
        self,
        sprite_file: str,
        palettes: dict[int, list[tuple[int, int, int]]] | None,
        tiles_per_row: int | None,
        status_callback: Callable[[str], None] | None = None,
        on_success: Callable[[str], None] | None = None,
    ) -> bool:
        """Open the row arrangement dialog.

        Args:
            sprite_file: Path to the sprite file
            palettes: Optional palette data to pass to dialog
            tiles_per_row: Tiles per row (None to auto-calculate)
            status_callback: Optional callback for status messages
            on_success: Optional callback with arranged file path on success

        Returns:
            True if dialog was accepted, False otherwise
        """
        # Validate sprite file exists
        sprite_result = FileValidator.validate_file_existence(sprite_file, "Sprite file")
        if not sprite_result.is_valid:
            if status_callback:
                status_callback(sprite_result.error_message or "Sprite file not found")
            return False

        try:
            # Calculate tiles per row if not provided
            if tiles_per_row is None:
                tiles_per_row = self._get_tiles_per_row_from_sprite(sprite_file)

            # Direct import and instantiation
            from ui.row_arrangement_dialog import RowArrangementDialog

            dialog = RowArrangementDialog(sprite_file, tiles_per_row, self._parent)

            # Pass palette data if available
            if palettes:
                try:
                    dialog.set_palettes(palettes)
                except Exception as e:
                    logger.warning(f"Failed to load palette data for dialog: {e}")

            if dialog.exec():
                arranged_path = dialog.get_arranged_path()

                if arranged_path and Path(arranged_path).exists():
                    if on_success:
                        on_success(arranged_path)
                    if status_callback:
                        status_callback("Opened arranged sprites in pixel editor")
                    return True
                else:
                    if status_callback:
                        status_callback("Row arrangement cancelled")
                    return False
            return False

        except Exception as e:
            self._error_handler.handle_exception(e, "Failed to open row arrangement dialog")
            return False

    def open_grid_arrangement(
        self,
        sprite_file: str,
        palettes: dict[int, list[tuple[int, int, int]]] | None,
        tiles_per_row: int | None,
        status_callback: Callable[[str], None] | None = None,
        on_success: Callable[[str], None] | None = None,
    ) -> bool:
        """Open the grid arrangement dialog.

        Args:
            sprite_file: Path to the sprite file
            palettes: Optional palette data to pass to dialog
            tiles_per_row: Tiles per row (None to auto-calculate)
            status_callback: Optional callback for status messages
            on_success: Optional callback with arranged file path on success

        Returns:
            True if dialog was accepted, False otherwise
        """
        # Validate sprite file exists
        sprite_result = FileValidator.validate_file_existence(sprite_file, "Sprite file")
        if not sprite_result.is_valid:
            if status_callback:
                status_callback(sprite_result.error_message or "Sprite file not found")
            return False

        # Calculate tiles per row if not provided
        if tiles_per_row is None:
            tiles_per_row = self._get_tiles_per_row_from_sprite(sprite_file)

        # Direct import and instantiation
        from ui.grid_arrangement_dialog import GridArrangementDialog

        dialog = GridArrangementDialog(sprite_file, tiles_per_row, self._parent)

        # Pass palette data if available
        if palettes:
            try:
                dialog.set_palettes(palettes)
            except Exception as e:
                logger.warning(f"Failed to load palette data for dialog: {e}")

        if dialog.exec():
            arranged_path = dialog.get_arranged_path()

            if arranged_path and Path(arranged_path).exists():
                if on_success:
                    on_success(arranged_path)
                if status_callback:
                    status_callback("Opened grid-arranged sprites in pixel editor")
                return True
            else:
                if status_callback:
                    status_callback("Grid arrangement cancelled")
                return False
        return False

    def _get_tiles_per_row_from_sprite(self, sprite_file: str) -> int:
        """Determine tiles per row from sprite file dimensions.

        Args:
            sprite_file: Path to sprite file

        Returns:
            Number of tiles per row
        """
        try:
            with Image.open(sprite_file) as img:
                # Calculate tiles per row based on sprite width
                # Assume 8x8 pixel tiles (TILE_WIDTH)
                calculated_tiles_per_row = img.width // TILE_WIDTH
                if calculated_tiles_per_row > 0:
                    return min(calculated_tiles_per_row, DEFAULT_TILES_PER_ROW)
        except Exception:
            # Intentionally silent: best-effort calculation with guaranteed fallback.
            pass

        return DEFAULT_TILES_PER_ROW
