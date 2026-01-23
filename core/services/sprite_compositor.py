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
from core.palette_utils import quantize_to_palette, quantize_with_mappings, snes_palette_to_rgb
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
    """

    composited_image: Image.Image
    original_mask: Image.Image
    canvas_width: int
    canvas_height: int
    uncovered_policy: Literal["transparent", "original"]


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

        Returns:
            CompositeResult with the composited image and metadata.
        """
        logger.debug(
            "composite_frame: policy=%s, transform=(%d,%d) flip_h=%s flip_v=%s scale=%.2f",
            self._uncovered_policy,
            transform.offset_x,
            transform.offset_y,
            transform.flip_h,
            transform.flip_v,
            transform.scale,
        )

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
            # BUT: AI content is masked to only appear where original sprite had tiles
            # This prevents AI content from "leaking" into gaps between sprite tiles
            composited = ai_canvas.copy()
            # Apply original sprite mask: keep AI alpha only where original was opaque
            ai_alpha = composited.split()[3]
            # Use minimum of AI alpha and original mask - this preserves AI transparency
            # while ensuring nothing appears outside sprite tile boundaries
            masked_alpha = Image.fromarray(
                np.minimum(np.array(ai_alpha), np.array(original_mask))
            )
            composited.putalpha(masked_alpha)
        else:
            # Original sprite preserved - AI composites on top
            composited = Image.alpha_composite(original_sprite.copy(), ai_canvas)

        # Quantize to game palette if requested
        if quantize:
            composited = self._quantize_to_palette(
                composited, filtered_capture, sheet_palette=sheet_palette
            )

        return CompositeResult(
            composited_image=composited,
            original_mask=original_mask,
            canvas_width=canvas_w,
            canvas_height=canvas_h,
            uncovered_policy=self._uncovered_policy,
        )

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
            Quantized RGBA image.
        """
        # Save original alpha before quantization
        original_alpha = image.split()[3]

        # Priority: sheet_palette > capture palette (matches injection behavior)
        if sheet_palette is not None:
            # Use sheet palette (user-defined for consistent AI frame rendering)
            palette_rgb = list(sheet_palette.colors)
            if sheet_palette.color_mappings:
                # Use explicit color mappings
                indexed = quantize_with_mappings(
                    image,
                    palette_rgb,
                    sheet_palette.color_mappings,
                    transparency_threshold=1,
                )
                logger.debug(
                    "Quantized preview using sheet palette with %d color mappings",
                    len(sheet_palette.color_mappings),
                )
            else:
                # Sheet palette without explicit mappings -> nearest color
                indexed = quantize_to_palette(image, palette_rgb)
                logger.debug("Quantized preview using sheet palette (nearest color)")
        else:
            # Fallback: capture palette (existing behavior)
            if not capture_result.entries or not capture_result.palettes:
                return image

            first_entry = capture_result.entries[0]
            snes_palette = capture_result.palettes.get(first_entry.palette, [])

            if not snes_palette:
                return image

            palette_rgb = snes_palette_to_rgb(snes_palette)
            indexed = quantize_to_palette(image, palette_rgb)

        # Convert back to RGBA for compositing
        quantized_rgba = indexed.convert("RGBA")

        # Restore original alpha (quantization may have changed it)
        quantized_rgba.putalpha(original_alpha)

        return quantized_rgba
