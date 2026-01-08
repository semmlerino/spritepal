"""
Extraction worker implementations.

These workers handle VRAM and ROM extraction operations by delegating
to the CoreOperationsManager while providing consistent threading interfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, override

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.managers.core_operations_manager import CoreOperationsManager

from PySide6.QtCore import Signal

from core.managers.core_operations_manager import CoreOperationsManager
from core.types import ROMExtractionParams, VRAMExtractionParams
from utils.logging_config import get_logger

from .base import ManagedWorker, handle_worker_errors
from .specialized import SignalConnectionHelper

logger = get_logger(__name__)


class VRAMExtractionWorker(ManagedWorker):
    """
    Worker for VRAM extraction operations.

    Handles extraction of sprites from VRAM memory dumps using
    CoreOperationsManager, providing progress updates and preview generation.
    """

    # Extraction-specific signals
    preview_ready = Signal(object, int)  # pixmap/image, tile_count
    preview_image_ready = Signal(object)  # PIL image for palette application
    palettes_ready = Signal(object)  # palette data
    active_palettes_ready = Signal(list)  # active palette indices
    extraction_finished = Signal(list)  # list of extracted files

    def __init__(
        self,
        params: VRAMExtractionParams,
        extraction_manager: CoreOperationsManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(manager=extraction_manager, parent=parent)
        self.params = params
        self._operation_name = "VRAMExtractionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect extraction manager signals to worker signals.

        Note: Preview and palette signals are connected directly by MainWindow
        to the manager. Only progress signals are forwarded through the worker
        for status updates.
        """
        helper = SignalConnectionHelper(self)

        # Validate manager type
        if not helper.validate_manager_type(CoreOperationsManager, "VRAM extraction"):
            return

        # Connect only progress signal - palette/preview signals are connected
        # directly by controller to manager (no forwarding through worker)
        helper.connect_progress_signals("extraction_progress", 50)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("VRAM extraction")
    def perform_operation(self) -> None:
        """Perform VRAM extraction via manager."""
        # Type cast for better type safety
        extraction_manager = cast(CoreOperationsManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting VRAM extraction")
        self.emit_progress(10, "Starting VRAM extraction...")

        # Perform extraction using manager
        extracted_files = extraction_manager.extract_from_vram(
            vram_path=self.params["vram_path"],
            output_base=self.params["output_base"],
            cgram_path=self.params.get("cgram_path"),
            oam_path=self.params.get("oam_path"),
            vram_offset=self.params.get("vram_offset"),
            create_grayscale=self.params.get("create_grayscale", True),
            create_metadata=self.params.get("create_metadata", True),
            grayscale_mode=self.params.get("grayscale_mode", False),
        )

        # Check for cancellation after extraction
        self.check_cancellation()

        # Emit completion signals
        self.extraction_finished.emit(extracted_files)
        self.operation_finished.emit(True, f"Successfully extracted {len(extracted_files)} files")

        logger.info(f"{self._operation_name}: Extraction completed successfully")


class ROMExtractionWorker(ManagedWorker):
    """
    Worker for ROM extraction operations.

    Handles extraction of sprites from ROM files using CoreOperationsManager,
    providing progress updates during the extraction process.
    """

    # Extraction-specific signals
    preview_ready = Signal(object, int)  # pixmap/image, tile_count
    preview_image_ready = Signal(object)  # PIL image for palette application
    palettes_ready = Signal(object)  # palette data
    active_palettes_ready = Signal(list)  # active palette indices
    extraction_finished = Signal(list)  # list of extracted files

    def __init__(
        self,
        params: ROMExtractionParams,
        extraction_manager: CoreOperationsManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(manager=extraction_manager, parent=parent)
        self.params = params
        self._operation_name = "ROMExtractionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect extraction manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        if not helper.validate_manager_type(CoreOperationsManager, "ROM extraction"):
            return

        # Connect standard progress signal using helper
        helper.connect_progress_signals("extraction_progress", 50)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("ROM extraction")
    def perform_operation(self) -> None:
        """Perform ROM extraction via manager."""
        # Type cast for better type safety
        extraction_manager = cast(CoreOperationsManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting ROM extraction")
        self.emit_progress(10, "Starting ROM extraction...")

        # Perform extraction using manager
        extracted_files = extraction_manager.extract_from_rom(
            rom_path=self.params["rom_path"],
            offset=self.params["sprite_offset"],
            output_base=self.params["output_base"],
            sprite_name=self.params["sprite_name"],
            cgram_path=self.params.get("cgram_path"),
        )

        # Check for cancellation after extraction
        self.check_cancellation()

        # Emit completion signals
        self.extraction_finished.emit(extracted_files)
        self.operation_finished.emit(True, f"Successfully extracted {len(extracted_files)} files")

        logger.info(f"{self._operation_name}: ROM extraction completed successfully")
