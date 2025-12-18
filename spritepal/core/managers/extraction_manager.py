"""
ExtractionManager - Base class for ExtractionAdapter.

This module provides the ExtractionManager class which serves as a base class
for the ExtractionAdapter in the consolidated manager architecture.

.. deprecated::
    Direct instantiation of ExtractionManager is deprecated. Use dependency injection::

        from core.di_container import inject
        from core.protocols.manager_protocols import ExtractionManagerProtocol

        extraction_mgr = inject(ExtractionManagerProtocol)

    This class exists primarily as a base class for ExtractionAdapter, which
    provides backward compatibility while delegating to CoreOperationsManager.
    All business logic now lives in CoreOperationsManager.

See Also:
    - :class:`core.managers.core_operations_manager.CoreOperationsManager`
    - :class:`core.managers.core_operations_manager.ExtractionAdapter`
"""
from __future__ import annotations

from typing import Any, override

from PIL import Image
from PySide6.QtCore import QObject, Signal

from core.extractor import SpriteExtractor
from core.palette_manager import PaletteManager
from core.rom_extractor import ROMExtractor
from core.services.rom_service import ROMService
from core.services.vram_service import VRAMService
from utils.file_validator import FileValidator

from .base_manager import BaseManager
from .exceptions import ExtractionError, ValidationError


