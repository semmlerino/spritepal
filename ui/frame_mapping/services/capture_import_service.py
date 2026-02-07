"""Capture import service for frame mapping.

Handles importing Mesen 2 capture files and creating GameFrames.
This service encapsulates all capture import logic including:
- Single file import
- Directory batch import with background parsing
- GameFrame creation from selected OAM entries
"""

from __future__ import annotations

import logging
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QPixmap

from core.frame_mapping_project import GameFrame
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry
from core.repositories.capture_result_repository import CaptureResultRepository
from core.types import CompressionType
from ui.common import WorkerManager
from ui.frame_mapping.services.preview_renderer import PreviewRenderer

if TYPE_CHECKING:
    from ui.frame_mapping.services.preview_service import PreviewService

logger = logging.getLogger(__name__)


class CaptureParseWorker(QThread):
    """Background worker for parsing multiple capture files."""

    file_parsed = Signal(object, object)  # CaptureResult, Path
    parse_error = Signal(object, str)  # Path, error message
    finished_all = Signal(int)  # parsed count

    def __init__(
        self,
        file_paths: list[Path],
        capture_repository: CaptureResultRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._file_paths = file_paths
        self._capture_repository = capture_repository

    @override
    def run(self) -> None:
        """Parse all files and emit signals for each."""
        parsed = 0
        for path in self._file_paths:
            if self.isInterruptionRequested():
                break
            try:
                result = self._capture_repository.get_or_parse(path)
                if result.has_entries:
                    self.file_parsed.emit(result, path)
                    parsed += 1
            except (JSONDecodeError, KeyError, ValueError, OSError) as e:
                self.parse_error.emit(path, str(e))
        self.finished_all.emit(parsed)


class CaptureImportService(QObject):
    """Service for importing Mesen 2 capture files into frame mapping projects.

    This service handles:
    - Parsing single capture files
    - Batch parsing directories of captures in the background
    - Creating GameFrame objects from selected OAM entries
    - Managing preview cache for imported frames

    Signals:
        import_requested: Emitted when a capture is ready for user selection
        import_completed: Emitted when a GameFrame is successfully created
        import_failed: Emitted when import fails
        directory_import_started: Emitted when batch directory import begins
        directory_import_finished: Emitted when batch directory import completes
    """

    # Signal for workspace to show sprite selection dialog
    import_requested = Signal(object, object)  # (CaptureResult, capture_path: Path)

    # Completion signals
    import_failed = Signal(str)  # error message

    # Directory import progress signals
    directory_import_started = Signal(int)  # total_files
    directory_import_finished = Signal(int)  # parsed_count

    def __init__(
        self,
        preview_service: PreviewService | None = None,
        capture_repository: CaptureResultRepository | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the capture import service.

        Args:
            preview_service: Service for caching preview images
            capture_repository: Shared repository for caching parsed capture files
            parent: Parent QObject
        """
        super().__init__(parent)
        self._preview_service = preview_service
        self._capture_repository = capture_repository
        self._capture_parse_worker: CaptureParseWorker | None = None
        self._existing_frame_ids: set[str] = set()
        self._is_single_file_import: bool = False
        self._single_file_error_emitted: bool = False


    def update_existing_frame_ids(self, frame_ids: set[str]) -> None:
        """Update the set of existing frame IDs for uniqueness checks.

        This should be called when the project changes to ensure
        _generate_unique_frame_id works correctly.

        Args:
            frame_ids: Set of existing game frame IDs
        """
        self._existing_frame_ids = frame_ids.copy()

    def _generate_unique_frame_id(self, base_id: str) -> str:
        """Generate a unique frame ID, adding suffix if collision exists.

        Args:
            base_id: The initial frame ID (e.g., from filename)

        Returns:
            A unique frame ID, potentially with _N suffix
        """
        if base_id not in self._existing_frame_ids:
            return base_id

        # Find next available suffix
        counter = 1
        while f"{base_id}_{counter}" in self._existing_frame_ids:
            counter += 1

        unique_id = f"{base_id}_{counter}"
        logger.info("Renamed duplicate capture ID %s -> %s", base_id, unique_id)
        return unique_id

    def import_mesen_capture(self, capture_path: Path) -> None:
        """Parse a Mesen 2 capture file and emit signal for sprite selection.

        Uses background thread to avoid blocking UI during JSON parsing.
        The workspace handles showing the sprite selection dialog and calls
        complete_import() with the user's selection.

        Args:
            capture_path: Path to capture JSON file
        """
        if not capture_path.exists():
            self.import_failed.emit(f"Capture file not found: {capture_path}")
            return

        # Cancel any existing parsing operation
        self._cancel_existing_worker()

        # Track that this is a single-file import (affects error handling)
        self._is_single_file_import = True
        self._single_file_error_emitted = False

        # Create and start background worker with single file
        assert self._capture_repository is not None, "CaptureImportService requires capture_repository"
        self._capture_parse_worker = CaptureParseWorker(
            [capture_path], capture_repository=self._capture_repository, parent=self
        )
        self._capture_parse_worker.file_parsed.connect(self._on_capture_file_parsed)
        self._capture_parse_worker.parse_error.connect(self._on_capture_parse_error)
        self._capture_parse_worker.finished_all.connect(self._on_single_file_finished)

        # Use WorkerManager for proper lifecycle tracking
        WorkerManager.start_worker(self._capture_parse_worker)

    def complete_import(
        self,
        capture_path: Path,
        capture_result: CaptureResult,
        selected_entries: list[OAMEntry],
    ) -> GameFrame | None:
        """Complete capture import after user selection.

        Called by workspace after sprite selection dialog is accepted.

        Args:
            capture_path: Path to capture JSON file
            capture_result: Parsed capture result
            selected_entries: OAM entries selected by user

        Returns:
            The created GameFrame, or None on error
        """
        if not selected_entries:
            self.import_failed.emit("No sprites selected")
            return None

        try:
            # Create filtered CaptureResult with only selected entries
            filtered_capture = CaptureResult(
                frame=capture_result.frame,
                visible_count=len(selected_entries),
                obsel=capture_result.obsel,
                entries=selected_entries,
                palettes=capture_result.palettes,
                timestamp=capture_result.timestamp,
            )

            # Generate frame ID from filename or ROM offsets
            frame_id = capture_path.stem
            if frame_id.startswith("sprite_capture_"):
                frame_id = frame_id.replace("sprite_capture_", "")

            # Ensure unique ID when importing captures with same filename
            frame_id = self._generate_unique_frame_id(frame_id)

            # Add to existing IDs to prevent duplicates within same batch
            self._existing_frame_ids.add(frame_id)

            # Get unique ROM offsets from selected entries only
            rom_offsets = filtered_capture.unique_rom_offsets

            # Render preview using filtered capture (cropped to bounding box)
            qimage = PreviewRenderer.render_preview_qimage(filtered_capture)
            # Convert QImage to QPixmap for caching
            pixmap = QPixmap.fromImage(qimage) if qimage is not None else None
            if pixmap is not None and self._preview_service is not None:
                mtime = capture_path.stat().st_mtime if capture_path.exists() else 0.0
                entry_ids = tuple(entry.id for entry in selected_entries)
                self._preview_service.set_preview_cache(frame_id, pixmap, mtime, entry_ids)

            # Infer palette from selected entries (use first entry's palette if all same)
            palette_idx = 0
            if selected_entries:
                first_palette = selected_entries[0].palette
                if all(e.palette == first_palette for e in selected_entries):
                    palette_idx = first_palette

            # Clamp to valid SNES palette range (0-7)
            if not (0 <= palette_idx <= 7):
                logger.warning(
                    "Capture entry has invalid palette index %d, clamping to [0, 7]",
                    palette_idx,
                )
                palette_idx = max(0, min(7, palette_idx))

            # Create game frame with selected entry IDs for filtering on retrieval
            bbox = filtered_capture.bounding_box
            # Default all ROM offsets to RAW compression (user can change in workbench)
            default_compression_types = dict.fromkeys(rom_offsets, CompressionType.RAW)
            # Cache mtime at import time to avoid stat() calls during preview updates
            cached_mtime = capture_path.stat().st_mtime if capture_path.exists() else 0.0
            frame = GameFrame(
                id=frame_id,
                rom_offsets=rom_offsets,
                capture_path=capture_path,
                palette_index=palette_idx,  # Inferred from selected entries
                width=bbox.width,
                height=bbox.height,
                selected_entry_ids=[entry.id for entry in selected_entries],
                compression_types=default_compression_types,
                cached_mtime=cached_mtime,
            )

            logger.info(
                "Imported game frame %s from %s (%d of %d entries selected, palette=%d)",
                frame_id,
                capture_path,
                len(selected_entries),
                len(capture_result.entries),
                palette_idx,
            )
            return frame

        except ValueError as e:
            # Duplicate frame ID, invalid data
            logger.exception("Invalid capture data from %s: %s", capture_path, e)
            self.import_failed.emit(f"Invalid capture data: {e}")
            return None
        except OSError as e:
            logger.exception("Failed to import capture from %s", capture_path)
            self.import_failed.emit(f"Failed to import capture: {e}")
            return None

    def _cancel_existing_worker(self) -> None:
        """Cancel any existing parsing operation and clean up worker."""
        if self._capture_parse_worker is not None:
            # Disconnect signals FIRST to prevent stale emissions from old worker
            try:
                self._capture_parse_worker.file_parsed.disconnect(self._on_capture_file_parsed)
                self._capture_parse_worker.parse_error.disconnect(self._on_capture_parse_error)
                # Try both possible finished handlers (directory or single-file)
                try:
                    self._capture_parse_worker.finished_all.disconnect(self._on_capture_directory_finished)
                except RuntimeError:
                    pass
                try:
                    self._capture_parse_worker.finished_all.disconnect(self._on_single_file_finished)
                except RuntimeError:
                    pass
            except RuntimeError:
                pass  # Signals may not be connected

            # Use WorkerManager for proper cleanup (handles wait, deleteLater, registry)
            WorkerManager.cleanup_worker(self._capture_parse_worker, timeout=1000)
            self._capture_parse_worker = None

    def import_directory(self, directory: Path) -> None:
        """Parse all captures from a directory in background and emit signals.

        Parses capture files in a background thread to avoid blocking UI.
        Emits import_requested for each valid capture file.
        The workspace handles showing dialogs and calling complete_import().

        Args:
            directory: Directory containing capture JSON files
        """
        if not directory.is_dir():
            self.import_failed.emit(f"Not a directory: {directory}")
            return

        json_files = sorted(directory.glob("sprite_capture_*.json"))
        if not json_files:
            json_files = sorted(directory.glob("*.json"))

        if not json_files:
            self.import_failed.emit(f"No capture files found in {directory}")
            return

        # Cancel any existing parsing operation
        self._cancel_existing_worker()

        # Create and start background worker
        assert self._capture_repository is not None, "CaptureImportService requires capture_repository"
        self._capture_parse_worker = CaptureParseWorker(
            json_files, capture_repository=self._capture_repository, parent=self
        )
        self._capture_parse_worker.file_parsed.connect(self._on_capture_file_parsed)
        self._capture_parse_worker.parse_error.connect(self._on_capture_parse_error)
        self._capture_parse_worker.finished_all.connect(self._on_capture_directory_finished)

        # Emit start signal with total count
        self.directory_import_started.emit(len(json_files))
        logger.info("Starting background parse of %d captures from %s", len(json_files), directory)
        # Use WorkerManager for proper lifecycle tracking
        WorkerManager.start_worker(self._capture_parse_worker)

    def _on_capture_file_parsed(self, capture_result: CaptureResult, capture_path: Path) -> None:
        """Handle a capture file parsed by the background worker.

        Emits import_requested for workspace to show dialog.

        Args:
            capture_result: Parsed capture result
            capture_path: Path to the capture file
        """
        self.import_requested.emit(capture_result, capture_path)

    def _on_capture_parse_error(self, capture_path: Path, error_message: str) -> None:
        """Handle capture parsing error from background worker.

        Args:
            capture_path: Path to the file that failed to parse
            error_message: Error description
        """
        logger.warning("Failed to parse capture %s: %s", capture_path, error_message)
        # For single-file imports, emit error signal immediately
        if self._is_single_file_import:
            self.import_failed.emit(f"Invalid capture file format: {error_message}")
            self._single_file_error_emitted = True

    def _on_capture_directory_finished(self, parsed_count: int) -> None:
        """Handle completion of directory capture parsing.

        Args:
            parsed_count: Number of captures successfully parsed
        """
        logger.info("Directory import finished: %d captures parsed", parsed_count)
        self.directory_import_finished.emit(parsed_count)
        self._capture_parse_worker = None

    def _on_single_file_finished(self, parsed_count: int) -> None:
        """Handle completion of single-file import.

        Args:
            parsed_count: Number of files parsed (typically 0 or 1 for single-file)
        """
        logger.debug("Single file import finished: %d parsed", parsed_count)
        # If no files were parsed and no error was emitted yet, it means the file had no entries
        if parsed_count == 0 and self._is_single_file_import and not self._single_file_error_emitted:
            self.import_failed.emit("No sprite entries in capture file")
        self._is_single_file_import = False
        self._single_file_error_emitted = False
        self._capture_parse_worker = None

