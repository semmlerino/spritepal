"""
Consolidated Core Operations Manager for SpritePal.

This manager combines extraction, injection, palette, and navigation functionality
into a single cohesive unit. It provides all extraction and injection functionality
directly without using adapters or protocols.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

from PIL import Image
from PySide6.QtCore import QObject, QThread, Signal, SignalInstance

from core.exceptions import (
    ExtractionError,
    ValidationError,
)
from core.extractor import SpriteExtractor
from core.managers.application_state_manager import ApplicationStateManager
from core.palette_manager import PaletteManager
from core.services.extraction_results import ExtractionResult
from core.services.path_suggestion_service import (
    find_suggested_input_vram,
    get_smart_vram_suggestion,
    suggest_output_rom_path,
    suggest_output_vram_path,
    validate_path,
)
from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_WIDTH,
    SETTINGS_KEY_FAST_COMPRESSION,
    SETTINGS_KEY_LAST_CUSTOM_OFFSET,
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_KEY_LAST_SPRITE_LOCATION,
    SETTINGS_NS_ROM_INJECTION,
    VRAM_TO_ROM_MAPPING,
)
from utils.file_validator import FileValidator, ValidationResult
from utils.validation import validate_range, validate_required_params, validate_type

from .base_manager import BaseManager

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache


class CoreOperationsManager(BaseManager):
    """
    Consolidated manager for all core operations:
    - Extraction (ROM and VRAM)
    - Injection (ROM and VRAM)
    - Palette management
    - Navigation and sprite discovery

    This manager provides all extraction and injection functionality directly
    without using adapter classes or intermediate protocols.
    """

    # ========== Signal Architecture (Consolidated) ==========
    # Phase 2 simplification: 13 signals → 6 signals
    # - extraction_completed replaces: preview_generated, palettes_extracted,
    #   active_palettes_found, files_created
    # - Removed cache signals (cache_operation_started, cache_hit, cache_miss, cache_saved)
    # ==========================================================

    # Extraction signals (consolidated)
    extraction_progress = Signal(str)  # Progress messages
    extraction_warning = Signal(str)  # Warning message (partial success)
    extraction_completed = Signal(object)  # ExtractionResult with all data

    # Legacy extraction signals (kept for direct MainWindow connections)
    preview_generated = Signal(object, int)  # pixmap, offset
    palettes_extracted = Signal(object)  # palette data
    active_palettes_found = Signal(list)  # list of active palette indices
    files_created = Signal(list)  # list of created file paths

    # Injection signals
    injection_progress = Signal(str)  # message only
    injection_finished = Signal(bool, str)  # success, message
    compression_info = Signal(object)  # compression statistics
    progress_percent = Signal(int)  # percent only (for progress bars)

    # Cache signals (deprecated - UI no longer connects to these)
    # Kept for internal logging, will be removed in Phase 3
    cache_operation_started = Signal(str, str)  # operation, key
    cache_hit = Signal(str, float)  # key, load_time
    cache_miss = Signal(str)  # key
    cache_saved = Signal(str, int)  # key, size_bytes

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        session_manager: ApplicationStateManager | None = None,
        rom_cache: ROMCache | None = None,
        rom_extractor: ROMExtractor | None = None,
    ) -> None:
        """Initialize the core operations manager.

        IMPORTANT: Do not instantiate directly. Use create_app_context() instead.

        The None defaults exist only for dependency injection during testing.
        All three dependencies (session_manager, rom_cache, rom_extractor) are
        REQUIRED and will raise RuntimeError in _initialize() if missing.

        Why the signature allows None but _initialize() requires them:
        - Allows test fixtures to inject mocks
        - Enforces that production code goes through create_app_context()
        - Provides clear error message if misused

        Args:
            parent: Qt parent object for proper lifecycle management
            session_manager: Required. Handles settings persistence.
            rom_cache: Required. Provides ROM data caching.
            rom_extractor: Required. Provides extraction/injection operations.

        Raises:
            RuntimeError: If any dependency is None at initialization time.
                The error message directs you to use create_app_context().
        """
        # Initialize components
        self._sprite_extractor: SpriteExtractor | None = None
        self._rom_extractor: ROMExtractor | None = rom_extractor
        self._palette_manager: PaletteManager | None = None
        self._current_worker: QThread | None = None

        # DI dependencies (passed explicitly or populated in _initialize)
        self._session_manager: ApplicationStateManager | None = session_manager
        self._rom_cache: ROMCache | None = rom_cache

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

            # Validate required dependencies (must be passed via constructor)
            missing = []
            if self._rom_extractor is None:
                missing.append("rom_extractor")
            if self._session_manager is None:
                missing.append("session_manager")
            if self._rom_cache is None:
                missing.append("rom_cache")
            if missing:
                raise RuntimeError(
                    f"CoreOperationsManager missing dependencies: {', '.join(missing)}. "
                    "Use create_app_context() or get_app_context() instead of direct instantiation."
                )

            self._is_initialized = True
            self._logger.info("CoreOperationsManager initialized successfully")

        except Exception as e:
            self._handle_error(e, "initialization")
            raise

    @override
    def cleanup(self) -> None:
        """Cleanup all core operation resources."""
        # Acquire worker reference under lock to prevent race with start_injection
        worker_to_cleanup = None

        with self._lock:
            self._active_operations.clear()
            # Capture references and clear them under lock
            worker_to_cleanup = self._current_worker
            self._current_worker = None

        # Cleanup captured references OUTSIDE lock to avoid blocking
        if worker_to_cleanup:
            from core.services.worker_lifecycle import WorkerManager

            self._logger.info("Stopping active worker")
            WorkerManager.cleanup_worker(worker_to_cleanup, timeout=5000)

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
                # Clear extractors and managers
                self._sprite_extractor = None
                self._rom_extractor = None
                self._palette_manager = None
                self._is_initialized = False
                self._logger.debug("CoreOperationsManager full reset: cleared all components")

    # ========== Helper Methods ==========

    def _ensure_rom_cache(self) -> ROMCache:
        """Ensure ROM cache is available (cached from DI at initialization)."""
        return self._ensure_component(self._rom_cache, "ROM cache", ExtractionError)

    def _ensure_session_manager(self) -> ApplicationStateManager:
        """Ensure session manager is available (cached from DI at initialization)."""
        return self._ensure_component(self._session_manager, "Session manager", ExtractionError)

    def _raise_extraction_failed(self, message: str) -> None:
        """Helper method to raise ExtractionError (for TRY301 compliance)."""
        raise ExtractionError(message)

    # ========== Extraction Operations ==========

    def extract_from_vram(
        self,
        vram_path: str,
        output_base: str,
        cgram_path: str | None = None,
        oam_path: str | None = None,
        vram_offset: int | None = None,
        create_grayscale: bool = True,
        create_metadata: bool = True,
        grayscale_mode: bool = False,
    ) -> list[str]:
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
        operation = "vram_extraction"
        started = self._start_operation(operation)
        if not started:
            raise ExtractionError(f"{operation} already in progress")

        try:
            self._update_progress(operation, 0, 100)

            # Validate parameters
            if not vram_path or not output_base:
                raise ValidationError("Missing required parameters: vram_path and output_base are required")
            FileValidator.validate_vram_file_or_raise(vram_path)
            if cgram_path:
                FileValidator.validate_cgram_file_or_raise(cgram_path)
            if oam_path:
                FileValidator.validate_oam_file_or_raise(oam_path)

            extracted_files: list[str] = []
            warning: str | None = None
            palettes: dict[int, list[list[int]]] = {}
            active_palette_indices: list[int] = []

            # Extract sprites
            self.extraction_progress.emit("Extracting sprites from VRAM...")
            output_file = f"{output_base}.png"
            assert self._sprite_extractor is not None
            img, num_tiles = self._sprite_extractor.extract_sprites_grayscale(
                vram_path, output_file, offset=vram_offset
            )
            extracted_files.append(output_file)

            # Generate preview
            self.extraction_progress.emit("Creating preview...")

            # Extract palettes if requested - catch errors for partial success
            if not grayscale_mode and cgram_path:
                try:
                    from core.services.palette_utils import extract_palettes_and_create_files

                    assert self._palette_manager is not None
                    palette_result = extract_palettes_and_create_files(
                        palette_manager=self._palette_manager,
                        cgram_path=cgram_path,
                        output_base=output_base,
                        png_file=output_file,
                        oam_path=oam_path,
                        source_path=vram_path,
                        source_offset=vram_offset,
                        num_tiles=num_tiles,
                        create_grayscale=create_grayscale,
                        create_metadata=create_metadata,
                        progress_callback=self.extraction_progress.emit,
                    )
                    extracted_files.extend(palette_result.files)
                    palettes = palette_result.palettes
                    active_palette_indices = palette_result.active_palette_indices
                except Exception as e:
                    # Log and track palette failure but don't fail sprite extraction
                    warning = f"Sprites extracted but palette extraction failed: {e}"
                    self._logger.warning(f"Palette extraction failed: {e}")

            # Log completion
            if warning:
                self.extraction_progress.emit("Extraction complete (palettes failed)")
            else:
                self.extraction_progress.emit("Extraction complete!")

            # Build result and emit signals
            result = ExtractionResult(
                files=extracted_files,
                preview_image=img,
                tile_count=num_tiles,
                palettes=palettes,
                active_palette_indices=active_palette_indices,
                warning=warning,
            )

            # Emit consolidated signal (new)
            self.extraction_completed.emit(result)

            # Emit legacy signals for backward compatibility (TODO: remove in Phase 3)
            if result.preview_image:
                self.preview_generated.emit(result.preview_image, result.tile_count)
            if result.palettes:
                self.palettes_extracted.emit(result.palettes)
            if result.active_palette_indices:
                self.active_palettes_found.emit(result.active_palette_indices)
            if result.warning:
                self.extraction_warning.emit(result.warning)
            self.files_created.emit(result.files)
            self._update_progress(operation, 100, 100)
            return result.files
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, operation, "VRAM extraction")
            raise  # Unreachable but satisfies type checker
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, operation, "VRAM extraction")
            raise
        except ValidationError:
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                self._handle_operation_error(e, operation, ExtractionError, "VRAM extraction")
            raise
        finally:
            if started:
                self._finish_operation(operation)

    def extract_from_rom(
        self, rom_path: str, offset: int, output_base: str, sprite_name: str, cgram_path: str | None = None
    ) -> list[str]:
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
        operation = "rom_extraction"
        started = self._start_operation(operation)
        if not started:
            raise ExtractionError(f"{operation} already in progress")

        try:
            self._update_progress(operation, 0, 100)

            # Validate parameters
            FileValidator.validate_rom_file_or_raise(rom_path)
            if offset < 0:
                raise ValidationError(f"offset must be >= 0, got {offset}")
            if cgram_path:
                FileValidator.validate_cgram_file_or_raise(cgram_path)

            extracted_files: list[str] = []
            warning: str | None = None
            preview_image: Image.Image | None = None
            tile_count = 0
            palettes: dict[int, list[list[int]]] = {}
            active_palette_indices: list[int] = []

            # Extract from ROM
            self.extraction_progress.emit(f"Extracting {sprite_name} from ROM...")
            assert self._rom_extractor is not None
            output_path, _extraction_info = self._rom_extractor.extract_sprite_from_rom(
                rom_path, offset, output_base, sprite_name
            )

            if output_path:
                # Create PIL image for preview using context manager to prevent resource leak
                with Image.open(output_path) as img:
                    tile_count = (img.width * img.height) // (8 * 8)
                    # Copy image data before context exits (caller needs valid data)
                    preview_image = img.copy()

                extracted_files.append(output_path)

                # Extract palettes if CGRAM provided - catch errors for partial success
                if cgram_path:
                    try:
                        from core.services.palette_utils import extract_palettes_and_create_files

                        assert self._palette_manager is not None
                        palette_result = extract_palettes_and_create_files(
                            palette_manager=self._palette_manager,
                            cgram_path=cgram_path,
                            output_base=output_base,
                            png_file=output_path,
                            oam_path=None,
                            source_path=rom_path,
                            source_offset=offset,
                            num_tiles=tile_count,
                            create_grayscale=True,
                            create_metadata=True,
                            progress_callback=self.extraction_progress.emit,
                        )
                        extracted_files.extend(palette_result.files)
                        palettes = palette_result.palettes
                        active_palette_indices = palette_result.active_palette_indices
                    except Exception as e:
                        # Log and track palette failure but don't fail sprite extraction
                        warning = f"Sprite extracted but palette extraction failed: {e}"
                        self._logger.warning(f"Palette extraction failed: {e}")
            else:
                raise ExtractionError("Failed to extract sprite from ROM")

            # Log completion
            if warning:
                self.extraction_progress.emit("ROM extraction complete (palettes failed)")
            else:
                self.extraction_progress.emit("ROM extraction complete!")

            # Build result and emit signals
            result = ExtractionResult(
                files=extracted_files,
                preview_image=preview_image,
                tile_count=tile_count,
                palettes=palettes,
                active_palette_indices=active_palette_indices,
                warning=warning,
            )

            # Emit consolidated signal (new)
            self.extraction_completed.emit(result)

            # Emit legacy signals for backward compatibility (TODO: remove in Phase 3)
            if result.preview_image:
                self.preview_generated.emit(result.preview_image, result.tile_count)
            if result.palettes:
                self.palettes_extracted.emit(result.palettes)
            if result.active_palette_indices:
                self.active_palettes_found.emit(result.active_palette_indices)
            if result.warning:
                self.extraction_warning.emit(result.warning)
            self.files_created.emit(result.files)
            self._update_progress(operation, 100, 100)
            return result.files
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, operation, "ROM extraction")
            raise
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, operation, "ROM extraction")
            raise
        except ValidationError:
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                self._handle_operation_error(e, operation, ExtractionError, "ROM extraction")
            raise
        finally:
            if started:
                self._finish_operation(operation)

    def get_sprite_preview(self, rom_path: str, offset: int, sprite_name: str | None = None) -> tuple[bytes, int, int]:
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
        operation = "sprite_preview"
        # Non-exclusive operation - always start (allows concurrent previews)
        started = self._start_operation(operation)

        try:
            # Validate parameters
            FileValidator.validate_rom_file_exists_or_raise(rom_path)
            if offset < 0:
                raise ValidationError(f"offset must be >= 0, got {offset}")

            name = sprite_name or f"offset_0x{offset:X}"
            self._logger.debug(f"Generating preview for {name} at offset 0x{offset:X}")

            # Calculate preview dimensions and expected data size
            width = DEFAULT_PREVIEW_WIDTH
            height = DEFAULT_PREVIEW_HEIGHT
            tile_count = (width * height) // (8 * 8)
            expected_bytes = tile_count * BYTES_PER_TILE

            # Validate offset against ROM size BEFORE reading
            rom_size = Path(rom_path).stat().st_size
            if offset >= rom_size:
                raise ValueError(f"Offset 0x{offset:X} exceeds ROM size 0x{rom_size:X}")

            available_bytes = rom_size - offset
            if expected_bytes > available_bytes:
                raise ValueError(
                    f"Insufficient data at offset 0x{offset:X}: "
                    f"need {expected_bytes} bytes, only {available_bytes} available"
                )

            # Read raw data from ROM with validation
            with Path(rom_path).open("rb") as f:
                f.seek(offset)
                tile_data = f.read(expected_bytes)

                if len(tile_data) != expected_bytes:
                    raise OSError(
                        f"Incomplete read at offset 0x{offset:X}: got {len(tile_data)}/{expected_bytes} bytes"
                    )

            return tile_data, width, height
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, operation, "preview generation")
            raise
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, operation, "preview generation")
            raise
        except ValidationError:
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                self._handle_operation_error(e, operation, ExtractionError, "preview generation")
            raise
        finally:
            if started:
                self._finish_operation(operation)

    def validate_extraction_params(self, params: Mapping[str, object]) -> bool:
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
            validate_required_params(params, ["output_base"])
        elif "rom_path" in params:
            # ROM extraction
            validate_required_params(params, ["rom_path", "offset", "output_base"])
            rom_path = cast(str, params["rom_path"])
            FileValidator.validate_rom_file_exists_or_raise(rom_path)
            validate_type(params["offset"], "offset", int)
            offset = cast(int, params["offset"])
            validate_range(offset, "offset", min_val=0)
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
        try:
            assert self._sprite_extractor is not None
            # Load VRAM
            self._sprite_extractor.load_vram(vram_path)
            # Extract tiles with new offset
            tiles, num_tiles = self._sprite_extractor.extract_tiles(offset=offset)
            # Create grayscale image
            img = self._sprite_extractor.create_grayscale_image(tiles)
            return img, num_tiles
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

    def get_rom_extractor(self) -> ROMExtractor:
        """Get the ROM extractor instance for advanced operations."""
        assert self._rom_extractor is not None
        return self._rom_extractor

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, object]:  # Pointer objects with .offset attribute
        """
        Get known sprite locations for a ROM with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations (values are pointer objects with .offset)

        Raises:
            ExtractionError: If operation fails
        """
        try:
            # Validate ROM file exists
            FileValidator.validate_rom_file_exists_or_raise(rom_path)

            # Try to load from cache first
            start_time = time.time()
            assert self._rom_cache is not None
            cached_locations = self._rom_cache.get_sprite_locations(rom_path)

            # Emit cache signals
            self.cache_operation_started.emit("Loading", "sprite_locations")

            if cached_locations:
                time_saved = 2.5  # Estimated time saved by not scanning ROM
                self._logger.debug(f"Loaded sprite locations from cache: {rom_path}")
                self.cache_hit.emit("sprite_locations", time_saved)
                return dict(cached_locations)

            # Cache miss - scan ROM file
            self.cache_miss.emit("sprite_locations")
            self._logger.debug(f"Cache miss, scanning ROM for sprite locations: {rom_path}")
            assert self._rom_extractor is not None
            locations = self._rom_extractor.get_known_sprite_locations(rom_path)
            scan_time = time.time() - start_time

            # Save to cache for future use
            if locations:
                cache_success = self._rom_cache.save_sprite_locations(rom_path, locations)
                if cache_success:
                    self._logger.debug(
                        f"Cached {len(locations)} sprite locations for future use (scan took {scan_time:.1f}s)"
                    )
                    self.cache_operation_started.emit("Saving", "sprite_locations")
                    self.cache_saved.emit("sprite_locations", len(locations))

            return dict(locations)
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, "get_known_sprite_locations", "getting sprite locations")
            raise
        except (ImportError, AttributeError) as e:
            self._handle_operation_error(e, "get_known_sprite_locations", ExtractionError, "ROM analysis not available")
            raise
        except Exception as e:
            if not isinstance(e, ExtractionError):
                self._handle_operation_error(
                    e, "get_known_sprite_locations", ExtractionError, "getting sprite locations"
                )
            raise

    def read_rom_header(self, rom_path: str) -> dict[str, object]:  # ROM header with title, rom_type, checksum, etc.
        """
        Read ROM header information.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary containing ROM header information

        Raises:
            ExtractionError: If operation fails
        """
        try:
            # Validate ROM file exists
            FileValidator.validate_rom_file_exists_or_raise(rom_path)
            # ROMExtractor has rom_injector with read_rom_header method
            assert self._rom_extractor is not None
            header = self._rom_extractor.rom_injector.read_rom_header(rom_path)
            return asdict(header)
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

    def _validate_rom_file(self, rom_path: str) -> ValidationResult:
        """Validate ROM file exists, is readable, and has reasonable size.

        Uses FileValidator for comprehensive validation.

        Returns:
            ValidationResult with is_valid, error_message, warnings, and file_info
        """
        return FileValidator.validate_rom_file(rom_path)

    def _validate_extraction_rom_file(self, rom_path: str) -> None:
        """Validate ROM file for extraction and raise if invalid."""
        result = FileValidator.validate_rom_file(rom_path)
        if not result.is_valid:
            raise ValidationError(result.error_message or f"Invalid ROM file: {rom_path}")

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
            from core.workers import (
                ROMInjectionParams,
                ROMInjectionWorker,
                VRAMInjectionParams,
                VRAMInjectionWorker,
            )

            # Validate parameters
            self.validate_injection_params(params)

            # Stop any existing worker
            cleanup_timeout = 5000 if params.get("mode") == "rom" else 2000
            if self._current_worker is not None:
                cleanup_success = WorkerManager.cleanup_worker(self._current_worker, timeout=cleanup_timeout)
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
                # Build VRAM params with type casts
                sprite_path_val = cast(str, params["sprite_path"])
                input_vram_val = cast(str, params["input_vram"])
                output_vram_val = cast(str, params["output_vram"])
                offset_val = cast(int, params["offset"])
                metadata_path_val = cast(str | None, params.get("metadata_path"))

                vram_params: VRAMInjectionParams = {
                    "mode": "vram",
                    "sprite_path": sprite_path_val,
                    "input_vram": input_vram_val,
                    "output_vram": output_vram_val,
                    "offset": offset_val,
                    "metadata_path": metadata_path_val,
                }
                # Use self as the injection manager
                worker = VRAMInjectionWorker(vram_params, self)
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
            # NOTE: Always finish operation if we didn't successfully start a worker.
            # If worker is running, it will call _finish_operation when it completes.
            # This prevents "injection already in progress" errors after validation failures.
            if not self._current_worker or not self._current_worker.isRunning():
                self._finish_operation(operation)

    def validate_injection_params(self, params: Mapping[str, object]) -> None:
        """
        Validate injection parameters.

        Args:
            params: Parameters to validate

        Raises:
            ValidationError: If parameters are invalid
        """
        # Check required common parameters
        required = ["mode", "sprite_path", "offset"]
        validate_required_params(params, required)

        validate_type(params["mode"], "mode", str)
        validate_type(params["sprite_path"], "sprite_path", str)
        validate_type(params["offset"], "offset", int)

        # Use FileValidator for sprite file validation
        sprite_path = cast(str, params["sprite_path"])
        sprite_result = FileValidator.validate_image_file(sprite_path)
        if not sprite_result.is_valid:
            raise ValidationError(f"Sprite file validation failed: {sprite_result.error_message}")

        offset = cast(int, params["offset"])
        validate_range(offset, "offset", min_val=0)

        # Check mode-specific parameters
        mode = cast(str, params["mode"])
        if mode == "vram":
            vram_required = ["input_vram", "output_vram"]
            validate_required_params(params, vram_required)

            input_vram = cast(str, params["input_vram"])
            vram_result = FileValidator.validate_vram_file(input_vram)
            if not vram_result.is_valid:
                raise ValidationError(f"Input VRAM file validation failed: {vram_result.error_message}")

        elif mode == "rom":
            rom_required = ["input_rom", "output_rom"]
            validate_required_params(params, rom_required)

            input_rom = cast(str, params["input_rom"])
            rom_result = FileValidator.validate_rom_file(input_rom)
            if not rom_result.is_valid:
                raise ValidationError(f"Input ROM file validation failed: {rom_result.error_message}")

            # Validate optional fast_compression parameter
            if "fast_compression" in params:
                validate_type(params["fast_compression"], "fast_compression", bool)
        else:
            raise ValidationError(f"Invalid injection mode: {mode}")

        # Validate optional metadata_path
        metadata_path_val = params.get("metadata_path")
        if metadata_path_val:
            metadata_path = cast(str, metadata_path_val)
            metadata_result = FileValidator.validate_json_file(metadata_path)
            if not metadata_result.is_valid:
                raise ValidationError(f"Metadata file validation failed: {metadata_result.error_message}")

    def is_injection_active(self) -> bool:
        """Check if injection is currently active."""
        # Check local worker (kept in facade for backward compatibility)
        return bool(self._current_worker and self._current_worker.isRunning())

    @override
    def is_initialized(self) -> bool:
        """Check if manager is initialized.

        Returns:
            True if initialization completed successfully.
        """
        return self._is_initialized

    def has_active_worker(self) -> bool:
        """Check if there's an active worker.

        Returns:
            True if a worker exists (running or not).
        """
        return self._current_worker is not None

    def _connect_worker_signals(self) -> None:
        """Connect worker signals to manager signals."""
        if not self._current_worker:
            return

        worker = self._current_worker
        progress_signal = getattr(worker, "progress", None)
        if isinstance(progress_signal, SignalInstance):
            progress_signal.connect(self._on_worker_progress_adapter)

        injection_finished_signal = getattr(worker, "injection_finished", None)
        if isinstance(injection_finished_signal, SignalInstance):
            injection_finished_signal.connect(self._on_worker_finished)
        else:
            worker.finished.connect(lambda: self._on_worker_finished(True, "Completed"))

        # ROM-specific signals
        progress_percent_signal = getattr(worker, "progress_percent", None)
        if isinstance(progress_percent_signal, SignalInstance):
            progress_percent_signal.connect(self.progress_percent.emit)

        compression_info_signal = getattr(worker, "compression_info", None)
        if isinstance(compression_info_signal, SignalInstance):
            compression_info_signal.connect(self.compression_info.emit)

    @override
    def _on_worker_progress(self, message: str) -> None:
        """Handle worker progress - emit injection-specific signal."""
        self.injection_progress.emit(message)

    def _on_worker_finished(self, success: bool, message: str) -> None:
        """Handle worker completion."""
        self._handle_worker_completion("injection", success, message)

        # Invalidate cache for modified ROM on successful injection
        if success:
            self._invalidate_injection_cache()

        self.injection_finished.emit(success, message)

    def _invalidate_injection_cache(self) -> None:
        """Invalidate cache entries for ROM modified by injection.

        Clears cache for the output ROM after successful injection to prevent
        stale sprite data from being displayed. Only applies to ROM injection,
        not VRAM injection.
        """
        if not self._current_worker:
            return

        # Get injection params from worker
        params = getattr(self._current_worker, "params", None)
        if not params:
            return

        # Only ROM injection modifies ROM files
        if params.get("mode") != "rom":
            return

        output_rom = params.get("output_rom")
        if not output_rom:
            return

        try:
            rom_cache = self._ensure_rom_cache()
            removed = rom_cache.invalidate_rom_cache(str(output_rom))
            self._logger.debug(f"Cache invalidation removed {removed} entries for {output_rom}")

        except Exception as e:
            # Cache invalidation failure should not break injection success
            self._logger.warning(f"Failed to invalidate cache after injection: {e}")

    def _cleanup_current_worker(self) -> None:
        """
        Stop and clear current worker on error.

        Ensures worker is properly stopped when exception occurs
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
        return validate_path(path)

    def get_smart_vram_suggestion(self, sprite_path: str, metadata_path: str = "") -> str:
        """
        Get smart suggestion for input VRAM path using multiple strategies.

        Args:
            sprite_path: Path to sprite file
            metadata_path: Optional metadata file path

        Returns:
            Suggested VRAM path or empty string if none found
        """
        return get_smart_vram_suggestion(
            sprite_path=sprite_path,
            metadata_path=metadata_path,
            session_manager=self._ensure_session_manager(),
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

                parsed_info = {"metadata": metadata, "source_type": source_type, "extraction": extraction}

                if source_type == "rom":
                    parsed_info["rom_extraction_info"] = {
                        "rom_source": extraction.get("rom_source", ""),
                        "rom_offset": extraction.get("rom_offset", "0x0"),
                        "sprite_name": extraction.get("sprite_name", ""),
                        "tile_count": extraction.get("tile_count", "Unknown"),
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
                "default_vram_offset": "0xC000",
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
            validation_result = self._validate_rom_file(rom_path)
            if not validation_result.is_valid:
                error_msg = validation_result.error_message or f"Invalid ROM file: {rom_path}"
                return _create_error_result(error_msg, "ValidationError")

            # Try cache first
            rom_cache = self._ensure_rom_cache()
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
                "header": {"title": header["title"], "rom_type": header["rom_type"], "checksum": header["checksum"]},
                "sprite_locations": {},
                "cached": False,
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
        self, sprite_path: str, metadata: Mapping[str, object] | None = None, suggested_vram: str = ""
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
        return find_suggested_input_vram(
            sprite_path=sprite_path,
            metadata=metadata,
            suggested_vram=suggested_vram,
            session_manager=self._ensure_session_manager(),
        )

    def suggest_output_vram_path(self, input_vram_path: str) -> str:
        """
        Suggest output VRAM path based on input path with smart numbering.

        Args:
            input_vram_path: Input VRAM file path

        Returns:
            Suggested output path
        """
        return suggest_output_vram_path(input_vram_path)

    def suggest_output_rom_path(self, input_rom_path: str) -> str:
        """
        Suggest output ROM path based on input path with smart numbering.

        Args:
            input_rom_path: Input ROM file path

        Returns:
            Suggested output path (in same directory as input)
        """
        return suggest_output_rom_path(input_rom_path)

    def convert_vram_to_rom_offset(self, vram_offset_str: str | int) -> int | None:
        """
        Convert VRAM offset to ROM offset based on known mappings.

        The SNES PPU loads sprite tiles from VRAM, but the actual graphics data
        lives in ROM at different addresses. This mapping is game-specific.
        See VRAM_TO_ROM_MAPPING in utils/constants.py for known mappings.

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

            # Use the documented VRAM→ROM mapping from constants
            return VRAM_TO_ROM_MAPPING.get(vram_offset)

        except (ValueError, TypeError):
            return None

    # ========== Settings Management ==========

    def save_rom_injection_settings(
        self, input_rom: str, sprite_location_text: str, custom_offset: str, fast_compression: bool
    ) -> None:
        """
        Save ROM injection parameters to settings for future use.

        Args:
            input_rom: Input ROM path
            sprite_location_text: Selected sprite location text from combo box
            custom_offset: Custom offset text if used
            fast_compression: Fast compression checkbox state
        """
        session_manager = self._ensure_session_manager()

        if input_rom:
            session_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, input_rom)

        if sprite_location_text and sprite_location_text != "Select sprite location...":
            session_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_SPRITE_LOCATION, sprite_location_text)

        if custom_offset:
            session_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET, custom_offset)

        session_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, fast_compression)

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
        session_manager = self._ensure_session_manager()
        result: dict[str, object] = {
            "input_rom": "",
            "output_rom": "",
            "rom_offset": None,
            "sprite_location_index": None,
            "custom_offset": "",
            "fast_compression": False,
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
                            # Log parse failure and indicate error in result
                            self._logger.warning(f"Failed to parse ROM offset '{rom_offset_str}': {e}")
                            result["offset_parse_error"] = str(e)

                        return result

        # Fall back to saved settings
        last_input_rom = cast(str, session_manager.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, ""))
        if last_input_rom and Path(last_input_rom).exists():
            result["input_rom"] = last_input_rom
            result["output_rom"] = self.suggest_output_rom_path(last_input_rom)

        result["custom_offset"] = session_manager.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET, "")

        result["fast_compression"] = session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, False
        )

        return result

    def restore_saved_sprite_location(
        self, extraction_vram_offset: str | None, sprite_locations: dict[str, int]
    ) -> dict[str, object]:  # Config data with sprite location name, index, custom offset
        """
        Restore saved sprite location selection.

        Args:
            extraction_vram_offset: VRAM offset from extraction metadata
            sprite_locations: Dict of sprite name -> offset from loaded ROM

        Returns:
            Dict containing sprite_location_name, sprite_location_index, custom_offset
        """
        session_manager = self._ensure_session_manager()
        result: dict[str, object] = {"sprite_location_name": None, "sprite_location_index": None, "custom_offset": ""}

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

        last_sprite_location = cast(
            str, session_manager.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_SPRITE_LOCATION, "")
        )
        if last_sprite_location:
            saved_display_name = (
                last_sprite_location.split(" (0x")[0] if " (0x" in last_sprite_location else last_sprite_location
            )

            for i, name in enumerate(sprite_locations.keys(), 1):
                if name == saved_display_name:
                    result["sprite_location_name"] = name
                    result["sprite_location_index"] = i
                    break

        return result

    # ========== Cache Management ==========

    def get_cache_stats(self) -> dict[str, object]:
        """Get ROM cache statistics."""
        if self._rom_cache is None:
            return {}
        return dict(self._rom_cache.get_cache_stats())

    def clear_rom_cache(self, older_than_days: int | None = None) -> int:
        """Clear ROM scan cache."""
        if self._rom_cache is None:
            return 0
        removed_count = self._rom_cache.clear_cache(older_than_days)
        self._logger.info(f"ROM cache cleared: {removed_count} files removed")
        return removed_count

    def get_scan_progress(self, rom_path: str, scan_params: dict[str, int]) -> dict[str, object] | None:
        """Get cached scan progress for resumable scanning."""
        if self._rom_cache is None:
            return None
        result = self._rom_cache.get_partial_scan_results(rom_path, scan_params)
        return dict(result) if result else None

    def save_scan_progress(
        self,
        rom_path: str,
        scan_params: dict[str, int],
        found_sprites: list[Mapping[str, object]],
        current_offset: int,
        completed: bool = False,
    ) -> bool:
        """Save partial scan results for resumable scanning."""
        if self._rom_cache is None:
            return False
        return self._rom_cache.save_partial_scan_results(
            rom_path, scan_params, found_sprites, current_offset, completed
        )

    def clear_scan_progress(self, rom_path: str | None = None, scan_params: dict[str, int] | None = None) -> int:
        """Clear scan progress caches."""
        if self._rom_cache is None:
            return 0
        removed_count = self._rom_cache.clear_scan_progress_cache(rom_path, scan_params)
        self._logger.info(f"Scan progress cache cleared: {removed_count} files removed")
        return removed_count
