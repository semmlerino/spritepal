"""Injection orchestrator for frame mapping injection pipeline.

Coordinates the full injection pipeline in a UI-independent way:
- Validates mapping and frames
- Prepares images with compositing
- Verifies ROM attribution
- Groups and injects tiles
- Manages ROM staging

This service returns results instead of emitting signals, enabling
batch/CLI operations without Qt dependencies.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
from PIL import Image

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult, MesenCaptureParser
from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    snap_to_snes_color,
    snes_palette_to_rgb,
)
from core.rom_injector import ROMInjector
from core.services.compression_strategies import get_compression_strategy
from core.services.injection_debug_context import InjectionDebugContext
from core.services.injection_results import (
    InjectionRequest,
    InjectionResult,
    TileInjectionResult,
)
from core.services.quantization_strategies import select_quantization_strategy
from core.services.rgb_to_indexed import load_image_preserving_indices
from core.services.rom_staging_manager import ROMStagingManager
from core.services.rom_verification_service import ROMVerificationService
from core.services.sprite_compositor import SpriteCompositor, TransformParams
from core.types import CompressionType
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame, SheetPalette
    from core.mesen_integration.click_extractor import OAMEntry
    from core.services.injection_snapshot import InjectionSnapshot

logger = get_logger(__name__)


class InjectionOrchestrator:
    """Coordinates full injection pipeline, UI-independent.

    Handles the complete frame injection workflow:
    1. Validate mapping data
    2. Load and composite images
    3. Verify ROM tile attribution
    4. Group tiles by ROM offset
    5. Extract, quantize, and inject each group
    6. Manage staging for atomic writes

    Does NOT:
    - Emit Qt signals (uses progress callback)
    - Modify project state (returns new status)
    - Hold mutable Qt objects

    Usage:
        orchestrator = InjectionOrchestrator(
            staging_manager=ROMStagingManager(),
            rom_injector=ROMInjector(),
        )

        with InjectionDebugContext.from_env() as debug_ctx:
            result = orchestrator.execute(
                request=InjectionRequest(...),
                project=project,
                debug_context=debug_ctx,
                on_progress=lambda msg: print(msg),
            )

        if result.success:
            mapping.status = result.new_mapping_status
    """

    def __init__(
        self,
        staging_manager: ROMStagingManager | None = None,
        rom_injector: ROMInjector | None = None,
    ) -> None:
        """Initialize orchestrator with dependencies.

        Args:
            staging_manager: ROM staging manager. Created if not provided.
            rom_injector: ROM injector. Created if not provided.
        """
        self._staging_manager = staging_manager or ROMStagingManager()
        self._rom_injector = rom_injector or ROMInjector()

    def execute(
        self,
        request: InjectionRequest,
        project: FrameMappingProject,
        debug_context: InjectionDebugContext | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> InjectionResult:
        """Execute injection pipeline.

        Args:
            request: Immutable injection parameters.
            project: Project with frames and mappings.
            debug_context: Optional debug mode context.
            on_progress: Optional callback for progress updates.

        Returns:
            InjectionResult with success/failure and details.
        """
        debug = debug_context or InjectionDebugContext(enabled=False)

        def progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        logger.info(
            "InjectionOrchestrator.execute: ai_frame_id=%s, rom_path=%s",
            request.ai_frame_id,
            request.rom_path,
        )

        # 1. Retrieve and validate mapping
        validation_result = self._validate_mapping(request, project)
        if validation_result is not None:
            return validation_result

        mapping = project.get_mapping_for_ai_frame(request.ai_frame_id)
        ai_frame = project.get_ai_frame_by_id(request.ai_frame_id)
        game_frame = project.get_game_frame_by_id(mapping.game_frame_id)  # type: ignore[union-attr]

        # Type narrowing - validation ensures these are not None
        assert mapping is not None
        assert ai_frame is not None
        assert game_frame is not None

        logger.info(
            "Injection: AI frame '%s' -> Game frame '%s' (offsets: %s)",
            ai_frame.path.name,
            game_frame.id,
            [f"0x{o:X}" for o in game_frame.rom_offsets],
        )

        # Apply debug force_raw
        force_raw = request.force_raw or debug.force_raw

        debug.log_canvas_info(
            ai_frame_name=ai_frame.path.name,
            ai_frame_index=ai_frame.index,  # Use actual index from frame
            game_frame_id=game_frame.id,
            rom_offsets=list(game_frame.rom_offsets),
            canvas_width=0,  # Will be updated after compositing
            canvas_height=0,
            offset_x=mapping.offset_x,
            offset_y=mapping.offset_y,
            flip_h=mapping.flip_h,
            flip_v=mapping.flip_v,
            scale=mapping.scale,
        )

        # 2. Load and prepare images
        try:
            composite_data = self._prepare_images(
                ai_frame,
                game_frame,
                mapping,
                request,
                debug,
                sheet_palette=project.sheet_palette,
            )
            if isinstance(composite_data, InjectionResult):
                return composite_data

            # BUG-1 FIX: Unpack index_map for index-preserving injection
            masked_canvas, filtered_capture, relevant_entries, transformed_index_map = composite_data

        except Exception as e:
            logger.exception("Failed to prepare masked image")
            return InjectionResult.failure(f"Image preparation failed: {e}")

        # 3. Execute with staging
        return self._execute_with_staging(
            request=request,
            sheet_palette=project.sheet_palette,
            ai_frame=ai_frame,
            game_frame=game_frame,
            mapping=mapping,
            masked_canvas=masked_canvas,
            filtered_capture=filtered_capture,
            relevant_entries=relevant_entries,
            transformed_index_map=transformed_index_map,
            force_raw=force_raw,
            debug=debug,
            on_progress=progress,
            project=project,
        )

    def execute_from_snapshot(
        self,
        request: InjectionRequest,
        snapshot: InjectionSnapshot,
        debug_context: InjectionDebugContext | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> InjectionResult:
        """Execute injection using immutable snapshot data.

        This method is used by the async injection path to avoid reading
        mutable project state from the worker thread. The snapshot captures
        all necessary data at queue time.

        Args:
            request: Immutable injection parameters.
            snapshot: Immutable snapshot of project data captured at queue time.
            debug_context: Optional debug mode context.
            on_progress: Optional callback for progress updates.

        Returns:
            InjectionResult with success/failure and details.
        """
        from core.frame_mapping_project import AIFrame, FrameMapping, GameFrame
        from core.services.injection_snapshot import PaletteSnapshot

        debug = debug_context or InjectionDebugContext(enabled=False)

        def progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        logger.info(
            "InjectionOrchestrator.execute_from_snapshot: ai_frame_id=%s, rom_path=%s",
            request.ai_frame_id,
            request.rom_path,
        )

        # Reconstruct objects from snapshot
        mapping = FrameMapping(
            ai_frame_id=snapshot.ai_frame.id,
            game_frame_id=snapshot.game_frame.id,
            offset_x=snapshot.mapping.offset_x,
            offset_y=snapshot.mapping.offset_y,
            flip_h=snapshot.mapping.flip_h,
            flip_v=snapshot.mapping.flip_v,
            scale=snapshot.mapping.scale,
            sharpen=snapshot.mapping.sharpen,
            resampling=snapshot.mapping.resampling,
        )

        ai_frame = AIFrame(
            path=snapshot.ai_frame.path,
            index=snapshot.ai_frame.index,
        )

        game_frame = GameFrame(
            id=snapshot.game_frame.id,
            rom_offsets=list(snapshot.game_frame.rom_offsets),
            capture_path=snapshot.game_frame.capture_path,
            palette_index=snapshot.game_frame.palette_index,
            selected_entry_ids=list(snapshot.game_frame.selected_entry_ids),
            compression_types=dict(snapshot.game_frame.compression_types),
            width=snapshot.game_frame.width,
            height=snapshot.game_frame.height,
        )

        class _PaletteHolder:
            """Wrapper mimicking project's sheet_palette attribute."""

            def __init__(self, palette_snapshot: PaletteSnapshot | None) -> None:
                if palette_snapshot is not None:

                    class _Palette:
                        """Minimal palette holder mimicking SheetPalette interface."""

                        def __init__(
                            self,
                            colors: list[tuple[int, int, int]],
                            color_mappings: dict[tuple[int, int, int], int],
                            background_color: tuple[int, int, int] | None,
                            background_tolerance: int,
                            alpha_threshold: int,
                            dither_mode: str,
                            dither_strength: float,
                        ) -> None:
                            self.colors = colors
                            self.color_mappings = color_mappings
                            self.background_color = background_color
                            self.background_tolerance = background_tolerance
                            self.alpha_threshold = alpha_threshold
                            self.dither_mode = dither_mode
                            self.dither_strength = dither_strength

                    self.sheet_palette: _Palette | None = _Palette(
                        colors=list(palette_snapshot.colors),
                        color_mappings=dict(palette_snapshot.color_mappings),
                        background_color=palette_snapshot.background_color,
                        background_tolerance=palette_snapshot.background_tolerance,
                        alpha_threshold=palette_snapshot.alpha_threshold,
                        dither_mode=palette_snapshot.dither_mode,
                        dither_strength=palette_snapshot.dither_strength,
                    )
                else:
                    self.sheet_palette = None

        palette_holder = _PaletteHolder(snapshot.palette)

        # Validation (snapshot guarantees most data is present, but check files)
        if not ai_frame.path.exists():
            logger.warning("AI frame file not found: %s", ai_frame.path)
            return InjectionResult.failure(f"AI frame file not found: {ai_frame.path}")

        if not request.rom_path.exists():
            logger.warning("ROM file not found: %s", request.rom_path)
            return InjectionResult.failure(f"ROM file not found: {request.rom_path}")

        if not game_frame.capture_path or not game_frame.capture_path.exists():
            logger.warning("Capture file missing: %s", game_frame.capture_path)
            return InjectionResult.failure(f"Capture file missing (required for masking): {game_frame.capture_path}")

        if not game_frame.rom_offsets:
            logger.warning("Game frame %s has no ROM offsets", game_frame.id)
            return InjectionResult.failure(f"Game frame {game_frame.id} has no ROM offsets associated")

        logger.info(
            "Injection from snapshot: AI frame '%s' -> Game frame '%s' (offsets: %s)",
            ai_frame.path.name,
            game_frame.id,
            [f"0x{o:X}" for o in game_frame.rom_offsets],
        )

        # Apply debug force_raw
        force_raw = request.force_raw or debug.force_raw

        debug.log_canvas_info(
            ai_frame_name=ai_frame.path.name,
            ai_frame_index=ai_frame.index,
            game_frame_id=game_frame.id,
            rom_offsets=list(game_frame.rom_offsets),
            canvas_width=0,
            canvas_height=0,
            offset_x=mapping.offset_x,
            offset_y=mapping.offset_y,
            flip_h=mapping.flip_h,
            flip_v=mapping.flip_v,
            scale=mapping.scale,
        )

        # Prepare images
        try:
            composite_data = self._prepare_images(
                ai_frame,
                game_frame,
                mapping,
                request,
                debug,
                sheet_palette=palette_holder.sheet_palette,  # type: ignore[arg-type]
            )
            if isinstance(composite_data, InjectionResult):
                return composite_data

            masked_canvas, filtered_capture, relevant_entries, transformed_index_map = composite_data

        except Exception as e:
            logger.exception("Failed to prepare masked image")
            return InjectionResult.failure(f"Image preparation failed: {e}")

        # Execute with staging
        return self._execute_with_staging(
            request=request,
            sheet_palette=palette_holder.sheet_palette,
            ai_frame=ai_frame,
            game_frame=game_frame,
            mapping=mapping,
            masked_canvas=masked_canvas,
            filtered_capture=filtered_capture,
            relevant_entries=relevant_entries,
            transformed_index_map=transformed_index_map,
            force_raw=force_raw,
            debug=debug,
            on_progress=progress,
            project=palette_holder,
        )

    def _execute_with_staging(
        self,
        request: InjectionRequest,
        sheet_palette: object | None,
        ai_frame: AIFrame,
        game_frame: GameFrame,
        mapping: FrameMapping,
        masked_canvas: Image.Image,
        filtered_capture: CaptureResult,
        relevant_entries: list[OAMEntry],
        transformed_index_map: np.ndarray | None,
        force_raw: bool,
        debug: InjectionDebugContext,
        on_progress: Callable[[str], None],
        project: object,  # FrameMappingProject or _PaletteHolder
    ) -> InjectionResult:
        """Execute injection with ROM staging and palette injection.

        This method handles:
        1. ROM staging setup (check existing output, create copy, create staging session)
        2. Call _execute_injection with all the necessary parameters
        3. On success: commit, inject palette, return success result
        4. On failure: cleanup and return failure

        Args:
            request: Immutable injection parameters.
            sheet_palette: Project's sheet palette or None.
            ai_frame: AI frame for injection.
            game_frame: Game frame for injection.
            mapping: Frame mapping data.
            masked_canvas: Composited RGBA canvas.
            filtered_capture: Filtered capture result.
            relevant_entries: OAM entries to inject.
            transformed_index_map: Optional palette index map from compositing.
            force_raw: Whether to force RAW compression.
            debug: Debug context.
            on_progress: Progress callback.
            project: Object with sheet_palette attribute (FrameMappingProject or _PaletteHolder).

        Returns:
            InjectionResult with success/failure and details.
        """
        # Set up ROM staging
        using_existing_output = request.output_path is not None and request.output_path.exists()

        if using_existing_output and request.output_path is not None:
            injection_rom_path = request.output_path
            logger.info("Using existing output ROM: %s", injection_rom_path)
        else:
            injection_rom_path = self._staging_manager.create_injection_copy(request.rom_path, request.output_path)
            if injection_rom_path is None:
                return InjectionResult.failure("Failed to create ROM copy for injection")
            logger.info("Created injection ROM copy: %s", injection_rom_path)

        session = self._staging_manager.create_staging(injection_rom_path)
        if session is None:
            if not using_existing_output:
                injection_rom_path.unlink(missing_ok=True)
            return InjectionResult.failure("Failed to create staging file for injection")

        # Execute injection with staging
        try:
            result = self._execute_injection(
                request=request,
                project=project,  # type: ignore[arg-type]
                ai_frame=ai_frame,
                game_frame=game_frame,
                mapping=mapping,
                masked_canvas=masked_canvas,
                filtered_capture=filtered_capture,
                relevant_entries=relevant_entries,
                injection_rom_path=injection_rom_path,
                staging_path=session.staging_path,
                using_existing_output=using_existing_output,
                force_raw=force_raw,
                debug=debug,
                on_progress=on_progress,
                transformed_index_map=transformed_index_map,
            )

            if result.success:
                # Commit staging
                if not self._staging_manager.commit(session):
                    self._staging_manager.rollback(session)
                    return InjectionResult.failure("Failed to commit staged injection to ROM")

                # Inject palette if offset provided
                messages = list(result.messages)
                if request.palette_rom_offset is not None and sheet_palette is not None:
                    palette_colors = [snap_to_snes_color(c) for c in sheet_palette.colors]  # type: ignore[attr-defined]
                    success, msg = self._rom_injector.inject_palette_to_rom(
                        rom_path=str(injection_rom_path),
                        output_path=str(injection_rom_path),
                        palette_offset=request.palette_rom_offset,
                        colors=palette_colors,
                        create_backup=False,  # Already have backup from tile injection
                        ignore_checksum=True,  # Checksum updated by tile injection
                    )
                    if success:
                        messages.append(f"Palette injected at 0x{request.palette_rom_offset:X}")
                        logger.info("Palette injected at 0x%X", request.palette_rom_offset)
                    else:
                        logger.warning("Palette injection failed: %s", msg)
                        messages.append(f"WARNING: Palette injection failed: {msg}")

                return InjectionResult(
                    success=True,
                    tile_results=result.tile_results,
                    output_rom_path=injection_rom_path,
                    messages=tuple(messages),
                    new_mapping_status="injected",
                )
            else:
                self._staging_manager.cleanup_on_failure(session, injection_rom_path, using_existing_output)
                return result

        except Exception as e:
            logger.exception("Injection process failed")
            self._staging_manager.cleanup_on_failure(session, injection_rom_path, using_existing_output)
            return InjectionResult.failure(f"Injection process failed: {e}")

    def _validate_mapping(
        self,
        request: InjectionRequest,
        project: FrameMappingProject,
    ) -> InjectionResult | None:
        """Validate mapping and frames exist.

        Returns InjectionResult on failure, None if valid.
        """
        mapping = project.get_mapping_for_ai_frame(request.ai_frame_id)
        if mapping is None:
            logger.warning("AI frame %s is not mapped", request.ai_frame_id)
            return InjectionResult.failure(f"AI frame {request.ai_frame_id} is not mapped")

        ai_frame = project.get_ai_frame_by_id(request.ai_frame_id)
        game_frame = project.get_game_frame_by_id(mapping.game_frame_id)

        if ai_frame is None or game_frame is None:
            logger.warning("Invalid mapping - missing frame reference")
            return InjectionResult.failure("Invalid mapping: missing frame reference")

        if not game_frame.rom_offsets:
            logger.warning("Game frame %s has no ROM offsets", game_frame.id)
            return InjectionResult.failure(f"Game frame {game_frame.id} has no ROM offsets associated")

        if not ai_frame.path.exists():
            logger.warning("AI frame file not found: %s", ai_frame.path)
            return InjectionResult.failure(f"AI frame file not found: {ai_frame.path}")

        if not request.rom_path.exists():
            logger.warning("ROM file not found: %s", request.rom_path)
            return InjectionResult.failure(f"ROM file not found: {request.rom_path}")

        if not game_frame.capture_path or not game_frame.capture_path.exists():
            logger.warning("Capture file missing: %s", game_frame.capture_path)
            return InjectionResult.failure(f"Capture file missing (required for masking): {game_frame.capture_path}")

        return None

    def _prepare_images(
        self,
        ai_frame: AIFrame,
        game_frame: GameFrame,
        mapping: FrameMapping,
        request: InjectionRequest,
        debug: InjectionDebugContext,
        sheet_palette: SheetPalette | None = None,
    ) -> tuple[Image.Image, CaptureResult, list[OAMEntry], np.ndarray | None] | InjectionResult:
        """Load and composite images for injection.

        Returns (masked_canvas, filtered_capture, relevant_entries, ai_index_map) on success,
        or InjectionResult on failure.

        BUG-1 FIX: Also returns ai_index_map (palette indices) if the AI frame is an
        indexed PNG, enabling index-preserving injection that avoids re-quantization.
        """
        # Load AI image, preserving palette indices if indexed PNG
        ai_index_map, ai_img = load_image_preserving_indices(
            ai_frame.path,
            sheet_palette=sheet_palette,
        )
        if ai_index_map is not None:
            logger.debug(
                "Loaded indexed PNG with preserved indices: %s (shape: %s)",
                ai_frame.path.name,
                ai_index_map.shape,
            )

        # Apply background removal if configured in sheet palette
        if sheet_palette is not None and sheet_palette.background_color is not None:
            from core.services.content_bounds_analyzer import remove_background

            ai_img = remove_background(
                ai_img,
                sheet_palette.background_color,
                sheet_palette.background_tolerance,
            )

        # Pre-quantize RGBA images at full resolution to preserve color mappings
        # This fixes the "muddy colors" issue caused by LANCZOS scaling before quantization
        # The compositor will then scale the index map with NEAREST, preserving exact indices
        if ai_index_map is None and sheet_palette is not None:
            from core.palette_utils import quantize_with_mappings, snap_to_snes_color

            # Get alpha threshold and dither settings from sheet_palette
            alpha_threshold = getattr(sheet_palette, "alpha_threshold", 128)
            dither_mode = getattr(sheet_palette, "dither_mode", "none")
            dither_strength = float(getattr(sheet_palette, "dither_strength", 0.0))

            # Snap palette to SNES precision
            palette_rgb = [snap_to_snes_color(c) for c in sheet_palette.colors]

            # Quantize at full resolution
            quantized_indexed = quantize_with_mappings(
                ai_img,
                palette_rgb,
                sheet_palette.color_mappings or {},
                transparency_threshold=alpha_threshold,
                dither_mode=dither_mode,
                dither_strength=dither_strength,
            )

            # Extract index map from quantized image
            import numpy as np

            ai_index_map = np.array(quantized_indexed, dtype=np.uint8)
            logger.debug(
                "Pre-quantized RGBA image at full resolution: %s (shape: %s)",
                ai_frame.path.name,
                ai_index_map.shape,
            )

        # Parse capture for tile layout
        # Note: capture_path is validated in _validate_mapping before this is called
        assert game_frame.capture_path is not None
        parser = MesenCaptureParser()
        capture_result = parser.parse_file(game_frame.capture_path)

        # Use shared filtering utility
        from core.mesen_integration.entry_filtering import (
            create_filtered_capture,
            filter_capture_entries,
        )

        filtering = filter_capture_entries(
            capture_result,
            selected_entry_ids=list(game_frame.selected_entry_ids),
            rom_offsets=game_frame.rom_offsets,
            allow_rom_offset_fallback=request.allow_fallback,
            allow_all_entries_fallback=request.allow_fallback,
            context_label=game_frame.id,
        )

        # Handle stale entries error (when allow_fallback=False)
        if filtering.is_stale and not filtering.has_entries and not request.allow_fallback:
            return InjectionResult.stale_entries(
                frame_id=game_frame.id,
                error=(
                    f"Entry selection for '{game_frame.id}' is outdated. Reimport the capture or enable fallback mode."
                ),
            )

        # Handle no entries found error
        if not filtering.has_entries:
            if not request.allow_fallback:
                return InjectionResult.stale_entries(
                    frame_id=game_frame.id,
                    error=(
                        f"No valid entries found for '{game_frame.id}'. "
                        "The capture file may have changed. Reimport the capture."
                    ),
                )
            # This shouldn't happen since allow_all_entries_fallback=True would use all entries
            logger.warning("No entries match for frame %s (unexpected)", game_frame.id)
            relevant_entries = list(capture_result.entries)
        else:
            relevant_entries = filtering.entries

        if filtering.used_fallback:
            if filtering.used_all_entries:
                logger.info("Using all entries fallback (allow_fallback=True)")
            else:
                logger.info("Using rom_offset fallback (allow_fallback=True)")

        # Create filtered capture for compositing
        filtered_capture = create_filtered_capture(capture_result, relevant_entries)

        # Composite using SpriteCompositor
        uncovered_policy: Literal["transparent", "original"] = "original" if request.preserve_sprite else "transparent"
        logger.info(
            "Compositing with preserve_sprite=%s, uncovered_policy=%s",
            request.preserve_sprite,
            uncovered_policy,
        )
        compositor = SpriteCompositor(uncovered_policy=uncovered_policy)
        transform = TransformParams(
            offset_x=mapping.offset_x,
            offset_y=mapping.offset_y,
            flip_h=mapping.flip_h,
            flip_v=mapping.flip_v,
            scale=mapping.scale,
        )

        composite_result = compositor.composite_frame(
            ai_image=ai_img,
            capture_result=filtered_capture,
            transform=transform,
            quantize=False,
            ai_index_map=ai_index_map,
        )

        masked_canvas = composite_result.composited_image
        transformed_index_map = composite_result.index_map

        # Debug: Save intermediate images
        if debug.enabled and debug.debug_dir:
            renderer = CaptureRenderer(filtered_capture)
            original_sprite_img = renderer.render_selection()
            debug.save_debug_image("original_sprite_mask", original_sprite_img)
            debug.save_debug_image("masked_canvas", masked_canvas)

        return masked_canvas, filtered_capture, relevant_entries, transformed_index_map

    def _execute_injection(
        self,
        request: InjectionRequest,
        project: FrameMappingProject,
        ai_frame: AIFrame,
        game_frame: GameFrame,
        mapping: FrameMapping,
        masked_canvas: Image.Image,
        filtered_capture: CaptureResult,
        relevant_entries: list[OAMEntry],
        injection_rom_path: Path,
        staging_path: Path,
        using_existing_output: bool,
        force_raw: bool,
        debug: InjectionDebugContext,
        on_progress: Callable[[str], None],
        transformed_index_map: np.ndarray | None = None,  # BUG-1 FIX
    ) -> InjectionResult:
        """Execute tile injection for all ROM offsets."""
        on_progress("Verifying ROM tile attribution...")

        # Verify ROM attribution
        verifier = ROMVerificationService(request.rom_path)
        include_missing = not request.preserve_sprite
        verification = verifier.verify_offsets(
            filtered_capture,
            game_frame.selected_entry_ids,
            include_missing=include_missing,
        )

        if verification.has_corrections:
            on_progress(
                f"ROM attribution: {verification.matched_hal + verification.matched_raw - verification.total + len([o for o, n in verification.corrections.items() if o != n and n is not None])} stale offsets corrected, {verification.not_found} not found"
            )

        if not verification.all_found and verification.not_found == verification.total:
            on_progress(f"ERROR: 0/{verification.total} tiles found in ROM")
            return InjectionResult.failure(
                "Could not find any tiles in ROM. The sprite data may use an "
                "unknown compression format or the ROM may be modified."
            )

        if verification.all_found and not verification.has_corrections and verification.total > 0:
            on_progress(f"ROM attribution verified: {verification.total} tiles matched")
        if (
            include_missing
            and verification.missing_total > 0
            and verification.missing_filled < verification.missing_total
        ):
            missing_unmatched = verification.missing_total - verification.missing_filled
            on_progress(
                f"WARNING: {missing_unmatched}/{verification.missing_total} tile offsets could not be matched; "
                "original sprite data may remain"
            )

        # Apply corrections
        for old_offset, new_offset in verification.corrections.items():
            if new_offset is not None and new_offset != old_offset:
                debug.log_offset_correction(old_offset, new_offset)

        verifier.apply_corrections(relevant_entries, verification.corrections)

        # Group tiles by ROM offset
        tile_groups = self._group_tiles_by_offset(relevant_entries, filtered_capture, debug)

        # Read ROM data for slot detection
        rom_data = request.rom_path.read_bytes()

        # Process each tile group
        messages: list[str] = []
        tile_results: list[TileInjectionResult] = []
        success = False
        first_tile_group = True
        current_rom_path = str(staging_path)

        bbox = filtered_capture.bounding_box

        for rom_offset, vram_tiles in tile_groups.items():
            result = self._inject_tile_group(
                rom_offset=rom_offset,
                vram_tiles=vram_tiles,
                masked_canvas=masked_canvas,
                filtered_capture=filtered_capture,
                bbox=bbox,
                project=project,
                game_frame=game_frame,
                rom_data=rom_data,
                force_raw=force_raw,
                current_rom_path=current_rom_path,
                source_rom_path=str(request.rom_path),
                create_backup=request.create_backup and first_tile_group,
                preserve_existing=using_existing_output or not first_tile_group,
                debug=debug,
                transformed_index_map=transformed_index_map,  # BUG-1 FIX
            )

            tile_results.append(result)

            if result.success:
                messages.append(result.message)
                first_tile_group = False
                success = True
            else:
                messages.append(result.message)
                success = False
                break

        debug.log_injection_results(messages)

        if success:
            return InjectionResult(
                success=True,
                tile_results=tuple(tile_results),
                messages=tuple(messages),
            )
        else:
            return InjectionResult(
                success=False,
                tile_results=tuple(tile_results),
                messages=tuple(messages),
                error=f"Injection failed:\n{chr(10).join(messages)}",
            )

    def _group_tiles_by_offset(
        self,
        entries: list[OAMEntry],
        capture: CaptureResult,
        debug: InjectionDebugContext,
    ) -> dict[int, dict[int, tuple[int, int, int, int | None, bool, bool]]]:
        """Group tiles by their ROM offset.

        Returns dict: rom_offset -> {vram_addr -> (screen_x, screen_y, palette, tile_idx, flip_h, flip_v)}
        """
        tile_groups: dict[int, dict[int, tuple[int, int, int, int | None, bool, bool]]] = {}
        bbox = capture.bounding_box

        debug.log_bounding_box(bbox.x, bbox.y, bbox.width, bbox.height)
        debug.log_entry_count(len(entries))

        for entry in entries:
            for tile in entry.tiles:
                if tile.rom_offset is None:
                    continue

                # Calculate tile's screen position
                local_x = tile.pos_x * 8
                local_y = tile.pos_y * 8

                if entry.flip_h:
                    local_x = entry.width - local_x - 8
                if entry.flip_v:
                    local_y = entry.height - local_y - 8

                screen_x = entry.x + local_x
                screen_y = entry.y + local_y

                debug.log_tile_details(
                    rom_offset=tile.rom_offset,
                    entry_id=entry.id,
                    tile_pos=(tile.pos_x, tile.pos_y),
                    local_pos=(local_x, local_y),
                    screen_pos=(screen_x, screen_y),
                    flip_h=entry.flip_h,
                    vram_addr=tile.vram_addr,
                )

                if tile.rom_offset not in tile_groups:
                    tile_groups[tile.rom_offset] = {}

                if tile.vram_addr not in tile_groups[tile.rom_offset]:
                    tile_groups[tile.rom_offset][tile.vram_addr] = (
                        screen_x,
                        screen_y,
                        entry.palette,
                        tile.tile_index_in_block,
                        entry.flip_h,
                        entry.flip_v,
                    )

        return tile_groups

    def _inject_tile_group(
        self,
        rom_offset: int,
        vram_tiles: dict[int, tuple[int, int, int, int | None, bool, bool]],
        masked_canvas: Image.Image,
        filtered_capture: CaptureResult,
        bbox: object,  # CaptureBoundingBox
        project: FrameMappingProject,
        game_frame: GameFrame,
        rom_data: bytes,
        force_raw: bool,
        current_rom_path: str,
        source_rom_path: str,
        create_backup: bool,
        preserve_existing: bool,
        debug: InjectionDebugContext,
        transformed_index_map: np.ndarray | None = None,  # BUG-1 FIX
    ) -> TileInjectionResult:
        """Inject a single tile group at a ROM offset."""

        # Sort tiles by tile_index_in_block
        def tile_sort_key(vram_addr: int) -> tuple[int, int]:
            _, _, _, tile_idx, _, _ = vram_tiles[vram_addr]
            if tile_idx is not None:
                return (tile_idx, vram_addr)
            return (vram_addr, 0)

        sorted_vram_addrs = sorted(vram_tiles.keys(), key=tile_sort_key)
        captured_tile_count = len(sorted_vram_addrs)

        if captured_tile_count == 0:
            return TileInjectionResult(
                rom_offset=rom_offset,
                tile_count=0,
                compression_used="RAW",
                success=True,
                message=f"Offset 0x{rom_offset:X}: No tiles",
            )

        # Select compression strategy
        stored_compression = game_frame.compression_types.get(rom_offset, CompressionType.RAW)
        is_raw = force_raw or stored_compression == CompressionType.RAW
        compression_strategy = get_compression_strategy(is_raw)

        # Detect original tile count using strategy
        original_tile_count = compression_strategy.detect_original_tile_count(
            rom_data, rom_offset, captured_tile_count, self._staging_manager, self._rom_injector
        )

        # Limit to original count
        if captured_tile_count > original_tile_count:
            logger.info(
                "ROM offset 0x%X: Capture has %d tiles but ROM has %d, limiting",
                rom_offset,
                captured_tile_count,
                original_tile_count,
            )
            sorted_vram_addrs = sorted_vram_addrs[:original_tile_count]

        tile_count = len(sorted_vram_addrs)

        # Determine padded tile count using strategy
        if compression_strategy.should_pad_tiles():
            padded_tile_count = max(tile_count, original_tile_count)
            if tile_count < original_tile_count:
                logger.info(
                    "ROM offset 0x%X: Padding from %d to %d tiles to clear VRAM",
                    rom_offset,
                    tile_count,
                    original_tile_count,
                )
        else:
            padded_tile_count = tile_count

        # Build tile image
        grid_width = math.ceil(math.sqrt(padded_tile_count))
        grid_height = math.ceil(padded_tile_count / grid_width)

        chunk_img = Image.new("RGBA", (grid_width * 8, grid_height * 8), (0, 0, 0, 0))

        # Build index chunk for index-preserving injection
        chunk_index_map: np.ndarray | None = None
        if transformed_index_map is not None:
            chunk_index_map = np.zeros((grid_height * 8, grid_width * 8), dtype=np.uint8)

        first_tile_info = vram_tiles[sorted_vram_addrs[0]]
        palette_index = first_tile_info[2]

        for idx, vram_addr in enumerate(sorted_vram_addrs):
            screen_x, screen_y, _, tile_idx, flip_h, flip_v = vram_tiles[vram_addr]

            canvas_x = screen_x - bbox.x  # type: ignore[attr-defined]
            canvas_y = screen_y - bbox.y  # type: ignore[attr-defined]

            tile_img = masked_canvas.crop((canvas_x, canvas_y, canvas_x + 8, canvas_y + 8))

            # Check for content
            tile_alpha = tile_img.split()[3]
            alpha_threshold = QUANTIZATION_TRANSPARENCY_THRESHOLD
            if project.sheet_palette is not None:
                alpha_threshold = project.sheet_palette.alpha_threshold
            has_content = any(p >= alpha_threshold for p in tile_alpha.getdata())
            if not has_content:
                tile_img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))

            if debug.enabled and debug.debug_dir:
                debug.save_debug_image(f"tile_0x{rom_offset:X}_v{vram_addr:X}_before", tile_img)

            # Counter-flip
            if flip_h:
                tile_img = tile_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if flip_v:
                tile_img = tile_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

            if debug.enabled and debug.debug_dir:
                debug.save_debug_image(f"tile_0x{rom_offset:X}_v{vram_addr:X}_after", tile_img)

            # Get grid position from strategy
            grid_x, grid_y = compression_strategy.get_grid_position(tile_idx, idx, grid_width)
            # Bounds check for HAL strategy with out-of-range tile_idx
            if grid_y >= grid_height * 8:
                grid_x, grid_y = (idx % grid_width) * 8, (idx // grid_width) * 8

            debug.log_extraction_details(vram_addr, (canvas_x, canvas_y), flip_h, (grid_x, grid_y))

            chunk_img.paste(tile_img, (grid_x, grid_y))

            # Extract index tile from transformed_index_map
            if chunk_index_map is not None and transformed_index_map is not None:
                canvas_h, canvas_w = transformed_index_map.shape
                if 0 <= canvas_x < canvas_w - 7 and 0 <= canvas_y < canvas_h - 7:
                    index_tile = transformed_index_map[canvas_y : canvas_y + 8, canvas_x : canvas_x + 8].copy()

                    if flip_h:
                        index_tile = np.fliplr(index_tile)
                    if flip_v:
                        index_tile = np.flipud(index_tile)

                    chunk_index_map[grid_y : grid_y + 8, grid_x : grid_x + 8] = index_tile

        debug.save_debug_image(f"chunk_0x{rom_offset:X}_pre_quant", chunk_img)

        # Get capture palette for fallback (only convert when needed)
        capture_palette_rgb: list[tuple[int, int, int]] | None = None
        if project.sheet_palette is None:
            snes_palette = filtered_capture.palettes.get(palette_index, [])
            capture_palette_rgb = snes_palette_to_rgb(snes_palette) if snes_palette else None

        # Select and apply quantization strategy
        alpha_threshold = QUANTIZATION_TRANSPARENCY_THRESHOLD
        dither_mode = "none"
        dither_strength = 0.0
        if project.sheet_palette is not None:
            alpha_threshold = project.sheet_palette.alpha_threshold
            dither_mode = project.sheet_palette.dither_mode
            dither_strength = project.sheet_palette.dither_strength

        quant_strategy = select_quantization_strategy(
            chunk_index_map,
            project.sheet_palette,
            capture_palette_rgb,
            alpha_threshold=alpha_threshold,
            dither_mode=dither_mode,
            dither_strength=dither_strength,
        )
        chunk_img = quant_strategy.quantize(
            chunk_img, chunk_index_map, project.sheet_palette, capture_palette_rgb, rom_offset
        )

        debug.save_debug_image(f"chunk_0x{rom_offset:X}_post_quant", chunk_img)

        # Inject via temp file
        compression_type = compression_strategy.get_compression_type()
        compression_used: Literal["HAL", "RAW"] = "RAW" if is_raw else "HAL"
        chunk_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(suffix=f"_{rom_offset:X}.png", delete=False) as tmp:
                chunk_path = Path(tmp.name)
                chunk_img.save(chunk_path, "PNG")

            result, message = self._rom_injector.inject_sprite_to_rom(
                sprite_path=str(chunk_path),
                rom_path=source_rom_path,
                output_path=current_rom_path,
                sprite_offset=rom_offset,
                fast_compression=(not is_raw),
                create_backup=create_backup,
                ignore_checksum=True,
                force=False,
                compression_type=compression_type,
                preserve_existing=preserve_existing,
            )

            # Fallback to RAW if HAL failed
            if not result and not is_raw and ("decompress" in message.lower() or "too large" in message.lower()):
                compression_used = "RAW"
                logger.info(
                    "ROM offset 0x%X: HAL failed, retrying as RAW",
                    rom_offset,
                )
                result, message = self._rom_injector.inject_sprite_to_rom(
                    sprite_path=str(chunk_path),
                    rom_path=source_rom_path,
                    output_path=current_rom_path,
                    sprite_offset=rom_offset,
                    fast_compression=False,
                    create_backup=create_backup,
                    ignore_checksum=True,
                    force=False,
                    compression_type=CompressionType.RAW,
                    preserve_existing=preserve_existing,
                )
        finally:
            if chunk_path is not None:
                chunk_path.unlink(missing_ok=True)

        if result:
            # Debug verification
            if debug.enabled:
                try:
                    written_rom = Path(current_rom_path).read_bytes()
                    smc_header = 512 if len(written_rom) % 0x8000 == 512 else 0
                    check_offset = rom_offset + smc_header
                    written_bytes = written_rom[check_offset : check_offset + 32]
                    debug.log_rom_write_verification(rom_offset, compression_used, tile_count, written_bytes.hex())
                except Exception as e:
                    logger.warning("Could not verify ROM bytes: %s", e)

            return TileInjectionResult(
                rom_offset=rom_offset,
                tile_count=tile_count,
                compression_used=compression_used,
                success=True,
                message=f"Offset 0x{rom_offset:X}: Success ({tile_count} tiles, {compression_used})",
            )
        else:
            return TileInjectionResult(
                rom_offset=rom_offset,
                tile_count=tile_count,
                compression_used=compression_used,
                success=False,
                message=f"Offset 0x{rom_offset:X}: Failed ({message})",
            )
