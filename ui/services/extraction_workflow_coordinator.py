"""Extraction workflow coordination service.

Extracted from MainWindow to manage extraction orchestration including:
- VRAM extraction workflow
- ROM extraction workflow
- Worker lifecycle management
- Signal emission and error handling
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

from core.services.worker_lifecycle import WorkerManager
from core.types import ROMExtractionParams, VRAMExtractionParams
from utils.constants import VRAM_SPRITE_OFFSET
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.app_context import AppContext
    from core.workers import ROMExtractionWorker, VRAMExtractionWorker

logger = get_logger(__name__)


class ExtractionWorkflowCoordinator(QObject):
    """Coordinates extraction workflows (VRAM/ROM).

    This service handles extraction orchestration that was previously
    in MainWindow, providing a cleaner separation of concerns.

    Signals:
        extraction_started(str): Emitted when extraction begins (mode: "VRAM" or "ROM")
        extraction_failed(str): Emitted when extraction fails (error message)
        progress(int, str): Emitted during extraction (percent, message)
        vram_extraction_finished(list): Emitted when VRAM extraction completes (file list)
        rom_extraction_finished(list): Emitted when ROM extraction completes (file list)

    Note:
        MainWindow should connect to CoreOperationsManager.extraction_completed
        directly for preview/palette updates (contains PIL.Image that can't be serialized).
    """

    extraction_started = Signal(str)  # mode: "VRAM" or "ROM"
    extraction_failed = Signal(str)  # error message
    progress = Signal(int, str)  # percent, message
    vram_extraction_finished = Signal(list)  # list of extracted files
    rom_extraction_finished = Signal(list)  # list of extracted files

    def __init__(self, app_context: AppContext) -> None:
        """Initialize the extraction workflow coordinator.

        Args:
            app_context: Application context with managers and services
        """
        super().__init__()
        self._app_context = app_context
        self._vram_worker: VRAMExtractionWorker | None = None
        self._rom_worker: ROMExtractionWorker | None = None

    @property
    def core_operations_manager(self):
        """Access to core operations manager for signal connections."""
        return self._app_context.core_operations_manager

    def start_vram_extraction(self, params: dict[str, Any]) -> None:  # pyright: ignore[reportExplicitAny] - params are dynamic extraction config
        """Start VRAM extraction workflow.

        Args:
            params: Extraction parameters dict containing:
                - vram_path: Path to VRAM dump file
                - cgram_path: Optional path to CGRAM dump file
                - oam_path: Optional path to OAM dump file
                - vram_offset: Offset into VRAM
                - output_base: Base output path for results
                - create_grayscale: Whether to create grayscale version
                - create_metadata: Whether to include metadata
                - grayscale_mode: Whether in grayscale mode
        """
        logger.debug("Starting VRAM extraction workflow")

        try:
            # VRAM file validation
            vram_path = params.get("vram_path", "")
            if vram_path:
                vram_result = FileValidator.validate_vram_file(vram_path)
                if not vram_result.is_valid:
                    error_msg = vram_result.error_message or "VRAM file validation failed"
                    self.extraction_failed.emit(error_msg)
                    return
                for warning in vram_result.warnings:
                    logger.warning(f"VRAM file warning: {warning}")

            # CGRAM file validation (if not in grayscale mode)
            cgram_path = params.get("cgram_path", "")
            grayscale_mode = params.get("grayscale_mode", False)
            if cgram_path and not grayscale_mode:
                cgram_result = FileValidator.validate_cgram_file(cgram_path)
                if not cgram_result.is_valid:
                    error_msg = cgram_result.error_message or "CGRAM file validation failed"
                    self.extraction_failed.emit(error_msg)
                    return
                for warning in cgram_result.warnings:
                    logger.warning(f"CGRAM file warning: {warning}")

            # OAM file validation
            oam_path = params.get("oam_path", "")
            if oam_path:
                oam_result = FileValidator.validate_oam_file(oam_path)
                if not oam_result.is_valid:
                    error_msg = oam_result.error_message or "OAM file validation failed"
                    self.extraction_failed.emit(error_msg)
                    return
                for warning in oam_result.warnings:
                    logger.warning(f"OAM file warning: {warning}")

            # Create extraction parameters TypedDict
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

            # Create and start worker
            from core.workers import VRAMExtractionWorker

            worker = VRAMExtractionWorker(
                extraction_params,
                extraction_manager=self._app_context.core_operations_manager,
            )
            self._vram_worker = worker

            # Connect worker signals
            _ = worker.progress.connect(self._on_progress)
            _ = worker.extraction_finished.connect(self._on_vram_extraction_finished)
            _ = worker.error.connect(self._on_vram_extraction_error)

            # Emit signal and start worker
            self.extraction_started.emit("VRAM")
            worker.start()

        except Exception as e:
            logger.exception("Error starting VRAM extraction")
            self.extraction_failed.emit(f"VRAM extraction error: {e}")
            self._cleanup_vram_worker()

    def start_rom_extraction(self, params: dict[str, Any]) -> None:  # pyright: ignore[reportExplicitAny] - params are dynamic extraction config
        """Start ROM extraction workflow.

        Args:
            params: Extraction parameters dict containing:
                - rom_path: Path to ROM file
                - sprite_offset: Offset in ROM
                - sprite_name: Name for the sprite
                - output_base: Base output path for results
                - cgram_path: Optional CGRAM file path
        """
        logger.debug("Starting ROM extraction workflow")

        try:
            # ROM file validation
            rom_path = params.get("rom_path", "")
            if rom_path:
                rom_result = FileValidator.validate_rom_file(rom_path)
                if not rom_result.is_valid:
                    error_msg = rom_result.error_message or "ROM file validation failed"
                    self.extraction_failed.emit(error_msg)
                    return
                for warning in rom_result.warnings:
                    logger.warning(f"ROM file warning: {warning}")

            # Create ROM extraction parameters TypedDict
            rom_extraction_params: ROMExtractionParams = {
                "rom_path": params["rom_path"],
                "sprite_offset": params["sprite_offset"],
                "sprite_name": params["sprite_name"],
                "output_base": params["output_base"],
                "cgram_path": params.get("cgram_path"),
            }

            # Create and start worker
            from core.workers import ROMExtractionWorker

            worker = ROMExtractionWorker(
                rom_extraction_params,
                extraction_manager=self._app_context.core_operations_manager,
            )
            self._rom_worker = worker

            # Connect worker signals
            _ = worker.progress.connect(self._on_progress)
            _ = worker.extraction_finished.connect(self._on_rom_extraction_finished)
            _ = worker.error.connect(self._on_rom_extraction_error)

            # Emit signal and start worker
            self.extraction_started.emit("ROM")
            worker.start()

        except Exception as e:
            logger.exception("Error starting ROM extraction")
            self.extraction_failed.emit(f"ROM extraction error: {e}")
            self._cleanup_rom_worker()

    # Signal handlers
    def _on_progress(self, percent: int, message: str) -> None:
        """Handle extraction progress updates.

        Args:
            percent: Progress percentage
            message: Progress message
        """
        logger.debug(f"Extraction progress: {percent}% - {message}")
        self.progress.emit(percent, message)

    def _on_vram_extraction_finished(self, extracted_files: list[str]) -> None:
        """Handle VRAM extraction completion.

        Args:
            extracted_files: List of extracted file paths
        """
        logger.debug(f"VRAM extraction finished: {len(extracted_files)} files")
        self._cleanup_vram_worker()
        self.vram_extraction_finished.emit(extracted_files)

    def _on_vram_extraction_error(self, error_message: str) -> None:
        """Handle VRAM extraction error.

        Args:
            error_message: Error message from worker
        """
        logger.error(f"VRAM extraction error: {error_message}")
        self.extraction_failed.emit(f"VRAM extraction failed: {error_message}")
        self._cleanup_vram_worker()

    def _on_rom_extraction_finished(self, extracted_files: list[str]) -> None:
        """Handle ROM extraction completion.

        Args:
            extracted_files: List of extracted file paths
        """
        logger.debug(f"ROM extraction finished: {len(extracted_files)} files")
        self._cleanup_rom_worker()
        self.rom_extraction_finished.emit(extracted_files)

    def _on_rom_extraction_error(self, error_message: str) -> None:
        """Handle ROM extraction error.

        Args:
            error_message: Error message from worker
        """
        logger.error(f"ROM extraction error: {error_message}")
        self.extraction_failed.emit(f"ROM extraction failed: {error_message}")
        self._cleanup_rom_worker()

    # Cleanup methods
    def _cleanup_vram_worker(self) -> None:
        """Clean up VRAM worker thread."""
        if self._vram_worker is not None:
            WorkerManager.cleanup_worker(self._vram_worker, timeout=3000)
            self._vram_worker = None

    def _cleanup_rom_worker(self) -> None:
        """Clean up ROM worker thread."""
        if self._rom_worker is not None:
            WorkerManager.cleanup_worker(self._rom_worker, timeout=3000)
            self._rom_worker = None
