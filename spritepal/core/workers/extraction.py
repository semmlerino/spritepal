"""
Extraction worker implementations using the new base classes.

These workers handle VRAM and ROM extraction operations by delegating
to the ExtractionManager while providing consistent threading interfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, override

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.managers.core_operations_manager import CoreOperationsManager

from core.managers.core_operations_manager import CoreOperationsManager
from core.types import ROMExtractionParams, VRAMExtractionParams
from utils.logging_config import get_logger

from .base import handle_worker_errors
from .specialized import (
    ExtractionWorkerBase,
    SignalConnectionHelper,
)

logger = get_logger(__name__)


class VRAMExtractionWorker(ExtractionWorkerBase):
    """
    Worker for VRAM extraction operations.

    Handles extraction of sprites from VRAM memory dumps using the
    ExtractionManager, providing progress updates and preview generation.
    """

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
        """Connect extraction manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_extraction_manager() -> CoreOperationsManager:
            from core.di_container import inject
            from core.managers.core_operations_manager import CoreOperationsManager
            return inject(CoreOperationsManager)
        if not helper.validate_manager_type(_get_extraction_manager, "VRAM extraction"):
            return

        # Type cast for better type checking - we know this is CoreOperationsManager from __init__
        extraction_manager = cast(CoreOperationsManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("extraction_progress", 50)
        helper.connect_extraction_signals(extraction_manager)
        helper.connect_preview_signals(extraction_manager)

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

class ROMExtractionWorker(ExtractionWorkerBase):
    """
    Worker for ROM extraction operations.

    Handles extraction of sprites from ROM files using the ExtractionManager,
    providing progress updates during the extraction process.
    """

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
        def _get_extraction_manager() -> CoreOperationsManager:
            from core.di_container import inject
            from core.managers.core_operations_manager import CoreOperationsManager
            return inject(CoreOperationsManager)
        if not helper.validate_manager_type(_get_extraction_manager, "ROM extraction"):
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

