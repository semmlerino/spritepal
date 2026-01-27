"""Unified sprite compositing for preview and injection.

This service provides consistent compositing logic for both the workbench
preview and ROM injection. It ensures WYSIWYG alignment between what the
user sees and what gets injected.

Key behaviors:
- Transform order: flip FIRST, then scale (SNES-correct, hardware applies flip at display)
- Uncovered areas: configurable policy ("transparent" for injection, "original" for preview)
- Palette quantization: uses first entry's palette by default
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
from PIL import Image

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.palette_utils import (
    QUANTIZATION_TRANSPARENCY_THRESHOLD,
    quantize_to_palette,
    quantize_with_mappings,
    snap_to_snes_color,
    snes_palette_to_rgb,
)
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import SheetPalette
    from core.mesen_integration.click_extractor import CaptureResult

logger = get_logger(__name__)


@dataclass
class TransformParams:
    """Parameters for AI frame transformation."""

    offset_x: int = 0
    offset_y: int = 0
    flip_h: bool = False
    flip_v: bool = False
    scale: float = 1.0


@dataclass
class CompositeResult:
    """Result of compositing an AI frame onto a game sprite.

    Attributes:
        composited_image: The final RGBA image with AI frame applied.
        original_mask: The alpha channel from the original sprite.
        canvas_width: Width of the compositing canvas.
        canvas_height: Height of the compositing canvas.
        uncovered_policy: Policy used for uncovered areas.
        index_map: Transformed palette index map (matching composited_image).
    """

    composited_image: Image.Image
    original_mask: Image.Image
    canvas_width: int
    canvas_height: int
    uncovered_policy: Literal["transparent", "original"]
    index_map: np.ndarray | None = None


class SpriteCompositor:
    """Unified compositing service for preview and injection.

    Provides consistent AI-to-game frame compositing with configurable
    policies for uncovered areas.

    The transform order is: flip -> scale -> offset
    This matches SNES hardware behavior where OAM flip bits are applied
    at display time.
    """

    def __init__(
        self,
        uncovered_policy: Literal["transparent", "original"] = "transparent",
    ) -> None:
        """Initialize the compositor.

        Args:
            uncovered_policy: How to handle areas where AI doesn't cover the
                original sprite:
                - "transparent": Original sprite is completely removed; only AI
                  content remains. Uncovered areas become transparent.
                - "original": Original sprite is preserved where AI doesn't cover
                  it. AI content composites on top of the original.
        """
        self._uncovered_policy: Literal["transparent", "original"] = uncovered_policy

    def composite_frame(
        self,
        ai_image: Image.Image,
        capture_result: CaptureResult,
        transform: TransformParams,
        selected_entry_ids: list[int] | None = None,
        quantize: bool = True,
        sheet_palette: SheetPalette | None = None,
        ai_index_map: np.ndarray | None = None,
    ) -> CompositeResult:
        """Composite an AI frame onto a game sprite.

        Args:
            ai_image: The AI-generated frame (RGBA).
            capture_result: Parsed Mesen capture with OAM entries.
            transform: Alignment parameters (offset, flip, scale).
            selected_entry_ids: If provided, only these entries are included.
            quantize: Whether to quantize to the game palette.
            sheet_palette: If provided, use this palette for quantization instead
                of the capture palette. This ensures preview matches injection.
            ai_index_map: Optional pre-indexed map for the AI frame. If provided,
                this is transformed and used to bypass quantization where possible.

        Returns:
            CompositeResult with the composited image and metadata.
        """
        # Ensure RGBA mode
        if ai_image.mode != "RGBA":
            ai_image = ai_image.convert("RGBA")

        # Filter capture to selected entries if specified
        filtered_capture = self._filter_capture(capture_result, selected_entry_ids)

        # Render original sprite from capture
        renderer = CaptureRenderer(filtered_capture)
        original_sprite = renderer.render_selection()

        # Get canvas dimensions from bounding box
        bbox = filtered_capture.bounding_box
        canvas_w = bbox.width
        canvas_h = bbox.height

        # Apply transforms to AI image: FLIP first, then SCALE (SNES-correct order)
        transformed_ai = self._apply_transforms(ai_image, transform)

        # Create canvas and paste AI at offset
        ai_canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        ai_canvas.paste(transformed_ai, (transform.offset_x, transform.offset_y), transformed_ai)

        # Get original sprite's alpha channel as mask (for result metadata)
        original_mask = original_sprite.split()[3]

        # Apply compositing based on policy
        if self._uncovered_policy == "transparent":
            # Original sprite completely removed - only AI content remains
            # AI content is masked to tile bounds (not pixel-level opacity)
            # This clips to the 8x8 tile grid areas, not the sprite's silhouette
            composited = ai_canvas.copy()
            ai_alpha = composited.split()[3]

            # Build tile-based mask from OAM entries
            tile_mask = self._build_tile_mask(filtered_capture, canvas_w, canvas_h)

            # Use minimum of AI alpha and tile mask - clips to tile bounds
            masked_alpha = Image.fromarray(np.minimum(np.array(ai_alpha), np.array(tile_mask)))
            composited.putalpha(masked_alpha)
        else:
            # Original sprite preserved - AI composites on top
            composited = Image.alpha_composite(original_sprite.copy(), ai_canvas)

        # Handle index map transformation if provided
        transformed_index_map: np.ndarray | None = None
        if ai_index_map is not None:
            transformed_index_map = self._transform_index_map(ai_index_map, transform, (canvas_w, canvas_h))

        # Quantize to game palette if requested
        if quantize:
            # BUG-1 FIX: Use transformed_index_map if available to bypass quantization
            # This ensures preview matches injection (index-preserving passthrough)
            if transformed_index_map is not None and sheet_palette is not None:
                # Check if index map has valid data for all opaque pixels
                # (actually _quantize_with_index_map handles this)
                composited = self._quantize_with_index_map(
                    composited,
                    transformed_index_map,
                    sheet_palette,
                )
            else:
                composited = self._quantize_to_palette(composited, filtered_capture, sheet_palette=sheet_palette)

        return CompositeResult(
            composited_image=composited,
            original_mask=original_mask,
            canvas_width=canvas_w,
            canvas_height=canvas_h,
            uncovered_policy=self._uncovered_policy,
            index_map=transformed_index_map,
        )

    def _transform_index_map(
        self,
        index_map: np.ndarray,
        transform: TransformParams,
        canvas_size: tuple[int, int],
    ) -> np.ndarray:
        """Transform index map to match the composited canvas coordinates.

        Applies the same transforms (flip, scale, offset) to the index map
        that are applied to the RGBA image during compositing, using NEAREST
        interpolation to preserve exact palette indices.

        Args:
            index_map: Original palette index array from AI frame
            transform: Alignment parameters (offset, flip, scale)
            canvas_size: Size of the composited canvas (width, height)

        Returns:
            Transformed index map at canvas coordinates, with 255 marking "no AI data"
        """
        canvas_w, canvas_h = canvas_size

        # Start with "no data" marker (255 = outside AI frame area)
        result = np.full((canvas_h, canvas_w), 255, dtype=np.uint8)

        # Convert to PIL for easy transforming (preserves indices)
        img = Image.fromarray(index_map, mode="P")

        # Apply flips FIRST
        if transform.flip_h:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if transform.flip_v:
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        # Apply scale SECOND
        if abs(transform.scale - 1.0) > 0.01:
            new_w = max(1, int(img.width * transform.scale))
            new_h = max(1, int(img.height * transform.scale))
            img = img.resize((new_w, new_h), Image.Resampling.NEAREST)

        scaled = np.array(img, dtype=np.uint8)
        scaled_h, scaled_w = scaled.shape

        # Calculate placement in canvas
        start_x = transform.offset_x
        start_y = transform.offset_y

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

    def _quantize_with_index_map(
        self,
        image: Image.Image,
        index_map: np.ndarray,
        sheet_palette: SheetPalette,
    ) -> Image.Image:
        """Quantize image using a pre-calculated index map where available.

        For pixels where index_map != 255, uses the index directly from the map.
        For other pixels (e.g. original sprite pixels in "original" policy),
        falls back to standard quantization.

        Args:
            image: RGBA image to quantize
            index_map: Transformed index map (255 = no index)
            sheet_palette: Target palette

        Returns:
            Quantized RGBA image with binary alpha (WYSIWYG).
        """
        # 1. Start with standard quantization as baseline
        # (This handles original sprite pixels if uncovered_policy="original")
        # Snap palette colors to SNES precision for WYSIWYG fidelity
        palette_rgb = [snap_to_snes_color(c) for c in sheet_palette.colors]
        if sheet_palette.color_mappings:
            indexed = quantize_with_mappings(
                image,
                palette_rgb,
                sheet_palette.color_mappings,
                transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
            )
        else:
            indexed = quantize_to_palette(
                image,
                palette_rgb,
                transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
            )

        # 2. Overlay indices from the map where available
        pixels = np.array(indexed)
        mask = index_map != 255
        pixels[mask] = index_map[mask]

        # 3. Create final indexed image
        final_indexed = Image.fromarray(pixels, mode="P")

        # Build palette for PIL
        flat_palette: list[int] = []
        for rgb in palette_rgb:
            flat_palette.extend([rgb[0], rgb[1], rgb[2]])
        flat_palette.extend([0] * (768 - len(flat_palette)))
        final_indexed.putpalette(flat_palette)

        # Convert back to RGBA
        result = final_indexed.convert("RGBA")

        # BUG-FIX: Enforce binary alpha for WYSIWYG fidelity.
        # Index 0 is always fully transparent, Indices 1-15 are fully opaque.
        binary_alpha = np.where(pixels == 0, 0, 255).astype(np.uint8)
        result.putalpha(Image.fromarray(binary_alpha, mode="L"))

        return result

    def _apply_transforms(
        self,
        ai_image: Image.Image,
        transform: TransformParams,
    ) -> Image.Image:
        """Apply flip and scale transforms in SNES-correct order.

        Transform order: flip -> scale
        This matches SNES hardware behavior.
        """
        result = ai_image.copy()

        # Apply flips FIRST
        if transform.flip_h:
            result = result.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if transform.flip_v:
            result = result.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        # Apply scale SECOND
        if abs(transform.scale - 1.0) > 0.01:
            new_w = max(1, int(result.width * transform.scale))
            new_h = max(1, int(result.height * transform.scale))
            result = result.resize((new_w, new_h), Image.Resampling.NEAREST)

        return result

    def _build_tile_mask(
        self,
        capture_result: CaptureResult,
        canvas_w: int,
        canvas_h: int,
    ) -> Image.Image:
        """Build a mask from tile bounds (8x8 grid rectangles).

        Creates an alpha mask where all pixels within OAM entry tile bounds
        are opaque (255) and pixels outside are transparent (0). This clips
        to tile boundaries rather than the original sprite's pixel-level shape.

        Args:
            capture_result: Mesen capture with OAM entries.
            canvas_w: Width of the canvas.
            canvas_h: Height of the canvas.

        Returns:
            Grayscale image (mode 'L') usable as an alpha mask.
        """
        bbox = capture_result.bounding_box
        mask = Image.new("L", (canvas_w, canvas_h), 0)

        # Draw filled rectangles for each OAM entry's tile area
        from PIL import ImageDraw

        draw = ImageDraw.Draw(mask)

        for entry in capture_result.entries:
            # Position relative to bounding box origin
            rel_x = entry.x - bbox.x
            rel_y = entry.y - bbox.y

            # Draw the full tile area (entry.width x entry.height)
            draw.rectangle(
                [rel_x, rel_y, rel_x + entry.width - 1, rel_y + entry.height - 1],
                fill=255,
            )

        return mask

    def _filter_capture(
        self,
        capture_result: CaptureResult,
        selected_entry_ids: list[int] | None,
    ) -> CaptureResult:
        """Filter capture to selected entries if specified."""
        if selected_entry_ids is None:
            return capture_result

        selected_ids = set(selected_entry_ids)
        relevant_entries = [e for e in capture_result.entries if e.id in selected_ids]

        if not relevant_entries:
            logger.warning("No entries matched selected_entry_ids, using all entries")
            return capture_result

        # Create filtered capture result
        from core.mesen_integration.click_extractor import CaptureResult as CaptureResultType

        return CaptureResultType(
            frame=capture_result.frame,
            visible_count=len(relevant_entries),
            obsel=capture_result.obsel,
            entries=relevant_entries,
            palettes=capture_result.palettes,
            timestamp=capture_result.timestamp,
        )

    def _quantize_to_palette(
        self,
        image: Image.Image,
        capture_result: CaptureResult,
        sheet_palette: SheetPalette | None = None,
    ) -> Image.Image:
        """Quantize image to a palette.

        Priority: sheet_palette > capture palette (matches injection behavior).

        Args:
            image: RGBA image to quantize.
            capture_result: Mesen capture with palette info (fallback).
            sheet_palette: User-defined palette with color mappings (preferred).

        Returns:
            Quantized RGBA image with binary alpha (WYSIWYG).
        """
        # Priority: sheet_palette > capture palette (matches injection behavior)
        if sheet_palette is not None:
            # Use sheet palette (user-defined for consistent AI frame rendering)
            # Snap palette colors to SNES precision for WYSIWYG fidelity
            palette_rgb = [snap_to_snes_color(c) for c in sheet_palette.colors]
            if sheet_palette.color_mappings:
                # Use explicit color mappings
                indexed = quantize_with_mappings(
                    image,
                    palette_rgb,
                    sheet_palette.color_mappings,
                    transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
                )
            else:
                # Sheet palette without explicit mappings -> nearest color
                indexed = quantize_to_palette(
                    image,
                    palette_rgb,
                    transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
                )
        else:
            # Fallback: capture palette (existing behavior)
            if not capture_result.entries or not capture_result.palettes:
                return image

            first_entry = capture_result.entries[0]
            snes_palette = capture_result.palettes.get(first_entry.palette, [])

            if not snes_palette:
                return image

            palette_rgb = snes_palette_to_rgb(snes_palette)
            indexed = quantize_to_palette(
                image,
                palette_rgb,
                transparency_threshold=QUANTIZATION_TRANSPARENCY_THRESHOLD,
            )

        # Convert back to RGBA for compositing
        quantized_rgba = indexed.convert("RGBA")

        # BUG-FIX: Enforce binary alpha for WYSIWYG fidelity.
        # SNES hardware doesn't support semi-transparency in sprites.
        # Index 0 is always fully transparent, Indices 1-15 are fully opaque.
        idx_array = np.array(indexed)
        binary_alpha = np.where(idx_array == 0, 0, 255).astype(np.uint8)
        quantized_rgba.putalpha(Image.fromarray(binary_alpha, mode="L"))

        return quantized_rgba
