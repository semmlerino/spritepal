"""
Consolidated Core Operations Manager for SpritePal.

This manager combines extraction, injection, palette, and navigation functionality
into a single cohesive unit while maintaining backward compatibility through
adapter patterns.
"""

from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, Signal
from typing_extensions import override

from core.extractor import SpriteExtractor
from core.palette_manager import PaletteManager
from core.rom_extractor import ROMExtractor
from core.services import ROMService, VRAMService
from utils.constants import (
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_WIDTH,
)

from .base_manager import BaseManager
from .exceptions import (
    ExtractionError,
    InjectionError,
    ValidationError,
)
from .extraction_manager import ExtractionManager
from .injection_manager import InjectionManager


class CoreOperationsManager(BaseManager):
    """
    Consolidated manager for all core operations:
    - Extraction (ROM and VRAM)
    - Injection (ROM and VRAM)
    - Palette management
    - Navigation and sprite discovery

    This manager provides a unified interface while maintaining backward
    compatibility through embedded adapter classes.
    """

    # Unified signals
    operation_progress = Signal(str, str, int)  # Operation type, message, percentage
    operation_completed = Signal(str, bool, str)  # Operation type, success, message

    # Extraction-specific signals (for backward compatibility)
    extraction_progress = Signal(str)
    preview_generated = Signal(object, int)
    palettes_extracted = Signal(dict)
    active_palettes_found = Signal(list)
    files_created = Signal(list)

    # Injection-specific signals
    injection_progress = Signal(str)
    injection_finished = Signal(bool, str)
    compression_info = Signal(dict)
    progress_percent = Signal(int)

    # Navigation-specific signals
    navigation_hints_ready = Signal(list)
    region_map_updated = Signal(dict)
    pattern_learned = Signal(str, dict)
    similarity_found = Signal(int, list)

    # Cache operation signals
    cache_operation_started = Signal(str, str)
    cache_hit = Signal(str, float)
    cache_miss = Signal(str)
    cache_saved = Signal(str, int)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the core operations manager."""
        # Initialize components
        self._sprite_extractor: SpriteExtractor | None = None
        self._rom_extractor: ROMExtractor | None = None
        self._palette_manager: PaletteManager | None = None
        self._current_worker: Any = None
        self._navigation_manager: Any = None  # Lazy loaded

        # Create backward compatibility adapters
        self._extraction_adapter: ExtractionAdapter | None = None
        self._injection_adapter: InjectionAdapter | None = None

        super().__init__("CoreOperationsManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize all core operation components."""
        try:
            # Initialize extractors
            self._sprite_extractor = SpriteExtractor()
            self._rom_extractor = ROMExtractor()
            self._palette_manager = PaletteManager()

            # Create adapters for backward compatibility
            self._extraction_adapter = ExtractionAdapter(self)
            self._injection_adapter = InjectionAdapter(self)

            self._is_initialized = True
            self._logger.info("CoreOperationsManager initialized successfully")

        except Exception as e:
            self._handle_error(e, "initialization")
            raise

    @override
    def cleanup(self) -> None:
        """Cleanup all core operation resources."""
        # Clean up any active operations
        with self._lock:
            self._active_operations.clear()

        # Stop any active workers
        if self._current_worker:
            from core.services.worker_lifecycle import WorkerManager

            self._logger.info("Stopping active worker")
            WorkerManager.cleanup_worker(self._current_worker, timeout=5000)
            self._current_worker = None

        # Clean up navigation manager if initialized
        if self._navigation_manager:
            try:
                self._navigation_manager.cleanup()
            except Exception as e:
                self._logger.warning(f"Error cleaning up navigation manager: {e}")
            self._navigation_manager = None

        self._logger.info("CoreOperationsManager cleaned up")

    def reset_state(self, full_reset: bool = False) -> None:
        """Reset internal state for test isolation."""
        with self._lock:
            self._active_operations.clear()
            self._current_worker = None
            # Reset sub-managers if needed
            if self._sprite_extractor and hasattr(self._sprite_extractor, 'reset_state'):
                self._sprite_extractor.reset_state()  # type: ignore
            if self._rom_extractor and hasattr(self._rom_extractor, 'reset_state'):
                self._rom_extractor.reset_state()  # type: ignore

    # ========== Extraction Operations ==========

    def extract_from_vram(self, vram_path: str, output_base: str,
                         cgram_path: str | None = None,
                         oam_path: str | None = None,
                         vram_offset: int | None = None,
                         create_grayscale: bool = True,
                         create_metadata: bool = True,
                         create_palette_files: bool = True,
                         grayscale_mode: bool = False) -> dict[str, Any]:
        """
        Extract sprites from VRAM dump.

        Args:
            grayscale_mode: Skip palette extraction entirely

        Returns:
            Dict with extraction results
        """
        operation = "vram_extraction"

        if not self._start_operation(operation):
            return {"success": False, "error": "Operation already in progress"}

        try:
            # Validate inputs
            self._validate_required(
                {"vram_path": vram_path, "output_base": output_base},
                ["vram_path", "output_base"]
            )

            # Perform extraction
            extractor = self._ensure_sprite_extractor()
            result = extractor.extract_sprite(
                vram_path, output_base,
                cgram_path=cgram_path,
                oam_path=oam_path,
                vram_offset=vram_offset,
                create_grayscale=create_grayscale,
                create_metadata=create_metadata,
                create_palette_files=create_palette_files
            )

            # Emit signals
            self.extraction_progress.emit("VRAM extraction completed")
            self.operation_completed.emit(operation, True, "Success")

            return result

        except Exception as e:
            self._handle_error(e, operation)
            self.operation_completed.emit(operation, False, str(e))
            raise ExtractionError(f"VRAM extraction failed: {e!s}") from e
        finally:
            self._finish_operation(operation)

    def extract_from_rom(self, rom_path: str, offset: int, output_base: str,
                        tile_count: int | None = None,
                        palette_data: list[list[int]] | None = None,
                        width: int = DEFAULT_PREVIEW_WIDTH,
                        height: int = DEFAULT_PREVIEW_HEIGHT) -> dict[str, Any]:
        """
        Extract sprites from ROM.

        Returns:
            Dict with extraction results
        """
        operation = "rom_extraction"

        if not self._start_operation(operation):
            return {"success": False, "error": "Operation already in progress"}

        try:
            # Validate inputs
            self._validate_required(
                {"rom_path": rom_path, "offset": offset, "output_base": output_base},
                ["rom_path", "offset", "output_base"]
            )
            self._validate_file_exists(rom_path, "ROM file")

            # Perform extraction
            extractor = self._ensure_rom_extractor()
            result = extractor.extract_sprite(  # type: ignore[attr-defined]  # TODO: Add extract_sprite to ROMExtractor
                rom_path, offset, output_base,
                tile_count=tile_count,
                palette_data=palette_data,
                width=width,
                height=height
            )

            # Emit signals
            self.extraction_progress.emit("ROM extraction completed")
            self.operation_completed.emit(operation, True, "Success")

            return result

        except Exception as e:
            self._handle_error(e, operation)
            self.operation_completed.emit(operation, False, str(e))
            raise ExtractionError(f"ROM extraction failed: {e!s}") from e
        finally:
            self._finish_operation(operation)

    # ========== Injection Operations ==========

    def start_injection(self, params: dict[str, Any]) -> bool:
        """
        Start injection process with unified interface.

        Args:
            params: Injection parameters

        Returns:
            True if injection started successfully
        """
        operation = "injection"
        mode = params.get("mode", "rom")

        if not self._start_operation(operation):
            return False

        try:
            # Validate common parameters
            self._validate_required(params, ["mode", "sprite_path"])

            if mode == "vram":
                return self._start_vram_injection(params)
            if mode == "rom":
                return self._start_rom_injection(params)
            raise ValidationError(f"Invalid injection mode: {mode}")

        except Exception as e:
            self._handle_error(e, operation)
            self.injection_finished.emit(False, str(e))
            self._finish_operation(operation)
            return False

    def _start_vram_injection(self, params: dict[str, Any]) -> bool:
        """Start VRAM injection."""
        from ui.workers.injection_worker import InjectionWorker  # Local import to avoid circular dependency

        self._validate_required(params, ["input_vram", "output_vram", "offset"])

        # Create and start worker
        worker = InjectionWorker(
            params["sprite_path"],
            params["input_vram"],
            params["output_vram"],
            params["offset"],
            params.get("metadata_path")
        )

        # Connect signals
        worker.progress.connect(lambda msg: self.injection_progress.emit(msg))
        worker.finished.connect(self._cleanup_current_worker)  # Ensure cleanup on finish (before emitting completion)
        worker.finished.connect(lambda: self._on_injection_finished(True, "VRAM injection completed"))
        worker.error.connect(lambda msg: self._on_injection_finished(False, msg))

        # Start worker
        self._current_worker = worker
        worker.start()

        return True

    def _start_rom_injection(self, params: dict[str, Any]) -> bool:
        """Start ROM injection."""
        from ui.workers.rom_injection_worker import ROMInjectionWorker  # Local import to avoid circular dependency

        self._validate_required(params, ["input_rom", "output_rom", "offset"])

        # Create and start worker
        worker = ROMInjectionWorker(
            params["sprite_path"],
            params["input_rom"],
            params["output_rom"],
            params["offset"],
            params.get("fast_compression", False),
            params.get("metadata_path")
        )

        # Connect signals
        worker.progress.connect(lambda msg: self.injection_progress.emit(msg))
        worker.finished.connect(self._cleanup_current_worker)  # Ensure cleanup on finish (before emitting completion)
        worker.finished.connect(lambda: self._on_injection_finished(True, "ROM injection completed"))
        worker.error.connect(lambda msg: self._on_injection_finished(False, msg))  # type: ignore[attr-defined]
        worker.compression_info.connect(self.compression_info.emit)

        # Start worker
        self._current_worker = worker
        worker.start()

        return True

    def _on_injection_finished(self, success: bool, message: str) -> None:
        """Handle injection completion."""
        self.injection_finished.emit(success, message)
        self.operation_completed.emit("injection", success, message)
        self._finish_operation("injection")
        # self._current_worker = None  # Moved to _cleanup_current_worker to prevent premature cleanup

    def _cleanup_current_worker(self) -> None:
        """Clean up current worker reference after thread finishes."""
        if self._current_worker:
            self._current_worker.deleteLater()
        self._current_worker = None

    # ========== Palette Operations ==========

    def load_palette(self, cgram_path: str) -> dict[int, list[list[int]]]:
        """Load palette from CGRAM dump."""
        if not self._palette_manager:
            raise ExtractionError("Palette manager not initialized")

        self._palette_manager.load_cgram(cgram_path)
        return self._palette_manager.get_sprite_palettes()

    def get_palette(self, palette_index: int) -> list[list[int]]:
        """Get a specific palette."""
        if not self._palette_manager:
            raise ExtractionError("Palette manager not initialized")

        return self._palette_manager.get_palette(palette_index)

    def create_palette_json(self, palette_index: int, output_path: str,
                           companion_image: str | None = None) -> str:
        """Create palette JSON file."""
        if not self._palette_manager:
            raise ExtractionError("Palette manager not initialized")

        return self._palette_manager.create_palette_json(
            palette_index, output_path, companion_image
        )

    # ========== Navigation Operations ==========

    def get_navigation_hints(self, rom_path: str, current_offset: int,
                            context: dict[str, Any] | None = None) -> list[Any]:
        """Get navigation hints for sprite discovery."""
        nav_manager = self._get_navigation_manager()
        if nav_manager:
            return nav_manager.get_navigation_hints(rom_path, current_offset, context)
        return []

    def update_navigation_context(self, sprite_data: dict[str, Any]) -> None:
        """Update navigation context with found sprite."""
        nav_manager = self._get_navigation_manager()
        if nav_manager:
            nav_manager.add_sprite_to_context(sprite_data)

    # ========== Helper Methods ==========

    def _ensure_sprite_extractor(self) -> SpriteExtractor:
        """Ensure sprite extractor is initialized."""
        if self._sprite_extractor is None:
            raise ExtractionError("Sprite extractor not initialized")
        return self._sprite_extractor

    def _ensure_rom_extractor(self) -> ROMExtractor:
        """Ensure ROM extractor is initialized."""
        if self._rom_extractor is None:
            raise ExtractionError("ROM extractor not initialized")
        return self._rom_extractor

    def _get_navigation_manager(self) -> Any:
        """Get or create navigation manager (lazy loading)."""
        if self._navigation_manager is None:
            try:
                from core.navigation.manager import NavigationManager
                self._navigation_manager = NavigationManager(parent=self)
            except ImportError:
                self._logger.warning("Navigation manager not available")
        return self._navigation_manager

    # ========== Backward Compatibility Adapters ==========

    def get_extraction_adapter(self) -> ExtractionManager:
        """Get extraction manager adapter for backward compatibility."""
        if not self._extraction_adapter:
            raise ExtractionError("Extraction adapter not initialized")
        return self._extraction_adapter

    def get_injection_adapter(self) -> InjectionManager:
        """Get injection manager adapter for backward compatibility."""
        if not self._injection_adapter:
            raise InjectionError("Injection adapter not initialized")
        return self._injection_adapter

