"""
Main controller for SpritePal extraction workflow
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from core.protocols.dialog_protocols import (
        DialogFactoryProtocol,
        InjectionDialogProtocol,
    )
    from core.protocols.manager_protocols import (
        ApplicationStateManagerProtocol,
        ExtractionManagerProtocol,
        InjectionManagerProtocol,
        SettingsManagerProtocol,
    )

from core.console_error_handler import ConsoleErrorHandler
from core.managers.core_operations_manager import CoreOperationsManager
from core.services.image_utils import pil_to_qpixmap
from core.services.preview_generator import create_vram_preview_request, get_preview_generator
from core.types import ROMExtractionParams, VRAMExtractionParams
from core.workers import ROMExtractionWorker, VRAMExtractionWorker
from utils.constants import (
    DEFAULT_TILES_PER_ROW,
    TILE_WIDTH,
    VRAM_SPRITE_OFFSET,
)
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

# from utils.settings_manager import get_settings_manager # Removed due to DI

logger = get_logger(__name__)


class ExtractionController(QObject):
    """Controller for the extraction workflow.

    This controller emits signals for UI updates, decoupling the business logic
    from the UI layer. The MainWindow or other UI components can connect to
    these signals to receive updates.
    """

    # Status and messaging signals
    status_message_changed = Signal(str)  # Status bar message updates
    status_message_timed = Signal(str, int)  # Status message with timeout (ms)

    # Preview update signals
    # Note: Using 'object' for complex types that PySide6 Signal doesn't support natively
    preview_ready = Signal(object, int)  # QPixmap and tile count
    preview_updated = Signal(object, int)  # Update without resetting view
    grayscale_image_ready = Signal(object)  # PIL Image for palette application
    preview_info_changed = Signal(str)  # Preview info text
    preview_cleared = Signal()  # Clear preview request

    # Palette signals
    palettes_ready = Signal(object)  # dict[str, list[tuple[int,int,int]]]
    active_palettes_ready = Signal(object)  # list[int]

    # Extraction state signals
    extraction_completed = Signal(object)  # list[str] of extracted files
    extraction_error = Signal(str)  # Error message

    # Cache operation signals
    cache_badge_show = Signal(str)  # Badge text
    cache_badge_hide = Signal()
    cache_status_updated = Signal(str, float)  # cache_type, time_saved
    cache_refresh_requested = Signal()  # Request UI to refresh cache display

    def __init__(
        self,
        main_window: Any,  # pyright: ignore[reportExplicitAny] - MainWindow has no protocol
        extraction_manager: ExtractionManagerProtocol,
        session_manager: ApplicationStateManagerProtocol,
        injection_manager: InjectionManagerProtocol,
        settings_manager: SettingsManagerProtocol,
        dialog_factory: DialogFactoryProtocol,
    ) -> None:
        super().__init__()
        self.main_window: Any = main_window  # pyright: ignore[reportExplicitAny] - MainWindow has no protocol
        self.extraction_manager = extraction_manager
        self.session_manager = session_manager
        self.injection_manager = injection_manager
        self.settings_manager = settings_manager
        self.dialog_factory = dialog_factory

        # Workers still managed locally (thin wrappers)
        self.worker: VRAMExtractionWorker | None = None
        self.rom_worker: ROMExtractionWorker | None = None

        # Store current injection dialog reference (not in session - not serializable)
        self._current_injection_dialog: InjectionDialogProtocol | None = None

        # Initialize error handler - always use console error handler for core layer
        # This removes the UI dependency while still properly logging errors
        self.error_handler = ConsoleErrorHandler()

        # Connect UI signals
        _ = self.main_window.extract_requested.connect(self.start_extraction)
        _ = self.main_window.open_in_editor_requested.connect(self.open_in_editor)
        _ = self.main_window.arrange_rows_requested.connect(self.open_row_arrangement)
        _ = self.main_window.arrange_grid_requested.connect(self.open_grid_arrangement)
        _ = self.main_window.inject_requested.connect(self.start_injection)
        _ = self.main_window.extraction_panel.offset_changed.connect(
            self.update_preview_with_offset
        )

        # Connect injection manager signals - cast to concrete type for signal access
        injection_mgr = cast(CoreOperationsManager, self.injection_manager)
        _ = injection_mgr.injection_progress.connect(self._on_injection_progress)
        _ = injection_mgr.injection_finished.connect(self._on_injection_finished)
        _ = injection_mgr.cache_saved.connect(self._on_cache_saved)

        # Connect extraction manager cache signals - cast to concrete type for signal access
        extraction_mgr = cast(CoreOperationsManager, self.extraction_manager)
        _ = extraction_mgr.cache_operation_started.connect(self._on_cache_operation_started)
        _ = extraction_mgr.cache_hit.connect(self._on_cache_hit)
        _ = extraction_mgr.cache_miss.connect(self._on_cache_miss)
        _ = extraction_mgr.cache_saved.connect(self._on_cache_saved)

        # Initialize preview generator with managers
        self.preview_generator = get_preview_generator()
        # Cast to concrete type for preview generator compatibility
        extraction_mgr = cast(CoreOperationsManager, self.extraction_manager)
        self.preview_generator.set_managers(
            extraction_manager=extraction_mgr,
            rom_extractor=extraction_mgr.get_rom_extractor()
        )

    def start_extraction(self) -> None:
        """Start the extraction process"""
        # Get parameters from UI
        params = self.main_window.get_extraction_params()

        # PARAMETER VALIDATION: Check requirements first for better UX
        # Users should get helpful parameter guidance before file system errors
        try:
            # TypedDict is compatible with dict[str, Any] for validation
            self.extraction_manager.validate_extraction_params(params)
        except (ValueError, TypeError) as e:
            # Expected validation errors - show to user
            self.main_window.extraction_failed(str(e))
            return
        except Exception as e:
            # Unexpected errors - log full traceback and show generic message
            logger.exception("Unexpected error during extraction parameter validation")
            self.main_window.extraction_failed(f"Validation error: {e}")
            return

        # DEFENSIVE VALIDATION: Only validate files that exist to prevent blocking I/O
        # This ensures fail-fast behavior before expensive worker thread operations
        vram_path = params.get("vram_path", "")

        # CRITICAL FIX FOR BUG #11: Add file format validation to prevent 2+ minute blocking
        # Only validate VRAM file if it was provided (already checked by parameter validation)
        if vram_path:
            vram_result = FileValidator.validate_vram_file(vram_path)
            if not vram_result.is_valid:
                self.main_window.extraction_failed(vram_result.error_message or "VRAM file validation failed")
                return

            # Show warnings if any
            for warning in vram_result.warnings:
                logger.warning(f"VRAM file warning: {warning}")

        cgram_path = params.get("cgram_path", "")
        grayscale_mode = params.get("grayscale_mode", False)
        # Only validate CGRAM if path was provided AND not in grayscale mode
        # Grayscale mode doesn't require CGRAM for color palette extraction
        if cgram_path and not grayscale_mode:
            cgram_result = FileValidator.validate_cgram_file(cgram_path)
            if not cgram_result.is_valid:
                self.main_window.extraction_failed(cgram_result.error_message or "CGRAM file validation failed")
                return

            # Show warnings if any
            for warning in cgram_result.warnings:
                logger.warning(f"CGRAM file warning: {warning}")

        oam_path = params.get("oam_path", "")
        if oam_path:
            oam_result = FileValidator.validate_oam_file(oam_path)
            if not oam_result.is_valid:
                self.main_window.extraction_failed(oam_result.error_message or "OAM file validation failed")
                return

            # Show warnings if any
            for warning in oam_result.warnings:
                logger.warning(f"OAM file warning: {warning}")

        # Create and start worker thread
        # Convert validated params dict to VRAMExtractionParams TypedDict
        extraction_params: VRAMExtractionParams = {
            "vram_path": params["vram_path"],
            "cgram_path": params.get("cgram_path") or None,
            "oam_path": params.get("oam_path") or None,
            "vram_offset": params.get("vram_offset", VRAM_SPRITE_OFFSET),
            "output_base": params["output_base"],
            "create_grayscale": params.get("create_grayscale", True),
            "create_metadata": params.get("create_metadata", True),
            "grayscale_mode": params.get("grayscale_mode", False),
        }
        # Pass extraction manager explicitly (B.2: constructor injection)
        extraction_mgr = cast(CoreOperationsManager, self.extraction_manager)
        self.worker = VRAMExtractionWorker(extraction_params, extraction_manager=extraction_mgr)
        _ = self.worker.progress.connect(self._on_progress)
        _ = self.worker.preview_ready.connect(self._on_preview_ready)
        _ = self.worker.preview_image_ready.connect(self._on_preview_image_ready)
        _ = self.worker.palettes_ready.connect(self._on_palettes_ready)
        _ = self.worker.active_palettes_ready.connect(self._on_active_palettes_ready)
        _ = self.worker.extraction_finished.connect(self._on_extraction_finished)
        _ = self.worker.error.connect(self._on_extraction_error)
        self.worker.start()

    def _on_progress(self, percent: int, message: str) -> None:
        """Handle progress updates"""
        self.status_message_changed.emit(message)

    def _on_preview_ready(self, pil_image: Image.Image, tile_count: int) -> None:
        """Handle preview ready - convert PIL Image to QPixmap in main thread"""
        # CRITICAL FIX FOR BUG #26: Convert PIL Image to QPixmap in main thread (safe!)
        # Worker now emits PIL Image to avoid Qt threading violations
        pixmap = pil_to_qpixmap(pil_image)
        if pixmap is not None:
            self.preview_ready.emit(pixmap, tile_count)
            self.preview_info_changed.emit(f"Tiles: {tile_count}")
        else:
            logger.error("Failed to convert PIL image to QPixmap for preview")
            self.error_handler.handle_warning(
                "Preview Error",
                "Failed to convert preview image for display"
            )

    def _on_preview_image_ready(self, pil_image: Image.Image) -> None:
        """Handle preview PIL image ready"""
        self.grayscale_image_ready.emit(pil_image)

    def _on_palettes_ready(self, palettes: dict[str, list[tuple[int, int, int]]]) -> None:
        """Handle palettes ready"""
        self.palettes_ready.emit(palettes)

    def _on_active_palettes_ready(self, active_palettes: list[int]) -> None:
        """Handle active palettes ready"""
        self.active_palettes_ready.emit(active_palettes)

    def _on_extraction_finished(self, extracted_files: list[str]) -> None:
        """Handle extraction finished"""
        self.extraction_completed.emit(extracted_files)
        self._cleanup_worker()

    def _on_extraction_error(self, error_message: str, exception: Exception | None = None) -> None:
        """Handle extraction error"""
        self.extraction_error.emit(error_message)
        self._cleanup_worker()

    def _cleanup_worker(self) -> None:
        """Safely cleanup worker thread"""
        from core.services.worker_lifecycle import WorkerManager

        WorkerManager.cleanup_worker(self.worker, timeout=3000)
        self.worker = None

    def update_preview_with_offset(self, offset: int) -> None:
        """Update preview with new VRAM offset without full extraction"""
        logger.debug(f"Updating preview with offset: 0x{offset:04X} ({offset})")

        try:
            # Check if we have VRAM loaded
            has_vram = self.main_window.extraction_panel.has_vram()
            logger.debug(f"Has VRAM loaded: {has_vram}")

            if not has_vram:
                logger.debug("No VRAM loaded, skipping preview update")
                return

            # Get VRAM path
            logger.debug("Getting VRAM path from extraction panel")
            vram_path = self.main_window.extraction_panel.get_vram_path()
            logger.debug(f"VRAM path: {vram_path}")

            if not vram_path:
                logger.warning("VRAM path is empty or None")
                self.status_message_changed.emit("VRAM path not available")
                return

            # Use PreviewGenerator service for unified preview generation
            logger.debug("Using PreviewGenerator service for preview generation")

            # Create preview request
            preview_request = create_vram_preview_request(
                vram_path=vram_path,
                offset=offset,
                sprite_name=f"vram_0x{offset:06X}",
                size=(self.main_window.sprite_preview.width(), self.main_window.sprite_preview.height())
            )

            # Generate preview with progress tracking
            def progress_callback(percent: int, message: str) -> None:
                progress_msg = f"{message} ({percent}%)"
                self.status_message_changed.emit(progress_msg)

            result = self.preview_generator.generate_preview(preview_request, progress_callback)

            if result is None:
                logger.error("Preview generation failed")
                self.status_message_changed.emit("Preview generation failed")
                return

            logger.debug(f"Generated preview with {result.tile_count} tiles, cached: {result.cached}")
            pixmap = result.pixmap
            num_tiles = result.tile_count
            img = result.pil_image

            # Update preview without resetting view (for real-time slider updates)
            logger.debug("Updating sprite preview widget")
            self.preview_updated.emit(pixmap, num_tiles)

            info_text = f"Tiles: {num_tiles} (Offset: 0x{offset:04X})"
            logger.debug(f"Setting preview info text: {info_text}")
            self.preview_info_changed.emit(info_text)

            # Also update the grayscale image for palette application
            logger.debug("Setting grayscale image in sprite preview")
            self.grayscale_image_ready.emit(img)

            logger.debug("Preview update completed successfully")

        except Exception as e:
            error_msg = f"Preview update failed: {e!s}"
            logger.exception("Error in preview update with offset 0x%04X", offset)

            # Log through error handler
            self.error_handler.handle_exception(e, f"Preview update with offset 0x{offset:04X}")

            # Emit signals for UI updates
            self.status_message_changed.emit(error_msg)
            self.preview_cleared.emit()
            self.preview_info_changed.emit("Preview update failed")

    def open_in_editor(self, sprite_file: str) -> None:
        """Open the extracted sprites in the pixel editor"""
        # Get the directory where this spritepal package is located
        spritepal_dir = Path(__file__).parent.parent
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

        if launcher_path:
            # Validate sprite file before launching
            image_result = FileValidator.validate_image_file(sprite_file)
            if not image_result.is_valid:
                self.main_window.status_bar.showMessage(
                    f"Invalid sprite file: {image_result.error_message}"
                )
                return

            # Ensure launcher path is absolute and exists
            launcher_path = launcher_path.resolve()
            if not launcher_path.exists():
                self.main_window.status_bar.showMessage(
                    "Pixel editor launcher not found"
                )
                return

            # Launch pixel editor with the sprite file
            try:
                # Use absolute paths for safety
                sprite_file_abs = Path(sprite_file).resolve()
                _ = subprocess.Popen([sys.executable, str(launcher_path), str(sprite_file_abs)])
                self.main_window.status_bar.showMessage(
                    f"Opened {sprite_file_abs.name} in pixel editor"
                )
            except (OSError, subprocess.SubprocessError) as e:
                # Expected subprocess errors (file not found, permission denied, etc.)
                self.error_handler.handle_warning("Pixel Editor", f"Failed to open: {e}")
                self.main_window.status_bar.showMessage(f"Failed to open pixel editor: {e}")
            except Exception as e:
                # Unexpected errors - log for debugging
                self.error_handler.handle_exception(e, "Launching pixel editor")
                self.main_window.status_bar.showMessage(f"Failed to open pixel editor: {e}")
        else:
            self.main_window.status_bar.showMessage("Pixel editor not found")

    def open_row_arrangement(self, sprite_file: str) -> None:
        """Open the row arrangement dialog"""
        # Validate sprite file exists and is valid
        sprite_result = FileValidator.validate_file_existence(sprite_file, "Sprite file")
        if not sprite_result.is_valid:
            self.main_window.status_bar.showMessage(sprite_result.error_message or "Sprite file not found")
            return

        try:
            # Try to get tiles_per_row from sprite preview or use default
            tiles_per_row = self._get_tiles_per_row_from_sprite(sprite_file)

            # Open row arrangement dialog using factory
            # Use main_window as parent only if it's a QWidget (for test compatibility)
            # Use local var to prevent isinstance() from narrowing self.main_window's type
            _mw = self.main_window
            parent = _mw if isinstance(_mw, QWidget) else None
            dialog = self.dialog_factory.create_row_arrangement_dialog(
                sprite_file, tiles_per_row, parent
            )

            # Pass palette data from the main window's sprite preview if available
            if (
                hasattr(self.main_window, "sprite_preview")
                and self.main_window.sprite_preview
            ) and hasattr(self.main_window.sprite_preview, "get_palettes"):
                try:
                    palettes = self.main_window.sprite_preview.get_palettes()
                    if palettes:
                        dialog.set_palettes(palettes)
                except Exception as e:
                    # Log palette loading error but continue with dialog
                    logger.warning(f"Failed to load palette data for dialog: {e}")
                        # Dialog can still function without palette data

            if dialog.exec():
                # Get the arranged sprite path
                arranged_path = dialog.get_arranged_path()

                if arranged_path and Path(arranged_path).exists():
                    # Open the arranged sprite in the pixel editor
                    self.open_in_editor(arranged_path)
                    self.main_window.status_bar.showMessage(
                        "Opened arranged sprites in pixel editor"
                    )
                else:
                    self.main_window.status_bar.showMessage("Row arrangement cancelled")
        except Exception as e:
            self.error_handler.handle_exception(e, "Failed to open row arrangement dialog")

    def open_grid_arrangement(self, sprite_file: str) -> None:
        """Open the grid arrangement dialog"""
        # Validate sprite file exists and is valid
        sprite_result = FileValidator.validate_file_existence(sprite_file, "Sprite file")
        if not sprite_result.is_valid:
            self.main_window.status_bar.showMessage(sprite_result.error_message or "Sprite file not found")
            return

        # Try to get tiles_per_row from sprite preview or use default
        tiles_per_row = self._get_tiles_per_row_from_sprite(sprite_file)

        # Open grid arrangement dialog using factory
        # Use local var to prevent isinstance() from narrowing self.main_window's type
        _mw = self.main_window
        parent = _mw if isinstance(_mw, QWidget) else None
        dialog = self.dialog_factory.create_grid_arrangement_dialog(
            sprite_file, tiles_per_row, parent
        )

        # Pass palette data from the main window's sprite preview if available
        if (
            hasattr(self.main_window, "sprite_preview")
            and self.main_window.sprite_preview
        ) and hasattr(self.main_window.sprite_preview, "get_palettes"):
            try:
                palettes = self.main_window.sprite_preview.get_palettes()
                if palettes:
                    dialog.set_palettes(palettes)
            except Exception as e:
                # Log palette loading error but continue with dialog
                logger.warning(f"Failed to load palette data for dialog: {e}")
                    # Dialog can still function without palette data

        if dialog.exec():
            # Get the arranged sprite path
            arranged_path = dialog.get_arranged_path()

            if arranged_path and Path(arranged_path).exists():
                # Open the arranged sprite in the pixel editor
                self.open_in_editor(arranged_path)
                self.main_window.status_bar.showMessage(
                    "Opened grid-arranged sprites in pixel editor"
                )
            else:
                self.main_window.status_bar.showMessage("Grid arrangement cancelled")

    def _get_tiles_per_row_from_sprite(self, sprite_file: str) -> int:
        """Determine tiles per row from sprite file or main window state

        Args:
            sprite_file: Path to sprite file

        Returns:
            Number of tiles per row
        """
        # Try to get from main window's sprite preview first
        if (
            hasattr(self.main_window, "sprite_preview")
            and self.main_window.sprite_preview
        ):
            try:
                _, tiles_per_row = self.main_window.sprite_preview.get_tile_info()
                if tiles_per_row > 0:
                    return tiles_per_row
            except (AttributeError, TypeError):
                pass

        # Fallback: try to calculate from sprite dimensions
        try:
            with Image.open(sprite_file) as img:
                # Calculate tiles per row based on sprite width
                # Assume 8x8 pixel tiles (TILE_WIDTH)
                calculated_tiles_per_row = img.width // TILE_WIDTH
                if calculated_tiles_per_row > 0:
                    return min(calculated_tiles_per_row, DEFAULT_TILES_PER_ROW)
        except Exception:
            # Intentionally silent: this is a best-effort calculation with a guaranteed fallback.
            # Any error (file not found, invalid image, etc.) just means we use the default.
            pass

        # Ultimate fallback
        return DEFAULT_TILES_PER_ROW

    def start_injection(self) -> None:
        """Start the injection process using InjectionManager"""
        # Get sprite path and metadata path
        output_base = self.main_window.get_output_path()
        if not output_base:
            self.main_window.status_bar.showMessage("No extraction to inject")
            return

        sprite_path = f"{output_base}.png"
        metadata_path = f"{output_base}.metadata.json"

        # Validate sprite file exists before creating dialog
        sprite_result = FileValidator.validate_file_existence(sprite_path, "Sprite file")
        if not sprite_result.is_valid:
            self.main_window.status_bar.showMessage(sprite_result.error_message or f"Sprite file not found: {sprite_path}")
            return

        # Get smart input VRAM suggestion using injection manager
        suggested_input_vram = self.injection_manager.get_smart_vram_suggestion(
            sprite_path, metadata_path if Path(metadata_path).exists() else ""
        )

        # Show injection dialog using factory
        # Use main_window as parent only if it's a QWidget (for test compatibility)
        parent = self.main_window if isinstance(self.main_window, QWidget) else None
        dialog = self.dialog_factory.create_injection_dialog(
            parent=parent,
            sprite_path=sprite_path,
            metadata_path=metadata_path if Path(metadata_path).exists() else "",
            input_vram=suggested_input_vram,
        )

        if dialog.exec():
            params = dialog.get_parameters()
            if params:
                # Store dialog reference for saving on success (instance attr, not session - not serializable)
                self._current_injection_dialog = dialog
                self.session_manager.set("workflow", "current_injection_params", params)

                # Start injection using manager
                success = self.injection_manager.start_injection(params)
                if not success:
                    # Log through error handler
                    self.error_handler.handle_warning("Injection", "Failed to start injection")
                    self.status_message_changed.emit("Failed to start injection")

    def _on_injection_progress(self, message: str) -> None:
        """Handle injection progress updates"""
        self.status_message_changed.emit(message)

    def _on_injection_finished(self, success: bool, message: str) -> None:
        """Handle injection completion"""
        if success:
            success_msg = f"Injection successful: {message}"
            self.status_message_changed.emit(success_msg)

            # Save injection parameters for future use if it was a ROM injection
            current_injection_params = self.session_manager.get("workflow", "current_injection_params")

            # Cast to Any for .get() method access (dynamic session data)
            params_dict: Any = current_injection_params  # pyright: ignore[reportExplicitAny] - session data is dynamic
            if (
                current_injection_params
                and params_dict.get("mode") == "rom"
                and self._current_injection_dialog
                and hasattr(
                    self._current_injection_dialog, "save_rom_injection_parameters"
                )
            ):
                try:
                    self._current_injection_dialog.save_rom_injection_parameters()
                except Exception as e:
                    # Don't fail the injection if saving parameters fails
                    logger.warning(f"Could not save ROM injection parameters: {e}")
        else:
            fail_msg = f"Injection failed: {message}"
            # Log through error handler
            self.error_handler.handle_warning("Injection", fail_msg)
            self.status_message_changed.emit(fail_msg)

        # Clean up
        self._current_injection_dialog = None
        self.session_manager.set("workflow", "current_injection_params", None)

    def _on_cache_operation_started(self, operation: str, cache_type: str) -> None:
        """Handle cache operation started notification"""
        settings_manager = self.settings_manager

        # Only show if indicators are enabled
        if settings_manager.get("cache", "show_indicators", True):
            badge_text = f"{operation} {cache_type.replace('_', ' ')}"
            self.cache_badge_show.emit(badge_text)

    def _on_cache_hit(self, cache_type: str, time_saved: float) -> None:
        """Handle cache hit notification"""
        settings_manager = self.settings_manager

        self.cache_badge_hide.emit()

        # Only show if indicators are enabled
        if settings_manager.get("cache", "show_indicators", True):
            message = f"Loaded {cache_type.replace('_', ' ')} from cache (saved {time_saved:.1f}s)"
            self.status_message_timed.emit(message, 5000)
            self.cache_status_updated.emit(cache_type, time_saved)

    def _on_cache_miss(self, cache_type: str) -> None:
        """Handle cache miss notification"""
        # Cache misses are normal - only log them, don't show in UI
        logger.debug(f"Cache miss for {cache_type}")

    def _on_cache_saved(self, cache_type: str, count: int) -> None:
        """Handle cache saved notification"""
        settings_manager = self.settings_manager

        self.cache_badge_hide.emit()

        # Only show if indicators are enabled
        if settings_manager.get("cache", "show_indicators", True):
            message = f"Saved {count} {cache_type.replace('_', ' ')} to cache"
            self.status_message_timed.emit(message, 5000)
            self.cache_refresh_requested.emit()

    def start_rom_extraction(self, params: dict[str, Any]) -> None:  # pyright: ignore[reportExplicitAny] - params are dynamic extraction config
        """Start ROM sprite extraction process"""
        # Convert validated params dict to ROMExtractionParams TypedDict
        rom_extraction_params: ROMExtractionParams = {
            "rom_path": params["rom_path"],
            "sprite_offset": params["sprite_offset"],
            "sprite_name": params["sprite_name"],
            "output_base": params["output_base"],
            "cgram_path": params.get("cgram_path"),
        }
        # Create and start ROM extraction worker (B.2: constructor injection)
        extraction_mgr = cast(CoreOperationsManager, self.extraction_manager)
        self.rom_worker = ROMExtractionWorker(rom_extraction_params, extraction_manager=extraction_mgr)
        _ = self.rom_worker.progress.connect(self._on_rom_progress)
        _ = self.rom_worker.extraction_finished.connect(self._on_rom_extraction_finished)
        _ = self.rom_worker.error.connect(self._on_rom_extraction_error)
        self.rom_worker.start()

    def _on_rom_progress(self, percent: int, message: str) -> None:
        """Handle ROM extraction progress"""
        self.status_message_changed.emit(message)

    def _on_rom_extraction_finished(self, extracted_files: list[str]) -> None:
        """Handle ROM extraction completion"""
        self.extraction_completed.emit(extracted_files)
        self._cleanup_rom_worker()

    def _on_rom_extraction_error(self, error_message: str) -> None:
        """Handle ROM extraction error"""
        self.extraction_error.emit(error_message)
        self._cleanup_rom_worker()

    def _cleanup_rom_worker(self) -> None:
        """Safely cleanup ROM worker thread"""
        from core.services.worker_lifecycle import WorkerManager

        WorkerManager.cleanup_worker(self.rom_worker, timeout=3000)
        self.rom_worker = None

