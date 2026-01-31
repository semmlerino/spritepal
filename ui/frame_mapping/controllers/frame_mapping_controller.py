"""Controller for Frame Mapping workspace.

Handles business logic for loading frames, managing mappings, and coordinating
between the view panels.
"""

from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject

from core.frame_mapping_project import (
    AIFrame,
    FrameMappingProject,
    GameFrame,
    SheetPalette,
)
from core.mesen_integration.click_extractor import (
    CaptureResult,
    OAMEntry,
)
from core.repositories.capture_result_repository import CaptureResultRepository
from core.repositories.frame_mapping_repository import FrameMappingRepository
from core.services.injection_debug_context import InjectionDebugContext
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.injection_results import InjectionRequest
from core.services.palette_offset_calculator import PaletteOffsetCalculator
from ui.frame_mapping.facades.controller_context import ControllerContext
from ui.frame_mapping.facades.mappings_facade import MappingsFacade
from ui.frame_mapping.services.ai_frame_service import AIFrameService
from ui.frame_mapping.services.alignment_service import AlignmentService
from ui.frame_mapping.services.async_game_frame_preview_service import (
    AsyncGameFramePreviewService,
)
from ui.frame_mapping.services.async_injection_service import AsyncInjectionService
from ui.frame_mapping.services.capture_import_service import CaptureImportService
from ui.frame_mapping.services.mapping_service import MappingService
from ui.frame_mapping.services.organization_service import OrganizationService
from ui.frame_mapping.services.palette_service import PaletteService
from ui.frame_mapping.services.preview_service import PreviewService
from ui.frame_mapping.services.stale_entry_detector import AsyncStaleEntryDetector
from ui.frame_mapping.undo import (
    CommandContext,
    ReorderAIFrameCommand,
    UndoRedoStack,
)
from ui.frame_mapping.views.workbench_types import AlignmentState
from utils.logging_config import get_logger