class ExtractionAdapter(ExtractionManager):
    """
    Adapter class that provides ExtractionManager interface while
    delegating to CoreOperationsManager.
    """

    def __init__(self, core_manager: CoreOperationsManager):
        """Initialize adapter with reference to core manager."""
        self._core = core_manager
        # Skip parent initialization to avoid creating duplicate resources
        QObject.__init__(self, core_manager)
        self._is_initialized = True
        self._name = "ExtractionAdapter"
        self._logger = core_manager._logger

        # Set up required attributes that parent methods expect
        self._rom_extractor = core_manager._rom_extractor
        self._sprite_extractor = core_manager._sprite_extractor
        self._palette_manager = core_manager._palette_manager

        # Create services with shared components (required for delegated methods)
        self._rom_service: ROMService | None = ROMService(
            rom_extractor=self._rom_extractor,
            palette_manager=self._palette_manager,
            parent=self,
        )
        self._vram_service: VRAMService | None = VRAMService(
            sprite_extractor=self._sprite_extractor,
            palette_manager=self._palette_manager,
            parent=self,
        )
        self._connect_service_signals()

        # Thread safety attributes required by BaseManager methods
        self._lock = threading.RLock()
        self._active_operations: set[str] = set()

        # Forward signals
        core_manager.extraction_progress.connect(self.extraction_progress.emit)
        core_manager.preview_generated.connect(self.preview_generated.emit)
        core_manager.palettes_extracted.connect(self.palettes_extracted.emit)
        core_manager.active_palettes_found.connect(self.active_palettes_found.emit)
        core_manager.files_created.connect(self.files_created.emit)
        core_manager.cache_operation_started.connect(self.cache_operation_started.emit)
        core_manager.cache_hit.connect(self.cache_hit.emit)
        core_manager.cache_miss.connect(self.cache_miss.emit)
        core_manager.cache_saved.connect(self.cache_saved.emit)

    @override
    def _initialize(self) -> None:
        """No-op, initialization handled by core manager."""
        pass

    @override
    def cleanup(self) -> None:
        """No-op, cleanup handled by core manager."""
        pass

    @override
    def reset_state(self, full_reset: bool = False) -> None:
        """Delegate reset to core manager."""
        self._core.reset_state(full_reset)

    def extract_active_palettes(self, *args: Any, **kwargs: Any) -> None:
        """Extract active palettes from OAM data."""
        # Implement palette extraction logic
        args[0]
        # This is a simplified implementation
        # The full implementation would analyze OAM data
        active_palettes = list(range(8, 16))  # Sprite palettes
        self._core.active_palettes_found.emit(active_palettes)

