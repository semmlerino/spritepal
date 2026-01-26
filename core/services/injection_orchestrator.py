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
    quantize_to_palette,
    quantize_with_mappings,
    snes_palette_to_rgb,
)
from core.rom_injector import ROMInjector
from core.services.injection_debug_context import InjectionDebugContext
from core.services.injection_results import (
    InjectionRequest,
    InjectionResult,
    TileInjectionResult,
)
from core.services.rgb_to_indexed import load_image_preserving_indices
from core.services.rom_staging_manager import ROMStagingManager
from core.services.rom_verification_service import ROMVerificationService
from core.services.sprite_compositor import SpriteCompositor, TransformParams
from core.types import CompressionType
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
    from core.mesen_integration.click_extractor import OAMEntry

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
            composite_data = self._prepare_images(ai_frame, game_frame, mapping, project, request, debug)
            if isinstance(composite_data, InjectionResult):
                return composite_data

            # BUG-1 FIX: Unpack index_map for index-preserving injection
            masked_canvas, filtered_capture, relevant_entries, transformed_index_map = composite_data

        except Exception as e:
            logger.exception("Failed to prepare masked image")
            return InjectionResult.failure(f"Image preparation failed: {e}")

        # 3. Set up ROM staging
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

        # 4. Execute injection with staging
        try:
            result = self._execute_injection(
                request=request,
                project=project,
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
                on_progress=progress,
                transformed_index_map=transformed_index_map,  # BUG-1 FIX
            )

            if result.success:
                # Commit staging
                if not self._staging_manager.commit(session):
                    self._staging_manager.rollback(session)
                    return InjectionResult.failure("Failed to commit staged injection to ROM")

                return InjectionResult(
                    success=True,
                    tile_results=result.tile_results,
                    output_rom_path=injection_rom_path,
                    messages=result.messages,
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
        project: FrameMappingProject,
        request: InjectionRequest,
        debug: InjectionDebugContext,
    ) -> tuple[Image.Image, CaptureResult, list[OAMEntry], np.ndarray | None] | InjectionResult:
        """Load and composite images for injection.

        Returns (masked_canvas, filtered_capture, relevant_entries, ai_index_map) on success,
        or InjectionResult on failure.

        BUG-1 FIX: Also returns ai_index_map (palette indices) if the AI frame is an
        indexed PNG, enabling index-preserving injection that avoids re-quantization.
        """
        # Load AI image, preserving palette indices if indexed PNG
        ai_index_map, ai_img = load_image_preserving_indices(ai_frame.path)
        if ai_index_map is not None:
            logger.debug(
                "Loaded indexed PNG with preserved indices: %s (shape: %s)",
                ai_frame.path.name,
                ai_index_map.shape,
            )

        # Parse capture for tile layout
        # Note: capture_path is validated in _validate_mapping before this is called
        assert game_frame.capture_path is not None
        parser = MesenCaptureParser()
        capture_result = parser.parse_file(game_frame.capture_path)

        # Filter to relevant entries
        if game_frame.selected_entry_ids:
            selected_ids = set(game_frame.selected_entry_ids)
            relevant_entries = [e for e in capture_result.entries if e.id in selected_ids]

            if not relevant_entries:
                logger.warning(
                    "Stored entry IDs %s not found in capture %s",
                    game_frame.selected_entry_ids,
                    game_frame.capture_path,
                )

                if not request.allow_fallback:
                    return InjectionResult.stale_entries(
                        frame_id=game_frame.id,
                        error=(
                            f"Entry selection for '{game_frame.id}' is outdated. "
                            "Reimport the capture or enable fallback mode."
                        ),
                    )

                # Fallback to rom_offset filtering
                logger.info("Using rom_offset fallback (allow_fallback=True)")
                relevant_entries = [e for e in capture_result.entries if e.rom_offset in game_frame.rom_offsets]
        else:
            relevant_entries = [e for e in capture_result.entries if e.rom_offset in game_frame.rom_offsets]

        if not relevant_entries:
            logger.warning("No entries match for frame %s", game_frame.id)

            if not request.allow_fallback:
                return InjectionResult.stale_entries(
                    frame_id=game_frame.id,
                    error=(
                        f"No valid entries found for '{game_frame.id}'. "
                        "The capture file may have changed. Reimport the capture."
                    ),
                )

            logger.info("Using all entries fallback (allow_fallback=True)")
            relevant_entries = capture_result.entries

        # Create filtered capture for compositing
        filtered_capture = CaptureResult(
            frame=capture_result.frame,
            visible_count=len(relevant_entries),
            obsel=capture_result.obsel,
            entries=relevant_entries,
            palettes=capture_result.palettes,
            timestamp=capture_result.timestamp,
        )

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
        )

        masked_canvas = composite_result.composited_image

        # Debug: Save intermediate images
        if debug.enabled and debug.debug_dir:
            renderer = CaptureRenderer(filtered_capture)
            original_sprite_img = renderer.render_selection()
            debug.save_debug_image("original_sprite_mask", original_sprite_img)
            debug.save_debug_image("masked_canvas", masked_canvas)

        # BUG-1 FIX: Transform the index map to match the composited canvas coordinates
        # This enables index-preserving injection (skipping re-quantization)
        transformed_index_map: np.ndarray | None = None
        if ai_index_map is not None:
            transformed_index_map = self._transform_index_map(
                ai_index_map,
                mapping,
                masked_canvas.size,
            )

        return masked_canvas, filtered_capture, relevant_entries, transformed_index_map

    def _transform_index_map(
        self,
        index_map: np.ndarray,
        mapping: FrameMapping,
        canvas_size: tuple[int, int],
    ) -> np.ndarray:
        """Transform index map to match the composited canvas coordinates.

        BUG-1 FIX: Applies the same transforms (flip, scale, offset) to the index map
        that are applied to the RGBA image during compositing, using NEAREST interpolation
        to preserve exact palette indices.

        Args:
            index_map: Original palette index array from AI frame
            mapping: Frame mapping with transform parameters
            canvas_size: Size of the composited canvas (width, height)

        Returns:
            Transformed index map at canvas coordinates, with 255 marking "no AI data"
        """
        from scipy.ndimage import zoom

        canvas_w, canvas_h = canvas_size

        # Start with "no data" marker (255 = outside AI frame area)
        result = np.full((canvas_h, canvas_w), 255, dtype=np.uint8)

        # Apply scale if needed (using NEAREST to preserve indices)
        if mapping.scale != 1.0:
            scaled: np.ndarray = np.asarray(zoom(index_map, mapping.scale, order=0), dtype=np.uint8)
        else:
            scaled = index_map

        # Apply flips
        if mapping.flip_h:
            scaled = np.fliplr(scaled)
        if mapping.flip_v:
            scaled = np.flipud(scaled)

        # Calculate placement in canvas (matching compositor logic)
        scaled_h, scaled_w = int(scaled.shape[0]), int(scaled.shape[1])

        # The AI frame is placed at offset relative to canvas center
        # (matching SpriteCompositor's placement logic)
        # Place at offset from canvas origin
        start_x = mapping.offset_x
        start_y = mapping.offset_y

        # Calculate overlap region
        src_x_start = max(0, -start_x)
        src_y_start = max(0, -start_y)
        dst_x_start = max(0, start_x)
        dst_y_start = max(0, start_y)

        copy_w = min(scaled_w - src_x_start, canvas_w - dst_x_start)
        copy_h = min(scaled_h - src_y_start, canvas_h - dst_y_start)

        if copy_w > 0 and copy_h > 0:
            result[
                dst_y_start : dst_y_start + copy_h,
                dst_x_start : dst_x_start + copy_w,
            ] = scaled[
                src_y_start : src_y_start + copy_h,
                src_x_start : src_x_start + copy_w,
            ]

        return result

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

        # Determine compression type
        stored_compression = game_frame.compression_types.get(rom_offset, "raw")
        is_raw = force_raw or stored_compression == "raw"

        # Determine original tile count
        if is_raw:
            detected_slot_size = self._staging_manager.detect_raw_slot_size(rom_data, rom_offset)
            if detected_slot_size is not None:
                original_tile_count = detected_slot_size
                logger.info(
                    "ROM offset 0x%X: Using RAW (detected slot: %d tiles)",
                    rom_offset,
                    detected_slot_size,
                )
            else:
                original_tile_count = captured_tile_count
                logger.info(
                    "ROM offset 0x%X: Using RAW (no boundary, using captured: %d tiles)",
                    rom_offset,
                    captured_tile_count,
                )
        else:
            try:
                _, original_data, _ = self._rom_injector.find_compressed_sprite(rom_data, rom_offset)
                original_tile_count = len(original_data) // 32
                if original_tile_count == 0:
                    original_tile_count = captured_tile_count
            except Exception:
                original_tile_count = captured_tile_count
            logger.info(
                "ROM offset 0x%X: Using HAL (%d tiles in block)",
                rom_offset,
                original_tile_count,
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

        # FIX: Pad to original tile count to fully overwrite VRAM
        # When captured_tile_count < original_tile_count, we need to create a larger
        # image so the compressed data fully replaces the original. Extra slots stay
        # transparent, which compiles to transparent SNES tiles that clear VRAM.
        padded_tile_count = max(tile_count, original_tile_count)
        if tile_count < original_tile_count:
            logger.info(
                "ROM offset 0x%X: Padding from %d to %d tiles to clear VRAM",
                rom_offset,
                tile_count,
                original_tile_count,
            )

        # Build tile image (sized for padded count, not captured count)
        grid_width = math.ceil(math.sqrt(padded_tile_count))
        grid_height = math.ceil(padded_tile_count / grid_width)

        chunk_img = Image.new("RGBA", (grid_width * 8, grid_height * 8), (0, 0, 0, 0))

        # BUG-1 FIX: Also build index chunk for index-preserving injection
        chunk_index_map: np.ndarray | None = None
        if transformed_index_map is not None:
            chunk_index_map = np.zeros((grid_height * 8, grid_width * 8), dtype=np.uint8)

        first_tile_info = vram_tiles[sorted_vram_addrs[0]]
        palette_index = first_tile_info[2]

        for idx, vram_addr in enumerate(sorted_vram_addrs):
            screen_x, screen_y, _, _, flip_h, flip_v = vram_tiles[vram_addr]

            canvas_x = screen_x - bbox.x  # type: ignore[attr-defined]
            canvas_y = screen_y - bbox.y  # type: ignore[attr-defined]

            tile_img = masked_canvas.crop((canvas_x, canvas_y, canvas_x + 8, canvas_y + 8))

            # Check for content
            tile_alpha = tile_img.split()[3]
            has_content = any(p >= QUANTIZATION_TRANSPARENCY_THRESHOLD for p in tile_alpha.getdata())
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

            grid_x = (idx % grid_width) * 8
            grid_y = (idx // grid_width) * 8

            debug.log_extraction_details(vram_addr, (canvas_x, canvas_y), flip_h, (grid_x, grid_y))

            chunk_img.paste(tile_img, (grid_x, grid_y))

            # BUG-1 FIX: Also extract index tile from transformed_index_map
            if chunk_index_map is not None and transformed_index_map is not None:
                # Extract 8x8 index tile
                canvas_h, canvas_w = transformed_index_map.shape
                if 0 <= canvas_x < canvas_w - 7 and 0 <= canvas_y < canvas_h - 7:
                    index_tile = transformed_index_map[canvas_y : canvas_y + 8, canvas_x : canvas_x + 8].copy()

                    # Apply same flips to index tile
                    if flip_h:
                        index_tile = np.fliplr(index_tile)
                    if flip_v:
                        index_tile = np.flipud(index_tile)

                    # Place in chunk index map
                    chunk_index_map[grid_y : grid_y + 8, grid_x : grid_x + 8] = index_tile

        debug.save_debug_image(f"chunk_0x{rom_offset:X}_pre_quant", chunk_img)

        # BUG-1 FIX: Use index map directly if available (skips re-quantization)
        use_index_passthrough = False
        if chunk_index_map is not None and project.sheet_palette:
            # Check if index map has valid data (no 255 markers = outside AI frame area)
            if not np.any(chunk_index_map == 255):
                use_index_passthrough = True
                logger.debug(
                    "ROM offset 0x%X: Using index passthrough (preserving palette indices)",
                    rom_offset,
                )

        if use_index_passthrough and chunk_index_map is not None and project.sheet_palette:
            # Create indexed image directly from index map (BUG-1 FIX)
            sheet_palette = project.sheet_palette
            palette_flat = []
            for r, g, b in sheet_palette.colors:
                palette_flat.extend([r, g, b])
            # Pad to 256 colors (PIL requirement)
            palette_flat.extend([0] * (768 - len(palette_flat)))

            chunk_img = Image.fromarray(chunk_index_map, mode="P")
            chunk_img.putpalette(palette_flat)
        # Quantize (fallback when no index map or index map has invalid data)
        elif project.sheet_palette:
            sheet_palette = project.sheet_palette
            palette_rgb = list(sheet_palette.colors)
            if sheet_palette.color_mappings:
                chunk_img = quantize_with_mappings(
                    chunk_img,
                    palette_rgb,
                    sheet_palette.color_mappings,
                    transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
                )
            else:
                chunk_img = quantize_to_palette(
                    chunk_img,
                    palette_rgb,
                    transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
                )
        else:
            snes_palette = filtered_capture.palettes.get(palette_index, [])
            if snes_palette:
                palette_rgb = snes_palette_to_rgb(snes_palette)
                chunk_img = quantize_to_palette(
                    chunk_img,
                    palette_rgb,
                    transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
                )
            else:
                logger.warning("No palette for index %d, using grayscale", palette_index)

        debug.save_debug_image(f"chunk_0x{rom_offset:X}_post_quant", chunk_img)

        # Inject via temp file
        compression_used: Literal["HAL", "RAW"] = "RAW" if is_raw else "HAL"
        chunk_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(suffix=f"_{rom_offset:X}.png", delete=False) as tmp:
                chunk_path = Path(tmp.name)
                chunk_img.save(chunk_path, "PNG")

            if is_raw:
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
            else:
                result, message = self._rom_injector.inject_sprite_to_rom(
                    sprite_path=str(chunk_path),
                    rom_path=source_rom_path,
                    output_path=current_rom_path,
                    sprite_offset=rom_offset,
                    fast_compression=True,
                    create_backup=create_backup,
                    ignore_checksum=True,
                    force=False,
                    compression_type=CompressionType.HAL,
                    preserve_existing=preserve_existing,
                )

                # Fallback to RAW if HAL failed
                if not result and ("decompress" in message.lower() or "too large" in message.lower()):
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
