"""
Background worker for loading ROM information without blocking the UI.

This worker moves file I/O operations (reading ROM headers, loading sprite locations)
off the main thread to prevent UI freezes, especially on slow storage.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal

from core.workers.base import BaseWorker, handle_worker_errors
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.managers import ExtractionManager, InjectionManager
    from core.protocols.manager_protocols import ROMExtractorProtocol

logger = get_logger(__name__)


class ROMInfoLoaderWorker(BaseWorker):
    """
    Background worker that loads ROM information asynchronously.

    Handles the blocking file I/O operations that would otherwise freeze the UI:
    - Reading ROM headers
    - Loading sprite configurations
    - Getting known sprite locations

    Signals:
        rom_info_loaded: Emitted when ROM info is successfully loaded
        sprite_locations_loaded: Emitted when sprite locations are loaded
    """

    # Custom signals for ROM info loading
    rom_info_loaded = Signal(dict)
    """Emitted when ROM info is loaded. Args: info_dict (with 'title', 'rom_type', etc.)."""

    sprite_locations_loaded = Signal(dict)
    """Emitted when sprite locations loaded. Args: locations (dict[sprite_name, pointer])."""

    def __init__(
        self,
        rom_path: str,
        injection_manager: InjectionManager | None = None,
        extraction_manager: ExtractionManager | ROMExtractorProtocol | None = None,
        load_header: bool = True,
        load_sprite_locations: bool = True,
    ) -> None:
        """
        Initialize ROM info loader worker.

        Args:
            rom_path: Path to the ROM file to load
            injection_manager: InjectionManager for loading full ROM info (injection dialog)
            extraction_manager: ExtractionManager or ROMExtractor for loading sprite locations
            load_header: Whether to load ROM header info
            load_sprite_locations: Whether to load known sprite locations
        """
        super().__init__()
        self.rom_path = rom_path
        self.injection_manager = injection_manager
        self.extraction_manager = extraction_manager
        self.load_header = load_header
        self.load_sprite_locations = load_sprite_locations

        logger.debug(f"ROMInfoLoaderWorker initialized for: {Path(rom_path).name}")

    @handle_worker_errors("ROM info loading", handle_interruption=True)
    def run(self) -> None:
        """Load ROM information in background thread."""
        rom_name = Path(self.rom_path).name
        logger.info(f"Starting ROM info loading for: {rom_name}")
        self.emit_progress(0, f"Loading ROM info for {rom_name}...")

        # Check for cancellation early
        self.check_cancellation()

        results: dict[str, Any] = {"rom_path": self.rom_path}

        # Load ROM header info via injection manager (used by injection dialog)
        if self.load_header and self.injection_manager is not None:
            self.emit_progress(20, "Reading ROM header...")
            self.check_cancellation()

            rom_info = self.injection_manager.load_rom_info(self.rom_path)
            results["rom_info"] = rom_info

            if rom_info:
                self.rom_info_loaded.emit(rom_info)
                logger.debug(f"ROM header loaded: {rom_info.get('header', {}).get('title', 'Unknown')}")

            self.emit_progress(50, "ROM header loaded")

        # Load sprite locations via extraction manager (used by extraction panel)
        if self.load_sprite_locations and self.extraction_manager is not None:
            self.emit_progress(60, "Loading sprite locations...")
            self.check_cancellation()

            locations = self.extraction_manager.get_known_sprite_locations(self.rom_path)
            results["sprite_locations"] = locations

            if locations:
                self.sprite_locations_loaded.emit(locations)
                logger.debug(f"Loaded {len(locations)} sprite locations")
            else:
                self.sprite_locations_loaded.emit({})

            self.emit_progress(90, f"Loaded {len(locations)} sprite locations")

        self.emit_progress(100, "ROM info loading complete")
        self.operation_finished.emit(True, f"Loaded info for {rom_name}")
        logger.info(f"ROM info loading complete for: {rom_name}")


class ROMHeaderLoaderWorker(BaseWorker):
    """
    Simpler worker that only loads ROM header information.

    Used by rom_extraction_panel for quick header reads without full ROM info loading.
    """

    # Signal with header info
    header_loaded = Signal(object)  # ROMHeader or None

    def __init__(
        self,
        rom_path: str,
        rom_injector: Any,  # ROMInjector
        sprite_config_loader: Any | None = None,
    ) -> None:
        """
        Initialize header loader worker.

        Args:
            rom_path: Path to the ROM file
            rom_injector: ROMInjector instance for reading headers
            sprite_config_loader: Optional loader for sprite configurations
        """
        super().__init__()
        self.rom_path = rom_path
        self.rom_injector = rom_injector
        self.sprite_config_loader = sprite_config_loader

    @handle_worker_errors("ROM header loading", handle_interruption=True)
    def run(self) -> None:
        """Load ROM header in background thread."""
        rom_name = Path(self.rom_path).name
        logger.debug(f"Loading ROM header for: {rom_name}")
        self.emit_progress(0, f"Reading header for {rom_name}...")

        self.check_cancellation()

        # Read ROM header (blocking I/O moved to worker thread)
        header = self.rom_injector.read_rom_header(self.rom_path)

        self.emit_progress(50, "Header read complete")
        self.check_cancellation()

        # Optionally load sprite configurations
        sprite_configs = None
        if self.sprite_config_loader is not None and header is not None:
            self.emit_progress(70, "Loading sprite configurations...")
            sprite_configs = self.sprite_config_loader.get_game_sprites(
                header.title, header.checksum
            )

        self.emit_progress(100, "Header loading complete")

        # Emit result
        result = {
            "header": header,
            "sprite_configs": sprite_configs,
        }
        self.header_loaded.emit(result)
        self.operation_finished.emit(True, f"Header loaded for {rom_name}")
        logger.debug(f"ROM header loading complete for: {rom_name}")
