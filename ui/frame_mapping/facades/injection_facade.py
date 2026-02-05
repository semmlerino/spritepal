"""Facade for injection operations.

Groups injection-related controller methods: create_copy, inject, inject_async.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from core.services.injection_debug_utils import managed_debug_context
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.injection_results import InjectionRequest
from ui.frame_mapping.services.async_injection_service import AsyncInjectionService
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.services.palette_offset_calculator import PaletteOffsetCalculator
    from ui.frame_mapping.facades.controller_context import ControllerContext

logger = get_logger(__name__)


class InjectionSignals(Protocol):
    """Protocol for injection-related signal emissions."""

    def emit_status_update(self, message: str) -> None: ...
    def emit_stale_entries_warning(self, frame_id: str) -> None: ...
    def emit_mapping_injected(self, ai_frame_id: str, message: str) -> None: ...
    def emit_error(self, message: str) -> None: ...
    def emit_project_changed(self) -> None: ...
    def emit_save_requested(self) -> None: ...


class InjectionFacade:
    """Facade for injection operations.

    Handles ROM injection pipeline for mapped frames.
    """

    def __init__(
        self,
        context: ControllerContext,
        signals: InjectionSignals,
        injection_orchestrator: InjectionOrchestrator,
        async_injection_service: AsyncInjectionService,
        palette_offset_calculator_getter: Callable[[], PaletteOffsetCalculator | None],
    ) -> None:
        """Initialize the injection facade.

        Args:
            context: Shared controller context for project access.
            signals: Signal emitter for UI updates.
            injection_orchestrator: Orchestrator for sync injection pipeline.
            async_injection_service: Service for async injection.
            palette_offset_calculator_getter: Callable to get palette calculator (lazy init).
        """
        self._context = context
        self._signals = signals
        self._injection_orchestrator = injection_orchestrator
        self._async_injection_service = async_injection_service
        self._get_palette_calculator = palette_offset_calculator_getter

    # ─── ROM Copy ─────────────────────────────────────────────────────────────

    def create_injection_copy(self, rom_path: Path) -> Path | None:
        """Create a numbered copy of the ROM for injection (public API).

        Use this to pre-create a copy for batch injection operations.

        Args:
            rom_path: Path to the source ROM.

        Returns:
            Path to the created copy, or None if creation failed.
        """
        from core.services.rom_staging_manager import ROMStagingManager

        staging_manager = ROMStagingManager()
        return staging_manager.create_injection_copy(rom_path, None)

    # ─── Sync Injection ───────────────────────────────────────────────────────

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
            debug: Enable debug mode (saves intermediate images to /tmp/inject_debug/).
            force_raw: Force RAW (uncompressed) injection for all tiles.
            allow_fallback: If True, allow fallback to rom_offset filtering.
            emit_project_changed: If True, emit project_changed after success.
            preserve_sprite: If True, original sprite remains visible where AI doesn't cover.

        Returns:
            True if injection was successful.
        """
        logger.info(
            "inject_mapping() called: ai_frame_id=%s, rom_path=%s",
            ai_frame_id,
            rom_path,
        )

        project = self._context.project
        if project is None:
            logger.warning("inject_mapping: No project loaded")
            self._signals.emit_error("No project loaded")
            return False

        # Calculate palette ROM offset for injection
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
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

        # Progress callback wraps signal emission
        def emit_progress(msg: str) -> None:
            self._signals.emit_status_update(msg)

        # Execute via orchestrator with debug context
        with managed_debug_context(explicit_debug=debug) as debug_ctx:
            result = self._injection_orchestrator.execute(
                request=request,
                project=project,
                debug_context=debug_ctx,
                on_progress=emit_progress,
            )

        # Handle stale entries warning
        if result.needs_fallback_confirmation and result.stale_frame_id:
            self._signals.emit_stale_entries_warning(result.stale_frame_id)

        # Handle result
        if result.success:
            # Update mapping status
            mapping = project.get_mapping_for_ai_frame(ai_frame_id)
            if mapping is not None and result.new_mapping_status:
                mapping.status = result.new_mapping_status

            self._signals.emit_mapping_injected(ai_frame_id, "\n".join(result.messages))

            # Emit project changed and save requested
            if emit_project_changed:
                self._signals.emit_project_changed()
            self._signals.emit_save_requested()

            return True
        else:
            # Emit error
            if result.error:
                self._signals.emit_error(result.error)
            return False

    # ─── Async Injection ──────────────────────────────────────────────────────

    def inject_mapping_async(
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
            emit_project_changed: If True, emit project_changed after success.
            preserve_sprite: If True, original sprite remains visible.
        """
        project = self._context.project
        if project is None:
            self._signals.emit_error("No project loaded")
            return

        # Calculate palette ROM offset for injection
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
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

        # Queue for async processing
        self._async_injection_service.queue_injection(
            ai_frame_id=ai_frame_id,
            injection_request=request,
            project=project,
            debug=debug,
        )

    # ─── Async Status ─────────────────────────────────────────────────────────

    def async_injection_busy(self) -> bool:
        """Check if async injection is currently running."""
        return self._async_injection_service.is_busy

    def async_injection_pending_count(self) -> int:
        """Get the number of pending async injections."""
        return self._async_injection_service.pending_count

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _calculate_palette_rom_offset(self, rom_path: Path, game_frame_id: str) -> int | None:
        """Calculate the palette ROM offset for injection.

        First checks for character-specific palette offsets,
        then falls back to the generic palette calculation.

        Args:
            rom_path: Path to the ROM file.
            game_frame_id: ID of the game frame.

        Returns:
            Palette ROM offset, or None if not available.
        """
        project = self._context.project
        if project is None:
            return None

        game_frame = project.get_game_frame_by_id(game_frame_id)
        if game_frame is None:
            logger.debug("Cannot calculate palette offset: game_frame %s not found", game_frame_id)
            return None

        calculator = self._get_palette_calculator()
        if calculator is None:
            logger.debug("Cannot calculate palette offset: calculator not available")
            return None

        return calculator.calculate(rom_path, game_frame)
