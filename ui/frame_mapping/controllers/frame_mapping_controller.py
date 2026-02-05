"""Controller for Frame Mapping workspace.

Handles business logic for loading frames, managing mappings, and coordinating
between the view panels.
"""

from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from core.exceptions import CaptureImportError
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
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.palette_offset_calculator import PaletteOffsetCalculator
from core.types import CompressionType
from ui.frame_mapping.facades.ai_frames_facade import AIFramesFacade
from ui.frame_mapping.facades.controller_context import ControllerContext
from ui.frame_mapping.facades.game_frames_facade import GameFramesFacade
from ui.frame_mapping.facades.injection_facade import InjectionFacade
from ui.frame_mapping.facades.palette_facade import PaletteFacade
from ui.frame_mapping.services.ai_frame_service import AIFrameService
from ui.frame_mapping.services.alignment_service import AlignmentService
from ui.frame_mapping.services.async_game_frame_preview_service import (
    AsyncGameFramePreviewService,
)
from ui.frame_mapping.services.async_injection_service import AsyncInjectionService
from ui.frame_mapping.services.capture_import_service import CaptureImportService
from ui.frame_mapping.services.mapping_service import MappingService
from ui.frame_mapping.services.organization_service import OrganizationService
from ui.frame_mapping.services.palette_service import GamePaletteInfo, PaletteService
from ui.frame_mapping.services.preview_service import PreviewService
from ui.frame_mapping.services.stale_entry_detector import AsyncStaleEntryDetector
from ui.frame_mapping.undo import (
    ApplyTransformsToAllCommand,
    CommandContext,
    CreateMappingCommand,
    RemoveMappingCommand,
    UndoRedoStack,
    UpdateAlignmentCommand,
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
        mapping_created: Emitted when a mapping is created (ai_frame_id, game_frame_id)
        mapping_removed: Emitted when a mapping is removed (ai_frame_id)
        alignment_updated: Emitted when mapping alignment changes (ai_frame_id)
        error_occurred: Emitted on errors (error_message)
    """

    project_changed = Signal()
    """Emitted when project is loaded, created, or has structural changes.

    Use this to refresh all UI sections after project operations like load, new, or undo/redo.

    Args:
        (none)

    Emitted by:
        - new_project()
        - load_project()
        - undo()
        - redo()

    Triggers:
        - FrameMappingWorkspace._on_project_changed() → refresh all views
    """

    ai_frames_loaded = Signal(int)
    """Emitted when AI frames are loaded from directory.

    Args:
        count: Number of AI frames loaded

    Emitted by:
        - AIFramesFacade.load_from_directory()

    Triggers:
        - FrameMappingWorkspace → updates AI frames pane
    """

    game_frame_added = Signal(str)
    """Emitted when a game frame (capture) is added to the project.

    Args:
        game_frame_id: ID of the newly added game frame

    Emitted by:
        - complete_capture_import() → after import completes
        - GameFramesFacade (internal)

    Triggers:
        - FrameMappingWorkspace → updates captures pane
    """

    game_frame_removed = Signal(str)
    """Emitted when a game frame is removed from the project.

    Args:
        game_frame_id: ID of the removed game frame

    Emitted by:
        - GameFramesFacade.remove() → after deletion

    Triggers:
        - FrameMappingWorkspace → updates captures pane and workspace
    """

    mapping_created = Signal(str, str)
    """Emitted when an AI frame is linked to a game frame.

    Args:
        ai_frame_id: ID of the AI frame being mapped
        game_frame_id: ID of the game frame being linked

    Emitted by:
        - FrameMappingController.create_mapping()
        - LinkFramesCommand.redo()

    Triggers:
        - FrameMappingWorkspace._on_mapping_created() → highlights mapping
    """

    mapping_removed = Signal(str, str)
    """Emitted when a mapping is removed or an AI frame is unlinked.

    Args:
        ai_frame_id: ID of the AI frame that was unmapped
        game_frame_id: ID of the game frame that was unlinked

    Emitted by:
        - FrameMappingController.remove_mapping()
        - RemoveMappingCommand.redo()

    Triggers:
        - FrameMappingWorkspace._on_mapping_removed() → updates workspace
    """

    mapping_injected = Signal(str, str)
    """Emitted when a mapping is successfully injected into the ROM.

    Args:
        ai_frame_id: ID of the AI frame that was injected
        message: Multi-line status message from injection pipeline

    Emitted by:
        - InjectionFacade.inject_mapping() → after successful injection
        - _on_async_injection_finished() → after async injection succeeds

    Triggers:
        - FrameMappingWorkspace → shows success notification
    """

    error_occurred = Signal(str)
    """Emitted when an error occurs in any operation.

    Used for displaying error messages to the user.

    Args:
        message: Human-readable error message

    Emitted by:
        - load_project() → on file read errors
        - save_project() → on write errors
        - Various service operations → on validation/processing errors

    Triggers:
        - FrameMappingWorkspace → displays error dialog
    """

    status_update = Signal(str)
    """Emitted for general status messages (non-error).

    Use for progress updates, confirmations, or informational feedback.

    Args:
        message: Status message to display

    Emitted by:
        - Various operations → progress updates

    Triggers:
        - FrameMappingWorkspace._on_status_update() → updates status bar
    """

    save_requested = Signal()
    """Emitted when the project should be auto-saved.

    Triggered after significant mutations (mapping changes, injection, etc.)
    to signal that the workspace should persist the project to disk.

    Args:
        (none)

    Emitted by:
        - complete_capture_import() → after adding game frame
        - undo() → after undoing changes
        - redo() → after redoing changes
        - InjectionFacade.inject_mapping() → after successful injection
        - _on_async_injection_finished() → after async injection succeeds

    Triggers:
        - FrameMappingWorkspace._on_save_requested() → saves project file
    """

    stale_entries_warning = Signal(str)
    """Emitted when stored OAM entry IDs are detected as stale.

    Stale entries occur when the ROM changes but capture metadata references
    old entry indices. This signal alerts the UI to warn the user or trigger
    fallback filtering logic.

    Args:
        frame_id: ID of the game frame with stale entries

    Emitted by:
        - PreviewService (via signal relay) → during preview generation
        - _on_async_injection_finished() → when injection detects staleness

    Triggers:
        - FrameMappingWorkspace → shows user confirmation dialog
    """

    stale_entries_on_load = Signal(list)
    """Emitted when project loads and stale entries are detected in game frames.

    This is emitted asynchronously after project load completes, allowing the
    UI to warn the user about potentially corrupted capture metadata without
    blocking the main thread.

    Args:
        stale_frame_ids: List of game frame IDs with stale entries

    Emitted by:
        - AsyncStaleEntryDetector.run() → after async detection completes

    Triggers:
        - FrameMappingWorkspace → shows batch stale entries warning
    """

    alignment_updated = Signal(str)
    """Emitted when mapping alignment changes (offset, flip, scale, sharpen).

    This is NOT emitted for structural changes (creation/deletion), only for
    transform updates to existing mappings.

    Args:
        ai_frame_id: ID of the AI frame whose alignment changed

    Emitted by:
        - MappingsFacade.update_alignment()
        - UpdateAlignmentCommand.redo()

    Triggers:
        - WorkbenchCanvas._on_alignment_updated() → redraws preview
        - MappingPanel → updates UI values
    """

    sheet_palette_changed = Signal()
    """Emitted when the sheet palette is set, modified, or cleared.

    The sheet palette is a 16-color palette used for rendering AI frame
    previews. Changes trigger cache invalidation and regeneration.

    Args:
        (none)

    Emitted by:
        - PaletteService (via signal relay) → after palette operation

    Triggers:
        - FrameMappingController → invalidates preview cache
        - Workspace → refreshes palette display
    """

    frame_renamed = Signal(str)
    """Emitted when an AI frame's display name changes.

    Part of frame organization support (V4).

    Args:
        ai_frame_id: ID of the AI frame that was renamed

    Emitted by:
        - OrganizationService (via signal relay) → after rename operation

    Triggers:
        - AIFramesPane → updates frame list display
    """

    frame_tags_changed = Signal(str)
    """Emitted when an AI frame's tags are added, removed, or modified.

    Part of frame organization support (V4). Tags allow grouping/filtering of frames.

    Args:
        ai_frame_id: ID of the AI frame whose tags changed

    Emitted by:
        - OrganizationService (via signal relay) → after tag operation

    Triggers:
        - AIFramesPane → updates frame tags display
    """

    ai_frame_moved = Signal(str, int, int)
    """Emitted when an AI frame is reordered in the list.

    Args:
        ai_frame_id: ID of the AI frame that moved
        from_index: Original position (0-based)
        to_index: New position (0-based)

    Emitted by:
        - AIFramesFacade.reorder()
        - ReorderAIFrameCommand.redo()

    Triggers:
        - AIFramesPane → updates frame list order
    """

    ai_frame_added = Signal(str)
    """Emitted when a single AI frame is added to the project.

    Distinct from ai_frames_loaded, which is emitted for batch directory loads.
    This is used for incremental additions.

    Args:
        ai_frame_id: ID of the newly added AI frame

    Emitted by:
        - AIFramesFacade.add_from_file()

    Triggers:
        - AIFramesPane → appends frame to list
    """

    ai_frame_removed = Signal(str)
    """Emitted when an AI frame is removed from the project.

    Args:
        ai_frame_id: ID of the removed AI frame

    Emitted by:
        - AIFramesFacade.remove() → after deletion

    Triggers:
        - FrameMappingWorkspace → updates mapping panel
    """

    ai_frames_removed_batch = Signal(list)
    """Emitted when multiple AI frames are removed from the project.

    Args:
        ai_frame_ids: List of IDs of the removed AI frames

    Emitted by:
        - AIFramesFacade.remove_batch() → after deletion

    Triggers:
        - FrameMappingWorkspace → updates mapping panel (efficiently)
    """

    capture_renamed = Signal(str)
    """Emitted when a game frame's (capture's) display name changes.

    Part of capture organization support.

    Args:
        game_frame_id: ID of the game frame that was renamed

    Emitted by:
        - OrganizationService (via signal relay) → after rename operation

    Triggers:
        - CapturesLibraryPane → updates capture name display
    """

    capture_import_requested = Signal(object, object)
    """Emitted when a capture file is parsed and awaits user sprite selection.

    The workspace shows a sprite selection dialog and calls
    complete_capture_import() with the user's selection.

    Args:
        capture_result: CaptureResult object with parsed sprite data
        capture_path: Path object pointing to the capture JSON file

    Emitted by:
        - CaptureImportService (via signal relay) → after parsing completes

    Triggers:
        - FrameMappingWorkspace._on_capture_import_requested() → shows dialog
    """

    directory_import_started = Signal(int)
    """Emitted when batch capture directory import begins.

    Signals the start of background parsing for a directory of captures.
    Used to show progress UI to the user.

    Args:
        total_files: Number of files to parse in the directory

    Emitted by:
        - CaptureImportService (via signal relay) → when parsing starts

    Triggers:
        - FrameMappingWorkspace → shows progress indicator
    """

    directory_import_finished = Signal(int)
    """Emitted when batch capture directory import completes.

    Signals the end of background parsing for a directory of captures.
    Used to hide progress UI and refresh the captures pane.

    Args:
        parsed_count: Number of captures successfully parsed

    Emitted by:
        - CaptureImportService (via signal relay) → when parsing completes

    Triggers:
        - FrameMappingWorkspace → hides progress indicator, refreshes pane
    """

    can_undo_changed = Signal(bool)
    """Emitted when the undo stack state changes.

    Indicates whether undo is available, used to enable/disable UI buttons.

    Args:
        can_undo: True if undo is available

    Emitted by:
        - UndoRedoStack → whenever undo state changes

    Triggers:
        - FrameMappingWorkspace → enables/disables undo button
    """

    can_redo_changed = Signal(bool)
    """Emitted when the redo stack state changes.

    Indicates whether redo is available, used to enable/disable UI buttons.

    Args:
        can_redo: True if redo is available

    Emitted by:
        - UndoRedoStack → whenever redo state changes

    Triggers:
        - FrameMappingWorkspace → enables/disables redo button
    """

    game_frame_preview_ready = Signal(str, QPixmap)
    """Emitted when an async-generated game frame preview is ready.

    Part of batch async preview generation. Each preview completion
    triggers this signal.

    Args:
        frame_id: ID of the game frame
        pixmap: QPixmap of the rendered preview

    Emitted by:
        - AsyncGameFramePreviewService (via signal relay) → for each completed preview

    Triggers:
        - WorkbenchCanvas → updates frame display
        - CapturesLibraryPane → updates thumbnail
    """

    async_injection_started = Signal(str)
    """Emitted when an async injection operation begins.

    Signals the start of a background injection. Multiple injections
    can be queued and processed sequentially.

    Args:
        ai_frame_id: ID of the AI frame being injected

    Emitted by:
        - AsyncInjectionService (via signal relay) → when injection starts

    Triggers:
        - Workspace → shows progress indicator
    """

    async_injection_progress = Signal(str, str)
    """Emitted to report progress during an async injection.

    Allows UI to show detailed progress updates during long-running injections.

    Args:
        ai_frame_id: ID of the AI frame being injected
        message: Progress message or status update

    Emitted by:
        - AsyncInjectionService (via signal relay) → during injection processing

    Triggers:
        - Workspace → updates progress message display
    """

    async_injection_finished = Signal(str, bool, str)
    """Emitted when an async injection operation completes.

    Signals successful or failed completion of an injection. The workspace
    uses this to update the mapping status and show results to the user.

    Args:
        ai_frame_id: ID of the AI frame that was injected
        success: True if injection succeeded, False otherwise
        message: Human-readable status message

    Emitted by:
        - _on_async_injection_finished() → after service completes

    Triggers:
        - Workspace → hides progress indicator, shows result notification
    """

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
        self._preview_service.stale_entries_warning.connect(self.stale_entries_warning)
        # Async game frame preview service (for batch async preview generation)
        self._async_preview_service = AsyncGameFramePreviewService(
            parent=self, capture_repository=self._capture_repository
        )
        self._async_preview_service.preview_ready.connect(self._on_async_preview_ready)
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
        self._capture_import_service = CaptureImportService(
            preview_service=self._preview_service,
            capture_repository=self._capture_repository,
            parent=self,
        )
        self._capture_import_service.import_requested.connect(self._on_capture_import_requested)
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
        self._ai_frames = AIFramesFacade(
            context=self._controller_context,
            signals=self,  # Controller implements AIFramesSignals protocol
            ai_frame_service=self._ai_frame_service,
            organization_service=self._organization_service,
            undo_stack=self._undo_stack,
            get_command_context=self._get_command_context,
        )
        self._game_frames = GameFramesFacade(
            context=self._controller_context,
            signals=self,  # Controller implements GameFramesSignals protocol
            preview_service=self._preview_service,
            organization_service=self._organization_service,
            undo_stack=self._undo_stack,
            get_command_context=self._get_command_context,
        )
        self._palette = PaletteFacade(
            context=self._controller_context,
            signals=self,  # Controller implements PaletteSignals protocol
            palette_service=self._palette_service,
        )
        self._injection = InjectionFacade(
            context=self._controller_context,
            signals=self,  # Controller implements InjectionSignals protocol
            injection_orchestrator=self._injection_orchestrator,
            async_injection_service=self._async_injection_service,
            palette_offset_calculator_getter=lambda: self.palette_offset_calculator,
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

    def emit_mapping_removed(self, ai_frame_id: str, game_frame_id: str) -> None:
        """Emit mapping_removed signal."""
        self.mapping_removed.emit(ai_frame_id, game_frame_id)

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

    def emit_ai_frames_loaded(self, count: int) -> None:
        """Emit ai_frames_loaded signal."""
        self.ai_frames_loaded.emit(count)

    def emit_ai_frame_added(self, frame_id: str) -> None:
        """Emit ai_frame_added signal."""
        self.ai_frame_added.emit(frame_id)

    def emit_ai_frame_removed(self, frame_id: str) -> None:
        """Emit ai_frame_removed signal."""
        self.ai_frame_removed.emit(frame_id)

    def emit_ai_frames_removed_batch(self, frame_ids: list[str]) -> None:
        """Emit ai_frames_removed_batch signal."""
        self.ai_frames_removed_batch.emit(frame_ids)

    def emit_game_frame_removed(self, frame_id: str) -> None:
        """Emit game_frame_removed signal."""
        self.game_frame_removed.emit(frame_id)

    def emit_error(self, message: str) -> None:
        """Emit error_occurred signal."""
        self.error_occurred.emit(message)

    def emit_save_requested(self) -> None:
        """Emit save_requested signal."""
        self.save_requested.emit()

    def emit_project_changed(self) -> None:
        """Emit project_changed signal."""
        self.project_changed.emit()

    def emit_status_update(self, message: str) -> None:
        """Emit status_update signal."""
        self.status_update.emit(message)

    def emit_stale_entries_warning(self, frame_id: str) -> None:
        """Emit stale_entries_warning signal."""
        self.stale_entries_warning.emit(frame_id)

    def emit_mapping_injected(self, ai_frame_id: str, message: str) -> None:
        """Emit mapping_injected signal."""
        self.mapping_injected.emit(ai_frame_id, message)

    # ─── Undo/Redo Public API ──────────────────────────────────────────────────

    def undo(self) -> str | None:
        """Undo the last command.

        Returns:
            Description of the undone command, or None if nothing to undo.
            Returns None without undoing if async injection is in progress.
        """
        if self.async_injection_busy:
            logger.warning("Undo blocked: injection in progress")
            self.status_update.emit("Cannot undo while injection is in progress")
            return None

        desc = self._undo_stack.undo()
        if desc:
            logger.info("Undo: %s", desc)
            self.project_changed.emit()
            self.save_requested.emit()
        return desc

    def redo(self) -> str | None:
        """Redo the last undone command.

        Returns:
            Description of the redone command, or None if nothing to redo.
            Returns None without redoing if async injection is in progress.
        """
        if self.async_injection_busy:
            logger.warning("Redo blocked: injection in progress")
            self.status_update.emit("Cannot redo while injection is in progress")
            return None

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
        return self._ai_frames.load_from_directory(directory, clear_undo=self.clear_undo_history)

    def add_ai_frame_from_file(self, file_path: Path) -> bool:
        """Add a single AI frame from a PNG file.

        Args:
            file_path: Path to the PNG file

        Returns:
            True if frame was added successfully
        """
        if self._project is None:
            self.new_project()
        return self._ai_frames.add_from_file(file_path)

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
        try:
            self._capture_import_service.import_mesen_capture(capture_path)
        except CaptureImportError:
            # Service already emits error signal, so we just swallow the exception
            # to prevent it from propagating to the UI/caller
            pass

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

    def create_mapping(self, ai_frame_id: str, game_frame_id: str) -> bool:
        """Create a mapping between an AI frame and a game frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            game_frame_id: ID of the game frame

        Returns:
            True if mapping was created
        """
        project = self._project
        if project is None:
            self.error_occurred.emit("No project loaded")
            return False

        # Validate both frames exist
        is_valid, error_msg = self._mapping_service.validate_mapping_frames(project, ai_frame_id, game_frame_id)
        if not is_valid:
            self.error_occurred.emit(error_msg)
            return False

        # Capture previous state for undo
        (
            prev_ai_game_id,
            prev_game_ai_id,
            prev_ai_alignment,
            prev_game_alignment,
        ) = self._mapping_service.capture_create_mapping_undo_state(project, ai_frame_id, game_frame_id)

        # Capture status for undo restoration
        prev_ai_status = (
            prev_ai_mapping.status if (prev_ai_mapping := project.get_mapping_for_ai_frame(ai_frame_id)) else None
        )
        prev_game_status = (
            prev_game_mapping.status
            if (prev_game_mapping := project.get_mapping_for_game_frame(game_frame_id))
            else None
        )

        # Create and execute command via undo stack
        command = CreateMappingCommand(
            ctx=self._get_command_context(),
            ai_frame_id=ai_frame_id,
            game_frame_id=game_frame_id,
            prev_ai_mapping_game_id=prev_ai_game_id,
            prev_game_mapping_ai_id=prev_game_ai_id,
            prev_ai_mapping_alignment=prev_ai_alignment,
            prev_game_mapping_alignment=prev_game_alignment,
            prev_ai_mapping_status=prev_ai_status,
            prev_game_mapping_status=prev_game_status,
        )
        self._undo_stack.push(command)

        self.mapping_created.emit(ai_frame_id, game_frame_id)
        self.save_requested.emit()
        logger.info("Created mapping: AI frame %s -> Game frame %s", ai_frame_id, game_frame_id)
        return True

    def get_existing_link_for_game_frame(self, game_frame_id: str) -> str | None:
        """Get the AI frame ID currently linked to a game frame.

        Args:
            game_frame_id: ID of the game frame to check

        Returns:
            AI frame ID if game frame is linked, None otherwise
        """
        project = self._project
        if project is None:
            return None
        return self._mapping_service.get_link_for_game_frame(project, game_frame_id)

    def get_existing_link_for_ai_frame(self, ai_frame_id: str) -> str | None:
        """Get the game frame ID currently linked to an AI frame.

        Args:
            ai_frame_id: ID of the AI frame to check

        Returns:
            Game frame ID if AI frame is linked, None otherwise
        """
        project = self._project
        if project is None:
            return None
        return self._mapping_service.get_link_for_ai_frame(project, ai_frame_id)

    def remove_mapping(self, ai_frame_id: str) -> bool:
        """Remove a mapping for an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)

        Returns:
            True if a mapping was removed
        """
        project = self._project
        if project is None:
            return False

        # Capture state for undo
        undo_state = self._mapping_service.capture_remove_mapping_undo_state(project, ai_frame_id)
        if undo_state is None:
            return False

        removed_game_id, removed_alignment, removed_status = undo_state

        # Create and execute command via undo stack
        command = RemoveMappingCommand(
            ctx=self._get_command_context(),
            ai_frame_id=ai_frame_id,
            removed_game_frame_id=removed_game_id,
            removed_alignment=removed_alignment,
            removed_status=removed_status,
        )
        self._undo_stack.push(command)

        self.mapping_removed.emit(ai_frame_id, removed_game_id)
        self.save_requested.emit()
        logger.info("Removed mapping for AI frame %s", ai_frame_id)
        return True

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
        project = self._project
        if project is None:
            return False

        new_alignment = AlignmentState(
            offset_x=offset_x,
            offset_y=offset_y,
            flip_h=flip_h,
            flip_v=flip_v,
            scale=scale,
            sharpen=sharpen,
            resampling=resampling,
        )

        # Only record undo for explicit user edits, not auto-centering
        if set_edited:
            # Capture state for undo
            undo_state = self._alignment_service.capture_alignment_undo_state(
                project, ai_frame_id, drag_start_alignment
            )
            if undo_state is None:
                return False

            old_alignment, old_status = undo_state

            # Create and execute command via undo stack
            command = UpdateAlignmentCommand(
                ctx=self._get_command_context(),
                ai_frame_id=ai_frame_id,
                new_alignment=new_alignment,
                old_alignment=old_alignment,
                old_status=old_status,
            )
            self._undo_stack.push(command)
        else:
            # Auto-centering - update directly without history
            self._alignment_service.apply_alignment_to_project(project, ai_frame_id, new_alignment, set_edited=False)

        # Use targeted signal to avoid full UI refresh (which blanks canvas)
        self.alignment_updated.emit(ai_frame_id)
        self.save_requested.emit()
        logger.info(
            "Updated alignment for AI frame %s: offset=(%d, %d), flip=(%s, %s), "
            "scale=%.2f, sharpen=%.1f, resampling=%s",
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
        project = self._project
        if project is None:
            return 0

        # Count affected mappings for return value
        affected = sum(1 for m in project.mappings if m.ai_frame_id != exclude_ai_frame_id)
        if affected == 0:
            return 0

        command = ApplyTransformsToAllCommand(
            ctx=self._get_command_context(),
            offset_x=offset_x,
            offset_y=offset_y,
            scale=scale,
            exclude_ai_frame_id=exclude_ai_frame_id,
        )
        self._undo_stack.push(command)

        self.project_changed.emit()
        self.save_requested.emit()

        return affected

    def get_cached_game_frame_preview(self, frame_id: str) -> QPixmap | None:
        """Get cached preview without triggering regeneration.

        Returns the cached preview only if it's available and valid.
        Does not block to regenerate - use this for non-blocking UI updates.
        Call request_game_frame_previews_async() for any cache misses.

        Args:
            frame_id: Game frame ID.

        Returns:
            Cached QPixmap or None if not available/stale.
        """
        return self._preview_service.get_cached_preview(frame_id, self._project)

    def get_capture_result_for_game_frame(self, frame_id: str) -> tuple[CaptureResult | None, bool]:
        """Get the CaptureResult for a game frame.

        Delegates to preview service for capture parsing and filtering.

        Args:
            frame_id: Game frame ID.

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
            frame_ids: List of game frame IDs to generate previews for.
        """
        if self._project is None:
            return
        self._async_preview_service.request_previews(frame_ids, self._project)

    def _on_async_preview_ready(self, frame_id: str, pixmap: QPixmap) -> None:
        """Handle async preview completion.

        Updates the preview cache and emits signal to UI.
        """
        # Update preview cache so get_cached_game_frame_preview() returns this
        if self._project is not None:
            game_frame = self._project.get_game_frame_by_id(frame_id)
            if game_frame is not None:
                mtime = 0.0
                if game_frame.capture_path and game_frame.capture_path.exists():
                    mtime = game_frame.capture_path.stat().st_mtime
                entry_ids = tuple(game_frame.selected_entry_ids)
                self._preview_service.set_preview_cache(frame_id, pixmap, mtime, entry_ids)

        self.game_frame_preview_ready.emit(frame_id, pixmap)

    def get_ai_frames(self) -> list[AIFrame]:
        """Get all AI frames from the current project."""
        return self._ai_frames.get_frames()

    def get_game_frames(self) -> list[GameFrame]:
        """Get all game frames from the current project."""
        return self._game_frames.get_frames()

    # --- Sheet Palette Methods ---

    def get_sheet_palette(self) -> SheetPalette | None:
        """Get the current sheet palette.

        Returns:
            SheetPalette if defined, None otherwise.
        """
        return self._palette.get_sheet_palette()

    def set_sheet_palette(self, palette: SheetPalette | None) -> None:
        """Set the sheet palette for the project.

        Args:
            palette: SheetPalette to set, or None to clear.
        """
        self._palette.set_sheet_palette(palette)

    def set_sheet_palette_color(self, index: int, rgb: tuple[int, int, int]) -> None:
        """Update a single color in the sheet palette.

        Args:
            index: Palette index (0-15).
            rgb: New RGB color tuple.
        """
        self._palette.set_sheet_palette_color(index, rgb)

    def _invalidate_previews_on_palette_change(self) -> None:
        """Mark all previews as stale for lazy regeneration.

        BUG-2 FIX: Game frame previews may use the sheet palette for rendering.
        When the palette changes, cached previews become stale and must be
        regenerated to reflect the new colors.

        PERF: We only mark previews as stale here. Actual regeneration happens
        lazily when previews are accessed (e.g., when MappingPanel requests them).
        This avoids regenerating ALL previews when the user might only view a few.
        """
        logger.debug("Marking preview cache stale due to palette change")
        self._preview_service.mark_all_stale()

    def extract_sheet_colors(self) -> dict[tuple[int, int, int], int]:
        """Extract unique colors from all AI frames in the project.

        Returns:
            Dict mapping RGB tuples to pixel counts.
        """
        return self._palette.extract_sheet_colors()

    def generate_sheet_palette_from_colors(
        self,
        colors: dict[tuple[int, int, int], int] | None = None,
    ) -> SheetPalette:
        """Generate a 16-color palette from AI sheet colors.

        Args:
            colors: Color counts to use, or None to extract from AI frames.

        Returns:
            Generated SheetPalette with auto-mapped colors.
        """
        return self._palette.generate_sheet_palette_from_colors(colors)

    def copy_game_palette_to_sheet(self, game_frame_id: str) -> SheetPalette | None:
        """Create a SheetPalette from a game frame's palette.

        Args:
            game_frame_id: ID of game frame to copy palette from.

        Returns:
            SheetPalette with the game frame's colors, or None if not found.
        """
        return self._palette.copy_game_palette_to_sheet(game_frame_id)

    def get_game_palettes(self) -> dict[str, GamePaletteInfo]:
        """Get palettes from all game frames with display info.

        Returns:
            Dict mapping game frame IDs to GamePaletteInfo (colors + display name).
        """
        return self._palette.get_game_palettes()

    def remove_game_frame(self, frame_id: str) -> bool:
        """Remove a game frame from the project.

        Also removes any associated mapping and clears the preview cache.

        Args:
            frame_id: ID of the game frame to remove.

        Returns:
            True if the frame was found and removed.
        """
        return self._game_frames.remove(frame_id)

    def remove_ai_frame(self, frame_id: str) -> bool:
        """Remove an AI frame from the project.

        Also removes any associated mapping.

        Args:
            frame_id: ID of the AI frame to remove.

        Returns:
            True if the frame was found and removed.
        """
        return self._ai_frames.remove(frame_id)

    def remove_ai_frames(self, frame_ids: list[str]) -> list[str]:
        """Remove multiple AI frames from the project.

        Also removes any associated mappings.

        Args:
            frame_ids: List of AI frame IDs to remove.

        Returns:
            List of IDs that were successfully removed.
        """
        return self._ai_frames.remove_batch(frame_ids)

    def reorder_ai_frame(self, ai_frame_id: str, new_index: int) -> bool:
        """Reorder an AI frame to a new position (undoable).

        Args:
            ai_frame_id: ID of the AI frame to move.
            new_index: Target position (0-based).

        Returns:
            True if the frame was moved.
        """
        return self._ai_frames.reorder(ai_frame_id, new_index)

    def update_game_frame_compression(self, frame_id: str, compression_type: CompressionType) -> bool:
        """Update compression type for a game frame.

        Updates the compression type for all ROM offsets in the game frame.
        By design, compression is a single setting per game frame, not per offset.

        Args:
            frame_id: ID of the game frame.
            compression_type: New compression type (CompressionType enum).

        Returns:
            True if the update was successful.
        """
        return self._game_frames.update_compression(frame_id, compression_type)

    def create_injection_copy(self, rom_path: Path) -> Path | None:
        """Create a numbered copy of the ROM for injection (public API).

        Use this to pre-create a copy for batch injection operations.

        Args:
            rom_path: Path to the source ROM.

        Returns:
            Path to the created copy, or None if creation failed.
        """
        return self._injection.create_injection_copy(rom_path)

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
            ai_frame_id: ID of the AI frame to inject (filename).
            rom_path: Path to the input ROM.
            output_path: Path for the output ROM (default: same as input).
            create_backup: Whether to create a backup before injection.
            debug: Enable debug mode.
            force_raw: Force RAW (uncompressed) injection for all tiles.
            allow_fallback: Allow fallback to rom_offset filtering.
            emit_project_changed: If True, emit project_changed after success.
            preserve_sprite: If True, original sprite remains visible.

        Returns:
            True if injection was successful.
        """
        return self._injection.inject_mapping(
            ai_frame_id=ai_frame_id,
            rom_path=rom_path,
            output_path=output_path,
            create_backup=create_backup,
            debug=debug,
            force_raw=force_raw,
            allow_fallback=allow_fallback,
            emit_project_changed=emit_project_changed,
            preserve_sprite=preserve_sprite,
        )

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
            ai_frame_id: ID of the AI frame to inject (filename).
            rom_path: Path to the input ROM.
            output_path: Path for the output ROM (default: same as input).
            create_backup: Whether to create a backup before injection.
            debug: Enable debug mode.
            force_raw: Force RAW (uncompressed) injection for all tiles.
            allow_fallback: Allow fallback to rom_offset filtering.
            preserve_sprite: If True, original sprite remains visible.
        """
        self._injection.inject_mapping_async(
            ai_frame_id=ai_frame_id,
            rom_path=rom_path,
            output_path=output_path,
            create_backup=create_backup,
            debug=debug,
            force_raw=force_raw,
            allow_fallback=allow_fallback,
            preserve_sprite=preserve_sprite,
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
                self.save_requested.emit()
            elif result.error:
                self.error_occurred.emit(result.error)

        # Emit the async_injection_finished signal
        self.async_injection_finished.emit(ai_frame_id, success, message)

    @property
    def async_injection_busy(self) -> bool:
        """Check if an async injection is currently in progress."""
        return self._injection.async_injection_busy()

    @property
    def async_injection_pending_count(self) -> int:
        """Get the number of pending async injections."""
        return self._injection.async_injection_pending_count()

    # ─── AI Frame Organization (V4) ───────────────────────────────────────────

    def rename_frame(self, frame_id: str, display_name: str | None) -> bool:
        """Set display name for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            display_name: New display name, or None to clear

        Returns:
            True if frame was found and renamed
        """
        return self._ai_frames.rename_frame(frame_id, display_name)

    def toggle_frame_tag(self, frame_id: str, tag: str) -> bool:
        """Toggle a tag on an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)
            tag: Tag to toggle (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag toggled
        """
        return self._ai_frames.toggle_tag(frame_id, tag)

    def get_frame_tags(self, frame_id: str) -> frozenset[str]:
        """Get tags for an AI frame.

        Args:
            frame_id: ID of the AI frame (filename)

        Returns:
            Set of tags (empty if frame not found)
        """
        return self._ai_frames.get_tags(frame_id)

    @staticmethod
    def get_available_tags() -> frozenset[str]:
        """Get the set of valid frame tags.

        Returns:
            Set of valid tag names
        """
        return AIFramesFacade.get_available_tags()

    # ─── Capture (GameFrame) Organization ──────────────────────────────────────

    def rename_capture(self, game_frame_id: str, new_name: str | None) -> bool:
        """Set display name for a game frame (capture).

        Args:
            game_frame_id: ID of the game frame to rename.
            new_name: New display name (empty or None to clear).

        Returns:
            True if renamed successfully.
        """
        return self._game_frames.rename_capture(game_frame_id, new_name)