logger = get_logger(__name__)


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

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        capture_repository: CaptureResultRepository | None = None,
        injection_orchestrator: InjectionOrchestrator | None = None,
        palette_offset_calculator: PaletteOffsetCalculator | None = None,
    ) -> None:
        super().__init__(parent)
        # Use list as mutable holder so context and controller share same reference
        self._project_holder: list[FrameMappingProject | None] = [None]
        # Shared capture repository for parsed capture file caching (thread-safe)
        # Both PreviewService and AsyncStaleEntryDetector use this to avoid duplicate parsing
        self._capture_repository = capture_repository or CaptureResultRepository()
        # Store injected dependencies or create defaults lazily
        self._injected_orchestrator = injection_orchestrator
        self._injected_palette_calculator = palette_offset_calculator
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
        # AI frame service for frame loading/management
        self._ai_frame_service = AIFrameService(parent=self)
        # Mapping service for mapping operations
        self._mapping_service = MappingService(parent=self)
        # Alignment service for alignment operations
        self._alignment_service = AlignmentService(parent=self)
        # Palette service for palette management (shares capture repository for caching)
        self._palette_service = PaletteService(parent=self, capture_repository=self._capture_repository)
        self._palette_service.sheet_palette_changed.connect(self.sheet_palette_changed)
        # BUG-2 FIX: Invalidate preview cache when palette changes (previews are palette-dependent)
        self._palette_service.sheet_palette_changed.connect(self._invalidate_previews_on_palette_change)
        # Organization service for frame/capture renaming and tagging
        self._organization_service = OrganizationService(parent=self)
        self._organization_service.frame_renamed.connect(self.frame_renamed)
        self._organization_service.frame_tags_changed.connect(self.frame_tags_changed)
        self._organization_service.capture_renamed.connect(self.capture_renamed)
        # Injection orchestrator for frame injection pipeline (sync)
        self._injection_orchestrator = self._injected_orchestrator or InjectionOrchestrator()
        # Async injection service (for non-blocking injections)
        self._async_injection_service = AsyncInjectionService(parent=self)
        self._async_injection_service.injection_started.connect(self.async_injection_started)
        self._async_injection_service.injection_progress.connect(self.async_injection_progress)
        self._async_injection_service.injection_finished.connect(self._on_async_injection_finished)
        # Async stale entry detector (avoids UI freeze during project load, uses shared repository)
        self._stale_entry_detector = AsyncStaleEntryDetector(parent=self, capture_repository=self._capture_repository)
        self._stale_entry_detector.stale_entries_detected.connect(self.stale_entries_on_load)
        # Capture import service (handles parsing and importing Mesen captures)
        self._capture_import_service = CaptureImportService(preview_service=self._preview_service, parent=self)
        self._capture_import_service.import_requested.connect(self._on_capture_import_requested)
        self._capture_import_service.import_completed.connect(self._on_capture_import_completed)
        self._capture_import_service.import_failed.connect(self.error_occurred)
        self._capture_import_service.directory_import_started.connect(self.directory_import_started)
        self._capture_import_service.directory_import_finished.connect(self.directory_import_finished)
        # Undo/Redo stack
        self._undo_stack = UndoRedoStack(parent=self)
        self._undo_stack.can_undo_changed.connect(self.can_undo_changed)
        self._undo_stack.can_redo_changed.connect(self.can_redo_changed)
        # Controller context for facades (shared state)
        # Pass the project holder so context and controller share same reference
        self._controller_context = ControllerContext(
            _project_holder=self._project_holder,
            undo_stack=self._undo_stack,
            capture_repository=self._capture_repository,
        )
        # Domain facades (thin wrappers grouping related methods)
        self._mappings = MappingsFacade(
            context=self._controller_context,
            signals=self,  # Controller implements MappingsSignals protocol
            mapping_service=self._mapping_service,
            alignment_service=self._alignment_service,
            get_command_context=self._get_command_context,
        )

    @property
    def _project(self) -> FrameMappingProject | None:
        """Internal project accessor via holder."""
        return self._project_holder[0]

    @_project.setter
    def _project(self, value: FrameMappingProject | None) -> None:
        """Internal project setter via holder."""
        self._project_holder[0] = value

    @property
    def project(self) -> FrameMappingProject | None:
        """Get the current project."""
        return self._project_holder[0]

    @project.setter
    def project(self, value: FrameMappingProject | None) -> None:
        """Set the current project (for testing - prefer new_project/load_project)."""
        self._project_holder[0] = value

    @property
    def has_project(self) -> bool:
        """Check if a project is loaded."""
        return self._project_holder[0] is not None

    @property
    def capture_repository(self) -> CaptureResultRepository:
        """Get the capture result repository (for test inspection)."""
        return self._capture_repository

    @property
    def injection_orchestrator(self) -> InjectionOrchestrator:
        """Get the injection orchestrator (for test inspection)."""
        return self._injection_orchestrator

    @property
    def palette_offset_calculator(self) -> PaletteOffsetCalculator | None:
        """Get the palette offset calculator (lazy-initialized from AppContext).

        Returns None if AppContext is not available (e.g., in tests without full setup).
        """
        if self._injected_palette_calculator is not None:
            return self._injected_palette_calculator
        # Lazy initialization from AppContext
        try:
            from core.app_context import get_app_context

            ctx = get_app_context()
            return PaletteOffsetCalculator(ctx.rom_extractor, ctx.sprite_config_loader)
        except RuntimeError:
            # AppContext not initialized (common in tests)
            return None

    # ─── Command Context (for undo commands) ───────────────────────────────────

    def _get_command_context(self) -> CommandContext:
        """Get command context for undo commands.

        Returns:
            CommandContext with services and signal emitter

        Raises:
            ValueError: If no project is loaded
        """
        if self._project is None:
            raise ValueError("No project loaded")
        return CommandContext(
            project=self._project,
            mapping_service=self._mapping_service,
            alignment_service=self._alignment_service,
            organization_service=self._organization_service,
            ai_frame_service=self._ai_frame_service,
            signal_emitter=self,
        )

    # CommandSignalEmitter protocol implementation
    def emit_mapping_created(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Emit mapping_created signal."""
        self.mapping_created.emit(ai_frame_id, game_frame_id)

    def emit_mapping_removed(self, ai_frame_id: str) -> None:
        """Emit mapping_removed signal."""
        self.mapping_removed.emit(ai_frame_id)

    def emit_alignment_updated(self, ai_frame_id: str) -> None:
        """Emit alignment_updated signal."""
        self.alignment_updated.emit(ai_frame_id)

    def emit_frame_renamed(self, frame_id: str) -> None:
        """Emit frame_renamed signal."""
        self.frame_renamed.emit(frame_id)

    def emit_frame_tags_changed(self, frame_id: str) -> None:
        """Emit frame_tags_changed signal."""
        self.frame_tags_changed.emit(frame_id)

    def emit_capture_renamed(self, game_frame_id: str) -> None:
        """Emit capture_renamed signal."""
        self.capture_renamed.emit(game_frame_id)

    def emit_ai_frame_moved(self, ai_frame_id: str, from_index: int, to_index: int) -> None:
        """Emit ai_frame_moved signal."""
        self.ai_frame_moved.emit(ai_frame_id, from_index, to_index)

    def emit_error(self, message: str) -> None:
        """Emit error_occurred signal."""
        self.error_occurred.emit(message)

    def emit_save_requested(self) -> None:
        """Emit save_requested signal."""
        self.save_requested.emit()

    def emit_project_changed(self) -> None:
        """Emit project_changed signal."""
        self.project_changed.emit()

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
        except (JSONDecodeError, KeyError, ValueError, AttributeError, TypeError) as e:
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

        # Delegate to service for frame creation
        frames, _orphan_count = self._ai_frame_service.load_frames_from_directory(
            self._project,
            directory,  # type: ignore[arg-type]
        )
        if not frames:
            self.error_occurred.emit(f"No PNG files found in {directory}")
            return 0

        # Replace AI frames using facade (handles index invalidation)
        self._project.replace_ai_frames(frames, directory)  # type: ignore[union-attr]

        # Clear undo history: old commands reference deleted frame IDs
        self.clear_undo_history()

        # Prune orphaned mappings that reference non-existent AI frame IDs
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

        # Delegate to service for frame creation
        frame = self._ai_frame_service.create_frame_from_file(
            self._project,
            file_path,  # type: ignore[arg-type]
        )

        if frame is None:
            # Frame already exists - just refresh UI
            existing_count = len(self._project.ai_frames) if self._project else 0
            self.ai_frames_loaded.emit(existing_count)
            return True

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

        # Update service with current frame IDs for uniqueness checking
        self._capture_import_service.update_existing_frame_ids(
            {gf.id for gf in self._project.game_frames} if self._project else set()
        )

        # Delegate to capture import service
        self._capture_import_service.import_mesen_capture(capture_path)

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

        # Update service with current frame IDs for uniqueness checking
        self._capture_import_service.update_existing_frame_ids({gf.id for gf in self._project.game_frames})

        # Delegate to capture import service
        frame = self._capture_import_service.complete_import(capture_path, capture_result, selected_entries)

        # If successful, add to project and emit signals
        if frame is not None:
            self._project.add_game_frame(frame)
            self.game_frame_added.emit(frame.id)
            self.project_changed.emit()
            self.save_requested.emit()

        return frame

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
        if self._project is None:
            self.new_project()

        # Update service with current frame IDs for uniqueness checking
        self._capture_import_service.update_existing_frame_ids(
            {gf.id for gf in self._project.game_frames} if self._project else set()
        )

        # Delegate to capture import service
        self._capture_import_service.import_directory(directory)

    def _on_capture_import_requested(self, capture_result: CaptureResult, capture_path: Path) -> None:
        """Handle capture import request from service.

        Relays to capture_import_requested signal for workspace.

        Args:
            capture_result: Parsed capture result
            capture_path: Path to the capture file
        """
        self.capture_import_requested.emit(capture_result, capture_path)

    def _on_capture_import_completed(self, frame_id: str) -> None:
        """Handle successful capture import from service.

        Args:
            frame_id: ID of the imported game frame
        """
        logger.debug("Capture import completed: %s", frame_id)

    def create_mapping(self, ai_frame_id: str, game_frame_id: str) -> bool:
        """Create a mapping between an AI frame and a game frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            game_frame_id: ID of the game frame

        Returns:
            True if mapping was created
        """
        return self._mappings.create_mapping(ai_frame_id, game_frame_id)

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
        return self._mappings.get_existing_link_for_game_frame(game_frame_id)

    def get_existing_link_for_ai_frame(self, ai_frame_id: str) -> str | None:
        """Get the game frame ID currently linked to an AI frame.

        Args:
            ai_frame_id: ID of the AI frame to check

        Returns:
            Game frame ID if AI frame is linked, None otherwise
        """
        return self._mappings.get_existing_link_for_ai_frame(ai_frame_id)

    def remove_mapping(self, ai_frame_id: str) -> bool:
        """Remove a mapping for an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)

        Returns:
            True if a mapping was removed
        """
        return self._mappings.remove_mapping(ai_frame_id)

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
        return self._mappings.update_alignment(
            ai_frame_id=ai_frame_id,
            offset_x=offset_x,
            offset_y=offset_y,
            flip_h=flip_h,
            flip_v=flip_v,
            scale=scale,
            sharpen=sharpen,
            resampling=resampling,
            set_edited=set_edited,
            drag_start_alignment=drag_start_alignment,
        )

    def _update_alignment_no_history(self, ai_frame_id: str, alignment: AlignmentState) -> bool:
        """Internal: Update alignment without undo history (for command execution)."""
        if self._project is None:
            return False
        return self._alignment_service.apply_alignment_to_project(
            self._project, ai_frame_id, alignment, set_edited=True
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
        return self._mappings.apply_transforms_to_all(
            offset_x=offset_x,
            offset_y=offset_y,
            scale=scale,
            exclude_ai_frame_id=exclude_ai_frame_id,
        )

    def get_game_frame_preview(self, frame_id: str) -> QPixmap | None:
        """Get the rendered preview pixmap for a game frame.

        Delegates to preview service for caching and rendering.

        Args:
            frame_id: Game frame ID

        Returns:
            QPixmap preview or None if not available
        """
        return self._preview_service.get_preview(frame_id, self._project)

    def get_cached_game_frame_preview(self, frame_id: str) -> QPixmap | None:
        """Get cached preview without triggering regeneration.

        Returns the cached preview only if it's available and valid.
        Does not block to regenerate - use this for non-blocking UI updates.
        Call request_game_frame_previews_async() for any cache misses.

        Args:
            frame_id: Game frame ID

        Returns:
            Cached QPixmap or None if not available/stale
        """
        return self._preview_service.get_cached_preview(frame_id, self._project)

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
        return self._ai_frame_service.get_frames(self._project)

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
        """Mark all previews as stale and trigger async regeneration.

        BUG-2 FIX: Game frame previews may use the sheet palette for rendering.
        When the palette changes, cached previews become stale and must be
        regenerated to reflect the new colors.

        PERF FIX (Issue 3): After marking stale, trigger async regeneration for
        all game frames so previews auto-update without user interaction.
        """
        logger.debug("Marking preview cache stale due to palette change")
        self._preview_service.mark_all_stale()

        # Trigger async regeneration for all game frames
        if self._project is not None:
            frame_ids = [gf.id for gf in self._project.game_frames]
            if frame_ids:
                logger.debug("Requesting async preview regeneration for %d frames", len(frame_ids))
                self._async_preview_service.request_previews(frame_ids, self._project)

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

        # Delegate to service for validation
        result = self._ai_frame_service.validate_reorder(self._project, ai_frame_id, new_index)
        if result is None:
            return False  # Invalid or no-op

        current_index, clamped_index = result

        # Create and execute command
        command = ReorderAIFrameCommand(
            ctx=self._get_command_context(),
            ai_frame_id=ai_frame_id,
            old_index=current_index,
            new_index=clamped_index,
        )
        self._undo_stack.push(command)
        # Emit signal for UI update (command emits in undo)
        self.ai_frame_moved.emit(ai_frame_id, current_index, clamped_index)
        return True

    def _reorder_ai_frame_no_history(self, ai_frame_id: str, new_index: int) -> bool:
        """Internal: Reorder AI frame without undo history (for command execution)."""
        if self._project is None:
            return False

        # Find current index before reordering
        old_index = self._ai_frame_service.find_frame_index(self._project, ai_frame_id)
        if old_index == -1:
            return False

        if self._project.reorder_ai_frame(ai_frame_id, new_index):
            # Emit with actual target index (may be clamped)
            actual_new_index = self._ai_frame_service.find_frame_index(self._project, ai_frame_id)
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

        game_frame = self._project.get_game_frame_by_id(game_frame_id)
        if game_frame is None:
            logger.debug("Cannot calculate palette offset: game_frame %s not found", game_frame_id)
            return None

        calculator = self.palette_offset_calculator
        if calculator is None:
            logger.debug("Cannot calculate palette offset: calculator not available (AppContext not initialized)")
            return None

        return calculator.calculate(rom_path, game_frame)

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
            ctx=self._get_command_context(),
            undo_stack=self._undo_stack,
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
            ctx=self._get_command_context(),
            undo_stack=self._undo_stack,
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
            ctx=self._get_command_context(),
            undo_stack=self._undo_stack,
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
