"""Apply operation for sprite rearrangement.

Samples pixels from overlay image and writes them back to tiles,
maintaining tile order and ROM layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from ui.row_arrangement.grid_arrangement_manager import (
        ArrangementType,
        TilePosition,
    )
    from ui.row_arrangement.overlay_layer import OverlayLayer


class WarningType(Enum):
    """Types of Apply operation warnings."""

    UNCOVERED = "uncovered"  # Tile not fully covered by overlay
    PALETTE_MISMATCH = "palette_mismatch"  # Pixels don't match palette
    UNPLACED = "unplaced"  # Tile in source but not placed on canvas


@dataclass
class ApplyWarning:
    """Warning produced during Apply operation validation."""

    type: WarningType
    message: str
    tile_ids: list[TilePosition] = field(default_factory=list)


@dataclass
class ApplyResult:
    """Result of Apply operation."""

    success: bool
    modified_tiles: dict[TilePosition, Image.Image] = field(default_factory=dict)
    warnings: list[ApplyWarning] = field(default_factory=list)
    error_message: str | None = None


class ApplyOperation:
    """Applies overlay pixels to arranged tiles.

    The Apply operation:
    1. For each tile placed on the canvas:
       - Read the tile's position on the canvas
       - Sample a tile-sized region from the overlay at that position
       - Quantize pixels to the sprite's palette
       - Write pixels back to the tile (index unchanged)

    Guarantees:
    - Tile count unchanged
    - Tile order unchanged
    - ROM layout unchanged
    """

    def __init__(
        self,
        overlay: OverlayLayer,
        grid_mapping: dict[tuple[int, int], tuple[ArrangementType, str]],
        tiles: dict[TilePosition, Image.Image],
        tile_width: int,
        tile_height: int,
        palette: list[tuple[int, int, int]] | None = None,
        use_source_positions: bool = True,
    ) -> None:
        """Initialize the Apply operation.

        Args:
            overlay: The overlay layer to sample from.
            grid_mapping: Canvas position -> (type, key) mapping.
            tiles: Source tiles by position.
            tile_width: Width of each tile in pixels.
            tile_height: Height of each tile in pixels.
            palette: Optional palette for quantization (16 RGB colors).
            use_source_positions: If True (default), sample overlay at source tile
                positions instead of canvas positions. This ensures overlays that
                match the source sprite layout are sampled correctly even when tiles
                are rearranged on the canvas.
        """
        self._overlay = overlay
        self._grid_mapping = grid_mapping
        self._tiles = tiles
        self._tile_width = tile_width
        self._tile_height = tile_height
        self._palette = palette
        self._use_source_positions = use_source_positions

    def validate(self) -> list[ApplyWarning]:
        """Validate the Apply operation and return warnings.

        Returns:
            List of warnings. Empty if all tiles are covered.
        """
        from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition

        warnings: list[ApplyWarning] = []

        # Check for uncovered tiles
        uncovered_tiles: list[TilePosition] = []
        for (r, c), (arr_type, key) in self._grid_mapping.items():
            if arr_type == ArrangementType.TILE:
                row, col = map(int, key.split(","))

                # Always use CANVAS coordinates (r, c) for overlay coverage check.
                # The overlay is positioned relative to the canvas grid.
                tile_x = c * self._tile_width
                tile_y = r * self._tile_height

                if not self._overlay.covers_tile(tile_x, tile_y, self._tile_width, self._tile_height):
                    uncovered_tiles.append(TilePosition(row, col))

        if uncovered_tiles:
            warnings.append(
                ApplyWarning(
                    type=WarningType.UNCOVERED,
                    message=f"{len(uncovered_tiles)} tile(s) not fully covered by overlay",
                    tile_ids=uncovered_tiles,
                )
            )

        # Check for unplaced tiles
        placed_tiles = set()
        for arr_type, key in self._grid_mapping.values():
            if arr_type == ArrangementType.TILE:
                row, col = map(int, key.split(","))
                placed_tiles.add(TilePosition(row, col))

        unplaced_tiles = [t for t in self._tiles if t not in placed_tiles]
        if unplaced_tiles:
            warnings.append(
                ApplyWarning(
                    type=WarningType.UNPLACED,
                    message=f"{len(unplaced_tiles)} tile(s) not placed on canvas",
                    tile_ids=unplaced_tiles,
                )
            )

        return warnings

    def execute(self, force: bool = False) -> ApplyResult:
        """Execute the Apply operation.

        Args:
            force: If True, execute even with warnings.

        Returns:
            ApplyResult with success status and modified tiles.
        """
        from ui.row_arrangement.grid_arrangement_manager import ArrangementType, TilePosition

        # Check prerequisites first
        if not self._overlay.has_image():
            return ApplyResult(
                success=False,
                error_message="No overlay image loaded.",
            )

        # Validate
        warnings = self.validate()
        if warnings and not force:
            return ApplyResult(
                success=False,
                warnings=warnings,
                error_message="Validation warnings exist. Use force=True to proceed.",
            )

        modified_tiles: dict[TilePosition, Image.Image] = {}
        palette_mismatches: list[TilePosition] = []

        # Process each placed tile
        for (r, c), (arr_type, key) in self._grid_mapping.items():
            if arr_type != ArrangementType.TILE:
                continue

            row, col = map(int, key.split(","))
            tile_pos = TilePosition(row, col)

            # Calculate sampling position - always use CANVAS coordinates (r, c)
            # The overlay is positioned relative to the canvas grid, not the source grid.
            # Note: use_source_positions is deprecated and ignored - it was fundamentally
            # broken because the overlay can only be positioned in canvas space.
            tile_x = c * self._tile_width
            tile_y = r * self._tile_height

            # Sample from overlay
            region = self._overlay.sample_region(tile_x, tile_y, self._tile_width, self._tile_height)

            if region is None:
                # Tile not covered - skip (warning already generated)
                continue

            # Convert RGBA to grayscale for SNES sprite format
            # (SNES sprites use 4bpp indexed color)
            if region.mode == "RGBA":
                # If we have a palette, quantize to it
                if self._palette:
                    quantized = self._quantize_to_palette(region, self._palette)
                    if quantized is None:
                        palette_mismatches.append(tile_pos)
                        # Fall back to grayscale conversion
                        quantized = region.convert("L")
                    modified_tiles[tile_pos] = quantized
                else:
                    # No palette - just convert to grayscale
                    modified_tiles[tile_pos] = region.convert("L")
            else:
                modified_tiles[tile_pos] = region

        # Add palette mismatch warning if any
        if palette_mismatches:
            warnings.append(
                ApplyWarning(
                    type=WarningType.PALETTE_MISMATCH,
                    message=f"{len(palette_mismatches)} tile(s) had palette quantization issues",
                    tile_ids=palette_mismatches,
                )
            )

        return ApplyResult(
            success=True,
            modified_tiles=modified_tiles,
            warnings=warnings,
        )

    def _quantize_to_palette(self, image: Image.Image, palette: list[tuple[int, int, int]]) -> Image.Image | None:
        """Quantize an image to the given palette.

        Args:
            image: RGBA image to quantize.
            palette: List of 16 RGB colors.

        Returns:
            Grayscale image with palette indices, or None on failure.
        """
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # Create output image (grayscale, values 0-15 * 16 for 4bpp)
        output = Image.new("L", image.size)
        pixels_out = output.load()
        pixels_in = image.load()

        if pixels_out is None or pixels_in is None:
            return None

        for y in range(image.height):
            for x in range(image.width):
                pixel = pixels_in[x, y]
                # PIL returns tuples for RGBA images
                if not isinstance(pixel, tuple) or len(pixel) != 4:
                    continue
                r, g, b, a = pixel

                # Transparent pixel -> index 0
                if a < 128:
                    pixels_out[x, y] = 0
                    continue

                # Find closest palette color
                min_dist = float("inf")
                best_idx = 0
                for idx, (pr, pg, pb) in enumerate(palette):
                    dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = idx

                # Store as grayscale value (index * 16 for 4bpp SNES format)
                pixels_out[x, y] = best_idx * 16

        return output
