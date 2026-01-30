"""Controller for Frame Mapping workspace.

Handles business logic for loading frames, managing mappings, and coordinating
between the view panels.
"""

from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, override

from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from core.services.image_utils import pil_to_qpixmap

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

from PySide6.QtCore import QThread

from core.frame_mapping_project import (
    AIFrame,
    FrameMappingProject,
    GameFrame,
    SheetPalette,
)
from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import (
    CaptureResult,
    MesenCaptureParser,
    OAMEntry,
)
from core.repositories.capture_result_repository import CaptureResultRepository
from core.repositories.frame_mapping_repository import FrameMappingRepository
from core.services.injection_debug_context import InjectionDebugContext
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.injection_results import InjectionRequest
from ui.common import WorkerManager
from ui.frame_mapping.services.async_game_frame_preview_service import (
    AsyncGameFramePreviewService,
)
from ui.frame_mapping.services.async_injection_service import AsyncInjectionService
from ui.frame_mapping.services.organization_service import OrganizationService
from ui.frame_mapping.services.palette_service import PaletteService
from ui.frame_mapping.services.preview_service import PreviewService
from ui.frame_mapping.services.stale_entry_detector import AsyncStaleEntryDetector
from ui.frame_mapping.undo import (
    CreateMappingCommand,
    RemoveMappingCommand,
    ReorderAIFrameCommand,
    UndoRedoStack,
    UpdateAlignmentCommand,
)
from ui.frame_mapping.views.workbench_types import AlignmentState
from utils.logging_config import get_logger

logger = get_logger(__name__)


