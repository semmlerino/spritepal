"""
Consolidated Core Operations Manager for SpritePal.

This manager combines extraction, injection, palette, and navigation functionality
into a single cohesive unit. It directly implements ExtractionManagerProtocol and
InjectionManagerProtocol without using adapters.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

from PIL import Image
from PySide6.QtCore import QObject, QThread, Signal

from core.exceptions import (
    ExtractionError,
    ValidationError,
)
from core.extractor import SpriteExtractor
from core.palette_manager import PaletteManager
from core.services import ROMService, VRAMService
from utils.constants import (
    SETTINGS_KEY_FAST_COMPRESSION,
    SETTINGS_KEY_LAST_CUSTOM_OFFSET,
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_KEY_LAST_INPUT_VRAM,
    SETTINGS_KEY_LAST_SPRITE_LOCATION,
    SETTINGS_NS_ROM_INJECTION,
)
from utils.file_validator import FileValidator

from .base_manager import BaseManager, with_operation_handling

from core.protocols.manager_protocols import ApplicationStateManagerProtocol

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ROMExtractorProtocol


class CoreOperationsManager(BaseManager):
    """
    Consolidated manager for all core operations:
    - Extraction (ROM and VRAM)
    - Injection (ROM and VRAM)
    - Palette management
    - Navigation and sprite discovery

    This manager directly implements ExtractionManagerProtocol and
    InjectionManagerProtocol without using adapter classes.
    """

    # ========== Signal Architecture ==========
    # Extraction: extraction_progress, extraction_warning, preview_generated,
    #             palettes_extracted, active_palettes_found, files_created
    # Injection: injection_progress, injection_finished, compression_info, progress_percent
    # Cache: cache_operation_started, cache_hit, cache_miss, cache_saved
    # =========================================

    # Extraction signals
    extraction_progress = Signal(str)  # message only (simpler for UI consumers)
    extraction_warning = Signal(str)  # Warning message (partial success)
    preview_generated = Signal(object, int)  # pixmap, offset
    palettes_extracted = Signal(dict)  # palette data
    active_palettes_found = Signal(list)  # list of active palette indices
    files_created = Signal(list)  # list of created file paths

    # Injection signals
    injection_progress = Signal(str)  # message only
    injection_finished = Signal(bool, str)  # success, message
    compression_info = Signal(dict)  # compression statistics
    progress_percent = Signal(int)  # percent only (for progress bars)

    # Cache signals (monitoring)
    cache_operation_started = Signal(str, str)  # operation, key
    cache_hit = Signal(str, float)  # key, load_time
    cache_miss = Signal(str)  # key
    cache_saved = Signal(str, int)  # key, size_bytes

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the core operations manager."""
        # Initialize components
        self._sprite_extractor: SpriteExtractor | None = None
        self._rom_extractor: ROMExtractorProtocol | None = None
        self._palette_manager: PaletteManager | None = None
        self._current_worker: QThread | None = None

        # Services (owned by this manager)
        self._rom_service: ROMService | None = None
        self._vram_service: VRAMService | None = None

        # Thread safety for inherited methods
        self._lock = threading.RLock()

        super().__init__("CoreOperationsManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize all core operation components."""
        try:
            # Initialize extractors
            self._sprite_extractor = SpriteExtractor()
            self._palette_manager = PaletteManager()

            # ROMExtractor via DI
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMExtractorProtocol
            self._rom_extractor = inject(ROMExtractorProtocol)

            # Initialize services
            self._rom_service = ROMService(
                rom_extractor=self._rom_extractor,
                palette_manager=self._palette_manager,
                parent=self,
            )
            self._vram_service = VRAMService(
                sprite_extractor=self._sprite_extractor,
                palette_manager=self._palette_manager,
                parent=self,
            )

            # Connect service signals for backward compatibility
            self._connect_service_signals()

            self._is_initialized = True
            self._logger.info("CoreOperationsManager initialized successfully")

        except Exception as e:
            self._handle_error(e, "initialization")
            raise

    def _connect_service_signals(self) -> None:
        """Connect service signals to manager signals for backward compatibility."""
        if self._rom_service:
            # Forward ROM service signals
            self._rom_service.extraction_progress.connect(self.extraction_progress)
            self._rom_service.extraction_warning.connect(self.extraction_warning)
            self._rom_service.preview_generated.connect(self.preview_generated)
            self._rom_service.palettes_extracted.connect(self.palettes_extracted)
            self._rom_service.active_palettes_found.connect(self.active_palettes_found)
            self._rom_service.files_created.connect(self.files_created)
            self._rom_service.cache_operation_started.connect(self.cache_operation_started)
            self._rom_service.cache_hit.connect(self.cache_hit)
            self._rom_service.cache_miss.connect(self.cache_miss)
            self._rom_service.cache_saved.connect(self.cache_saved)
            self._rom_service.error_occurred.connect(self.error_occurred)

        if self._vram_service:
            # Forward VRAM service signals
            self._vram_service.extraction_progress.connect(self.extraction_progress)
            self._vram_service.extraction_warning.connect(self.extraction_warning)
            self._vram_service.preview_generated.connect(self.preview_generated)
            self._vram_service.palettes_extracted.connect(self.palettes_extracted)
            self._vram_service.active_palettes_found.connect(self.active_palettes_found)
            self._vram_service.files_created.connect(self.files_created)
            self._vram_service.error_occurred.connect(self.error_occurred)

    @override
    def cleanup(self) -> None:
        """Cleanup all core operation resources."""
        # Acquire worker reference under lock to prevent race with start_injection
        worker_to_cleanup = None
        rom_service_to_cleanup = None
        vram_service_to_cleanup = None

        with self._lock:
            self._active_operations.clear()
            # Capture references and clear them under lock
            worker_to_cleanup = self._current_worker
            self._current_worker = None
            rom_service_to_cleanup = self._rom_service
            vram_service_to_cleanup = self._vram_service

        # Cleanup captured references OUTSIDE lock to avoid blocking
        if worker_to_cleanup:
            from core.services.worker_lifecycle import WorkerManager

            self._logger.info("Stopping active worker")
            WorkerManager.cleanup_worker(worker_to_cleanup, timeout=5000)

        if rom_service_to_cleanup:
            rom_service_to_cleanup.cleanup()
        if vram_service_to_cleanup:
            vram_service_to_cleanup.cleanup()

        # Mark injection operation as finished so new injections can start
        self._finish_operation("injection")

        self._logger.info("CoreOperationsManager cleaned up")

    def reset_state(self, full_reset: bool = False) -> None:
        """Reset internal state for test isolation."""
        # Stop any active worker
        if self._current_worker:
            from core.services.worker_lifecycle import WorkerManager

            self._logger.debug("Stopping active worker during reset_state")
            WorkerManager.cleanup_worker(self._current_worker, timeout=1000)
            self._current_worker = None

        with self._lock:
            self._active_operations.clear()

            if full_reset:
                # Clear services first
                if self._rom_service:
                    self._rom_service.cleanup()
                    self._rom_service = None
                if self._vram_service:
                    self._vram_service.cleanup()
                    self._vram_service = None

                # Clear long-lived components
                self._sprite_extractor = None
                self._rom_extractor = None
                self._palette_manager = None
                self._is_initialized = False
                self._logger.debug("CoreOperationsManager full reset: cleared all components")

    # ========== Helper Methods ==========

    def _ensure_sprite_extractor(self) -> SpriteExtractor:
        """Ensure sprite extractor is initialized."""
        return self._ensure_component(
            self._sprite_extractor, "Sprite extractor", ExtractionError
        )

    def _ensure_rom_extractor(self) -> ROMExtractorProtocol:
        """Ensure ROM extractor is initialized."""
        return self._ensure_component(
            self._rom_extractor, "ROM extractor", ExtractionError
        )

    def _ensure_palette_manager(self) -> PaletteManager:
        """Ensure palette manager is initialized."""
        return self._ensure_component(
            self._palette_manager, "Palette manager", ExtractionError
        )

    def _get_session_manager(self) -> ApplicationStateManagerProtocol:
        """Get session manager via dependency injection container."""
        from core.di_container import inject
        from core.protocols.manager_protocols import ApplicationStateManagerProtocol
        return inject(ApplicationStateManagerProtocol)

    def _raise_extraction_failed(self, message: str) -> None:
        """Helper method to raise ExtractionError (for TRY301 compliance)."""
        raise ExtractionError(message)

    # ========== Service Accessors ==========

    @property
    def rom_service(self) -> ROMService:
        """Get ROM service."""
        if self._rom_service is None:
            raise ExtractionError("ROM service not initialized")
        return self._rom_service

    @property
    def vram_service(self) -> VRAMService:
        """Get VRAM service."""
        if self._vram_service is None:
            raise ExtractionError("VRAM service not initialized")
        return self._vram_service

    # ========== Extraction Operations ==========

    @with_operation_handling(
        "vram_extraction", "VRAM extraction", with_progress=True, exclusive=True, target_error=ExtractionError
    )
    def extract_from_vram(self, vram_path: str, output_base: str,
                         cgram_path: str | None = None,
                         oam_path: str | None = None,
                         vram_offset: int | None = None,
                         create_grayscale: bool = True,
                         create_metadata: bool = True,
                         grayscale_mode: bool = False) -> list[str]:
        """
        Extract sprites from VRAM dump.

        Args:
            vram_path: Path to VRAM dump file
            output_base: Base name for output files (without extension)
            cgram_path: path to CGRAM dump for palette extraction
            oam_path: path to OAM dump for palette analysis
            vram_offset: offset in VRAM (default: 0xC000)
            create_grayscale: Create grayscale palette files
            create_metadata: Create metadata JSON file
            grayscale_mode: Skip palette extraction entirely

        Returns:
            List of created file paths

        Raises:
            ExtractionError: If extraction fails
            ValidationError: If parameters are invalid
        """
        if self._vram_service is None:
            raise ExtractionError("VRAMService not initialized")

        return self._vram_service.extract_from_vram(
            vram_path=vram_path,
            output_base=output_base,
            cgram_path=cgram_path,
            oam_path=oam_path,
            vram_offset=vram_offset,
            create_grayscale=create_grayscale,
            create_metadata=create_metadata,
            grayscale_mode=grayscale_mode,
        )

    @with_operation_handling(
        "rom_extraction", "ROM extraction", with_progress=True, exclusive=True, target_error=ExtractionError
    )
    def extract_from_rom(self, rom_path: str, offset: int,
                        output_base: str, sprite_name: str,
                        cgram_path: str | None = None) -> list[str]:
        """
        Extract sprites from ROM at specific offset.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM to extract from
            output_base: Base name for output files
            sprite_name: Name of the sprite being extracted
            cgram_path: CGRAM dump for palette extraction

        Returns:
            List of created file paths

        Raises:
            ExtractionError: If extraction fails
            ValidationError: If parameters are invalid
        """
        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")

        return self._rom_service.extract_from_rom(
            rom_path=rom_path,
            offset=offset,
            output_base=output_base,
            sprite_name=sprite_name,
            cgram_path=cgram_path,
        )

    @with_operation_handling(
        "sprite_preview", "preview generation", with_progress=False, exclusive=False, target_error=ExtractionError
    )
    def get_sprite_preview(self, rom_path: str, offset: int,
                          sprite_name: str | None = None) -> tuple[bytes, int, int]:
        """
        Get a preview of sprite data from ROM without saving files.

        Args:
            rom_path: Path to ROM file
            offset: Offset in ROM
            sprite_name: sprite name for logging

        Returns:
            Tuple of (tile_data, width, height)

        Raises:
            ExtractionError: If preview generation fails
        """
        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")

        return self._rom_service.get_sprite_preview(rom_path, offset, sprite_name)

    def validate_extraction_params(
        self, params: Mapping[str, object]
    ) -> bool:
        """
        Validate extraction parameters.

        Args:
            params: Parameters to validate

        Returns:
            True if validation passes

        Raises:
            ValidationError: If validation fails
        """
        # Determine extraction type
        if "vram_path" in params:
            # VRAM extraction - check for missing VRAM file specifically
            if not params.get("vram_path"):
                raise ValidationError("VRAM file is required for extraction")
            self._validate_required(params, ["output_base"])
        elif "rom_path" in params:
            # ROM extraction
            self._validate_required(params, ["rom_path", "offset", "output_base"])
            rom_path = cast(str, params["rom_path"])
            FileValidator.validate_rom_file_exists_or_raise(rom_path)
            self._validate_type(params["offset"], "offset", int)
            offset = cast(int, params["offset"])
            self._validate_range(offset, "offset", min_val=0)
        else:
            raise ValidationError("Must provide either vram_path or rom_path")

        # Validate CGRAM requirements for VRAM extraction
        if "vram_path" in params:
            grayscale_mode = params.get("grayscale_mode", False)
            cgram_path = params.get("cgram_path")

            # CGRAM is required for full color mode
            if not grayscale_mode and not cgram_path:
                raise ValidationError(
                    "CGRAM file is required for Full Color mode.\n"
                    "Please provide a CGRAM file or switch to Grayscale Only mode."
                )

        # Validate output_base is provided and not empty
        output_base = cast(str, params.get("output_base", ""))
        if not output_base or not output_base.strip():
            raise ValidationError("Output name is required for extraction")

        return True

    def generate_preview(self, vram_path: str, offset: int) -> tuple[Image.Image, int]:
        """Generate a preview image from VRAM at the specified offset.

        Args:
            vram_path: Path to VRAM dump file
            offset: Offset in VRAM to start extracting from

        Returns:
            Tuple of (PIL image, tile count)

        Raises:
            ExtractionError: If preview generation fails
        """
        if self._vram_service is None:
            raise ExtractionError("VRAMService not initialized")

        try:
            return self._vram_service.generate_preview(vram_path, offset)
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, "preview_generation", "generating preview")
            raise
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, "preview_generation", "generating preview")
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                self._handle_operation_error(e, "preview_generation", ExtractionError, "generating preview")
            raise

    def get_rom_extractor(self) -> ROMExtractorProtocol:
        """Get the ROM extractor instance for advanced operations."""
        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")
        return self._rom_service.get_rom_extractor()

    def extract_sprite_to_png(self, rom_path: str, sprite_offset: int,
                             output_path: str, cgram_path: str | None = None) -> bool:
        """
        Extract a single sprite to PNG file.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset of sprite in ROM
            output_path: Full path where PNG should be saved
            cgram_path: Optional CGRAM file for palette data

        Returns:
            True if extraction successful

        Raises:
            ExtractionError: If operation fails (service not initialized, etc.)
        """
        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")
        return self._rom_service.extract_sprite_to_png(
            rom_path, sprite_offset, output_path, cgram_path
        )

    def get_known_sprite_locations(
        self, rom_path: str
    ) -> dict[str, object]:  # Pointer objects with .offset attribute
        """
        Get known sprite locations for a ROM with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations (values are pointer objects with .offset)

        Raises:
            ExtractionError: If operation fails
        """
        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")

        try:
            return self._rom_service.get_known_sprite_locations(rom_path)
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, "get_known_sprite_locations", "getting sprite locations")
            raise
        except (ImportError, AttributeError) as e:
            self._handle_operation_error(e, "get_known_sprite_locations", ExtractionError, "ROM analysis not available")
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                self._handle_operation_error(e, "get_known_sprite_locations", ExtractionError, "getting sprite locations")
            raise

    def read_rom_header(
        self, rom_path: str
    ) -> dict[str, object]:  # ROM header with title, rom_type, checksum, etc.
        """
        Read ROM header information.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary containing ROM header information

        Raises:
            ExtractionError: If operation fails
        """
        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")

        try:
            return self._rom_service.read_rom_header(rom_path)
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, "read_rom_header", "reading ROM header")
            raise
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, "read_rom_header", "reading ROM header")
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                self._handle_operation_error(e, "read_rom_header", ExtractionError, "reading ROM header")
            raise

    # ========== Extraction Validation Helpers ==========

    def _validate_rom_file(
        self, rom_path: str
    ) -> dict[str, object] | None:  # Error dict with error and error_type keys
        """Validate ROM file exists, is readable, and has reasonable size.

        Uses FileValidator for comprehensive validation, converts result to dict format.

        Returns:
            Error dict if validation fails, None if valid
        """
        result = FileValidator.validate_rom_file(rom_path)
        if result.is_valid:
            return None

        # Convert ValidationResult to legacy dict format for backward compatibility
        error_msg = result.error_message or f"Invalid ROM file: {rom_path}"

        # Determine error_type from error message
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
            error_type = "FileNotFoundError"
        elif "permission" in error_msg.lower() or "cannot read" in error_msg.lower():
            error_type = "PermissionError"
        else:
            error_type = "ValueError"

        return {"error": error_msg, "error_type": error_type}

    def _validate_extraction_rom_file(self, rom_path: str) -> None:
        """Validate ROM file for extraction and raise if invalid."""
        error_result = self._validate_rom_file(rom_path)
        if error_result:
            raise ValidationError(f"ROM file validation failed: {error_result['error']}")

    # ========== Injection Operations ==========

    def start_injection(self, params: Mapping[str, object]) -> bool:
        """
        Start injection process with unified interface.

        Args:
            params: Injection parameters containing:
                - mode: "vram" or "rom"
                - sprite_path: Path to sprite PNG file
                - For VRAM: input_vram, output_vram, offset
                - For ROM: input_rom, output_rom, offset, fast_compression
                - Optional: metadata_path

        Returns:
            True if injection started successfully, False otherwise

        Raises:
            InjectionError: If injection cannot be started
            ValidationError: If parameters are invalid
        """
        operation = "injection"

        if not self._start_operation(operation):
            return False

        def _validate_injection_mode(mode: str) -> None:
            """Validate injection mode and raise error if invalid."""
            if mode not in ("vram", "rom"):
                raise ValidationError(f"Invalid injection mode: {mode}")

        try:
            from core.services.worker_lifecycle import WorkerManager
            from core.workers import InjectionWorker, ROMInjectionParams, ROMInjectionWorker

            # Validate parameters
            self.validate_injection_params(params)

            # Stop any existing worker
            cleanup_timeout = 5000 if params.get("mode") == "rom" else 2000
            if self._current_worker is not None:
                cleanup_success = WorkerManager.cleanup_worker(
                    self._current_worker, timeout=cleanup_timeout
                )
                if not cleanup_success:
                    # Worker did not stop within timeout - use cleanup result to avoid race
                    self._logger.warning(
                        f"Previous worker still running after {cleanup_timeout}ms cleanup timeout. "
                        "Declining to start new injection to prevent data corruption."
                    )
                    # Clear zombie reference even though worker is still running.
                    # This prevents holding references to unresponsive workers.
                    self._current_worker = None
                    self._finish_operation(operation)
                    return False
            self._current_worker = None

            # Create appropriate worker based on mode
            mode = cast(str, params["mode"])
            if mode == "vram":
                sprite_path = cast(str, params["sprite_path"])
                input_vram = cast(str, params["input_vram"])
                output_vram = cast(str, params["output_vram"])
                offset = cast(int, params["offset"])
                metadata_path = cast(str | None, params.get("metadata_path"))
                worker = InjectionWorker(
                    sprite_path,
                    input_vram,
                    output_vram,
                    offset,
                    metadata_path
                )
            elif mode == "rom":
                # Build ROM params with type casts
                sprite_path_val = cast(str, params["sprite_path"])
                input_rom_val = cast(str, params["input_rom"])
                output_rom_val = cast(str, params["output_rom"])
                offset_val = cast(int, params["offset"])
                fast_comp_val = cast(bool, params.get("fast_compression", False))
                metadata_path_val = cast(str | None, params.get("metadata_path"))

                rom_params: ROMInjectionParams = {
                    "mode": "rom",
                    "sprite_path": sprite_path_val,
                    "input_rom": input_rom_val,
                    "output_rom": output_rom_val,
                    "offset": offset_val,
                    "fast_compression": fast_comp_val,
                    "metadata_path": metadata_path_val,
                }
                # Use self as the injection manager
                worker = ROMInjectionWorker(rom_params, self)
            else:
                _validate_injection_mode(mode)
                return False

            # Connect worker signals before starting
            self._current_worker = worker
            self._connect_worker_signals()

            # Start the worker
            worker.start()

            mode_text = "VRAM" if params["mode"] == "vram" else "ROM"
            self._logger.info(f"Started {mode_text} injection: {params['sprite_path']}")
            self.injection_progress.emit(f"Starting {mode_text} injection...")
            return True

        except (OSError, PermissionError) as e:
            self._cleanup_current_worker()
            self._handle_file_io_error(e, operation, "injection startup")
            raise
        except (ValueError, TypeError) as e:
            self._cleanup_current_worker()
            self._handle_data_format_error(e, operation, "injection startup")
            raise
        except Exception as e:
            self._cleanup_current_worker()
            self._handle_error(e, operation)
            return False
        finally:
            # FIX T1.1: Always finish operation if we didn't successfully start a worker.
            # If worker is running, it will call _finish_operation when it completes.
            # This prevents "injection already in progress" errors after validation failures.
            if not self._current_worker or not self._current_worker.isRunning():
                self._finish_operation(operation)

    def validate_injection_params(
        self, params: Mapping[str, object]
    ) -> None:
        """
        Validate injection parameters.

        Args:
            params: Parameters to validate

        Raises:
            ValidationError: If parameters are invalid
        """
        # Check required common parameters
        required = ["mode", "sprite_path", "offset"]
        self._validate_required(params, required)

        self._validate_type(params["mode"], "mode", str)
        self._validate_type(params["sprite_path"], "sprite_path", str)
        self._validate_type(params["offset"], "offset", int)

        # Use FileValidator for sprite file validation
        sprite_path = cast(str, params["sprite_path"])
        sprite_result = FileValidator.validate_image_file(sprite_path)
        if not sprite_result.is_valid:
            raise ValidationError(
                f"Sprite file validation failed: {sprite_result.error_message}"
            )

        offset = cast(int, params["offset"])
        self._validate_range(offset, "offset", min_val=0)

        # Check mode-specific parameters
        mode = cast(str, params["mode"])
        if mode == "vram":
            vram_required = ["input_vram", "output_vram"]
            self._validate_required(params, vram_required)

            input_vram = cast(str, params["input_vram"])
            vram_result = FileValidator.validate_vram_file(input_vram)
            if not vram_result.is_valid:
                raise ValidationError(
                    f"Input VRAM file validation failed: {vram_result.error_message}"
                )

        elif mode == "rom":
            rom_required = ["input_rom", "output_rom"]
            self._validate_required(params, rom_required)

            input_rom = cast(str, params["input_rom"])
            rom_result = FileValidator.validate_rom_file(input_rom)
            if not rom_result.is_valid:
                raise ValidationError(
                    f"Input ROM file validation failed: {rom_result.error_message}"
                )

            # Validate optional fast_compression parameter
            if "fast_compression" in params:
                self._validate_type(
                    params["fast_compression"], "fast_compression", bool
                )
        else:
            raise ValidationError(f"Invalid injection mode: {mode}")

        # Validate optional metadata_path
        metadata_path_val = params.get("metadata_path")
        if metadata_path_val:
            metadata_path = cast(str, metadata_path_val)
            metadata_result = FileValidator.validate_json_file(metadata_path)
            if not metadata_result.is_valid:
                raise ValidationError(
                    f"Metadata file validation failed: {metadata_result.error_message}"
                )

    def is_injection_active(self) -> bool:
        """Check if injection is currently active."""
        return bool(self._current_worker and self._current_worker.isRunning())

    def _connect_worker_signals(self) -> None:
        """Connect worker signals to manager signals."""
        if not self._current_worker:
            return

        worker = self._current_worker
        # Signal attributes checked via hasattr but not visible to static analysis (BaseWorker defines these)
        if hasattr(worker, "progress"):
            worker.progress.connect(self._on_worker_progress_adapter)  # type: ignore[attr-defined] - Signal from BaseWorker
        if hasattr(worker, "injection_finished"):
            worker.injection_finished.connect(self._on_worker_finished)  # type: ignore[attr-defined] - Signal from BaseWorker
        else:
            worker.finished.connect(lambda: self._on_worker_finished(True, "Completed"))

        # ROM-specific signals
        if hasattr(worker, "progress_percent"):
            worker.progress_percent.connect(self.progress_percent.emit)  # type: ignore[attr-defined] - Signal from BaseWorker
        if hasattr(worker, "compression_info"):
            worker.compression_info.connect(self.compression_info.emit)  # type: ignore[attr-defined] - Signal from BaseWorker

    @override
    def _on_worker_progress_adapter(self, *args: object) -> None:
        """Adapter to handle different worker progress signal signatures."""
        # Use inherited implementation from BaseManager
        super()._on_worker_progress_adapter(*args)

    @override
    def _on_worker_progress(self, message: str) -> None:
        """Handle worker progress - emit injection-specific signal."""
        self.injection_progress.emit(message)

    def _on_worker_finished(self, success: bool, message: str) -> None:
        """Handle worker completion."""
        self._handle_worker_completion("injection", success, message)
        self.injection_finished.emit(success, message)

    def _cleanup_current_worker(self) -> None:
        """
        Stop and clear current worker on error.

        FIX #2: Ensures worker is properly stopped when exception occurs
        after worker.start() but before normal completion.
        """
        if self._current_worker is None:
            return

        try:
            from core.services.worker_lifecycle import WorkerManager
            WorkerManager.cleanup_worker(self._current_worker, timeout=1000)
        except Exception:
            # Best effort cleanup - don't let cleanup errors mask original error
            pass
        finally:
            self._current_worker = None

    # ========== VRAM Suggestion Strategies ==========

    def _validate_vram_path(self, path: str | None) -> str:
        """Validate and return VRAM path if it exists, empty string otherwise."""
        if path and Path(path).exists():
            return str(path)
        return ""

    def _find_vram_path_internal(
        self,
        sprite_path: str,
        metadata_path: str = "",
        metadata: dict[str, object] | None = None,
        pre_suggested: str = "",
        strip_editor_suffixes: bool = False,
    ) -> str:
        """
        Find VRAM path using multiple strategies in priority order.

        Strategies (in order):
        1. Pre-suggested path
        2. Session manager vram_path
        3. Metadata file (source_vram or extraction.vram_source)
        4. Basename pattern matching
        5. Last injection settings

        Args:
            sprite_path: Path to sprite file
            metadata_path: Optional metadata file path (loads and parses)
            metadata: Pre-loaded metadata dict (from load_metadata)
            pre_suggested: Pre-suggested VRAM path to check first
            strip_editor_suffixes: Strip editor suffixes from sprite name

        Returns:
            Suggested VRAM path or empty string if none found
        """
        # Strategy 1: Pre-suggested path
        if result := self._validate_vram_path(pre_suggested):
            return result

        # Strategy 2: Session manager vram_path
        try:
            session_manager = self._get_session_manager()
            if result := self._validate_vram_path(
                cast(str, session_manager.get("session", "vram_path", ""))
            ):
                return result
        except (OSError, ValueError, TypeError):
            pass

        # Strategy 3: Metadata file
        loaded_metadata = metadata
        if not loaded_metadata and metadata_path and Path(metadata_path).exists():
            try:
                with Path(metadata_path).open() as f:
                    loaded_metadata = cast(dict[str, object], json.load(f))
            except (OSError, ValueError, json.JSONDecodeError):
                pass

        if loaded_metadata:
            # Check top-level source_vram (absolute path)
            if result := self._validate_vram_path(cast(str, loaded_metadata.get("source_vram", ""))):
                return result
            # Check extraction.vram_source (relative path)
            extraction = loaded_metadata.get("extraction")
            if isinstance(extraction, dict):
                vram_source = cast(str, extraction.get("vram_source", ""))
                if vram_source and sprite_path:
                    sprite_dir = Path(sprite_path).parent
                    if result := self._validate_vram_path(str(sprite_dir / vram_source)):
                        return result

        # Strategy 4: Basename pattern matching
        if sprite_path:
            sprite_path_obj = Path(sprite_path)
            sprite_dir = sprite_path_obj.parent
            base_name = sprite_path_obj.stem

            if strip_editor_suffixes:
                for suffix in ["_sprites_editor", "_sprites", "_editor", "Edited"]:
                    if base_name.endswith(suffix):
                        base_name = base_name[: -len(suffix)]
                        break

            vram_patterns = [
                f"{base_name}.dmp",
                f"{base_name}_VRAM.dmp",
                f"{base_name}.VRAM.dmp",
                f"{base_name}.vram",
                f"{base_name}.SnesVideoRam.dmp",
                f"{base_name}.VideoRam.dmp",
                "VRAM.dmp",
                "vram.dmp",
            ]

            for pattern in vram_patterns:
                if result := self._validate_vram_path(str(sprite_dir / pattern)):
                    return result

        # Strategy 5: Last injection settings
        try:
            session_manager = self._get_session_manager()
            if result := self._validate_vram_path(
                cast(str, session_manager.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_VRAM, ""))
            ):
                return result
        except (OSError, ValueError, TypeError):
            pass

        self._logger.debug("No VRAM suggestion found")
        return ""

    def get_smart_vram_suggestion(self, sprite_path: str, metadata_path: str = "") -> str:
        """
        Get smart suggestion for input VRAM path using multiple strategies.

        Tries multiple sources in priority order: extraction panel, metadata,
        basename patterns, session data, and last injection settings.

        Args:
            sprite_path: Path to sprite file
            metadata_path: Optional metadata file path

        Returns:
            Suggested VRAM path or empty string if none found
        """
        return self._find_vram_path_internal(
            sprite_path=sprite_path,
            metadata_path=metadata_path,
            strip_editor_suffixes=False,
        )

    # ========== Metadata and ROM Info ==========

    def load_metadata(
        self, metadata_path: str
    ) -> dict[str, object] | None:  # Parsed extraction metadata with mixed types
        """
        Load and parse metadata file.

        Args:
            metadata_path: Path to metadata JSON file

        Returns:
            Parsed metadata dict with extraction info, or None if loading fails
        """
        if not metadata_path or not Path(metadata_path).exists():
            return None

        parsed_info: dict[str, object] | None = None
        metadata: dict[str, object] | None = None

        try:
            with Path(metadata_path).open() as f:
                metadata = cast(dict[str, object], json.load(f))

            if "extraction" in metadata:
                extraction = metadata["extraction"]
                if not isinstance(extraction, dict):
                    return None
                source_type = cast(str, extraction.get("source_type", "vram"))

                parsed_info = {
                    "metadata": metadata,
                    "source_type": source_type,
                    "extraction": extraction
                }

                if source_type == "rom":
                    parsed_info["rom_extraction_info"] = {
                        "rom_source": extraction.get("rom_source", ""),
                        "rom_offset": extraction.get("rom_offset", "0x0"),
                        "sprite_name": extraction.get("sprite_name", ""),
                        "tile_count": extraction.get("tile_count", "Unknown")
                    }
                    parsed_info["extraction_vram_offset"] = None
                    parsed_info["default_vram_offset"] = "0xC000"
                else:
                    vram_offset = extraction.get("vram_offset", "0xC000")
                    parsed_info["extraction_vram_offset"] = vram_offset
                    parsed_info["rom_extraction_info"] = None

        except (OSError, PermissionError) as e:
            self._logger.warning(f"File I/O error loading metadata from {metadata_path}: {e}")
            return None
        except (json.JSONDecodeError, ValueError) as e:
            self._logger.warning(f"Invalid metadata format in {metadata_path}: {e}")
            return None
        except Exception as e:
            self._logger.warning(f"Failed to load metadata from {metadata_path}: {e}")
            return None
        else:
            if metadata and "extraction" in metadata and parsed_info:
                return parsed_info
            return {
                "metadata": metadata,
                "source_type": "vram",
                "extraction": None,
                "extraction_vram_offset": None,
                "rom_extraction_info": None,
                "default_vram_offset": "0xC000"
            }

    def load_rom_info(
        self, rom_path: str
    ) -> dict[str, object] | None:  # ROM header, sprite locations, cached flag, or error info
        """
        Load ROM information and sprite locations with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dict containing header, sprite_locations, cached flag, or error info
        """
        def _create_error_result(message: str, error_type: str) -> dict[str, object]:
            return {"error": message, "error_type": error_type}

        try:
            error_result = self._validate_rom_file(rom_path)
            if error_result:
                return error_result

            # Try cache first
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMCacheProtocol
            rom_cache = inject(ROMCacheProtocol)
            cached_info = rom_cache.get_rom_info(rom_path)

            if cached_info:
                self._logger.debug(f"Loaded ROM info from cache: {rom_path}")
                # Convert Mapping to mutable dict
                result_dict = dict(cached_info)
                result_dict["cached"] = True
                return result_dict

            # Cache miss - load from file
            self._logger.debug(f"Cache miss, loading ROM info from file: {rom_path}")

            header = self.read_rom_header(rom_path)

            result: dict[str, object] = {
                "header": {
                    "title": header["title"],
                    "rom_type": header["rom_type"],
                    "checksum": header["checksum"]
                },
                "sprite_locations": {},
                "cached": False
            }

            # Get sprite locations if this is Kirby Super Star
            title = cast(str, header["title"])
            if "KIRBY" in title.upper():
                try:
                    self._logger.info(f"Scanning ROM for sprite locations: {title}")
                    locations = self.get_known_sprite_locations(rom_path)

                    sprite_dict: dict[str, int] = {}
                    for name, pointer in locations.items():
                        display_name = name.replace("_", " ").title()
                        # Pointer objects have .offset attribute (from ROM analysis)
                        sprite_dict[display_name] = cast(object, pointer).offset  # type: ignore[attr-defined] - SpritePointer has offset attr
                    result["sprite_locations"] = sprite_dict

                    self._logger.info(f"Found {len(sprite_dict)} sprite locations")

                    cache_success = rom_cache.save_rom_info(rom_path, result)
                    if cache_success:
                        self._logger.debug(f"Cached ROM info for future use: {rom_path}")
                        self.cache_saved.emit("rom_info", 1)

                except Exception as sprite_error:
                    self._logger.warning(f"Failed to load sprite locations: {sprite_error}")
                    result["sprite_locations_error"] = str(sprite_error)
            elif rom_cache.save_rom_info(rom_path, result):
                self.cache_saved.emit("rom_info", 1)

        except Exception as e:
            self._logger.exception("Failed to load ROM info")
            return _create_error_result(str(e), type(e).__name__)
        else:
            return result

    # ========== Path Suggestions ==========

    def find_suggested_input_vram(
        self, sprite_path: str,
        metadata: dict[str, object] | None = None,
        suggested_vram: str = ""
    ) -> str:
        """
        Find the best suggestion for input VRAM path.

        Args:
            sprite_path: Path to sprite file
            metadata: Loaded metadata dict (from load_metadata)
            suggested_vram: Pre-suggested VRAM path

        Returns:
            Suggested VRAM path or empty string if none found
        """
        return self._find_vram_path_internal(
            sprite_path=sprite_path,
            metadata=metadata,
            pre_suggested=suggested_vram,
            strip_editor_suffixes=True,
        )

    def _suggest_output_path(
        self,
        input_path: str,
        suffix: str,
        extension: str | None = None,
        preserve_parent: bool = False,
    ) -> str:
        """
        Generic output path suggestion with smart numbering.

        Args:
            input_path: Input file path
            suffix: Suffix to add (e.g., "_injected", "_modified")
            extension: Override extension (e.g., ".dmp") or None to preserve original
            preserve_parent: Whether to keep file in same directory as input

        Returns:
            Suggested non-existent output path
        """
        path = Path(input_path)
        base = path.stem.removesuffix(suffix)
        ext = extension if extension else path.suffix
        parent = path.parent if preserve_parent else Path()

        # Try base name with suffix
        suggested = parent / f"{base}{suffix}{ext}"
        if not suggested.exists():
            return str(suggested)

        # Try numbered variations
        for counter in range(2, 11):
            suggested = parent / f"{base}{suffix}{counter}{ext}"
            if not suggested.exists():
                return str(suggested)

        # Fall back to timestamp
        timestamp = int(time.time())
        return str(parent / f"{base}{suffix}_{timestamp}{ext}")

    def suggest_output_vram_path(self, input_vram_path: str) -> str:
        """
        Suggest output VRAM path based on input path with smart numbering.

        Args:
            input_vram_path: Input VRAM file path

        Returns:
            Suggested output path
        """
        return self._suggest_output_path(input_vram_path, "_injected", ".dmp")

    def suggest_output_rom_path(self, input_rom_path: str) -> str:
        """
        Suggest output ROM path based on input path with smart numbering.

        Args:
            input_rom_path: Input ROM file path

        Returns:
            Suggested output path (in same directory as input)
        """
        return self._suggest_output_path(
            input_rom_path, "_modified", None, preserve_parent=True
        )

    def convert_vram_to_rom_offset(self, vram_offset_str: str | int) -> int | None:
        """
        Convert VRAM offset to ROM offset based on known mappings.

        Args:
            vram_offset_str: VRAM offset as string (e.g., "0xC000") or int

        Returns:
            ROM offset as integer, or None if no mapping found
        """
        try:
            if isinstance(vram_offset_str, str):
                vram_offset = int(vram_offset_str, 16)
            else:
                vram_offset = vram_offset_str

            if vram_offset == 0xC000:
                return 0x0C8000

        except (ValueError, TypeError):
            return None
        else:
            return None

    # ========== Settings Management ==========

    def save_rom_injection_settings(self, input_rom: str, sprite_location_text: str,
                                    custom_offset: str, fast_compression: bool) -> None:
        """
        Save ROM injection parameters to settings for future use.

        Args:
            input_rom: Input ROM path
            sprite_location_text: Selected sprite location text from combo box
            custom_offset: Custom offset text if used
            fast_compression: Fast compression checkbox state
        """
        session_manager = self._get_session_manager()

        if input_rom:
            session_manager.set(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, input_rom
            )

        if sprite_location_text and sprite_location_text != "Select sprite location...":
            session_manager.set(
                SETTINGS_NS_ROM_INJECTION,
                SETTINGS_KEY_LAST_SPRITE_LOCATION,
                sprite_location_text
            )

        if custom_offset:
            session_manager.set(
                SETTINGS_NS_ROM_INJECTION,
                SETTINGS_KEY_LAST_CUSTOM_OFFSET,
                custom_offset
            )

        session_manager.set(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, fast_compression
        )

        try:
            session_manager.save_session()
        except Exception:
            self._logger.exception("Failed to save ROM injection parameters")

    def load_rom_injection_defaults(
        self, sprite_path: str, metadata: dict[str, object] | None = None
    ) -> dict[str, object]:  # Config data with mixed types (str, int, bool, None)
        """
        Load ROM injection defaults from metadata or saved settings.

        Args:
            sprite_path: Path to sprite file
            metadata: Loaded metadata dict (from load_metadata)

        Returns:
            Dict containing input_rom, output_rom, rom_offset, etc.
        """
        session_manager = self._get_session_manager()
        result: dict[str, object] = {
            "input_rom": "",
            "output_rom": "",
            "rom_offset": None,
            "sprite_location_index": None,
            "custom_offset": "",
            "fast_compression": False
        }

        if metadata and metadata.get("rom_extraction_info"):
            rom_info = metadata["rom_extraction_info"]
            if isinstance(rom_info, dict):
                rom_source = cast(str, rom_info.get("rom_source", ""))
                rom_offset_str = cast(str, rom_info.get("rom_offset", "0x0"))

                if rom_source and sprite_path:
                    sprite_dir = Path(sprite_path).parent
                    possible_rom_path = Path(sprite_dir) / rom_source
                    if possible_rom_path.exists():
                        result["input_rom"] = str(possible_rom_path)
                        result["output_rom"] = self.suggest_output_rom_path(str(possible_rom_path))

                        try:
                            if rom_offset_str.startswith(("0x", "0X")):
                                result["rom_offset"] = int(rom_offset_str, 16)
                            else:
                                result["rom_offset"] = int(rom_offset_str, 16)
                            result["custom_offset"] = rom_offset_str
                        except (ValueError, TypeError) as e:
                            # FIX #3: Log parse failure and indicate error in result
                            self._logger.warning(
                                f"Failed to parse ROM offset '{rom_offset_str}': {e}"
                            )
                            result["offset_parse_error"] = str(e)

                        return result

        # Fall back to saved settings
        last_input_rom = cast(str, session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, ""
        ))
        if last_input_rom and Path(last_input_rom).exists():
            result["input_rom"] = last_input_rom
            result["output_rom"] = self.suggest_output_rom_path(last_input_rom)

        result["custom_offset"] = session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET, ""
        )

        result["fast_compression"] = session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, False
        )

        return result

    def restore_saved_sprite_location(
        self, extraction_vram_offset: str | None,
        sprite_locations: dict[str, int]
    ) -> dict[str, object]:  # Config data with sprite location name, index, custom offset
        """
        Restore saved sprite location selection.

        Args:
            extraction_vram_offset: VRAM offset from extraction metadata
            sprite_locations: Dict of sprite name -> offset from loaded ROM

        Returns:
            Dict containing sprite_location_name, sprite_location_index, custom_offset
        """
        session_manager = self._get_session_manager()
        result: dict[str, object] = {
            "sprite_location_name": None,
            "sprite_location_index": None,
            "custom_offset": ""
        }

        if extraction_vram_offset:
            rom_offset = self.convert_vram_to_rom_offset(extraction_vram_offset)
            if rom_offset is not None:
                for i, (name, offset) in enumerate(sprite_locations.items(), 1):
                    if offset == rom_offset:
                        result["sprite_location_name"] = name
                        result["sprite_location_index"] = i
                        return result
                result["custom_offset"] = f"0x{rom_offset:X}"
                return result

        last_sprite_location = cast(str, session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_SPRITE_LOCATION, ""
        ))
        if last_sprite_location:
            saved_display_name = last_sprite_location.split(" (0x")[0] if " (0x" in last_sprite_location else last_sprite_location

            for i, name in enumerate(sprite_locations.keys(), 1):
                if name == saved_display_name:
                    result["sprite_location_name"] = name
                    result["sprite_location_index"] = i
                    break

        return result

    # ========== Cache Management ==========

    def get_cache_stats(self) -> dict[str, object]:  # Cache stats with mixed types
        """Get ROM cache statistics."""
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMCacheProtocol
        rom_cache = inject(ROMCacheProtocol)
        return dict(rom_cache.get_cache_stats())  # Convert Mapping to dict

    def clear_rom_cache(self, older_than_days: int | None = None) -> int:
        """
        Clear ROM scan cache.

        Args:
            older_than_days: If specified, only clear files older than this many days

        Returns:
            Number of cache files removed
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMCacheProtocol
        rom_cache = inject(ROMCacheProtocol)
        removed_count = rom_cache.clear_cache(older_than_days)
        self._logger.info(f"ROM cache cleared: {removed_count} files removed")
        return removed_count

    def get_scan_progress(
        self, rom_path: str, scan_params: dict[str, int]
    ) -> dict[str, object] | None:  # Scan progress with found sprites, current offset, completed flag
        """
        Get cached scan progress for resumable scanning.

        Args:
            rom_path: Path to ROM file
            scan_params: Scan parameters (int values like start offset, end offset)

        Returns:
            Dictionary with scan progress or None if not cached
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMCacheProtocol
        rom_cache = inject(ROMCacheProtocol)
        result = rom_cache.get_partial_scan_results(rom_path, scan_params)
        return dict(result) if result else None  # Convert Mapping to dict

    def save_scan_progress(
        self, rom_path: str, scan_params: dict[str, int],
        found_sprites: list[Mapping[str, object]],  # Sprite data dicts
        current_offset: int,
        completed: bool = False
    ) -> bool:
        """
        Save partial scan results for resumable scanning.

        Args:
            rom_path: Path to ROM file
            scan_params: Scan parameters (int values like start offset, end offset)
            found_sprites: List of sprites found so far
            current_offset: Current scan position
            completed: Whether the scan is complete

        Returns:
            True if saved successfully, False otherwise
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMCacheProtocol
        rom_cache = inject(ROMCacheProtocol)
        return rom_cache.save_partial_scan_results(
            rom_path, scan_params, found_sprites, current_offset, completed
        )

    def clear_scan_progress(
        self, rom_path: str | None = None,
        scan_params: dict[str, int] | None = None
    ) -> int:
        """
        Clear scan progress caches.

        Args:
            rom_path: If specified, only clear caches for this ROM
            scan_params: If specified, only clear cache for this specific scan

        Returns:
            Number of files removed
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMCacheProtocol
        rom_cache = inject(ROMCacheProtocol)
        removed_count = rom_cache.clear_scan_progress_cache(rom_path, scan_params)
        self._logger.info(f"Scan progress cache cleared: {removed_count} files removed")
        return removed_count