class InjectionAdapter(InjectionManager):
    """
    Adapter class that provides InjectionManager interface while
    delegating to CoreOperationsManager.
    """

    def __init__(self, core_manager: CoreOperationsManager):
        """Initialize adapter with reference to core manager."""
        self._core = core_manager
        # Skip parent initialization
        QObject.__init__(self, core_manager)
        self._is_initialized = True
        self._name = "InjectionAdapter"
        self._logger = core_manager._logger
        self._current_worker = None

        # Forward signals
        core_manager.injection_progress.connect(self.injection_progress.emit)
        core_manager.injection_finished.connect(self.injection_finished.emit)
        core_manager.compression_info.connect(self.compression_info.emit)
        core_manager.progress_percent.connect(self.progress_percent.emit)
        core_manager.cache_saved.connect(self.cache_saved.emit)

    @override
    def _initialize(self) -> None:
        """No-op, initialization handled by core manager."""
        pass

    @override
    def cleanup(self) -> None:
        """No-op, cleanup handled by core manager."""
        pass

    @override
    def start_injection(self, params: dict[str, Any]) -> bool:
        """Delegate to core manager."""
        return self._core.start_injection(params)

    def cancel_injection(self) -> None:
        """Cancel current injection operation."""
        if self._core._current_worker:
            from core.services.worker_lifecycle import WorkerManager

            WorkerManager.cleanup_worker(self._core._current_worker, timeout=2000)