class CaptureParseWorker(QThread):
    """Background worker for parsing capture files without blocking UI.

    Emits file_parsed for each successfully parsed file, then finished when done.
    """

    file_parsed = Signal(object, object)  # CaptureResult, Path
    parse_error = Signal(object, str)  # Path, error_message
    finished_all = Signal(int)  # total_count

    def __init__(self, paths: list[Path], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._paths = paths
        self._parser = MesenCaptureParser()

    @override
    def run(self) -> None:
        """Parse all capture files in background thread."""
        parsed_count = 0
        for path in self._paths:
            if self.isInterruptionRequested():
                break
            try:
                capture_result = self._parser.parse_file(path)
                if capture_result.has_entries:
                    self.file_parsed.emit(capture_result, path)
                    parsed_count += 1
                else:
                    self.parse_error.emit(path, "No sprite entries")
            except (OSError, JSONDecodeError, KeyError, ValueError) as e:
                self.parse_error.emit(path, str(e))
        self.finished_all.emit(parsed_count)


class FrameMappingController(QObject):
    """Controller for frame mapping operations.

    Manages the data model and coordinates view updates.

    Signal flow documentation: docs/frame_mapping_signals.md

    Signals:
        project_changed: Emitted when project is loaded/created/modified (structural changes)
        ai_frames_loaded: Emitted when AI frames are loaded (count)
        game_frame_added: Emitted when a game frame is added (frame_id)
        mapping_created: Emitted when a mapping is created (ai_index, game_id)
        mapping_removed: Emitted when a mapping is removed (ai_index)
        alignment_updated: Emitted when mapping alignment changes (ai_frame_index)
        error_occurred: Emitted on errors (error_message)
    """

    project_changed = Signal()
    ai_frames_loaded = Signal(int)  # count
    game_frame_added = Signal(str)  # game frame ID
    game_frame_removed = Signal(str)  # game frame ID
    mapping_created = Signal(str, str)  # ai_frame_id, game_frame_id
    mapping_removed = Signal(str)  # ai_frame_id
    mapping_injected = Signal(str, str)  # ai_frame_id, message
    error_occurred = Signal(str)  # error message
    status_update = Signal(str)  # status message for UI feedback
    save_requested = Signal()  # Emitted when auto-save should occur (e.g., after injection)
    stale_entries_warning = Signal(str)  # frame_id - Emitted when stored entry IDs are stale
    stale_entries_on_load = Signal(list)  # list[str] of game_frame_ids - Emitted when project loads with stale entries
    alignment_updated = Signal(str)  # ai_frame_id - Emitted when alignment changes (not structural)
    sheet_palette_changed = Signal()  # Emitted when sheet palette is set/cleared
    # AI Frame Organization signals (V4)
    frame_renamed = Signal(str)  # ai_frame_id - display name changed
    frame_tags_changed = Signal(str)  # ai_frame_id - tags changed
    ai_frame_moved = Signal(str, int, int)  # (ai_frame_id, from_index, to_index)
    ai_frame_added = Signal(str)  # ai_frame_id - Emitted when a single AI frame is added
    # Capture Organization signals
    capture_renamed = Signal(str)  # game_frame_id - display name changed
    # Preview cache signal - emitted when a preview is regenerated (mtime/entries changed)
    preview_cache_invalidated = Signal(str)  # game_frame_id - preview was regenerated
    # Capture import signal - emitted when capture parsed, workspace shows dialog
    capture_import_requested = Signal(object, object)  # (CaptureResult, capture_path: Path)
    # Directory import signals - for background parsing progress
    directory_import_started = Signal(int)  # total_files - Emitted when directory import begins
    directory_import_finished = Signal(int)  # parsed_count - Emitted when directory import completes
    # Undo/Redo signals
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    # Async game frame preview signals (for batch preview generation)
    game_frame_preview_ready = Signal(str, QPixmap)  # frame_id, pixmap
    game_frame_previews_finished = Signal()
    # Async injection signals
    async_injection_started = Signal(str)  # ai_frame_id
    async_injection_progress = Signal(str, str)  # ai_frame_id, message
    async_injection_finished = Signal(str, bool, str)  # ai_frame_id, success, message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._project: FrameMappingProject | None = None
        # Shared capture repository for parsed capture file caching (thread-safe)
        # Both PreviewService and AsyncStaleEntryDetector use this to avoid duplicate parsing
        self._capture_repository = CaptureResultRepository()
        # Preview service for game frame preview cache (uses shared repository)
        self._preview_service = PreviewService(parent=self, capture_repository=self._capture_repository)
        self._preview_service.preview_cache_invalidated.connect(self.preview_cache_invalidated)
        self._preview_service.stale_entries_warning.connect(self.stale_entries_warning)
        # Async game frame preview service (for batch async preview generation)
        self._async_preview_service = AsyncGameFramePreviewService(
            parent=self, capture_repository=self._capture_repository
        )
        self._async_preview_service.preview_ready.connect(self._on_async_preview_ready)
        self._async_preview_service.batch_finished.connect(self._on_async_previews_finished)
        # Palette service for palette management
        self._palette_service = PaletteService(parent=self)
        self._palette_service.sheet_palette_changed.connect(self.sheet_palette_changed)
        # BUG-2 FIX: Invalidate preview cache when palette changes (previews are palette-dependent)
        self._palette_service.sheet_palette_changed.connect(self._invalidate_previews_on_palette_change)
        # Organization service for frame/capture renaming and tagging
        self._organization_service = OrganizationService(parent=self)
        self._organization_service.frame_renamed.connect(self.frame_renamed)
        self._organization_service.frame_tags_changed.connect(self.frame_tags_changed)
        self._organization_service.capture_renamed.connect(self.capture_renamed)
        # Injection orchestrator for frame injection pipeline (sync)
        self._injection_orchestrator = InjectionOrchestrator()
        # Async injection service (for non-blocking injections)
        self._async_injection_service = AsyncInjectionService(parent=self)
        self._async_injection_service.injection_started.connect(self.async_injection_started)
        self._async_injection_service.injection_progress.connect(self.async_injection_progress)
        self._async_injection_service.injection_finished.connect(self._on_async_injection_finished)
        # Async stale entry detector (avoids UI freeze during project load, uses shared repository)
        self._stale_entry_detector = AsyncStaleEntryDetector(parent=self, capture_repository=self._capture_repository)
        self._stale_entry_detector.stale_entries_detected.connect(self.stale_entries_on_load)
        # Undo/Redo stack
        self._undo_stack = UndoRedoStack(parent=self)
        self._undo_stack.can_undo_changed.connect(self.can_undo_changed)
        self._undo_stack.can_redo_changed.connect(self.can_redo_changed)
        # Background capture parsing worker (kept alive during parsing)
        self._capture_parse_worker: CaptureParseWorker | None = None

    @property
    def project(self) -> FrameMappingProject | None:
        """Get the current project."""
        return self._project

    @property
    def has_project(self) -> bool:
        """Check if a project is loaded."""
        return self._project is not None

    # ─── Undo/Redo Public API ──────────────────────────────────────────────────

    def undo(self) -> str | None:
        """Undo the last command.

        Returns:
            Description of the undone command, or None if nothing to undo
        """
        desc = self._undo_stack.undo()
        if desc:
            logger.info("Undo: %s", desc)
            self.project_changed.emit()
            self.save_requested.emit()
        return desc

    def redo(self) -> str | None:
        """Redo the last undone command.

        Returns:
            Description of the redone command, or None if nothing to redo
        """
        desc = self._undo_stack.redo()
        if desc:
            logger.info("Redo: %s", desc)
            self.project_changed.emit()
            self.save_requested.emit()
        return desc

    def clear_undo_history(self) -> None:
        """Clear all undo/redo history."""
        self._undo_stack.clear()

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self._undo_stack.can_undo()

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self._undo_stack.can_redo()

    def new_project(self, name: str = "Untitled") -> None:
        """Create a new empty project.

        Args:
            name: Project name
        """
        self._project = FrameMappingProject(name=name)
        self._preview_service.invalidate_all()
        self._undo_stack.clear()  # Clear history on new project
        self.project_changed.emit()
        logger.info("Created new frame mapping project: %s", name)

    def _generate_unique_frame_id(self, base_id: str) -> str:
        """Generate a unique frame ID, adding suffix if collision exists.

        Args:
            base_id: The initial frame ID (e.g., from filename)

        Returns:
            A unique frame ID, potentially with _N suffix
        """
        if self._project is None:
            return base_id

        existing_ids = {gf.id for gf in self._project.game_frames}
        if base_id not in existing_ids:
            return base_id

        # Find next available suffix
        counter = 1
        while f"{base_id}_{counter}" in existing_ids:
            counter += 1

        unique_id = f"{base_id}_{counter}"
        logger.info("Renamed duplicate capture ID %s -> %s", base_id, unique_id)
        return unique_id

    def load_project(self, path: Path) -> bool:
        """Load a project from file.

        Args:
            path: Path to project file

        Returns:
            True if loaded successfully
        """
        try:
            self._project = FrameMappingRepository.load(path)

            # Start async stale entry detection (UI won't freeze for large projects)
            # Signal will emit stale_entries_on_load when detection completes
            self._stale_entry_detector.detect_stale_entries(self._project.game_frames)

            self._preview_service.invalidate_all()
            self._undo_stack.clear()  # Clear history on project load
            self.project_changed.emit()
            logger.info("Loaded frame mapping project from %s", path)
            return True
        except FileNotFoundError:
            logger.warning("Project file not found: %s", path)
            self.error_occurred.emit(f"Project file not found: {path}")
            return False
        except (JSONDecodeError, KeyError, ValueError) as e:
            logger.exception("Invalid project file format: %s", path)
            self.error_occurred.emit(f"Invalid project file format: {e}")
            return False
        except OSError as e:
            logger.exception("Failed to read project file: %s", path)
            self.error_occurred.emit(f"Failed to read project: {e}")
            return False

    def save_project(self, path: Path) -> bool:
        """Save the current project to file.

        Args:
            path: Destination path

        Returns:
            True if saved successfully
        """
        if self._project is None:
            self.error_occurred.emit("No project to save")
            return False

        try:
            FrameMappingRepository.save(self._project, path)
            logger.info("Saved frame mapping project to %s", path)
            return True
        except PermissionError as e:
            logger.exception("Permission denied saving project to %s", path)
            self.error_occurred.emit(f"Permission denied: {e}")
            return False
        except OSError as e:
            logger.exception("Failed to save project to %s", path)
            self.error_occurred.emit(f"Failed to save project: {e}")
            return False

    def load_ai_frames_from_directory(self, directory: Path) -> int:
        """Load AI frames from a directory of PNG files.

        Args:
            directory: Directory containing PNG files

        Returns:
            Number of frames loaded
        """
        if self._project is None:
            self.new_project()

        if not directory.is_dir():
            self.error_occurred.emit(f"Not a directory: {directory}")
            return 0

        # Find all PNG files, sorted by name
        png_files = sorted(directory.glob("*.png"))
        if not png_files:
            self.error_occurred.emit(f"No PNG files found in {directory}")
            return 0

        frames: list[AIFrame] = []
        for idx, png_path in enumerate(png_files):
            # Get image dimensions from header only (fast - reads ~100 bytes vs full decode)
            try:
                with Image.open(png_path) as img:
                    width, height = img.size
            except Exception:
                width, height = 0, 0

            frame = AIFrame(
                path=png_path,
                index=idx,
                width=width,
                height=height,
            )
            frames.append(frame)

        # Replace AI frames using facade (handles index invalidation)
        self._project.replace_ai_frames(frames, directory)  # type: ignore[union-attr]

        # Clear undo history: old commands reference deleted frame IDs
        self.clear_undo_history()

        # Bug #3 fix: Prune orphaned mappings that reference non-existent AI frame IDs
        valid_ids = {f.id for f in frames}
        removed = self._project.filter_mappings_by_valid_ai_ids(valid_ids)  # type: ignore[union-attr]
        if removed > 0:
            logger.info(
                "Pruning %d orphaned mappings after AI frames reload",
                removed,
            )

        self.ai_frames_loaded.emit(len(frames))
        self.project_changed.emit()
        logger.info("Loaded %d AI frames from %s", len(frames), directory)
        return len(frames)

    def add_ai_frame_from_file(self, file_path: Path) -> bool:
        """Add a single AI frame from a PNG file.

        Args:
            file_path: Path to the PNG file

        Returns:
            True if frame was added successfully
        """
        if self._project is None:
            self.new_project()

        if not file_path.is_file() or file_path.suffix.lower() != ".png":
            self.error_occurred.emit(f"Not a PNG file: {file_path}")
            return False

        # Get image dimensions from header only (fast - reads ~100 bytes vs full decode)
        try:
            with Image.open(file_path) as img:
                width, height = img.size
        except Exception:
            width, height = 0, 0

        # Check if frame already exists (by path)
        existing_frames = self._project.ai_frames if self._project else []
        for frame in existing_frames:
            if frame.path == file_path:
                logger.info("AI frame already exists: %s", file_path)
                # Just notify UI to refresh/select it
                self.ai_frames_loaded.emit(len(existing_frames))
                return True

        # Create new frame with next available index
        next_index = len(existing_frames)
        frame = AIFrame(
            path=file_path,
            index=next_index,
            width=width,
            height=height,
        )

        # Add to project (may raise ValueError for duplicate ID)
        try:
            self._project.add_ai_frame(frame)  # type: ignore[union-attr]
        except ValueError as e:
            self.error_occurred.emit(f"Cannot add frame: {e}")
            return False

        self.ai_frames_loaded.emit(len(self._project.ai_frames))  # type: ignore[union-attr]
        # Emit targeted signal instead of project_changed to avoid full refresh
        self.ai_frame_added.emit(frame.id)
        logger.info("Added AI frame: %s", file_path)
        return True

    def import_mesen_capture(self, capture_path: Path) -> None:
        """Parse a Mesen 2 capture file and emit signal for sprite selection.

        The workspace handles showing the sprite selection dialog and calls
        complete_capture_import() with the user's selection.

        Args:
            capture_path: Path to capture JSON file
        """
        if self._project is None:
            self.new_project()

        try:
            # Parse the capture file
            parser = MesenCaptureParser()
            capture_result = parser.parse_file(capture_path)

            if not capture_result.has_entries:
                self.error_occurred.emit(f"No sprite entries in capture: {capture_path}")
                return

            # Emit signal for workspace to show sprite selection dialog
            self.capture_import_requested.emit(capture_result, capture_path)

        except FileNotFoundError:
            logger.warning("Capture file not found: %s", capture_path)
            self.error_occurred.emit(f"Capture file not found: {capture_path}")
        except JSONDecodeError as e:
            logger.exception("Invalid JSON in capture file: %s", capture_path)
            self.error_occurred.emit(f"Invalid capture file format: {e}")
        except (KeyError, ValueError) as e:
            logger.exception("Malformed capture data in %s", capture_path)
            self.error_occurred.emit(f"Malformed capture data: {e}")
        except OSError as e:
            logger.exception("Failed to read capture file: %s", capture_path)
            self.error_occurred.emit(f"Failed to read capture: {e}")

    def complete_capture_import(
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
        if self._project is None:
            self.error_occurred.emit("No project loaded")
            return None

        if not selected_entries:
            self.error_occurred.emit("No sprites selected")
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

            # Bug #4 fix: Ensure unique ID when importing captures with same filename
            frame_id = self._generate_unique_frame_id(frame_id)

            # Get unique ROM offsets from selected entries only
            rom_offsets = filtered_capture.unique_rom_offsets

            # Render preview using filtered capture (cropped to bounding box)
            renderer = CaptureRenderer(filtered_capture)
            preview_img = renderer.render_selection()

            # Convert PIL Image to QPixmap and cache with mtime + entry IDs for invalidation
            pixmap = pil_to_qpixmap(preview_img)
            if pixmap is not None:
                mtime = capture_path.stat().st_mtime if capture_path.exists() else 0.0
                entry_ids = tuple(entry.id for entry in selected_entries)
                self._preview_service.set_preview_cache(frame_id, pixmap, mtime, entry_ids)

            # Infer palette from selected entries (use first entry's palette if all same)
            palette_idx = 0
            if selected_entries:
                first_palette = selected_entries[0].palette
                if all(e.palette == first_palette for e in selected_entries):
                    palette_idx = first_palette

            # Create game frame with selected entry IDs for filtering on retrieval
            bbox = filtered_capture.bounding_box
            # Default all ROM offsets to RAW compression (user can change in workbench)
            default_compression_types = dict.fromkeys(rom_offsets, "raw")
            frame = GameFrame(
                id=frame_id,
                rom_offsets=rom_offsets,
                capture_path=capture_path,
                palette_index=palette_idx,  # Inferred from selected entries
                width=bbox.width,
                height=bbox.height,
                selected_entry_ids=[entry.id for entry in selected_entries],
                compression_types=default_compression_types,
            )

            self._project.add_game_frame(frame)
            self.game_frame_added.emit(frame_id)
            self.project_changed.emit()
            self.save_requested.emit()
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
            self.error_occurred.emit(f"Invalid capture data: {e}")
            return None
        except OSError as e:
            logger.exception("Failed to import capture from %s", capture_path)
            self.error_occurred.emit(f"Failed to import capture: {e}")
            return None

    def import_capture_directory(self, directory: Path) -> None:
        """Parse all captures from a directory in background and emit signals.

        Parses capture files in a background thread to avoid blocking UI.
        Emits capture_import_requested for each valid capture file.
        The workspace handles showing dialogs and calling complete_capture_import().

        Emits:
            directory_import_started: When parsing begins (total_files count)
            capture_import_requested: For each successfully parsed capture
            directory_import_finished: When all parsing completes (parsed_count)

        Args:
            directory: Directory containing capture JSON files
        """
        if not directory.is_dir():
            self.error_occurred.emit(f"Not a directory: {directory}")
            return

        json_files = sorted(directory.glob("sprite_capture_*.json"))
        if not json_files:
            json_files = sorted(directory.glob("*.json"))

        if not json_files:
            self.error_occurred.emit(f"No capture files found in {directory}")
            return

        # Cancel any existing parsing operation
        if self._capture_parse_worker is not None:
            # Disconnect signals FIRST to prevent stale emissions from old worker
            try:
                self._capture_parse_worker.file_parsed.disconnect(self._on_capture_file_parsed)
                self._capture_parse_worker.parse_error.disconnect(self._on_capture_parse_error)
                self._capture_parse_worker.finished_all.disconnect(self._on_capture_directory_finished)
            except RuntimeError:
                pass  # Signals may not be connected

            # Use WorkerManager for proper cleanup (handles wait, deleteLater, registry)
            WorkerManager.cleanup_worker(self._capture_parse_worker, timeout=1000)
            self._capture_parse_worker = None

        if self._project is None:
            self.new_project()

        # Create and start background worker
        self._capture_parse_worker = CaptureParseWorker(json_files, parent=self)
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

        Emits capture_import_requested for workspace to show dialog.

        Args:
            capture_result: Parsed capture result
            capture_path: Path to the capture file
        """
        self.capture_import_requested.emit(capture_result, capture_path)

    def _on_capture_parse_error(self, capture_path: Path, error_message: str) -> None:
        """Handle capture parsing error from background worker.

        Args:
            capture_path: Path to the file that failed to parse
            error_message: Error description
        """
        logger.warning("Failed to parse capture %s: %s", capture_path, error_message)

    def _on_capture_directory_finished(self, parsed_count: int) -> None:
        """Handle completion of directory capture parsing.

        Args:
            parsed_count: Number of captures successfully parsed
        """
        logger.info("Directory import finished: %d captures parsed", parsed_count)
        self.directory_import_finished.emit(parsed_count)
        self._capture_parse_worker = None

    def create_mapping(self, ai_frame_id: str, game_frame_id: str) -> bool:
        """Create a mapping between an AI frame and a game frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            game_frame_id: ID of the game frame

        Returns:
            True if mapping was created
        """
        if self._project is None:
            self.error_occurred.emit("No project loaded")
            return False

        # Verify both frames exist
        ai_frame = self._project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            self.error_occurred.emit(f"AI frame {ai_frame_id} not found")
            return False

        game_frame = self._project.get_game_frame_by_id(game_frame_id)
        if game_frame is None:
            self.error_occurred.emit(f"Game frame {game_frame_id} not found")
            return False

        # Capture previous state for undo
        prev_ai_mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
        prev_game_mapping = self._project.get_mapping_for_game_frame(game_frame_id)

        prev_ai_game_id = prev_ai_mapping.game_frame_id if prev_ai_mapping else None
        prev_game_ai_id = prev_game_mapping.ai_frame_id if prev_game_mapping else None
        prev_ai_alignment = None
        prev_game_alignment = None

        if prev_ai_mapping:
            prev_ai_alignment = (
                prev_ai_mapping.offset_x,
                prev_ai_mapping.offset_y,
                prev_ai_mapping.flip_h,
                prev_ai_mapping.flip_v,
                prev_ai_mapping.scale,
                prev_ai_mapping.sharpen,
                prev_ai_mapping.resampling,
            )
        if prev_game_mapping and prev_game_ai_id != ai_frame_id:
            prev_game_alignment = (
                prev_game_mapping.offset_x,
                prev_game_mapping.offset_y,
                prev_game_mapping.flip_h,
                prev_game_mapping.flip_v,
                prev_game_mapping.scale,
                prev_game_mapping.sharpen,
                prev_game_mapping.resampling,
            )

        # Create and execute command via undo stack
        command = CreateMappingCommand(
            controller=self,
            ai_frame_id=ai_frame_id,
            game_frame_id=game_frame_id,
            prev_ai_mapping_game_id=prev_ai_game_id,
            prev_game_mapping_ai_id=prev_game_ai_id,
            prev_ai_mapping_alignment=prev_ai_alignment,
            prev_game_mapping_alignment=prev_game_alignment,
        )
        self._undo_stack.push(command)

        self.mapping_created.emit(ai_frame_id, game_frame_id)
        self.save_requested.emit()
        logger.info("Created mapping: AI frame %s -> Game frame %s", ai_frame_id, game_frame_id)
        return True

    def _create_mapping_no_history(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Internal: Create mapping without undo history (for command execution)."""
        if self._project is None:
            return
        self._project.create_mapping(ai_frame_id, game_frame_id)

    def get_existing_link_for_game_frame(self, game_frame_id: str) -> str | None:
        """Get the AI frame ID currently linked to a game frame.

        Args:
            game_frame_id: ID of the game frame to check

        Returns:
            AI frame ID if game frame is linked, None otherwise
        """
        if self._project is None:
            return None
        return self._project.get_ai_frame_linked_to_game_frame(game_frame_id)

    def get_existing_link_for_ai_frame(self, ai_frame_id: str) -> str | None:
        """Get the game frame ID currently linked to an AI frame.

        Args:
            ai_frame_id: ID of the AI frame to check

        Returns:
            Game frame ID if AI frame is linked, None otherwise
        """
        if self._project is None:
            return None
        mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
        return mapping.game_frame_id if mapping else None

    def remove_mapping(self, ai_frame_id: str) -> bool:
        """Remove a mapping for an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)

        Returns:
            True if a mapping was removed
        """
        if self._project is None:
            return False

        # Capture state for undo
        mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return False

        removed_game_id = mapping.game_frame_id
        removed_alignment = (
            mapping.offset_x,
            mapping.offset_y,
            mapping.flip_h,
            mapping.flip_v,
            mapping.scale,
            mapping.sharpen,
            mapping.resampling,
        )
        removed_status = mapping.status

        # Create and execute command via undo stack
        command = RemoveMappingCommand(
            controller=self,
            ai_frame_id=ai_frame_id,
            removed_game_frame_id=removed_game_id,
            removed_alignment=removed_alignment,
            removed_status=removed_status,
        )
        self._undo_stack.push(command)

        self.mapping_removed.emit(ai_frame_id)
        self.save_requested.emit()
        logger.info("Removed mapping for AI frame %s", ai_frame_id)
        return True

    def _remove_mapping_no_history(self, ai_frame_id: str) -> bool:
        """Internal: Remove mapping without undo history (for command execution)."""
        if self._project is None:
            return False
        return self._project.remove_mapping_for_ai_frame(ai_frame_id)

    def update_mapping_alignment(
        self,
        ai_frame_id: str,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
        sharpen: float = 0.0,
        resampling: str = "lanczos",
        set_edited: bool = True,
        drag_start_alignment: AlignmentState | None = None,
    ) -> bool:
        """Update alignment for a mapping.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            offset_x: X offset for alignment
            offset_y: Y offset for alignment
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
            scale: Scale factor (0.1 - 1.0)
            sharpen: Pre-sharpening amount (0.0 - 4.0)
            resampling: Resampling method ("lanczos" or "nearest")
            set_edited: If True and status is not 'injected', set status to 'edited'.
                        Use False for auto-centering during initial link creation.
            drag_start_alignment: If provided, use this as old state for undo command.
                        This creates a single undo for an entire drag operation.

        Returns:
            True if alignment was updated
        """
        if self._project is None:
            return False

        mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return False

        # Only record undo for explicit user edits, not auto-centering
        if set_edited:
            # Use drag start alignment for undo if provided (creates single undo for entire drag)
            # Otherwise use current mapping state (for keyboard nudge, etc.)
            if drag_start_alignment is not None:
                old_x = drag_start_alignment.offset_x
                old_y = drag_start_alignment.offset_y
                old_flip_h = drag_start_alignment.flip_h
                old_flip_v = drag_start_alignment.flip_v
                old_scale = drag_start_alignment.scale
                old_sharpen = drag_start_alignment.sharpen
                old_resampling = drag_start_alignment.resampling
            else:
                old_x = mapping.offset_x
                old_y = mapping.offset_y
                old_flip_h = mapping.flip_h
                old_flip_v = mapping.flip_v
                old_scale = mapping.scale
                old_sharpen = mapping.sharpen
                old_resampling = mapping.resampling

            # Capture previous state for undo
            command = UpdateAlignmentCommand(
                controller=self,
                ai_frame_id=ai_frame_id,
                new_offset_x=offset_x,
                new_offset_y=offset_y,
                new_flip_h=flip_h,
                new_flip_v=flip_v,
                new_scale=scale,
                new_sharpen=sharpen,
                new_resampling=resampling,
                old_offset_x=old_x,
                old_offset_y=old_y,
                old_flip_h=old_flip_h,
                old_flip_v=old_flip_v,
                old_scale=old_scale,
                old_sharpen=old_sharpen,
                old_resampling=old_resampling,
                old_status=mapping.status,
            )
            self._undo_stack.push(command)
        else:
            # Auto-centering - update directly without history
            self._project.update_mapping_alignment(
                ai_frame_id, offset_x, offset_y, flip_h, flip_v, scale, sharpen, resampling, set_edited
            )

        # Use targeted signal to avoid full UI refresh (which blanks canvas)
        self.alignment_updated.emit(ai_frame_id)
        self.save_requested.emit()
        logger.info(
            "Updated alignment for AI frame %s: offset=(%d, %d), flip=(%s, %s), scale=%.2f, sharpen=%.1f, resampling=%s",
            ai_frame_id,
            offset_x,
            offset_y,
            flip_h,
            flip_v,
            scale,
            sharpen,
            resampling,
        )
        return True

    def _update_alignment_no_history(
        self,
        ai_frame_id: str,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float,
        sharpen: float = 0.0,
        resampling: str = "lanczos",
    ) -> bool:
        """Internal: Update alignment without undo history (for command execution)."""
        if self._project is None:
            return False
        return self._project.update_mapping_alignment(
            ai_frame_id, offset_x, offset_y, flip_h, flip_v, scale, sharpen, resampling, set_edited=True
        )

    def _set_mapping_status_no_history(self, ai_frame_id: str, status: str) -> bool:
        """Internal: Set mapping status without undo history (for command execution)."""
        if self._project is None:
            return False
        mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return False
        mapping.status = status
        return True

    def apply_transforms_to_all_mappings(
        self,
        offset_x: int,
        offset_y: int,
        scale: float,
        exclude_ai_frame_id: str | None = None,
    ) -> int:
        """Apply position and scale to all mapped frames.

        Args:
            offset_x: X offset to apply
            offset_y: Y offset to apply
            scale: Scale factor to apply (0.01 - 1.0)
            exclude_ai_frame_id: AI frame ID to exclude (typically the current frame)

        Returns:
            Number of mappings updated
        """
        if self._project is None:
            return 0

        updated_count = 0
        for mapping in self._project.mappings:
            # Skip excluded frame
            if mapping.ai_frame_id == exclude_ai_frame_id:
                continue

            # Update position and scale, preserve flip values
            mapping.offset_x = offset_x
            mapping.offset_y = offset_y
            mapping.scale = max(0.01, min(1.0, scale))
            mapping.status = "edited"
            updated_count += 1

        if updated_count > 0:
            self.project_changed.emit()
            self.save_requested.emit()

        return updated_count

    def get_game_frame_preview(self, frame_id: str) -> QPixmap | None:
        """Get the rendered preview pixmap for a game frame.

        Delegates to preview service for caching and rendering.

        Args:
            frame_id: Game frame ID

        Returns:
            QPixmap preview or None if not available
        """
        return self._preview_service.get_preview(frame_id, self._project)

    def get_capture_result_for_game_frame(self, frame_id: str) -> tuple[CaptureResult | None, bool]:
        """Get the CaptureResult for a game frame.

        Delegates to preview service for capture parsing and filtering.

        Args:
            frame_id: Game frame ID

        Returns:
            Tuple of (CaptureResult or None, used_fallback flag).
            used_fallback is True if the stored entry IDs were stale and
            rom_offset filtering was used instead.
        """
        return self._preview_service.get_capture_result_for_game_frame(frame_id, self._project)

    def request_game_frame_previews_async(self, frame_ids: list[str]) -> None:
        """Request async preview generation for specified game frames.

        Generates previews in a background thread, emitting game_frame_preview_ready
        for each completed preview.

        Args:
            frame_ids: List of game frame IDs to generate previews for
        """
        if self._project is None:
            self.game_frame_previews_finished.emit()
            return

        self._async_preview_service.request_previews(frame_ids, self._project)

    def _on_async_preview_ready(self, frame_id: str, pixmap: QPixmap) -> None:
        """Handle async preview completion.

        Updates the synchronous preview cache and emits signal to UI.
        """
        # Update synchronous preview cache so get_game_frame_preview() returns this
        if self._project is not None:
            game_frame = self._project.get_game_frame_by_id(frame_id)
            if game_frame is not None:
                mtime = 0.0
                if game_frame.capture_path and game_frame.capture_path.exists():
                    mtime = game_frame.capture_path.stat().st_mtime
                entry_ids = tuple(game_frame.selected_entry_ids)
                self._preview_service.set_preview_cache(frame_id, pixmap, mtime, entry_ids)

        self.game_frame_preview_ready.emit(frame_id, pixmap)

    def _on_async_previews_finished(self) -> None:
        """Handle async preview batch completion."""
        self.game_frame_previews_finished.emit()

    def get_ai_frames(self) -> list[AIFrame]:
        """Get all AI frames from the current project."""
        if self._project is None:
            return []
        return self._project.ai_frames

    def get_game_frames(self) -> list[GameFrame]:
        """Get all game frames from the current project."""
        if self._project is None:
            return []
        return self._project.game_frames

    # --- Sheet Palette Methods ---

    def get_sheet_palette(self) -> SheetPalette | None:
        """Get the current sheet palette.

        Returns:
            SheetPalette if defined, None otherwise
        """
        return self._palette_service.get_sheet_palette(self._project)

    def set_sheet_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette for the project.

        Args:
            palette: SheetPalette to set, or None to clear
        """
        self._palette_service.set_sheet_palette(self._project, palette)
        self.project_changed.emit()

    def set_sheet_palette_color(self, index: int, rgb: tuple[int, int, int]) -> None:
        """Update a single color in the sheet palette.

        Args:
            index: Palette index (0-15)
            rgb: New RGB color tuple
        """
        self._palette_service.set_sheet_palette_color(self._project, index, rgb)
        self.project_changed.emit()

    def _invalidate_previews_on_palette_change(self) -> None:
        """Mark all previews as stale when sheet palette changes.

        BUG-2 FIX: Game frame previews may use the sheet palette for rendering.
        When the palette changes, cached previews become stale and must be
        regenerated to reflect the new colors.

        Using mark_all_stale() instead of invalidate_all() allows the UI to
        remain responsive - existing previews are displayed immediately while
        regeneration happens lazily on next access.
        """
        logger.debug("Marking preview cache stale due to palette change")
        self._preview_service.mark_all_stale()

    def extract_sheet_colors(self) -> dict[tuple[int, int, int], int]:
        """Extract unique colors from all AI frames in the project.

        Returns:
            Dict mapping RGB tuples to pixel counts
        """
        return self._palette_service.extract_sheet_colors(self._project)

    def generate_sheet_palette_from_colors(
        self,
        colors: dict[tuple[int, int, int], int] | None = None,
    ) -> SheetPalette:
        """Generate a 16-color palette from AI sheet colors.

        Args:
            colors: Color counts to use, or None to extract from AI frames

        Returns:
            Generated SheetPalette with auto-mapped colors
        """
        return self._palette_service.generate_sheet_palette_from_colors(self._project, colors)

    def copy_game_palette_to_sheet(self, game_frame_id: str) -> SheetPalette | None:
        """Create a SheetPalette from a game frame's palette.

        Args:
            game_frame_id: ID of game frame to copy palette from

        Returns:
            SheetPalette with the game frame's colors, or None if not found
        """
        return self._palette_service.copy_game_palette_to_sheet(self._project, game_frame_id)

    def get_game_palettes(self) -> dict[str, list[tuple[int, int, int]]]:
        """Get palettes from all game frames.

        Returns:
            Dict mapping game frame IDs to their RGB palettes
        """
        return self._palette_service.get_game_palettes(self._project)

    def remove_game_frame(self, frame_id: str) -> bool:
        """Remove a game frame from the project.

        Also removes any associated mapping and clears the preview cache.

        Args:
            frame_id: ID of the game frame to remove.

        Returns:
            True if the frame was found and removed.
        """
        if self._project is None:
            return False

        # Clear preview cache for this frame
        self._preview_service.invalidate(frame_id)

        if self._project.remove_game_frame(frame_id):
            self.game_frame_removed.emit(frame_id)
            self.project_changed.emit()
            logger.info("Removed game frame %s", frame_id)
            return True
        return False

    def remove_ai_frame(self, frame_id: str) -> bool:
        """Remove an AI frame from the project.

        Also removes any associated mapping.

        Args:
            frame_id: ID of the AI frame to remove.

        Returns:
            True if the frame was found and removed.
        """
        if self._project is None:
            return False

        if self._project.remove_ai_frame(frame_id):
            self.project_changed.emit()
            logger.info("Removed AI frame %s", frame_id)
            return True
        return False

    def reorder_ai_frame(self, ai_frame_id: str, new_index: int) -> bool:
        """Reorder an AI frame to a new position (undoable).

        Args:
            ai_frame_id: ID of the AI frame to move.
            new_index: Target position (0-based).

        Returns:
            True if the frame was moved.
        """
        if self._project is None:
            return False

        # Find current index
        current_index = -1
        for i, frame in enumerate(self._project.ai_frames):
            if frame.id == ai_frame_id:
                current_index = i
                break

        if current_index == -1:
            return False

        # Clamp and check for no-op
        max_index = len(self._project.ai_frames) - 1
        clamped_index = max(0, min(new_index, max_index))
        if current_index == clamped_index:
            return False

        # Create and execute command
        command = ReorderAIFrameCommand(
            controller=self,
            ai_frame_id=ai_frame_id,
            old_index=current_index,
            new_index=clamped_index,
        )
        self._undo_stack.push(command)
        return True

    def _reorder_ai_frame_no_history(self, ai_frame_id: str, new_index: int) -> bool:
        """Internal: Reorder AI frame without undo history (for command execution)."""
        if self._project is None:
            return False

        # Find current index before reordering
        old_index = -1
        for i, frame in enumerate(self._project.ai_frames):
            if frame.id == ai_frame_id:
                old_index = i
                break

        if old_index == -1:
            return False

        if self._project.reorder_ai_frame(ai_frame_id, new_index):
            # Emit with actual target index (may be clamped)
            actual_new_index = -1
            for i, frame in enumerate(self._project.ai_frames):
                if frame.id == ai_frame_id:
                    actual_new_index = i
                    break
            self.ai_frame_moved.emit(ai_frame_id, old_index, actual_new_index)
            logger.info("Reordered AI frame %s from %d to %d", ai_frame_id, old_index, actual_new_index)
            return True
        return False

    def update_game_frame_compression(self, frame_id: str, compression_type: str) -> bool:
        """Update compression type for a game frame.

        Updates the compression type for all ROM offsets in the game frame.
        By design, compression is a single setting per game frame, not per offset.
        This routes compression changes through the controller instead of
        directly mutating game frame state.

        Args:
            frame_id: ID of the game frame
            compression_type: New compression type ('raw' or 'hal')

        Returns:
            True if the update was successful
        """
        if self._project is None:
            self.error_occurred.emit("No project loaded")
            return False

        game_frame = self._project.get_game_frame_by_id(frame_id)
        if game_frame is None:
            self.error_occurred.emit(f"Game frame {frame_id} not found")
            return False

        # Update compression type for all ROM offsets
        for rom_offset in game_frame.rom_offsets:
            game_frame.compression_types[rom_offset] = compression_type

        self.project_changed.emit()
        self.save_requested.emit()
        logger.info(
            "Updated compression type for game frame %s to %s (%d offsets)",
            frame_id,
            compression_type,
            len(game_frame.rom_offsets),
        )
        return True

    def create_injection_copy(self, rom_path: Path) -> Path | None:
        """Create a numbered copy of the ROM for injection (public API).

        Use this to pre-create a copy for batch injection operations.

        Args:
            rom_path: Path to the source ROM

        Returns:
            Path to the created copy, or None if creation failed
        """
        from core.services.rom_staging_manager import ROMStagingManager

        staging_manager = ROMStagingManager()
        return staging_manager.create_injection_copy(rom_path, None)

    def _calculate_palette_rom_offset(self, rom_path: Path, game_frame_id: str) -> int | None:
        """Calculate palette ROM offset from game config and frame's palette index.

        First checks for character-specific palette offsets (e.g., King Dedede),
        then falls back to the generic palette calculation.

        Args:
            rom_path: Path to the ROM file.
            game_frame_id: ID of the game frame being injected.

        Returns:
            ROM offset where the palette should be written, or None if not available.
        """
        if self._project is None:
            return None

        # Get the game frame to get its palette_index and rom_offsets
        game_frame = self._project.get_game_frame_by_id(game_frame_id)
        if game_frame is None:
            logger.debug("Cannot calculate palette offset: game_frame %s not found", game_frame_id)
            return None

        try:
            # Read ROM header to get title/checksum
            from core.app_context import get_app_context

            rom_extractor = get_app_context().rom_extractor
            header = rom_extractor.read_rom_header(str(rom_path))

            # Find game config
            config_loader = get_app_context().sprite_config_loader
            game_name, game_config = config_loader.find_game_config(header.title, header.checksum)
            if not game_config:
                logger.debug("No game config found for %s (checksum 0x%04X)", header.title, header.checksum)
                return None

            palettes = game_config.get("palettes", {})
            if not isinstance(palettes, dict):
                return None

            # Check for character-specific palette offsets first
            character_offsets = palettes.get("character_offsets", {})
            if isinstance(character_offsets, dict):
                # Try hint-based matching first
                for char_name, char_config in character_offsets.items():
                    if not isinstance(char_config, dict):
                        continue
                    rom_offset_hints = char_config.get("rom_offset_hints", [])
                    if not isinstance(rom_offset_hints, list) or not rom_offset_hints:
                        continue

                    # Convert hints to integers for comparison
                    hint_ints: set[int] = set()
                    for hint in rom_offset_hints:
                        if isinstance(hint, str):
                            hint_ints.add(int(hint, 16) if hint.startswith("0x") else int(hint))
                        elif isinstance(hint, int):
                            hint_ints.add(hint)

                    # Check if any of the game frame's ROM offsets match the hints
                    if game_frame.rom_offsets and hint_ints.intersection(game_frame.rom_offsets):
                        char_offset_str = char_config.get("offset")
                        if char_offset_str and isinstance(char_offset_str, str):
                            char_offset = (
                                int(char_offset_str, 16) if char_offset_str.startswith("0x") else int(char_offset_str)
                            )
                            logger.info(
                                "Using character-specific palette offset for %s (hint match): 0x%X",
                                char_name,
                                char_offset,
                            )
                            return char_offset

                # No hint match - if there's only one character config, use it as default
                # This handles the common case of single-character replacement projects
                if len(character_offsets) == 1:
                    char_name, char_config = next(iter(character_offsets.items()))
                    if isinstance(char_config, dict):
                        char_offset_str = char_config.get("offset")
                        if char_offset_str and isinstance(char_offset_str, str):
                            char_offset = (
                                int(char_offset_str, 16) if char_offset_str.startswith("0x") else int(char_offset_str)
                            )
                            logger.info(
                                "Using character-specific palette offset for %s (single character default): 0x%X",
                                char_name,
                                char_offset,
                            )
                            return char_offset

            # Fall back to generic palette calculation
            base_offset_str = palettes.get("offset")
            if not base_offset_str or not isinstance(base_offset_str, str):
                logger.debug("No palette offset in game config for %s", game_name)
                return None

            base_offset = int(base_offset_str, 16) if base_offset_str.startswith("0x") else int(base_offset_str)

            # Calculate offset for this palette index
            # Each palette is 32 bytes (16 colors x 2 bytes BGR555)
            palette_offset = base_offset + (game_frame.palette_index * 32)
            logger.info(
                "Calculated palette ROM offset: 0x%X (base 0x%X + palette_index %d * 32)",
                palette_offset,
                base_offset,
                game_frame.palette_index,
            )
            return palette_offset

        except Exception as e:
            logger.warning("Failed to calculate palette offset: %s", e)
            return None

    def inject_mapping(
        self,
        ai_frame_id: str,
        rom_path: Path,
        output_path: Path | None = None,
        create_backup: bool = True,
        debug: bool = False,
        force_raw: bool = False,
        allow_fallback: bool = False,
        emit_project_changed: bool = True,
        preserve_sprite: bool = False,
    ) -> bool:
        """Inject a mapped frame into the ROM using tile-aware masking.

        Delegates to InjectionOrchestrator for the actual injection pipeline.

        Args:
            ai_frame_id: ID of the AI frame to inject (filename)
            rom_path: Path to the input ROM
            output_path: Path for the output ROM (default: same as input)
            create_backup: Whether to create a backup before injection
            debug: Enable debug mode (saves intermediate images to /tmp/inject_debug/)
            force_raw: Force RAW (uncompressed) injection for all tiles, skip HAL compression
            allow_fallback: If True, allow fallback to rom_offset filtering or all entries
                           when stored entry IDs are stale. If False (default), abort injection
                           and emit stale_entries_warning for user to decide.
            emit_project_changed: If True (default), emit project_changed after success.
                                 Set False for batch operations to emit once at the end.
            preserve_sprite: If True, original sprite remains visible where AI doesn't
                            cover it. If False (default), original sprite is completely
                            removed - only AI content remains.

        Returns:
            True if injection was successful
        """
        logger.info(
            "inject_mapping() called: ai_frame_id=%s, rom_path=%s",
            ai_frame_id,
            rom_path,
        )

        if self._project is None:
            logger.warning("inject_mapping: No project loaded")
            self.error_occurred.emit("No project loaded")
            return False

        # Calculate palette ROM offset for injection
        mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
        palette_rom_offset: int | None = None
        if mapping is not None:
            palette_rom_offset = self._calculate_palette_rom_offset(rom_path, mapping.game_frame_id)

        # Build injection request
        request = InjectionRequest(
            ai_frame_id=ai_frame_id,
            rom_path=rom_path,
            output_path=output_path,
            create_backup=create_backup,
            force_raw=force_raw,
            allow_fallback=allow_fallback,
            preserve_sprite=preserve_sprite,
            emit_project_changed=emit_project_changed,
            palette_rom_offset=palette_rom_offset,
        )

        # Progress callback wraps Qt signal
        def emit_progress(msg: str) -> None:
            self.status_update.emit(msg)

        # Execute via orchestrator with debug context
        with InjectionDebugContext.from_env() as debug_ctx:
            # Override with explicit debug flag if passed
            if debug and not debug_ctx.enabled:
                debug_ctx = InjectionDebugContext(enabled=True)
                debug_ctx.__enter__()
                try:
                    result = self._injection_orchestrator.execute(
                        request=request,
                        project=self._project,
                        debug_context=debug_ctx,
                        on_progress=emit_progress,
                    )
                finally:
                    debug_ctx.__exit__(None, None, None)
            else:
                result = self._injection_orchestrator.execute(
                    request=request,
                    project=self._project,
                    debug_context=debug_ctx,
                    on_progress=emit_progress,
                )

        # Handle stale entries warning
        if result.needs_fallback_confirmation and result.stale_frame_id:
            self.stale_entries_warning.emit(result.stale_frame_id)

        # Handle result
        if result.success:
            # Update mapping status
            mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
            if mapping is not None and result.new_mapping_status:
                mapping.status = result.new_mapping_status

            self.mapping_injected.emit(ai_frame_id, "\n".join(result.messages))

            # Emit project changed and save requested
            if emit_project_changed:
                self.project_changed.emit()
            self.save_requested.emit()

            return True
        else:
            # Emit error
            if result.error:
                self.error_occurred.emit(result.error)
            return False

    def inject_mapping_async(
        self,
        ai_frame_id: str,
        rom_path: Path,
        output_path: Path | None = None,
        create_backup: bool = True,
        debug: bool = False,
        force_raw: bool = False,
        allow_fallback: bool = False,
        preserve_sprite: bool = False,
    ) -> None:
        """Queue async injection of a mapped frame into the ROM.

        Non-blocking version of inject_mapping(). Uses background thread to avoid
        UI freeze during ROM I/O and image processing.

        Args:
            ai_frame_id: ID of the AI frame to inject (filename)
            rom_path: Path to the input ROM
            output_path: Path for the output ROM (default: same as input)
            create_backup: Whether to create a backup before injection
            debug: Enable debug mode (saves intermediate images to /tmp/inject_debug/)
            force_raw: Force RAW (uncompressed) injection for all tiles
            allow_fallback: Allow fallback to rom_offset filtering when entry IDs stale
            preserve_sprite: If True, original sprite remains visible where AI doesn't cover
        """
        if self._project is None:
            self.error_occurred.emit("No project loaded")
            return

        # Calculate palette ROM offset for injection
        mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
        palette_rom_offset: int | None = None
        if mapping is not None:
            palette_rom_offset = self._calculate_palette_rom_offset(rom_path, mapping.game_frame_id)

        # Build injection request
        request = InjectionRequest(
            ai_frame_id=ai_frame_id,
            rom_path=rom_path,
            output_path=output_path,
            create_backup=create_backup,
            force_raw=force_raw,
            allow_fallback=allow_fallback,
            preserve_sprite=preserve_sprite,
            emit_project_changed=True,
            palette_rom_offset=palette_rom_offset,
        )

        # Queue for async processing
        self._async_injection_service.queue_injection(
            ai_frame_id=ai_frame_id,
            injection_request=request,
            project=self._project,
            debug=debug,
        )

    def _on_async_injection_finished(self, ai_frame_id: str, success: bool, message: str, result: object) -> None:
        """Handle async injection completion.

        Updates mapping status and emits signals like the sync version.
        """
        from core.services.injection_results import InjectionResult

        if self._project is None:
            return

        if isinstance(result, InjectionResult):
            # Handle stale entries warning
            if result.needs_fallback_confirmation and result.stale_frame_id:
                self.stale_entries_warning.emit(result.stale_frame_id)

            if success:
                # Update mapping status
                mapping = self._project.get_mapping_for_ai_frame(ai_frame_id)
                if mapping is not None and result.new_mapping_status:
                    mapping.status = result.new_mapping_status

                self.mapping_injected.emit(ai_frame_id, "\n".join(result.messages))
                self.project_changed.emit()
                self.save_requested.emit()
            elif result.error:
                self.error_occurred.emit(result.error)

        # Emit the async_injection_finished signal
        self.async_injection_finished.emit(ai_frame_id, success, message)

    @property
    def async_injection_busy(self) -> bool:
        """Check if an async injection is currently in progress."""
        return self._async_injection_service.is_busy

    @property
    def async_injection_pending_count(self) -> int:
        """Get the number of pending async injections."""
        return self._async_injection_service.pending_count

    # ─── AI Frame Organization (V4) ───────────────────────────────────────────

    def rename_frame(self, frame_id: str, display_name: str | None) -> bool:
        """Set display name for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            display_name: New display name, or None to clear

        Returns:
            True if frame was found and renamed
        """
        if self._project is None:
            return False

        result = self._organization_service.rename_frame(
            project=self._project,
            undo_stack=self._undo_stack,
            controller=self,
            frame_id=frame_id,
            display_name=display_name,
        )
        if result:
            self.save_requested.emit()
        return result

    def _rename_frame_no_history(self, frame_id: str, display_name: str | None) -> bool:
        """Internal: Rename frame without undo history (for command execution)."""
        if self._project is None:
            return False
        return self._organization_service._rename_frame_no_history(
            project=self._project, frame_id=frame_id, display_name=display_name
        )

    def add_frame_tag(self, frame_id: str, tag: str) -> bool:
        """Add a tag to an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            tag: Tag to add (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag added
        """
        if self._project is None:
            return False
        return self._organization_service.add_frame_tag(project=self._project, frame_id=frame_id, tag=tag)

    def remove_frame_tag(self, frame_id: str, tag: str) -> bool:
        """Remove a tag from an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            tag: Tag to remove

        Returns:
            True if frame was found and tag removed
        """
        if self._project is None:
            return False
        return self._organization_service.remove_frame_tag(project=self._project, frame_id=frame_id, tag=tag)

    def toggle_frame_tag(self, frame_id: str, tag: str) -> bool:
        """Toggle a tag on an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            tag: Tag to toggle (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag toggled
        """
        if self._project is None:
            return False

        result = self._organization_service.toggle_frame_tag(
            project=self._project,
            undo_stack=self._undo_stack,
            controller=self,
            frame_id=frame_id,
            tag=tag,
        )
        if result:
            self.save_requested.emit()
        return result

    def _toggle_frame_tag_no_history(self, frame_id: str, tag: str) -> bool:
        """Internal: Toggle frame tag without undo history (for command execution)."""
        if self._project is None:
            return False
        return self._organization_service._toggle_frame_tag_no_history(
            project=self._project, frame_id=frame_id, tag=tag
        )

    def set_frame_tags(self, frame_id: str, tags: frozenset[str]) -> bool:
        """Set all tags for an AI frame (replace existing).

        Args:
            frame_id: ID of the AI frame (filename)
            tags: New set of tags

        Returns:
            True if frame was found and tags updated
        """
        if self._project is None:
            return False
        return self._organization_service.set_frame_tags(project=self._project, frame_id=frame_id, tags=tags)

    def get_frame_tags(self, frame_id: str) -> frozenset[str]:
        """Get tags for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)

        Returns:
            Set of tags (empty if frame not found)
        """
        if self._project is None:
            return frozenset()
        return self._organization_service.get_frame_tags(project=self._project, frame_id=frame_id)

    def get_frame_display_name(self, frame_id: str) -> str | None:
        """Get display name for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)

        Returns:
            Display name if set, None otherwise
        """
        if self._project is None:
            return None
        return self._organization_service.get_frame_display_name(project=self._project, frame_id=frame_id)

    def get_frames_with_tag(self, tag: str) -> list[AIFrame]:
        """Get all AI frames with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of AIFrame objects with the tag
        """
        if self._project is None:
            return []
        return self._organization_service.get_frames_with_tag(project=self._project, tag=tag)

    @staticmethod
    def get_available_tags() -> frozenset[str]:
        """Get the set of valid frame tags.

        Returns:
            Set of valid tag names
        """
        return OrganizationService.get_available_tags()

    # ─── Capture (GameFrame) Organization ──────────────────────────────────────

    def rename_capture(self, game_frame_id: str, new_name: str | None) -> bool:
        """Set display name for a game frame (capture).

        Args:
            game_frame_id: ID of the game frame to rename
            new_name: New display name (empty or None to clear)

        Returns:
            True if renamed successfully, False otherwise
        """
        if self._project is None:
            return False

        result = self._organization_service.rename_capture(
            project=self._project,
            undo_stack=self._undo_stack,
            controller=self,
            game_frame_id=game_frame_id,
            new_name=new_name,
        )
        if result:
            self.save_requested.emit()
        return result

    def _rename_capture_no_history(self, game_frame_id: str, display_name: str | None) -> bool:
        """Internal: Rename capture without undo history (for command execution)."""
        if self._project is None:
            return False
        return self._organization_service._rename_capture_no_history(
            project=self._project, game_frame_id=game_frame_id, display_name=display_name
        )

    def get_capture_display_name(self, game_frame_id: str) -> str | None:
        """Get display name for a game frame (capture).

        Args:
            game_frame_id: ID of the game frame

        Returns:
            Display name if set, None otherwise
        """
        if self._project is None:
            return None
        return self._organization_service.get_capture_display_name(project=self._project, game_frame_id=game_frame_id)
