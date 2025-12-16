"""
Worker orchestrator for ROM extraction panel.

This module centralizes the management of all background workers used by the
ROM extraction panel, providing a clean interface for worker lifecycle management.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, QThread, Signal

from ui.common import WorkerManager
from ui.rom_extraction.workers.similarity_indexing_worker import SimilarityIndexingWorker
from ui.workers.sprite_scan_worker import SpriteScanWorker
from ui.workers.rom_info_loader_worker import ROMHeaderLoaderWorker, ROMInfoLoaderWorker
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor

logger = get_logger(__name__)


class ROMWorkerOrchestrator(QObject):
    """
    Manages all background workers for ROM extraction panel.

    This class centralizes worker lifecycle management, signal forwarding,
    and cleanup coordination. It provides a simpler interface for the panel
    to interact with without managing individual worker instances.
    """

    # ========== Header Loading Signals ==========
    header_loaded = Signal(dict)  # ROM header data
    header_error = Signal(str)  # Error message

    # ========== Sprite Location Signals ==========
    sprite_locations_loaded = Signal(list)  # List of sprite location dicts
    sprite_locations_error = Signal(str)  # Error message

    # ========== Scan Signals ==========
    scan_progress = Signal(int, int, str)  # current, total, message
    sprite_found = Signal(dict)  # Found sprite data
    scan_complete = Signal(list, bool)  # sprites list, from_cache flag
    scan_error = Signal(str)

    # ========== Similarity Indexing Signals ==========
    similarity_progress = Signal(str)  # Progress message
    sprite_indexed = Signal(dict)  # Indexed sprite data
    index_saved = Signal(str)  # Save path
    index_loaded = Signal(str)  # Load path
    similarity_finished = Signal()
    similarity_error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the worker orchestrator."""
        super().__init__(parent)

        # Worker tracking
        self._header_worker: ROMHeaderLoaderWorker | None = None
        self._header_thread: QThread | None = None

        self._info_worker: ROMInfoLoaderWorker | None = None
        self._info_thread: QThread | None = None

        self._scan_worker: SpriteScanWorker | None = None
        self._scan_thread: QThread | None = None

        self._similarity_worker: SimilarityIndexingWorker | None = None
        self._similarity_thread: QThread | None = None

        # State tracking
        self._is_scanning = False
        self._found_sprites: list[dict[str, Any]] = []

        logger.debug("ROMWorkerOrchestrator initialized")

    # ========== Header Loading ==========

    def load_header(self, rom_path: str, extractor: ROMExtractor) -> None:
        """Load ROM header information asynchronously."""
        self._cleanup_header_worker()

        self._header_worker = ROMHeaderLoaderWorker(rom_path, extractor)
        self._header_thread = QThread()
        self._header_worker.moveToThread(self._header_thread)

        # Connect signals
        self._header_worker.header_loaded.connect(self._on_header_loaded)
        self._header_worker.error.connect(self._on_header_error)
        self._header_thread.started.connect(self._header_worker.run)

        WorkerManager.start_worker(self._header_worker, self._header_thread)
        logger.debug(f"Started header loading for: {rom_path}")

    def _on_header_loaded(self, header_data: dict[str, Any]) -> None:
        """Handle header load completion."""
        self.header_loaded.emit(header_data)
        self._cleanup_header_worker()

    def _on_header_error(self, error_msg: str) -> None:
        """Handle header load error."""
        self.header_error.emit(error_msg)
        self._cleanup_header_worker()

    def _cleanup_header_worker(self) -> None:
        """Clean up header worker resources."""
        if self._header_worker:
            WorkerManager.cleanup_worker(self._header_worker, timeout=2000)
            self._header_worker = None
            self._header_thread = None

    # ========== Sprite Location Loading ==========

    def load_sprite_locations(
        self, rom_path: str, extraction_manager: ROMExtractor
    ) -> None:
        """Load known sprite locations from ROM asynchronously.

        Args:
            rom_path: Path to the ROM file
            extraction_manager: ROMExtractor for loading sprite locations
        """
        self._cleanup_info_worker()

        self._info_worker = ROMInfoLoaderWorker(
            rom_path,
            extraction_manager=extraction_manager,
            load_header=False,
            load_sprite_locations=True,
        )
        self._info_thread = QThread()
        self._info_worker.moveToThread(self._info_thread)

        # Connect signals (ROMInfoLoaderWorker uses sprite_locations_loaded signal)
        self._info_worker.sprite_locations_loaded.connect(self._on_locations_loaded)
        self._info_worker.error.connect(self._on_locations_error)
        self._info_thread.started.connect(self._info_worker.run)

        WorkerManager.start_worker(self._info_worker, self._info_thread)
        logger.debug(f"Started sprite location loading for: {rom_path}")

    def _on_locations_loaded(self, locations: list[dict[str, Any]]) -> None:
        """Handle sprite locations load completion."""
        self.sprite_locations_loaded.emit(locations)
        self._cleanup_info_worker()

    def _on_locations_error(self, error_msg: str) -> None:
        """Handle sprite locations load error."""
        self.sprite_locations_error.emit(error_msg)
        self._cleanup_info_worker()

    def _cleanup_info_worker(self) -> None:
        """Clean up info worker resources."""
        if self._info_worker:
            WorkerManager.cleanup_worker(self._info_worker, timeout=2000)
            self._info_worker = None
            self._info_thread = None

    # ========== Sprite Scanning ==========

    def start_scan(self, rom_path: str, step: int = 0x1000) -> None:
        """Start sprite scanning on the ROM."""
        if self._is_scanning:
            logger.warning("Scan already in progress")
            return

        self._cleanup_scan_worker()
        self._found_sprites = []
        self._is_scanning = True

        self._scan_worker = SpriteScanWorker(rom_path, step=step)
        self._scan_thread = QThread()
        self._scan_worker.moveToThread(self._scan_thread)

        # Connect signals
        self._scan_worker.scan_progress.connect(self._on_scan_progress)
        self._scan_worker.item_found.connect(self._on_sprite_found)
        self._scan_worker.scan_finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_thread.started.connect(self._scan_worker.run)

        WorkerManager.start_worker(self._scan_worker, self._scan_thread)
        logger.info(f"Started sprite scan for: {rom_path}")

    def cancel_scan(self) -> None:
        """Cancel the current scan."""
        if self._scan_worker:
            self._scan_worker.cancel()
            logger.info("Scan cancellation requested")

    def _on_scan_progress(self, current: int, total: int) -> None:
        """Handle scan progress update."""
        percent = int((current / total) * 100) if total > 0 else 0
        self.scan_progress.emit(current, total, f"Scanning... {percent}%")

    def _on_sprite_found(self, sprite_data: dict[str, Any]) -> None:
        """Handle sprite found during scan."""
        self._found_sprites.append(sprite_data)
        self.sprite_found.emit(sprite_data)

    def _on_scan_finished(self, success: bool) -> None:
        """Handle scan completion."""
        self._is_scanning = False
        if success:
            self.scan_complete.emit(self._found_sprites, False)
        self._cleanup_scan_worker()

    def _on_scan_error(self, error_msg: str) -> None:
        """Handle scan error."""
        self._is_scanning = False
        self.scan_error.emit(error_msg)
        self._cleanup_scan_worker()

    def _cleanup_scan_worker(self) -> None:
        """Clean up scan worker resources."""
        if self._scan_worker:
            WorkerManager.cleanup_worker(self._scan_worker, timeout=5000)
            self._scan_worker = None
            self._scan_thread = None

    # ========== Similarity Indexing ==========

    def start_similarity_indexing(
        self,
        rom_path: str,
        sprites: list[dict[str, Any]],
    ) -> None:
        """Start similarity indexing for sprites.

        Args:
            rom_path: Path to the ROM file
            sprites: List of sprite info dicts to index
        """
        self._cleanup_similarity_worker()

        self._similarity_worker = SimilarityIndexingWorker(rom_path=rom_path)

        # Feed sprites to the worker before starting
        for sprite_info in sprites:
            self._similarity_worker.on_sprite_found(sprite_info)

        self._similarity_thread = QThread()
        self._similarity_worker.moveToThread(self._similarity_thread)

        # Connect signals
        self._similarity_worker.progress.connect(
            lambda p, m: self.similarity_progress.emit(m)
        )
        self._similarity_worker.sprite_indexed.connect(self.sprite_indexed.emit)
        self._similarity_worker.index_saved.connect(self.index_saved.emit)
        self._similarity_worker.index_loaded.connect(self.index_loaded.emit)
        self._similarity_worker.operation_finished.connect(self._on_similarity_finished)
        self._similarity_worker.error.connect(self._on_similarity_error)
        self._similarity_thread.started.connect(self._similarity_worker.run)

        WorkerManager.start_worker(self._similarity_worker, self._similarity_thread)
        logger.debug(f"Started similarity indexing for: {rom_path}")

    def _on_similarity_finished(self, success: bool, message: str) -> None:
        """Handle similarity indexing completion."""
        if success:
            self.similarity_finished.emit()
        self._cleanup_similarity_worker()

    def _on_similarity_error(self, error_msg: str) -> None:
        """Handle similarity indexing error."""
        self.similarity_error.emit(error_msg)
        self._cleanup_similarity_worker()

    def _cleanup_similarity_worker(self) -> None:
        """Clean up similarity worker resources."""
        if self._similarity_worker:
            WorkerManager.cleanup_worker(self._similarity_worker, timeout=5000)
            self._similarity_worker = None
            self._similarity_thread = None

    # ========== General Methods ==========

    @property
    def is_scanning(self) -> bool:
        """Check if a scan is currently in progress."""
        return self._is_scanning

    @property
    def found_sprites(self) -> list[dict[str, Any]]:
        """Get the list of sprites found during the current/last scan."""
        return self._found_sprites

    def cleanup(self) -> None:
        """Clean up all worker resources."""
        logger.debug("Cleaning up all workers")
        self._cleanup_header_worker()
        self._cleanup_info_worker()
        self._cleanup_scan_worker()
        self._cleanup_similarity_worker()
        self._is_scanning = False
        self._found_sprites = []