class ExtractionManager(BaseManager):
    """
    Base class for extraction management - provides interface for ExtractionAdapter.

    .. deprecated::
        Do not instantiate directly. Use dependency injection instead::

            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            extraction_mgr = inject(ExtractionManagerProtocol)

        This class serves as a base class for ExtractionAdapter, which inherits
        from it for interface compatibility while delegating to
        CoreOperationsManager for actual functionality.
    """

    # Additional signals specific to extraction
    extraction_progress = Signal(str)  # Progress message
    extraction_warning = Signal(str)  # Warning message (partial success)
    preview_generated = Signal(object, int)  # PIL Image, tile count
    palettes_extracted = Signal(dict)  # Palette data
    active_palettes_found = Signal(list)  # Active palette indices
    files_created = Signal(list)  # List of created files
    cache_operation_started = Signal(str, str)  # Operation type, cache type
    cache_hit = Signal(str, float)  # Cache type, time saved in seconds
    cache_miss = Signal(str)  # Cache type
    cache_saved = Signal(str, int)  # Cache type, number of items saved

    def __init__(self, parent: QObject | None = None) -> None:
        """
        Initialize the extraction manager.

        Args:
            parent: Optional parent QObject

        Note:
            This class should not be instantiated directly. Use dependency injection::

                from core.di_container import inject
                from core.protocols.manager_protocols import ExtractionManagerProtocol
                extraction_mgr = inject(ExtractionManagerProtocol)
        """
        # Note: deprecation warning removed - it never fired since ExtractionAdapter
        # is the only subclass and always passes through here

        # Declare instance variables with type hints
        self._sprite_extractor: SpriteExtractor | None = None
        self._rom_extractor: ROMExtractor | None = None
        self._palette_manager: PaletteManager | None = None

        # Services for delegation
        self._rom_service: ROMService | None = None
        self._vram_service: VRAMService | None = None

        super().__init__("ExtractionManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize extraction components and services"""
        # Initialize extractors (kept for backward compatibility and direct access)
        # ROMExtractor via DI (has required rom_cache dependency)
        from core.di_container import inject
        from core.protocols.manager_protocols import ROMExtractorProtocol
        self._sprite_extractor = SpriteExtractor()
        self._rom_extractor = inject(ROMExtractorProtocol)
        self._palette_manager = PaletteManager()

        # Initialize services with shared components
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

        # Connect service signals to manager signals for backward compatibility
        self._connect_service_signals()

        self._is_initialized = True
        self._logger.info("ExtractionManager initialized with ROM and VRAM services")

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
        """Cleanup extraction resources"""
        # Clear any active operations to prevent "already active" warnings
        with self._lock:
            self._active_operations.clear()

        # Cleanup services
        if self._rom_service:
            self._rom_service.cleanup()
        if self._vram_service:
            self._vram_service.cleanup()

    def reset_state(self, full_reset: bool = False) -> None:
        """Reset internal state for test isolation.

        This method clears any mutable state that could leak between tests
        when the manager is used in class-scoped fixtures.

        Args:
            full_reset: If True, also clears long-lived components (sprite_extractor,
                       rom_extractor, palette_manager, services). They will be recreated on
                       next use. Use for tests requiring complete isolation.
                       Default is False for performance (these are stateless).
        """
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

                # Clear long-lived components - they'll be recreated via _initialize()
                self._sprite_extractor = None
                self._rom_extractor = None
                self._palette_manager = None
                self._is_initialized = False
                self._logger.debug("ExtractionManager full reset: cleared all components and services")

    def _ensure_sprite_extractor(self) -> SpriteExtractor:
        """Ensure sprite extractor is initialized and return it."""
        if self._sprite_extractor is None:
            raise ExtractionError("ExtractionManager not properly initialized - sprite extractor is None")
        return self._sprite_extractor

    def _ensure_rom_extractor(self) -> ROMExtractor:
        """Ensure ROM extractor is initialized and return it."""
        if self._rom_extractor is None:
            raise ExtractionError("ExtractionManager not properly initialized - ROM extractor is None")
        return self._rom_extractor

    def _ensure_palette_manager(self) -> PaletteManager:
        """Ensure palette manager is initialized and return it."""
        if self._palette_manager is None:
            raise ExtractionError("ExtractionManager not properly initialized - palette manager is None")
        return self._palette_manager

    def extract_from_vram(self, vram_path: str, output_base: str,
                         cgram_path: str | None = None,
                         oam_path: str | None = None,
                         vram_offset: int | None = None,
                         create_grayscale: bool = True,
                         create_metadata: bool = True,
                         grayscale_mode: bool = False) -> list[str]:
        """
        Extract sprites from VRAM dump.

        Delegates to VRAMService while maintaining operation tracking.

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

        if self._vram_service is None:
            raise ExtractionError("VRAMService not initialized")

        if not self._start_operation(operation):
            raise ExtractionError("VRAM extraction already in progress")

        try:
            self._update_progress(operation, 0, 100)
            # Delegate to VRAM service (signals are forwarded automatically)
            result = self._vram_service.extract_from_vram(
                vram_path=vram_path,
                output_base=output_base,
                cgram_path=cgram_path,
                oam_path=oam_path,
                vram_offset=vram_offset,
                create_grayscale=create_grayscale,
                create_metadata=create_metadata,
                grayscale_mode=grayscale_mode,
            )
            self._update_progress(operation, 100, 100)
            return result
        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, operation, "VRAM extraction")
            raise
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
            self._finish_operation(operation)

    def extract_from_rom(self, rom_path: str, offset: int,
                        output_base: str, sprite_name: str,
                        cgram_path: str | None = None) -> list[str]:
        """
        Extract sprites from ROM at specific offset.

        Delegates to ROMService while maintaining operation tracking.

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

        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")

        if not self._start_operation(operation):
            raise ExtractionError("ROM extraction already in progress")

        try:
            self._update_progress(operation, 0, 100)
            # Delegate to ROM service (signals are forwarded automatically)
            result = self._rom_service.extract_from_rom(
                rom_path=rom_path,
                offset=offset,
                output_base=output_base,
                sprite_name=sprite_name,
                cgram_path=cgram_path,
            )
            self._update_progress(operation, 100, 100)
            return result
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
            self._finish_operation(operation)

    def get_sprite_preview(self, rom_path: str, offset: int,
                          sprite_name: str | None = None) -> tuple[bytes, int, int]:
        """
        Get a preview of sprite data from ROM without saving files.

        Delegates to ROMService.

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

        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")

        started = self._start_operation(operation)
        if not started:
            # Allow multiple preview operations
            self._logger.debug("Preview operation already running, allowing concurrent preview")

        try:
            return self._rom_service.get_sprite_preview(rom_path, offset, sprite_name)
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

    def validate_extraction_params(self, params: dict[str, Any]) -> bool:
        """
        Validate extraction parameters

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

            # Use FileValidator for ROM file validation
            self._validate_rom_file_exists(params["rom_path"])

            self._validate_type(params["offset"], "offset", int)
            self._validate_range(params["offset"], "offset", min_val=0)
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

            # Note: File existence validation is now handled by controller
            # to provide better fail-fast behavior and avoid blocking I/O

        # Validate output_base is provided and not empty
        output_base = params.get("output_base", "")
        if not output_base or not output_base.strip():
            raise ValidationError("Output name is required for extraction")

        # Note: Optional file existence validation is now handled by controller

        # Return True if all validation passes
        return True

    def generate_preview(self, vram_path: str, offset: int) -> tuple[Image.Image, int]:
        """Generate a preview image from VRAM at the specified offset.

        Delegates to VRAMService.

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

    def get_rom_extractor(self) -> ROMExtractor:
        """
        Get the ROM extractor instance for advanced operations.

        Delegates to ROMService.

        Returns:
            ROMExtractor instance

        Note:
            This method provides access to the underlying ROM extractor
            for UI components that need direct access to ROM operations.
            Consider using the manager methods when possible.
        """
        if self._rom_service is None:
            raise ExtractionError("ROMService not initialized")
        return self._rom_service.get_rom_extractor()

    def extract_sprite_to_png(self, rom_path: str, sprite_offset: int,
                             output_path: str, cgram_path: str | None = None) -> bool:
        """
        Extract a single sprite to PNG file.

        Delegates to ROMService.

        Args:
            rom_path: Path to ROM file
            sprite_offset: Offset of sprite in ROM
            output_path: Full path where PNG should be saved
            cgram_path: Optional CGRAM file for palette data

        Returns:
            True if extraction successful, False otherwise
        """
        if self._rom_service is None:
            self.error_occurred.emit("ROMService not initialized")
            return False
        return self._rom_service.extract_sprite_to_png(
            rom_path, sprite_offset, output_path, cgram_path
        )

    def get_known_sprite_locations(self, rom_path: str) -> dict[str, Any]:
        """
        Get known sprite locations for a ROM with caching.

        Delegates to ROMService.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of known sprite locations

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

    def read_rom_header(self, rom_path: str) -> dict[str, Any]:
        """
        Read ROM header information.

        Delegates to ROMService.

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

    def _raise_extraction_failed(self, message: str) -> None:
        """Helper method to raise ExtractionError (for TRY301 compliance)"""
        raise ExtractionError(message)

    def _validate_vram_file(self, vram_path: str) -> None:
        """Validate VRAM file and raise if invalid"""
        vram_result = FileValidator.validate_vram_file(vram_path)
        if not vram_result.is_valid:
            raise ValidationError(f"VRAM file validation failed: {vram_result.error_message}")

    def _validate_cgram_file(self, cgram_path: str) -> None:
        """Validate CGRAM file and raise if invalid"""
        cgram_result = FileValidator.validate_cgram_file(cgram_path)
        if not cgram_result.is_valid:
            raise ValidationError(f"CGRAM file validation failed: {cgram_result.error_message}")

    def _validate_oam_file(self, oam_path: str) -> None:
        """Validate OAM file and raise if invalid"""
        oam_result = FileValidator.validate_oam_file(oam_path)
        if not oam_result.is_valid:
            raise ValidationError(f"OAM file validation failed: {oam_result.error_message}")

    def _validate_rom_file(self, rom_path: str) -> None:
        """Validate ROM file and raise if invalid"""
        rom_result = FileValidator.validate_rom_file(rom_path)
        if not rom_result.is_valid:
            raise ValidationError(f"ROM file validation failed: {rom_result.error_message}")

    def _validate_rom_file_exists(self, rom_path: str) -> None:
        """Validate ROM file existence and raise if not found"""
        rom_result = FileValidator.validate_file_existence(rom_path, "ROM file")
        if not rom_result.is_valid:
            raise ValidationError(f"ROM file validation failed: {rom_result.error_message}")
